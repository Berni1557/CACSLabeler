import logging
import os
from pathlib import Path
import qt

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from PIL import ImageColor

import concurrent.futures
import SimpleITK as sitk
import numpy
import json

import sys

from scipy.ndimage import label
from scipy import ndimage as ndi

import importlib

import timeit

class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, numpy.integer):
            return int(obj)
        if isinstance(obj, numpy.floating):
            return float(obj)
        if isinstance(obj, numpy.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)

#
# CACSLabeler
#

lowerThresholdValue = 130

class CACSLabeler(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "CACSLabeler"
        self.parent.categories = ["Examples"]
        self.parent.dependencies = []
        self.parent.contributors = ["Bernhard Foellmer, Charité"]  # replace with "Firstname Lastname (Organization)"

        self.parent.helpText = """
                                This is an example of scripted loadable module bundled in an extension.
                                It performs a simple thresholding on the input volume and optionally captures a screenshot.
                                """

        self.parent.acknowledgementText = """
                                            This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc.
                                            and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
                                            """  # replace with organization, grant and thanks.

#
# CACSLabelerWidget
#

class CACSLabelerWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None

        #clears screen on reload
        slicer.mrmlScene.Clear(0)

    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/CACSLabeler.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = CACSLabelerLogic()

        # Default UI Status
        self.mainUIHidden(True)
        self.ui.errorText.setHidden(True)

        self.ui.exportFromReferenceFolder.connect('clicked(bool)', self.onExportFromReferenceFolderButtonClicked)
        self.ui.exportFromJsonFile.connect('clicked(bool)', self.onExportFromJSONFileButtonClicked)
        self.ui.loadVolumeButton.connect('clicked(bool)', self.onLoadButton)
        self.ui.thresholdVolumeButton.connect('clicked(bool)', self.onThresholdVolume)
        self.ui.selectNextUnlabeledImageButton.connect('clicked(bool)', self.onSelectNextUnlabeledImage)
        self.ui.saveButton.connect('clicked(bool)', self.onSaveButton)

        self.topLevelPath = Path(__file__).absolute().parent.parent.parent.parent
        self.dataPath = os.path.join(Path(__file__).absolute().parent.parent.parent.parent, "data")

        # Loads Settings
        self.settingsPath = os.path.join(self.dataPath, "settings_CACSLabeler5.x.json")
        self.settings = None
        self.availableDatasetsAndObservers = {}

        self.loadSettings()
        self.loadDatasetSettings()

        self.checkIfDependenciesAreInstalled()

        if self.availableDatasetsAndObservers:
            self.selectDatasetAndObserver()
            self.saveSettings()
            self.mainUIHidden(False)
            self.updateDatasetAndObserverDropdownSelection()

            # after first updateDatasetAndObserverDropdownSelection to prevent call on automatic selection
            self.datasetComboBoxEventBlocked = False
            self.ui.datasetComboBox.connect("currentIndexChanged(int)", self.onChangeDataset)
            self.observerComboBoxEventBlocked = False
            self.ui.observerComboBox.connect("currentIndexChanged(int)", self.onChangeObserver)
            self.exportTypeComboBoxEventBlocked = False
            self.ui.exportTypeComboBox.connect("currentIndexChanged(int)", self.onChangeExportType)

            self.currentLoadedNode = None
            self.currentLoadedReferenceNode = None
            self.initializeMainUI()
        else:
            print("Settings file error! Change settings in JSON file!")
            self.ui.errorText.setHidden(False)
            self.ui.settingsCollapsibleButton.setHidden(True)
            self.ui.errorText.text = "Settings file error! \n Change settings in JSON file!"

        self.ui.embeddedSegmentEditorWidget.setMRMLScene(slicer.mrmlScene)
        self.ui.embeddedSegmentEditorWidget.setSegmentationNodeSelectorVisible(False)
        self.ui.embeddedSegmentEditorWidget.setSourceVolumeNodeSelectorVisible(False)
        self.ui.embeddedSegmentEditorWidget.setEffectNameOrder(['Paint', 'Erase'])
        self.ui.embeddedSegmentEditorWidget.unorderedEffectsVisible = False
        self.ui.embeddedSegmentEditorWidget.setMRMLSegmentEditorNode(self.logic.getSegmentEditorNode())
        self.ui.embeddedSegmentEditorWidget.setSwitchToSegmentationsButtonVisible(False)

        self.colorTableNode = None
        self.createColorTable()

        self.ui.embeddedSegmentEditorWidget.setHidden(True)
        self.ui.saveButton.setHidden(True)

        self.selectedExportType = self.settings["exportType"]
        self.availableExportTypes = list(self.settings["exportedLabels"].keys())

        self.ui.exportTypeComboBox.clear()
        self.ui.exportTypeComboBox.addItems(self.availableExportTypes)
        self.ui.exportTypeComboBox.setCurrentText(self.selectedExportType)

    def checkIfDependenciesAreInstalled(self):
        dependencies = ["pandas"]

        for dependency in dependencies:
            if dependency not in sys.modules:
                if slicer.util.confirmOkCancelDisplay("This module requires '" + dependency + "' Python package. Click OK to install it now."):
                    slicer.util.pip_install(dependency)

    def cleanup(self):
        """
        Called when the application closes and the module widget is destroyed.
        """
        pass

    def enter(self):
        """
        Called each time the user opens this module.
        """
        pass

    def exit(self):
        """
        Called each time the user opens a different module.
        """
        pass

    def onChangeExportType(self, exportTypeId=None):
        if not self.exportTypeComboBoxEventBlocked:
            self.exportTypeComboBoxEventBlocked = True

            self.settings["exportType"] = self.availableExportTypes[exportTypeId]
            self.saveSettings()

            self.exportTypeComboBoxEventBlocked = False

    def onChangeDataset(self, datasetListId=None):
        self.clearCurrentViewedNode(True)

        #protect from triggering during change
        if not self.datasetComboBoxEventBlocked:
            self.datasetComboBoxEventBlocked = True
            self.observerComboBoxEventBlocked = True

            newDataset = list(self.availableDatasetsAndObservers.keys())[datasetListId]
            self.selectDatasetAndObserver(newDataset)
            self.updateDatasetAndObserverDropdownSelection()
            self.saveSettings()
            self.initializeMainUI()

            self.datasetComboBoxEventBlocked = False
            self.observerComboBoxEventBlocked = False

    def onChangeObserver(self, item=None):
        self.clearCurrentViewedNode(True)

        if not self.observerComboBoxEventBlocked:
            self.datasetComboBoxEventBlocked = True
            self.observerComboBoxEventBlocked = True

            self.selectDatasetAndObserver(self.settings["savedDatasetAndObserverSelection"]["dataset"], self.availableDatasetsAndObservers[self.settings["savedDatasetAndObserverSelection"]["dataset"]][item])
            self.saveSettings()
            self.initializeMainUI()

            self.datasetComboBoxEventBlocked = False
            self.observerComboBoxEventBlocked = False

    def loadVolumeToSlice(self, filename, imagesPath):
        self.ui.embeddedSegmentEditorWidget.setHidden(True)
        self.ui.saveButton.setHidden(True)

        self.createColorTable()
        properties = {'Name': filename}

        self.currentLoadedNode = slicer.util.loadVolume(os.path.join(imagesPath, filename), properties=properties)
        self.currentLoadedNode.SetName(filename)

        # Activate buttons
        self.ui.RadioButton120keV.enabled = True
        self.ui.thresholdVolumeButton.enabled = True
        self.ui.selectedVolumeTextField.text = filename
        self.ui.selectedVolumeTextField.cursorPosition = 0

    def onSelectNextUnlabeledImage(self):
        self.clearCurrentViewedNode(True)
        imageList = self.logic.getImageList(self.selectedDatasetAndObserverSetting())


        dataset = self.settings["savedDatasetAndObserverSelection"]["dataset"]
        imagesPath = self.settings["datasets"][dataset]["imagesPath"]
        filename = imageList["unlabeledImages"][0] + ".mhd"

        if os.path.isfile(os.path.join(imagesPath, filename)):
            self.loadVolumeToSlice(filename, imagesPath)

    def onLoadButton(self):
        dataset = self.settings["savedDatasetAndObserverSelection"]["dataset"]
        imagesPath = self.settings["datasets"][dataset]["imagesPath"]


        self.clearCurrentViewedNode(True)

        # opens file selection window
        filepath = qt.QFileDialog.getOpenFileName(self.parent, 'Open files', imagesPath, "Files(*.mhd)")
        filename = filepath.split("/")[-1]

        self.loadVolumeToSlice(filename, imagesPath)

    def onThresholdVolume(self):
        if not self.ui.RadioButton120keV.checked:
            qt.QMessageBox.warning(slicer.util.mainWindow(),"Select KEV", "The KEV (80 or 120) must be selected to continue.")
            return

        #removes file extension
        inputVolumeName = self.currentLoadedNode.GetName()
        labelName = os.path.splitext(inputVolumeName)[0] + '-label-lesion'

        imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer = self.selectedDatasetAndObserverSetting()

        self.logic.runThreshold(inputVolumeName, labelName, segmentationMode, self.settings, labelsPath, self.colorTableNode)
        self.currentLoadedReferenceNode = slicer.util.getNode(labelName)

        self.ui.embeddedSegmentEditorWidget.setSegmentationNode(slicer.util.getNode(labelName))
        #target = slicer.util.getNode(labelName).GetSegmentation().GetSegmentIdBySegmentName('RCA_PROXIMAL')
        #self.logic.getSegmentEditorNode().SetSelectedSegmentID(target)

        #self.ui.embeddedSegmentEditorWidget.setActiveEffectByName("Paint")

        #effect = self.ui.embeddedSegmentEditorWidget.activeEffect()
        #effect.setCommonParameter("BrushRelativeDiameter", float(3))
        self.logic.getSegmentEditorNode().SetMasterVolumeIntensityMask(True)
        self.logic.getSegmentEditorNode().SetSourceVolumeIntensityMaskRange(float(lowerThresholdValue), 10000.0)

        self.ui.embeddedSegmentEditorWidget.setHidden(False)
        self.ui.saveButton.setHidden(False)

    def initializeMainUI(self):
        self.clearCurrentViewedNode()
        self.progressBarUpdate()

    def clearCurrentViewedNode(self, changeAlert = False):
        if changeAlert:
            if self.currentLoadedNode != None or len(slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")):
                if not slicer.util.confirmOkCancelDisplay(
                        "This will close current scene.  Please make sure you have saved your current work.\n"
                        "Are you sure to continue?"
                ):
                    return

        slicer.mrmlScene.Clear(0)
        self.ui.RadioButton120keV.enabled = False
        self.ui.thresholdVolumeButton.enabled = False
        self.ui.selectedVolumeTextField.text = ""
        self.ui.selectedVolumeTextField.cursorPosition = 0
        self.currentLoadedNode = None

    def progressBarUpdate(self):
        images = self.logic.getImageList(self.selectedDatasetAndObserverSetting())
        self.ui.progressBar.minimum = 0
        self.ui.progressBar.maximum = len(images["allImages"])
        self.ui.progressBar.value = len(images["allImages"]) - len(images["unlabeledImages"])

        self.ui.completedCountText.text = str(len(images["allImages"]) - len(images["unlabeledImages"])) + " / " + str(len(images["allImages"]))

        if self.ui.progressBar.value < self.ui.progressBar.maximum:
            self.ui.selectNextUnlabeledImageButton.enabled = True
        else:
            self.ui.selectNextUnlabeledImageButton.enabled = False

    def loadSettings(self):
        if os.path.isfile(self.settingsPath):
            with open(self.settingsPath, 'r', encoding='utf-8') as file:
                self.settings = None
                self.settings = json.load(file)
        else:
            #create default settings file
            defaultSettings = {
                "datasets": {
                    "VAR_DATASET_NAME": {
                        "imagesPath": "",
                        "sliceStepFile": "",
                        "observers": {
                            "VAR_OBSERVER_NAME": {
                                "labelsPath": "",
                                "segmentationMode": ""
                            }
                        }
                    }
                },
                "exportType": "SegmentLevel",
                "exportFolder": "",
                "savedDatasetAndObserverSelection": {
                    "dataset": "",
                    "observer": ""
                },
                "labels": {
                    "SegmentLevel": {
                        "OTHER": {
                            "value": 1,
                            "color": "#00ff00"
                        },
                        "RCA_PROXIMAL": {
                            "value": 4,
                            "color": "#cc0000"
                        },
                        "RCA_MID": {
                            "value": 5,
                            "color": "#f5b207"
                        },
                        "RCA_DISTAL": {
                            "value": 6,
                            "color": "#ff7c80"
                        },
                        "RCA_SIDE_BRANCH": {
                            "value": 7,
                            "color": "#ffc2c2"
                        },
                        "LM_BIF_LAD_LCX": {
                            "value": 9,
                            "color": "#0bfde0"
                        },
                        "LM_BIF_LAD": {
                            "value": 10,
                            "color": "#1acbee"
                        },
                        "LM_BIF_LCX": {
                            "value": 11,
                            "color": "#208482"
                        },
                        "LM_BRANCH": {
                            "value": 12,
                            "color": "#ffce79"
                        },
                        "LAD_PROXIMAL": {
                            "value": 14,
                            "color": "#ff641c"
                        },
                        "LAD_MID": {
                            "value": 15,
                            "color": "#ff8c00"
                        },
                        "LAD_DISTAL": {
                            "value": 16,
                            "color": "#ffe51e"
                        },
                        "LAD_SIDE_BRANCH": {
                            "value": 17,
                            "color": "#0bfdf4"
                        },
                        "LCX_PROXIMAL": {
                            "value": 19,
                            "color": "#ff00ff"
                        },
                        "LCX_MID": {
                            "value": 20,
                            "color": "#ff66ff"
                        },
                        "LCX_DISTAL": {
                            "value": 21,
                            "color": "#ff99ff"
                        },
                        "LCX_SIDE_BRANCH": {
                            "value": 22,
                            "color": "#ffccff"
                        },
                        "RIM": {
                            "value": 23,
                            "color": "#fc0303"
                        },
                        "AORTA_ASC": {
                            "value": 26,
                            "color": "#483fff"
                        },
                        "AORTA_DSC": {
                            "value": 27,
                            "color": "#0c00f6"
                        },
                        "AORTA_ARC": {
                            "value": 28,
                            "color": "#8b85ff"
                        },
                        "VALVE_AORTIC": {
                            "value": 30,
                            "color": "#caffa7"
                        },
                        "VALVE_PULMONIC": {
                            "value": 31,
                            "color": "#8dff4f"
                        },
                        "VALVE_TRICUSPID": {
                            "value": 32,
                            "color": "#009900"
                        },
                        "VALVE_MITRAL": {
                            "value": 33,
                            "color": "#5dcc80"
                        },
                        "PAPILLAR_MUSCLE": {
                            "value": 34,
                            "color": "#a7954b"
                        },
                        "NFS_CACS": {
                            "value": 35,
                            "color": "#d8cfa8"
                        }
                    },
                    "SegmentLevelDLNExport":{
                        "LM": {
                            "value": 2,
                            "color": "#feda00"
                        },
                        "LAD_PROXIMAL": {
                            "value": 3,
                            "color": "#4dff00"
                        },
                        "LAD_MID": {
                            "value": 4,
                            "color": "#d0ff85"
                        },
                        "LAD_DISTAL": {
                            "value": 5,
                            "color": "#03ad00"
                        },
                        "LAD_SIDE_BRANCH": {
                            "value": 6,
                            "color": "#0ec9fd"
                        },
                        "LCX_PROXIMAL": {
                            "value": 7,
                            "color": "#b300ff"
                        },
                        "LCX_MID": {
                            "value": 8,
                            "color": "#ff93b9"
                        },
                        "LCX_DISTAL": {
                            "value": 9,
                            "color": "#b8b3ff"
                        },
                        "LCX_SIDE_BRANCH": {
                            "value": 10,
                            "color": "#97d2ff"
                        },
                        "RCA_PROXIMAL": {
                            "value": 11,
                            "color": "#ff0000"
                        },
                        "RCA_MID": {
                            "value": 12,
                            "color": "#ff8989"
                        },
                        "RCA_DISTAL": {
                            "value": 13,
                            "color": "#ffe5c1"
                        },
                        "RCA_SIDE_BRANCH": {
                            "value": 14,
                            "color": "#e3ffb8"
                        },
                        "RIM": {
                            "value": 15,
                            "color": "#ffaa00"
                        },
                    },
                    "ArteryLevel": {
                        "OTHER": {
                            "value": 1,
                            "color": "#00ff00"
                        },
                        "LAD": {
                            "value": 2,
                            "color": "#ffcc66"
                        },
                        "LCX": {
                            "value": 3,
                            "color": "#ff00ff"
                        },
                        "RCA": {
                            "value": 4,
                            "color": "#cc0000"
                        }
                    },
                    "ArteryLevelWithLM": {
                        "OTHER": {
                            "value": 1,
                            "color": "#00ff00"
                        },
                        "LAD": {
                            "value": 2,
                            "color": "#ffcc66"
                        },
                        "LCX": {
                            "value": 3,
                            "color": "#ff00ff"
                        },
                        "RCA": {
                            "value": 4,
                            "color": "#cc0000"
                        },
                        "LM": {
                            "value": 5,
                            "color": "#00c3ff"
                        }
                    }
                },
                "exportedLabels": {
                    "SegmentLevel": {
                        "CC": [
                            "RCA_PROXIMAL",
                            "RCA_MID",
                            "RCA_DISTAL",
                            "RCA_SIDE_BRANCH",
                            "LM_BIF_LAD_LCX",
                            "LM_BIF_LAD",
                            "LM_BIF_LCX",
                            "LM_BRANCH",
                            "LAD_PROXIMAL",
                            "LAD_MID",
                            "LAD_DISTAL",
                            "LAD_SIDE_BRANCH",
                            "LCX_PROXIMAL",
                            "LCX_MID",
                            "LCX_DISTAL",
                            "LCX_SIDE_BRANCH",
                            "RIM"
                        ],
                        "RCA": [
                            "RCA_PROXIMAL",
                            "RCA_MID",
                            "RCA_DISTAL",
                            "RCA_SIDE_BRANCH"
                        ],
                        "RCA_PROXIMAL": "RCA_PROXIMAL",
                        "RCA_MID": "RCA_MID",
                        "RCA_DISTAL": "RCA_DISTAL",
                        "RCA_SIDE_BRANCH": "RCA_SIDE_BRANCH",
                        "LM": [
                            "LM_BIF_LAD_LCX",
                            "LM_BIF_LAD",
                            "LM_BIF_LCX",
                            "LM_BRANCH"
                        ],
                        "LM_BIF_LAD_LCX": "LM_BIF_LAD_LCX",
                        "LM_BIF_LAD": "LM_BIF_LAD",
                        "LM_BIF_LCX": "LM_BIF_LCX",
                        "LM_BRANCH": "LM_BRANCH",
                        "LAD": [
                            "LAD_PROXIMAL",
                            "LAD_MID",
                            "LAD_DISTAL",
                            "LAD_SIDE_BRANCH"
                        ],
                        "LAD_PROXIMAL": "LAD_PROXIMAL",
                        "LAD_MID": "LAD_MID",
                        "LAD_DISTAL": "LAD_DISTAL",
                        "LAD_SIDE_BRANCH": "LAD_SIDE_BRANCH",
                        "LCX": [
                            "LCX_PROXIMAL",
                            "LCX_MID",
                            "LCX_DISTAL",
                            "LCX_SIDE_BRANCH"
                        ],
                        "LCX_PROXIMAL": "LCX_PROXIMAL",
                        "LCX_MID": "LCX_MID",
                        "LCX_DISTAL": "LCX_DISTAL",
                        "LCX_SIDE_BRANCH": "LCX_SIDE_BRANCH",
                        "RIM": "RIM",
                        "NCC": [
                            "AORTA_ASC",
                            "AORTA_DSC",
                            "AORTA_ARC",
                            "VALVE_AORTIC",
                            "VALVE_PULMONIC",
                            "VALVE_TRICUSPID",
                            "VALVE_MITRAL",
                            "NFS_CACS",
                            "PAPILLAR_MUSCLE"
                        ],
                        "AORTA": [
                            "AORTA_ASC",
                            "AORTA_DSC",
                            "AORTA_ARC"
                        ],
                        "AORTA_ASC": "AORTA_ASC",
                        "AORTA_DSC": "AORTA_DSC",
                        "AORTA_ARC": "AORTA_ARC",
                        "VALVES": [
                            "VALVE_AORTIC",
                            "VALVE_PULMONIC",
                            "VALVE_TRICUSPID",
                            "VALVE_MITRAL"
                        ],
                        "VALVE_AORTIC": "VALVE_AORTIC",
                        "VALVE_PULMONIC": "VALVE_PULMONIC",
                        "VALVE_TRICUSPID": "VALVE_TRICUSPID",
                        "VALVE_MITRAL": "VALVE_MITRAL",
                        "PAPILLAR_MUSCLE": "PAPILLAR_MUSCLE",
                        "NFS_CACS": "NFS_CACS"
                    },
                    "SegmentLevelDLNExport": {
                        "CC": [
                            "LM",
                            "LAD_PROXIMAL",
                            "LAD_MID",
                            "LAD_DISTAL",
                            "LAD_SIDE_BRANCH",
                            "LCX_PROXIMAL",
                            "LCX_MID",
                            "LCX_DISTAL",
                            "LCX_SIDE_BRANCH",
                            "RCA_PROXIMAL",
                            "RCA_MID",
                            "RCA_DISTAL",
                            "RCA_SIDE_BRANCH",
                            "RIM"
                        ],
                        "LM": "LM",
                        "LAD": [
                            "LAD_PROXIMAL",
                            "LAD_MID",
                            "LAD_DISTAL",
                            "LAD_SIDE_BRANCH"
                        ],
                        "LAD_PROXIMAL": "LAD_PROXIMAL",
                        "LAD_MID": "LAD_MID",
                        "LAD_DISTAL": "LAD_DISTAL",
                        "LAD_SIDE_BRANCH": "LAD_SIDE_BRANCH",
                        "RCA": [
                            "RCA_PROXIMAL",
                            "RCA_MID",
                            "RCA_DISTAL",
                            "RCA_SIDE_BRANCH"
                        ],
                        "RCA_PROXIMAL": "RCA_PROXIMAL",
                        "RCA_MID": "RCA_MID",
                        "RCA_DISTAL": "RCA_DISTAL",
                        "RCA_SIDE_BRANCH": "RCA_SIDE_BRANCH",
                        "LCX": [
                            "LCX_PROXIMAL",
                            "LCX_MID",
                            "LCX_DISTAL",
                            "LCX_SIDE_BRANCH"
                        ],
                        "LCX_PROXIMAL": "LCX_PROXIMAL",
                        "LCX_MID": "LCX_MID",
                        "LCX_DISTAL": "LCX_DISTAL",
                        "LCX_SIDE_BRANCH": "LCX_SIDE_BRANCH",
                        "RIM": "RIM"
                    },
                    "ArteryLevel": {
                        "CC": [
                            "LAD",
                            "RCA",
                            "LCX"
                        ],
                        "LAD": "LAD",
                        "RCA": "RCA",
                        "LCX": "LCX"
                    },
                    "ArteryLevelWithLM": {
                        "CC": [
                            "LAD",
                            "RCA",
                            "LCX",
                            "LM"
                        ],
                        "LAD": "LAD",
                        "RCA": "RCA",
                        "LCX": "LCX",
                        "LM": "LM"
                    }
                }
            }

            self.settings = defaultSettings
            self.saveSettings()

    def saveSettings(self):
        with open(self.settingsPath, 'w', encoding='utf-8') as file:
            # explicit copy to prevent race condition
            json.dump(self.settings, file, ensure_ascii=False, indent=4, cls=NpEncoder)

    def loadDatasetSettings(self):
        for dataset in self.settings["datasets"]:
            if self.settings["datasets"][dataset]:
                if self.settings["datasets"][dataset]["imagesPath"] and os.path.isdir(self.settings["datasets"][dataset]["imagesPath"]):

                    if dataset not in self.availableDatasetsAndObservers:
                        self.availableDatasetsAndObservers[dataset] = []

                    for observer in self.settings["datasets"][dataset]["observers"]:
                        if os.path.isdir(self.settings["datasets"][dataset]["observers"][observer]["labelsPath"]):

                            # Options: ArteryLevel, SegmentLevel, ArteryLevelWithLM, SegmentLevelDLNExport
                            if self.settings["datasets"][dataset]["observers"][observer]["segmentationMode"] == "ArteryLevel" \
                                    or self.settings["datasets"][dataset]["observers"][observer]["segmentationMode"] == "SegmentLevel" \
                                    or self.settings["datasets"][dataset]["observers"][observer]["segmentationMode"] == "SegmentLevelDLNExport" \
                                    or self.settings["datasets"][dataset]["observers"][observer]["segmentationMode"] == "ArteryLevelWithLM":
                                self.availableDatasetsAndObservers[dataset].append(observer)

                            else:
                                print(f"Observer [{observer}] missing segmentationMode")
                        else:
                            print(f"Observer [{observer}] missing labels folder path")
                else:
                    print(f"Dataset [{dataset}] missing images folder path")
            else:
                print(f"Dataset [{dataset}] settings empty")

    def selectDatasetAndObserver(self, dataset = None, observer = None):
        if dataset is None and observer is None:
            if ("savedDatasetAndObserverSelection" in self.settings) \
                    and (self.settings["savedDatasetAndObserverSelection"]) \
                    and ("dataset" in self.settings["savedDatasetAndObserverSelection"]) \
                    and ("observer" in self.settings["savedDatasetAndObserverSelection"]):

                if self.settings["savedDatasetAndObserverSelection"]["dataset"] in self.availableDatasetsAndObservers:
                    try:
                        self.availableDatasetsAndObservers[self.settings["savedDatasetAndObserverSelection"]["dataset"]].index(self.settings["savedDatasetAndObserverSelection"]["observer"])
                        return
                    except ValueError:
                        pass
        else:
            if dataset in self.availableDatasetsAndObservers:
                self.settings["savedDatasetAndObserverSelection"]["dataset"] = dataset
                try:
                    self.availableDatasetsAndObservers[dataset].index(observer)
                    self.settings["savedDatasetAndObserverSelection"]["observer"] = observer
                    return
                except ValueError:
                    #if no observer selected select first available
                    self.settings["savedDatasetAndObserverSelection"]["observer"] = self.availableDatasetsAndObservers[dataset][0]
                    return

        # if not already selected in settings selecting first element
        firstDataset = list(self.availableDatasetsAndObservers.keys())[0]
        firstObserver = self.availableDatasetsAndObservers[firstDataset][0]

        self.settings["savedDatasetAndObserverSelection"]["dataset"] = firstDataset
        self.settings["savedDatasetAndObserverSelection"]["observer"] = firstObserver

    def selectedDatasetAndObserverSetting(self):
        dataset = self.settings["savedDatasetAndObserverSelection"]["dataset"]
        observer = self.settings["savedDatasetAndObserverSelection"]["observer"]

        imagesPath = self.settings["datasets"][dataset]["imagesPath"]
        labelsPath = self.settings["datasets"][dataset]["observers"][observer]["labelsPath"]
        segmentationMode = self.settings["datasets"][dataset]["observers"][observer]["segmentationMode"]
        sliceStepFile = self.settings["datasets"][dataset]["sliceStepFile"]
        exportFolder = self.settings["exportFolder"]

        return imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer

    def mainUIHidden(self, hide):
        self.ui.inputCollapsibleButton.setHidden(hide)
        self.ui.exportCollapsibleButton.setHidden(hide)
        self.ui.datasetComboBox.setHidden(hide)
        self.ui.datasetLabel.setHidden(hide)
        self.ui.observerComboBox.setHidden(hide)
        self.ui.observerLabel.setHidden(hide)

    def updateDatasetAndObserverDropdownSelection(self):
        self.ui.datasetComboBox.clear()
        self.ui.datasetComboBox.addItems(list(self.availableDatasetsAndObservers.keys()))
        self.ui.datasetComboBox.setCurrentText(self.settings["savedDatasetAndObserverSelection"]["dataset"])

        self.ui.observerComboBox.clear()
        self.ui.observerComboBox.addItems(self.availableDatasetsAndObservers[self.settings["savedDatasetAndObserverSelection"]["dataset"]])
        self.ui.observerComboBox.setCurrentText(self.settings["savedDatasetAndObserverSelection"]["observer"])

    def onExportFromReferenceFolderButtonClicked(self):
        exporter = ScoreExport(self.selectedDatasetAndObserverSetting(), self.settings)
        exporter.exportFromReferenceFolder()

    def onExportFromJSONFileButtonClicked(self):
        exporter = ScoreExport(self.selectedDatasetAndObserverSetting(), self.settings)
        exporter.exportFromJSONFile()

    def createColorTable(self):
        imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer = self.selectedDatasetAndObserverSetting()
        segmentNamesToLabels = []

        for key in self.settings["labels"][segmentationMode]:

            value = self.settings["labels"][segmentationMode][key]["value"]
            color = self.settings["labels"][segmentationMode][key]["color"]

            segmentNamesToLabels.append((key, value, color))

        self.colorTableNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLColorTableNode")
        self.colorTableNode.SetTypeToUser()
        self.colorTableNode.HideFromEditorsOff()  # make the color table selectable in the GUI outside Colors module
        slicer.mrmlScene.AddNode(self.colorTableNode)
        self.colorTableNode.UnRegister(None)
        largestLabelValue = max([name_value[1] for name_value in segmentNamesToLabels])
        self.colorTableNode.SetNumberOfColors(largestLabelValue + 1)
        self.colorTableNode.SetNamesInitialised(True)  # prevent automatic color name generation
        # import random
        for segmentName, labelValue, color in segmentNamesToLabels:
            r,g,b = ImageColor.getcolor(color, "RGB")
            a = 1.0
            self.colorTableNode.SetColor(labelValue, segmentName, r, g, b, a)

    def onSaveButton(self):
        imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer = self.selectedDatasetAndObserverSetting()

        labelmapVolumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
        labelmapVolumeNode.SetName("temporaryExportLabel")
        referenceVolumeNode = None  # it could be set to the master volume
        segmentIds = self.currentLoadedReferenceNode.GetSegmentation().GetSegmentIDs()  # export all segments
        slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(self.currentLoadedReferenceNode, segmentIds,
                                                                           labelmapVolumeNode, referenceVolumeNode,
                                                                           slicer.vtkSegmentation.EXTENT_REFERENCE_GEOMETRY,
                                                                           self.colorTableNode)

        filename = self.currentLoadedReferenceNode.GetName() + ".nrrd"

        volumeNode = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLLabelMapVolumeNode')
        slicer.util.exportNode(volumeNode, os.path.join(labelsPath, filename))

        slicer.mrmlScene.RemoveNode(labelmapVolumeNode)
        self.progressBarUpdate()
        print(f"Saved {filename}")

#
# CACSLabelerLogic
#

class CACSLabelerLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self):
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)

    def setDefaultParameters(self, parameterNode):
        """
        Initialize parameter node with default settings.
        """
        if not parameterNode.GetParameter("Threshold"):
            parameterNode.SetParameter("Threshold", "100.0")
        if not parameterNode.GetParameter("Invert"):
            parameterNode.SetParameter("Invert", "false")

    def process(self, inputVolume, outputVolume, imageThreshold, invert=False, showResult=True):
        """
        Run the processing algorithm.
        Can be used without GUI widget.
        :param inputVolume: volume to be thresholded
        :param outputVolume: thresholding result
        :param imageThreshold: values above/below this threshold will be set to 0
        :param invert: if True then values above the threshold will be set to 0, otherwise values below are set to 0
        :param showResult: show output volume in slice viewers
        """

        if not inputVolume or not outputVolume:
            raise ValueError("Input or output volume is invalid")

        import time
        startTime = time.time()
        logging.info('Processing started')

        # Compute the thresholded output volume using the "Threshold Scalar Volume" CLI module
        cliParams = {
            'InputVolume': inputVolume.GetID(),
            'OutputVolume': outputVolume.GetID(),
            'ThresholdValue': imageThreshold,
            'ThresholdType': 'Above' if invert else 'Below'
        }
        cliNode = slicer.cli.run(slicer.modules.thresholdscalarvolume, None, cliParams, wait_for_completion=True, update_display=showResult)
        # We don't need the CLI module node anymore, remove it to not clutter the scene with it
        slicer.mrmlScene.RemoveNode(cliNode)

        stopTime = time.time()
        logging.info(f'Processing completed in {stopTime-startTime:.2f} seconds')

    def runThreshold(self, inputVolumeName ,labelName, segmentationMode, settings, labelsPath, colorTableNode):
        node = slicer.util.getFirstNodeByName(labelName)
        if node is None:
            print('----- Thresholding -----')
            print('Threshold value:', lowerThresholdValue)

            imageNode = slicer.util.getNode(inputVolumeName)

            segmentationNode = None
            segmentation = None

            #file exists
            if os.path.isfile(os.path.join(labelsPath, labelName + '.nrrd')):
                loadedVolumeNode = slicer.util.loadVolume(os.path.join(labelsPath, labelName + '.nrrd'), {"labelmap": True})
                segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")  # import into new segmentation node
                segmentationNode.SetName(labelName)
                segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(imageNode)
                loadedVolumeNode.GetDisplayNode().SetAndObserveColorNodeID(colorTableNode.GetID())  # just in case the custom color table has not been already associated with the labelmap volume
                slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(loadedVolumeNode, segmentationNode)

                slicer.mrmlScene.RemoveNode(loadedVolumeNode)
            else:
                segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
                segmentationNode.SetName(labelName)
                segmentationNode.CreateDefaultDisplayNodes()  # only needed for display

                segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(imageNode)

            segmentation = segmentationNode.GetSegmentation()
            displayNode = segmentationNode.GetDisplayNode()

            for key in settings["labels"][segmentationMode]:
                color = settings["labels"][segmentationMode][key]["color"]

                if segmentation.GetSegment(key) is None:
                    segmentation.AddEmptySegment(key)

                segment = segmentation.GetSegment(key)

                r, g, b = ImageColor.getcolor(color, "RGB")
                segment.SetColor(r/255, g/255, b/255)  # red
                displayNode.SetSegmentOpacity3D(key, 1)  # Set opacity of a single segment

                if key == "OTHER" and not os.path.isfile(os.path.join(labelsPath, labelName + '.nrrd')):
                    segmentId = segmentationNode.GetSegmentation().GetSegmentIdBySegmentName(key)
                    segmentArray = slicer.util.arrayFromSegmentBinaryLabelmap(segmentationNode, key, imageNode)
                    segmentArray[slicer.util.arrayFromVolume(imageNode) >= lowerThresholdValue] = 1  # create segment by simple thresholding of an image
                    slicer.util.updateSegmentBinaryLabelmapFromArray(segmentArray, segmentationNode, segmentId,
                                                                     imageNode)

    def getSegmentEditorNode(self):
        # Use the Segment Editor module's parameter node for the embedded segment editor widget.
        # This ensures that if the user switches to the Segment Editor then the selected
        # segmentation node, volume node, etc. are the same.
        segmentEditorSingletonTag = "SegmentEditor"
        segmentEditorNode = slicer.mrmlScene.GetSingletonNode(segmentEditorSingletonTag, "vtkMRMLSegmentEditorNode")
        if segmentEditorNode is None:
            segmentEditorNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLSegmentEditorNode")
            segmentEditorNode.UnRegister(None)
            segmentEditorNode.SetSingletonTag(segmentEditorSingletonTag)
            segmentEditorNode = slicer.mrmlScene.AddNode(segmentEditorNode)
        return segmentEditorNode

    def getImageList(self, datasetSettings):
        imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer = datasetSettings

        files = {"allImages": [], "unlabeledImages": []}
        references = []

        for referenceFileName in sorted(filter(lambda x: os.path.isfile(os.path.join(labelsPath, x)),os.listdir(labelsPath))):
            name, extension = os.path.splitext(referenceFileName)
            if extension == ".nrrd" and os.path.isfile(os.path.join(imagesPath, name.split("-label-lesion")[0] + ".mhd")):
               references.append(name.split("-label-lesion")[0])

        for imageFileName in sorted(filter(lambda x: os.path.isfile(os.path.join(imagesPath, x)),os.listdir(imagesPath))):
            name, extension = os.path.splitext(imageFileName)
            if extension == ".mhd":
                files["allImages"].append(name)

                try:
                    references.index(name)
                except ValueError:
                    files["unlabeledImages"].append(name)

        return files

class ScoreExport():
    def __init__(self, datasetInformation, settings):
        imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer = datasetInformation

        self.segmentationMode = segmentationMode
        self.dataset = dataset

        exportTypesOrder = ["ArteryLevel", "ArteryLevelWithLM", "SegmentLevelDLNExport", "SegmentLevel"]

        if exportTypesOrder.index(segmentationMode) >= exportTypesOrder.index(settings["exportType"]):
            self.exportType = settings["exportType"]

        else:
            self.exportType = segmentationMode

        self.filepaths = {
            "imageFolder": imagesPath,
            "referenceFolder": labelsPath,
            "sliceStepFile": sliceStepFile,
            "exportFileCSV": os.path.join(exportFolder, dataset + "_" + observer + "_" + self.exportType + ".csv"),
            "exportFileJSON": os.path.join(exportFolder, dataset + "_" + observer + "_" + self.exportType + ".json")
        }

        self.Items = self.createItems(settings)

        self.arteryId = {}

        for key in self.Items:
            if isinstance(self.Items[key], int):
                self.arteryId[self.Items[key]] = key

        self.exportJson = {}
        self.exportList = []

        self.pandas = importlib.import_module('pandas')

    def createItems(self, settings):
        items = None

        generatedItems = {}

        for item in settings["exportedLabels"][self.exportType]:
            itemContent = None

            labelContent = settings["exportedLabels"][self.exportType][item]

            if isinstance(labelContent, list):
                itemContent = []

                for groupElement in labelContent:
                    itemContent.append(settings["labels"][self.exportType][groupElement]["value"])

            else:
                itemContent = settings["labels"][self.exportType][labelContent]["value"]
                pass

            generatedItems[item] = itemContent

        return generatedItems

    def exportFromJSONFile(self):
        # Opening JSON file

        with open(self.filepaths["exportFileJSON"], 'r', encoding='utf-8') as file:
            # returns JSON object as
            # a dictionary
            self.exportJson = None
            self.exportJson = json.load(file)

            # Iterating through the json
            # list
            for patientId in self.exportJson:
                for seriesInstanceUID in self.exportJson[patientId]:

                    result = self.calculateScore(patientId, seriesInstanceUID)
                    self.exportList.append(result)
                    print("Exported", patientId, seriesInstanceUID)

        self.createExportFilesAndSaveContent(createJson=False)

    def createExportFilesAndSaveContent(self, createJson):
        dataframe = self.pandas.DataFrame.from_records(self.exportList)
        dataframe.to_csv(self.filepaths["exportFileCSV"], index=False, sep=';', float_format='%.3f')

        if createJson:
            with open(self.filepaths["exportFileJSON"], 'w', encoding='utf-8') as file:
                #explicit copy to prevent race condition
                json.dump(dict(self.exportJson), file, ensure_ascii=False, indent=4, cls=NpEncoder)

    def exportFromReferenceFolder(self):
        sliceStepDataframe = self.pandas.read_csv(self.filepaths["sliceStepFile"], dtype={'patient_id': 'string'})

        #total = timeit.default_timer()

        with concurrent.futures.ThreadPoolExecutor() as executor:
            [executor.submit(self.processImages, filename, sliceStepDataframe)
             for filename in sorted(filter(lambda x: os.path.isfile(os.path.join(self.filepaths["referenceFolder"], x)),
                                           os.listdir(self.filepaths["referenceFolder"])))]

        #print("total", timeit.default_timer() - total)

    def processFilename(self, filepath):
        if self.dataset == "DISCHARGE" or self.dataset == "CADMAN":
            fileName = filepath.split("/")[-1]
            PatientID = fileName.split("_")[0]
            fileId = PatientID + "_" + fileName.split("_")[1].split("-")[0]
            SeriesInstanceUID = fileId.split("_")[1]

        elif self.dataset == "OrCaScore":
            fileName = filepath.split("/")[-1]
            fileId = fileName.split("-")[0]
            PatientID = fileId.split("_")[0]
            SeriesInstanceUID = fileId.split("_")[1]

        return fileName, fileId, PatientID, SeriesInstanceUID

    def label(self, referenceTemporaryCopy, uniqueId, structureConnections2d, iterator, connectedElements2d):
        labeled_array, num_features = ndi.label((referenceTemporaryCopy == uniqueId).astype(int),structure=structureConnections2d)
        return numpy.where(labeled_array > 0, labeled_array + iterator, 0).astype(connectedElements2d.dtype)

    def findLesions(self, reference):
        # preprocessing label
        reference[reference == 24] = 35

        # Options: ArteryLevel, SegmentLevel, ArteryLevelWithLM, SegmentLevelDLNExport
        if self.segmentationMode == "SegmentLevel" and self.exportType == "ArteryLevel":
            # Combines all lesions in each artery to one group
            # RCA
            reference[(reference >= 4) & (reference <= 7)] = 4

            # LM
            reference[(reference >= 9) & (reference <= 12)] = 2

            # LAD
            reference[(reference >= 14) & (reference <= 17)] = 2

            # LCX
            reference[(reference >= 19) & (reference <= 22)] = 3

            # RIM
            reference[(reference == 23)] = 2

            reference[(reference >= 5)] = 0
        elif self.segmentationMode == "SegmentLevel" and self.exportType == "ArteryLevelWithLM":
            # Combines all lesions in each artery to one group
            # RCA
            reference[(reference >= 4) & (reference <= 7)] = 4

            # LAD
            reference[(reference >= 14) & (reference <= 17)] = 2

            # LCX
            reference[(reference >= 19) & (reference <= 22)] = 3

            # RIM
            reference[(reference == 23)] = 2

            # LM
            reference[(reference >= 9) & (reference <= 12)] = 5

            reference[(reference >= 6)] = 0
        elif self.segmentationMode == "ArteryLevelWithLM" and self.exportType == "ArteryLevel":
            # LM
            reference[reference == 5] = 2
            reference[(reference > 5)] = 0

        elif self.segmentationMode == "SegmentLevel" and self.exportType == "SegmentLevelDLNExport":
            reference[reference == 4] = 104  # RCA PROX
            reference[reference == 5] = 105  # RCA MID
            reference[reference == 6] = 106  # RCA DIST
            reference[reference == 7] = 107  # RCA SIDE

            reference[reference == 14] = 114  # LAD PROX
            reference[reference == 15] = 115  # LAD MID
            reference[reference == 16] = 116  # LAD DIST
            reference[reference == 17] = 117  # LAD SIDE

            reference[reference == 19] = 119  # LCX PROX
            reference[reference == 20] = 120  # LCX MID
            reference[reference == 21] = 121  # LCX DIST
            reference[reference == 22] = 122  # LCX SIDE

            #convert ids
            reference[(reference >= 9) & (reference <= 12)] = 2 # LM

            reference[reference == 114] = 3  # LAD PROX
            reference[reference == 115] = 4  # LAD MID
            reference[reference == 116] = 5  # LAD DIST
            reference[reference == 117] = 6  # LAD SIDE

            reference[reference == 119] = 7  # LCX PROX
            reference[reference == 120] = 8  # LCX MID
            reference[reference == 121] = 9  # LCX DIST
            reference[reference == 122] = 10  # LCX SIDE

            reference[reference == 104] = 11  # RCA PROX
            reference[reference == 105] = 12  # RCA MID
            reference[reference == 106] = 13  # RCA DIST
            reference[reference == 107] = 14  # RCA SIDE

            reference[reference == 23] = 15  # RIM

            reference[(reference >= 16)] = 0  # LM

        elif self.segmentationMode == "SegmentLevelDLNExport" and self.exportType == "ArteryLevelWithLM":
            reference[reference == 2] = 102  # LM

            reference[reference == 3] = 103  # LAD PROX
            reference[reference == 4] = 104  # LAD MID
            reference[reference == 5] = 105  # LAD DIST
            reference[reference == 6] = 106  # LAD SIDE

            reference[reference == 7] = 107  # LCX PROX
            reference[reference == 8] = 108  # LCX MID
            reference[reference == 9] = 109  # LCX DIST
            reference[reference == 10] = 110  # LCX SIDE

            reference[reference == 11] = 111  # RCA PROX
            reference[reference == 12] = 112  # RCA MID
            reference[reference == 13] = 113  # RCA DIST
            reference[reference == 14] = 114  # RCA SIDE

            reference[reference == 15] = 115  # RIM

            # Combines all lesions in each artery to one group
            # RCA
            reference[(reference >= 111) & (reference <= 114)] = 4

            # LAD
            reference[(reference >= 103) & (reference <= 106)] = 2

            # LCX
            reference[(reference >= 107) & (reference <= 110)] = 3

            # RIM
            reference[(reference == 115)] = 2

            # LM
            reference[reference == 102] = 5

            reference[(reference >= 6)] = 0

        elif self.segmentationMode == "SegmentLevelDLNExport" and self.exportType == "ArteryLevel":
            reference[reference == 2] = 102  # LM

            reference[reference == 3] = 103  # LAD PROX
            reference[reference == 4] = 104  # LAD MID
            reference[reference == 5] = 105  # LAD DIST
            reference[reference == 6] = 106  # LAD SIDE

            reference[reference == 7] = 107  # LCX PROX
            reference[reference == 8] = 108  # LCX MID
            reference[reference == 9] = 109  # LCX DIST
            reference[reference == 10] = 110  # LCX SIDE

            reference[reference == 11] = 111  # RCA PROX
            reference[reference == 12] = 112  # RCA MID
            reference[reference == 13] = 113  # RCA DIST
            reference[reference == 14] = 114  # RCA SIDE

            reference[reference == 15] = 115  # RIM

            # Combines all lesions in each artery to one group
            # RCA
            reference[(reference >= 111) & (reference <= 114)] = 4

            # LAD
            reference[(reference >= 103) & (reference <= 106)] = 2

            # LCX
            reference[(reference >= 107) & (reference <= 110)] = 3

            # RIM
            reference[(reference == 115)] = 2

            # LM
            reference[reference == 102] = 2

            reference[(reference >= 5)] = 0

        referenceTemporaryCopy = reference.copy()
        referenceTemporaryCopy[referenceTemporaryCopy < 2] = 0


        structure = numpy.array([[[0, 0, 0],
                                   [0, 1, 0],
                                   [0, 0, 0]],

                                  [[0, 1, 0],
                                   [1, 1, 1],
                                   [0, 1, 0]],

                                  [[0, 0, 0],
                                   [0, 1, 0],
                                   [0, 0, 0]]])

        uniqueElements = numpy.unique(referenceTemporaryCopy)

        connectedElements = numpy.zeros_like(referenceTemporaryCopy)
        elementIterator = 0

        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = [executor.submit(ndi.label, (referenceTemporaryCopy == uniqueId).astype(int),
                                       structure=structure)
                       for uniqueId in uniqueElements[1:]]

            for future in concurrent.futures.as_completed(results):
                label, elementCount = future.result()
                connectedElements += numpy.where(label > 0, label + elementIterator, 0).astype(
                    connectedElements.dtype)
                elementIterator += elementCount

        return connectedElements, len(numpy.unique(connectedElements)) - 1

    def lesionPositionListEntry(self, connectedElements3d, index, image, reference):
        positions = numpy.array(list(zip(*numpy.where(connectedElements3d[0] == index))))

        newList = []

        for element in positions:
            attenuation = image[element[0], element[1], element[2]]
            originalLabel = reference[element[0], element[1], element[2]]
            element = numpy.concatenate((element, [attenuation, originalLabel]))
            newList.append(element)

        return numpy.array(newList)

    def jsonLesionLoop(self, lesion, it, patientID,seriesInstanceUID):
        self.exportJson[patientID][seriesInstanceUID]["lesions"][it] = {}
        self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["voxelCount3d"] = len(lesion)
        self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"] = {}

        slices = lesion[:, 0:1]
        slice, voxelCount = numpy.unique(slices, return_counts=True)
        slicesDict = dict(zip(slice, voxelCount))

        sliceIterator = 0
        for slice in slicesDict:
            self.jsonSliceLoop(patientID, seriesInstanceUID, it, lesion, slice, sliceIterator, slicesDict)
            sliceIterator += 1

    def jsonSliceLoop(self, patientID, seriesInstanceUID, it, lesion, slice, sliceIterator, slicesDict):
        sliceArray = lesion[numpy.in1d(lesion[:, 0], slice)]

        #needed to check if lesions are seperated in 2d but connected in 3d
        maxCoordinate = 513

        tempComponentAnalysis = numpy.zeros(shape=(maxCoordinate,maxCoordinate))
        tempAttenuation = numpy.zeros(shape=(maxCoordinate, maxCoordinate))
        tempLabel = numpy.zeros(shape=(maxCoordinate, maxCoordinate))

        for element in sliceArray:
            row = element[1]
            column = element[2]
            tempComponentAnalysis[row, column] = 1
            tempAttenuation[row, column] = element[3]
            tempLabel[row, column] = element[4]

        structureConnections2d = numpy.array([[0, 1, 0],
                                               [1, 1, 1],
                                               [0, 1, 0]])

        connections, N = label(tempComponentAnalysis, structureConnections2d)

        self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceIterator] = {}
        self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceIterator]["voxelCount2D"] = slicesDict[slice]
        self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceIterator]["labeledAs"] = {}
        self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceIterator]["sliceNumber"] = slice

        if N > 1:
            labelsSummary = {}

            for lesionId in range(1, N + 1):
                positions = numpy.array(list(zip(*numpy.where(connections == lesionId))))
                lesionSummary = {}

                for position in positions:
                    labelAtPosition = tempLabel[position[0],position[1]]
                    attenuationAtPosition = tempAttenuation[position[0],position[1]]

                    if self.arteryId[labelAtPosition] in lesionSummary:
                        lesionSummary[self.arteryId[labelAtPosition]]["voxelCount"] = lesionSummary[self.arteryId[labelAtPosition]]["voxelCount"] + 1
                        if attenuationAtPosition > lesionSummary[self.arteryId[labelAtPosition]]["maxAttenuation"]:
                            lesionSummary[self.arteryId[labelAtPosition]]["maxAttenuation"] = attenuationAtPosition
                    else:
                        lesionSummary[self.arteryId[labelAtPosition]] = {}
                        lesionSummary[self.arteryId[labelAtPosition]]["voxelCount"] = 1
                        lesionSummary[self.arteryId[labelAtPosition]]["maxAttenuation"] = attenuationAtPosition

                labelsSummary[lesionId] = lesionSummary

            self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceIterator]["labeledAs"] = labelsSummary
            self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceIterator]["maxAttenuation"] = None
        else:
            self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceIterator]["maxAttenuation"] = max(max(sliceArray[:, 3:4]))

            arteryId = sliceArray[:, 4:5]
            arteries, arteryCount = numpy.unique(arteryId, return_counts=True)
            arteryDict = dict(zip(arteries, arteryCount))

            for artery in arteryDict:
                self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceIterator]["labeledAs"][self.arteryId[artery]] = arteryDict[artery]

    def calculateLesions(self, image, reference, connectedElements3d, patientID, seriesInstanceUID):
        lesionPositionList = []

        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = [executor.submit(self.lesionPositionListEntry, connectedElements3d, index, image, reference) for index in range(1, connectedElements3d[1] + 1)]

            for future in concurrent.futures.as_completed(results):
                lesionPositionList.append(future.result())

        it = 0
        for lesion in lesionPositionList:
            self.jsonLesionLoop(lesion, it, patientID, seriesInstanceUID)

            it += 1

    def agatstonScore(self, voxelLength, voxelCount, attenuation, ratio):
        score = 0.0

        if (voxelLength is not None) and (voxelCount is not None) and (attenuation is not None) and (ratio is not None):
            voxelArea = voxelLength * voxelLength
            lesionArea = voxelArea * voxelCount

            if attenuation >= 130 and lesionArea > 1:
                score = lesionArea * self.densityFactor(attenuation) * ratio

        return score

    def calculateScore(self, patientID, seriesInstanceUID):
        total = {"PatientID": patientID, "SeriesInstanceUID": seriesInstanceUID}

        for key in self.Items:
            total[key] = 0.0

        for lesionsJson in self.exportJson[patientID][seriesInstanceUID]["lesions"]:
            for sliceJson in self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"]:

                sliceNumber = self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["sliceNumber"]
                if sliceNumber in self.exportJson[patientID][seriesInstanceUID]["countingSlices"]:
                    attenuation = self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["maxAttenuation"]

                    if attenuation is not None:
                        for arteryJson in self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["labeledAs"]:
                            voxelCount = self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["labeledAs"][arteryJson]
                            voxelLength = self.exportJson[patientID][seriesInstanceUID]["voxelLength"]

                            score = self.agatstonScore(voxelLength, voxelCount, attenuation,self.exportJson[patientID][seriesInstanceUID]["sliceRatio"])

                            if arteryJson in total:
                                total[arteryJson] += score
                            else:
                                total[arteryJson] = score
                    else:
                        for subLabelId in self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["labeledAs"]:
                            for sublabelArtery in self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["labeledAs"][subLabelId]:
                                maxAttenuation = self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["labeledAs"][subLabelId][sublabelArtery]["maxAttenuation"]
                                voxelLength = self.exportJson[patientID][seriesInstanceUID]["voxelLength"]
                                voxelCount = self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["labeledAs"][subLabelId][sublabelArtery]["voxelCount"]

                                score = self.agatstonScore(voxelLength, voxelCount, maxAttenuation, self.exportJson[patientID][seriesInstanceUID]["sliceRatio"])

                                if sublabelArtery in total:
                                    total[sublabelArtery] += score
                                else:
                                    total[sublabelArtery] = score

        for key in self.Items:
            if isinstance(self.Items[key], list):
                sum = 0.0
                for id in self.Items[key]:
                    if id in self.arteryId and self.arteryId[id] in total:
                        sum += total[self.arteryId[id]]

                total[key] = sum

        return total

    def calculateScoreFromImage(self, image, reference, patientID, seriesInstanceUID):
        connectedElements = self.findLesions(reference)

        self.calculateLesions(image, reference, connectedElements, patientID, seriesInstanceUID)
        return self.calculateScore(patientID, seriesInstanceUID)


    def processImages(self, filename, sliceStepDataframe):
        processedFilename = self.processFilename(os.path.join(self.filepaths["referenceFolder"], filename))

        if os.path.isfile(os.path.join(self.filepaths["imageFolder"], processedFilename[1] + ".mhd")):
            image = sitk.ReadImage(os.path.join(self.filepaths["imageFolder"], processedFilename[1] + ".mhd"))
            label = sitk.ReadImage(os.path.join(self.filepaths["referenceFolder"], filename))

            # Convert the image to a numpy array first and then shuffle the dimensions to get axis in the order z,y,x
            imageArray = sitk.GetArrayFromImage(image)
            labelArray = sitk.GetArrayFromImage(label)

            # Read the spacing along each dimension
            spacing = numpy.array(list(reversed(image.GetSpacing())))
            sliceThickness = sliceStepDataframe.loc[(sliceStepDataframe['patient_id'] == processedFilename[2])].slice_thickness.item()
            sliceStep = sliceStepDataframe.loc[(sliceStepDataframe['patient_id'] == processedFilename[2])].slice_step.item()

            exportData = {"PatientID": processedFilename[2], "SeriesInstanceUID": processedFilename[3]}

            self.exportJson[processedFilename[2]] = {}
            self.exportJson[processedFilename[2]][processedFilename[3]] = {}
            self.exportJson[processedFilename[2]][processedFilename[3]]["sliceRatio"] = sliceThickness / 3.0
            self.exportJson[processedFilename[2]][processedFilename[3]]["voxelLength"] = spacing[1]  # voxel length in mm
            self.exportJson[processedFilename[2]][processedFilename[3]]["lesions"] = {}
            self.exportJson[processedFilename[2]][processedFilename[3]]["sliceCount"] = len(imageArray)
            self.exportJson[processedFilename[2]][processedFilename[3]]["sliceStep"] = sliceStep

            countingSlices = []

            for sliceNumber in range(0, len(imageArray), sliceStep):
                countingSlices.append(sliceNumber)

            self.exportJson[processedFilename[2]][processedFilename[3]]["countingSlices"] = countingSlices

            result = self.calculateScoreFromImage(imageArray, labelArray, processedFilename[2], processedFilename[3])

            print("Exported " + processedFilename[1])
            self.exportList.append(result)
            self.createExportFilesAndSaveContent(createJson=True)



    def densityFactor(self, maxDensity):
        if maxDensity >= 130 and maxDensity <= 199:
            return 1
        if maxDensity >= 200 and maxDensity <= 299:
            return 2
        if maxDensity >= 300 and maxDensity <= 399:
            return 3
        if maxDensity >= 400:
            return 4

#
# CACSLabelerTest
#

class CACSLabelerTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_CACSLabeler1()

    def test_CACSLabeler1(self):
        """ Ideally you should have several levels of tests.  At the lowest level
        tests should exercise the functionality of the logic with different inputs
        (both valid and invalid).  At higher levels your tests should emulate the
        way the user would interact with your code and confirm that it still works
        the way you intended.
        One of the most important features of the tests is that it should alert other
        developers when their changes will have an impact on the behavior of your
        module.  For example, if a developer removes a feature that you depend on,
        your test should break so they know that the feature is needed.
        """

        self.delayDisplay("Starting the test")

        # Get/create input data

        import SampleData
        registerSampleData()
        inputVolume = SampleData.downloadSample('CACSLabeler1')
        self.delayDisplay('Loaded test data set')

        inputScalarRange = inputVolume.GetImageData().GetScalarRange()
        self.assertEqual(inputScalarRange[0], 0)
        self.assertEqual(inputScalarRange[1], 695)

        outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
        threshold = 100

        # Test the module logic

        logic = CACSLabelerLogic()

        # Test algorithm with non-inverted threshold
        logic.process(inputVolume, outputVolume, threshold, True)
        outputScalarRange = outputVolume.GetImageData().GetScalarRange()
        self.assertEqual(outputScalarRange[0], inputScalarRange[0])
        self.assertEqual(outputScalarRange[1], threshold)

        # Test algorithm with inverted threshold
        logic.process(inputVolume, outputVolume, threshold, False)
        outputScalarRange = outputVolume.GetImageData().GetScalarRange()
        self.assertEqual(outputScalarRange[0], inputScalarRange[0])
        self.assertEqual(outputScalarRange[1], inputScalarRange[1])

        self.delayDisplay('Test passed')
