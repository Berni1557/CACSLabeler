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

import vtk
import random

import sys

from scipy.ndimage import label
from scipy import ndimage as ndi

import importlib

import time
import threading

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
        self.parent.categories = ["Cardiac Computed Tomography"]
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
        self.ui.compareLabelsButton.connect('clicked(bool)', self.onCompareLabelsButton)

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

            self.compareObserverComboBoxEventBlocked = False
            self.ui.compareObserverComboBox.connect("currentIndexChanged(int)", self.onCompareObserverComboBoxChange)

            self.ui.comparableSegmentationTypes.connect("currentIndexChanged(int)",
                                                        self.onComparisonSegmentationTypeChange)

            self.currentLoadedNode = None
            self.currentLoadedReferenceNode = None
            self.initializeMainUI()
        else:
            print("Settings file error! Change settings in JSON file!")
            self.ui.errorText.setHidden(False)
            self.ui.settingsCollapsibleButton.setHidden(True)
            self.ui.errorText.text = "Settings file error! \n Change settings in JSON file!"

        self.colorTableNode = None
        self.createColorTable()

        self.createEditorWidget(self.ui.embeddedSegmentEditorWidget, "createEditor")
        self.createEditorWidget(self.ui.compareObserversEditor, "compareEditor")

        self.ui.comparisonLine1.setHidden(True)
        self.ui.comparisonLine2.setHidden(True)
        self.ui.comparisonSaveButton.setHidden(True)


        self.ui.saveButton.setHidden(True)

        self.selectedExportType = self.settings["exportType"]
        self.availableExportTypes = list(self.settings["exportedLabels"].keys())

        self.ui.exportTypeComboBox.clear()
        self.ui.exportTypeComboBox.addItems(self.availableExportTypes)
        self.ui.exportTypeComboBox.setCurrentText(self.selectedExportType)

        #Init Comparison
        self.comparisonObserver1 = None
        self.comparisonObserver2 = None

        self.ui.comparisonSelectNextImageButton.connect('clicked(bool)', self.onComparisonSelectNextImage)
        self.ui.comparisonSelectNextImageToLoadButton.connect('clicked(bool)', self.onComparisonSelectImageToLoad)

        self.createCompareObserversBox()

        self.ui.CompareObserver1Selector.connect("currentIndexChanged(int)", self.onComparisonChangeFirstObserver)
        self.ui.CompareObserver2Selector.connect("currentIndexChanged(int)", self.onComparisonChangeSecondObserver)

        self.ui.comparisonSaveButton.connect('clicked(bool)', self.onSaveComparisonLabel)

    def checkIfDependenciesAreInstalled(self):
        dependencies = ["pandas"]

        for dependency in dependencies:
            if importlib.util.find_spec(dependency) is None:
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

    def createEditorWidget(self, editorObject, editorName):
        editorObject.setMRMLScene(slicer.mrmlScene)
        editorObject.setSegmentationNodeSelectorVisible(False)
        editorObject.setSourceVolumeNodeSelectorVisible(False)
        editorObject.setEffectNameOrder(['Paint', 'Erase'])
        editorObject.unorderedEffectsVisible = False
        editorObject.setMRMLSegmentEditorNode(self.getSegmentEditorNode(editorName))
        editorObject.setSwitchToSegmentationsButtonVisible(False)
        editorObject.setHidden(True)

    def getSegmentEditorNode(self, segmentEditorSingletonTag):
        # Use the Segment Editor module's parameter node for the embedded segment editor widget.
        # This ensures that if the user switches to the Segment Editor then the selected
        # segmentation node, volume node, etc. are the same.
        segmentEditorNode = slicer.mrmlScene.GetSingletonNode(segmentEditorSingletonTag, "vtkMRMLSegmentEditorNode")
        if segmentEditorNode is None:
            segmentEditorNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLSegmentEditorNode")
            segmentEditorNode.UnRegister(None)
            segmentEditorNode.SetSingletonTag(segmentEditorSingletonTag)
            segmentEditorNode = slicer.mrmlScene.AddNode(segmentEditorNode)
        return segmentEditorNode

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
            self.compareObserverComboBoxEventBlocked = True

            newDataset = list(self.availableDatasetsAndObservers.keys())[datasetListId]
            self.selectDatasetAndObserver(newDataset)
            self.updateDatasetAndObserverDropdownSelection()
            self.saveSettings()
            self.initializeMainUI()

            self.datasetComboBoxEventBlocked = False
            self.observerComboBoxEventBlocked = False
            self.compareObserverComboBoxEventBlocked = False

    def onChangeObserver(self, item=None):
        self.clearCurrentViewedNode(True)

        if not self.observerComboBoxEventBlocked:
            self.datasetComboBoxEventBlocked = True
            self.observerComboBoxEventBlocked = True
            self.compareObserverComboBoxEventBlocked = True

            self.selectDatasetAndObserver(self.settings["savedDatasetAndObserverSelection"]["dataset"], self.availableDatasetsAndObservers[self.settings["savedDatasetAndObserverSelection"]["dataset"]][item])
            self.saveSettings()
            self.initializeMainUI()

            self.createObserverAvailableList()

            self.datasetComboBoxEventBlocked = False
            self.observerComboBoxEventBlocked = False
            self.compareObserverComboBoxEventBlocked = False

    def loadVolumeToSlice(self, filename, imagesPath):
        self.changeViewCreateView()
        self.ui.embeddedSegmentEditorWidget.setHidden(True)
        self.ui.saveButton.setHidden(True)

        self.createColorTable()
        properties = {'Name': filename}

        self.currentLoadedNode = slicer.util.loadVolume(os.path.join(imagesPath, filename), properties=properties)
        self.currentLoadedNode.SetName(filename)

        slicer.util.setSliceViewerLayers(background=self.currentLoadedNode)
        self.currentLoadedNode.GetScalarVolumeDisplayNode().AutoWindowLevelOff()
        self.currentLoadedNode.GetScalarVolumeDisplayNode().SetWindowLevel(800, 180)

        # Activate buttons
        self.ui.compareCollapsibleButton.enabled = True

        self.ui.RadioButton120keV.enabled = True
        self.ui.thresholdVolumeButton.enabled = True
        self.ui.selectedVolumeTextField.text = filename
        self.ui.selectedVolumeTextField.cursorPosition = 0
        self.ui.selectedVolumeLabel.enabled = True

        self.checkIfOtherLabelIsAvailable(filename)

        self.ui.compareLabelsButton.enabled = False
        self.checkIfLabelCanBeCompared(filename)

    def onSelectNextUnlabeledImage(self):
        self.clearCurrentViewedNode(True)
        imageList = self.getImageList(self.selectedDatasetAndObserverSetting())

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

    def checkIfOtherLabelIsAvailable(self, filename):
        differentLabelType = self.differentLabelType()

        labelFileName = filename.split(".mhd")[0] + differentLabelType["labelFileSuffix"] + '.nrrd'
        file = os.path.join(differentLabelType["labelPath"], labelFileName)

        if differentLabelType is not None and os.path.isfile(file):
            self.ui.availableLabelType.text = differentLabelType["labelSegmentationMode"]
            self.ui.availableLabelType.cursorPosition = 0
            self.ui.availableLabel.enabled = True

    def onThresholdVolume(self):
        if not self.ui.RadioButton120keV.checked:
            qt.QMessageBox.warning(slicer.util.mainWindow(),"Select KEV", "The KEV (80 or 120) must be selected to continue.")
            return

        imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer, labelFileSuffix = self.selectedDatasetAndObserverSetting()

        #removes file extension
        inputVolumeName = self.currentLoadedNode.GetName()
        labelName = os.path.splitext(inputVolumeName)[0] + labelFileSuffix

        differentLabelType = self.differentLabelType()

        self.logic.runThreshold(inputVolumeName, labelName, segmentationMode, self.settings, labelsPath, self.colorTableNode, differentLabelType)
        self.currentLoadedReferenceNode = slicer.util.getNode(labelName)

        self.ui.embeddedSegmentEditorWidget.setSegmentationNode(slicer.util.getNode(labelName))
        self.getSegmentEditorNode("createEditor").SetMasterVolumeIntensityMask(True)
        self.getSegmentEditorNode("createEditor").SetSourceVolumeIntensityMaskRange(float(lowerThresholdValue), 10000.0)

        self.ui.embeddedSegmentEditorWidget.setHidden(False)
        self.ui.saveButton.setHidden(False)

    def differentLabelType(self):
        imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer, labelFileSuffix = self.selectedDatasetAndObserverSetting()
        differentLabelType = None

        # check if other labels exist
        if "differentSegmentationModeLabels" in self.settings["datasets"][dataset]["observers"][observer]:
            if "labelsPath" in self.settings["datasets"][dataset]["observers"][observer][
                "differentSegmentationModeLabels"] and "segmentationMode" in \
                    self.settings["datasets"][dataset]["observers"][observer]["differentSegmentationModeLabels"]:
                differentLabelType = {
                    "labelPath": self.settings["datasets"][dataset]["observers"][observer]["differentSegmentationModeLabels"]["labelsPath"],
                    "labelSegmentationMode": self.settings["datasets"][dataset]["observers"][observer]["differentSegmentationModeLabels"]["segmentationMode"],
                    "labelFileSuffix": self.settings["datasets"][dataset]["observers"][observer]["differentSegmentationModeLabels"]["labelFileSuffix"]
                }

        return differentLabelType

    def initializeMainUI(self):
        self.clearCurrentViewedNode()
        self.progressBarUpdate()

        observer = self.settings["savedDatasetAndObserverSelection"]["observer"]
        dataset = self.settings["savedDatasetAndObserverSelection"]["dataset"]
        self.ui.currentObserverName.text = observer
        self.ui.currentObserverSegmentationType.text = self.settings["datasets"][dataset]["observers"][observer]["segmentationMode"]

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
        self.ui.selectedVolumeLabel.enabled = False

        self.ui.availableLabelType.text = ""
        self.ui.availableLabelType.cursorPosition = 0
        self.ui.availableLabel.enabled = False
        self.currentLoadedNode = None

    def progressBarUpdate(self):
        images = self.getImageList(self.selectedDatasetAndObserverSetting())
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
                                "labelFileSuffix": "",
                                "segmentationMode": "",
                                "differentSegmentationModeLabels": {
                                    "labelsPath": "",
                                    "segmentationMode": "",
                                    "labelFileSuffix": ""
                                },
                                "includedImageFilter" :""
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
                            "color": "#fc5000"
                        },
                        "RCA_MID": {
                            "value": 5,
                            "color": "#feda00"
                        },
                        "RCA_DISTAL": {
                            "value": 6,
                            "color": "#ffe4a5"
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
                            "color": "#d8ffcd"
                        },
                        "LAD_PROXIMAL": {
                            "value": 14,
                            "color": "#0050fd"
                        },
                        "LAD_MID": {
                            "value": 15,
                            "color": "#00ffff"
                        },
                        "LAD_DISTAL": {
                            "value": 16,
                            "color": "#91ffff"
                        },
                        "LAD_SIDE_BRANCH": {
                            "value": 17,
                            "color": "#00b3ff"
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
                            "color": "#edfc9f"
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
        labelFileSuffix = self.settings["datasets"][dataset]["observers"][observer]["labelFileSuffix"]

        return imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer, labelFileSuffix

    def mainUIHidden(self, hide):
        self.ui.inputCollapsibleButton.setHidden(hide)
        self.ui.exportCollapsibleButton.setHidden(hide)
        self.ui.compareCollapsibleButton.setHidden(hide)

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

        self.createObserverAvailableList()

    def onExportFromReferenceFolderButtonClicked(self):
        exporter = ScoreExport(self.selectedDatasetAndObserverSetting(), self.settings)
        exporter.exportFromReferenceFolder()

    def onExportFromJSONFileButtonClicked(self):
        exporter = ScoreExport(self.selectedDatasetAndObserverSetting(), self.settings)
        exporter.exportFromJSONFile()

    def createColorTable(self):
        imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer, labelFileSuffix = self.selectedDatasetAndObserverSetting()
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
        imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer, labelFileSuffix = self.selectedDatasetAndObserverSetting()

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

    def onCompareObserverComboBoxChange(self, item=None):
        if not self.compareObserverComboBoxEventBlocked:
            self.selectedComparableObserver = self.comparableObserversList[item]
            self.updateSecondObserverSegmentationTypeLabel(self.selectedComparableObserver)

    def updateSecondObserverSegmentationTypeLabel(self, observer):
        currentDataset = self.settings["savedDatasetAndObserverSelection"]["dataset"]
        segmentationType = self.settings["datasets"][currentDataset]["observers"][observer]["segmentationMode"]

        self.ui.secondObserverSegmentationType.text = segmentationType

        self.checkForComparableLabelSegmentationTypes(self.settings["savedDatasetAndObserverSelection"]["observer"], observer)

    def createObserverAvailableList(self):
        self.ui.compareObserverComboBox.clear()

        list = self.compareObserverAvailableList()
        self.ui.compareObserverComboBox.addItems(list)

        if len(list) > 0:
            self.ui.compareObserverComboBox.enabled = True
            self.ui.compareObserverLabel.enabled = True
            self.ui.secondObserverSegmentationType.enabled = True

            self.ui.compareObserverComboBox.setCurrentText(list[0])
            self.updateSecondObserverSegmentationTypeLabel(list[0])

            self.comparableObserversList = list
            self.selectedComparableObserver = list[0]
        else:
            self.ui.compareObserverComboBox.enabled = False
            self.ui.compareObserverLabel.enabled = False
            self.ui.secondObserverSegmentationType.enabled = False

    def compareObserverAvailableList(self):
        currentDataset = self.settings["savedDatasetAndObserverSelection"]["dataset"]
        currentObserver = self.settings["savedDatasetAndObserverSelection"]["observer"]
        currentSegmentationType = self.settings["datasets"][currentDataset]["observers"][currentObserver]["segmentationMode"]

        comparableObservers = []

        for observer in self.settings["datasets"][currentDataset]["observers"]:
            if observer != currentObserver:
                segmentationModeOfObserver = self.settings["datasets"][currentDataset]["observers"][observer]["segmentationMode"]

                if (currentSegmentationType == "SegmentLevel") and (segmentationModeOfObserver == "SegmentLevel" or segmentationModeOfObserver == "SegmentLevelDLNExport"):
                    comparableObservers.append(observer)

                if (currentSegmentationType == "SegmentLevelDLNExport") and (segmentationModeOfObserver == "SegmentLevel" or segmentationModeOfObserver == "SegmentLevelDLNExport"):
                    comparableObservers.append(observer)

        return comparableObservers

    def checkIfLabelCanBeCompared(self, filename):
        file = filename.split(".mhd")[0]
        currentDataset = self.settings["savedDatasetAndObserverSelection"]["dataset"]
        labelsPath = self.settings["datasets"][currentDataset]["observers"][self.selectedComparableObserver]["labelsPath"]
        labelFileSuffix = self.settings["datasets"][currentDataset]["observers"][self.selectedComparableObserver]["labelFileSuffix"]

        fullLabelFilename = file + labelFileSuffix + ".nrrd"

        if os.path.isfile(os.path.join(labelsPath, fullLabelFilename)):
            self.ui.compareLabelsButton.enabled = True
        else:
            self.ui.compareLabelsButton.enabled = False

    def isSegmentationTypeLowerLevel(self, firstType, secondType):
        segmentationTypes = ["ArteryLevel", "ArteryLevelWithLM", "SegmentLevelDLNExport", "SegmentLevel"]

        return (segmentationTypes.index(firstType) < segmentationTypes.index(secondType))

    def getEqualAndLowerSegmentationTypes(self, segmentationType):
        segmentationTypes = ["ArteryLevel", "ArteryLevelWithLM", "SegmentLevelDLNExport", "SegmentLevel"]
        return segmentationTypes[:segmentationTypes.index(segmentationType)+1]

    def checkForComparableLabelSegmentationTypes(self, firstObserver, secondObserver):
        currentDataset = self.settings["savedDatasetAndObserverSelection"]["dataset"]
        firstSegmentationType = self.settings["datasets"][currentDataset]["observers"][firstObserver]["segmentationMode"]
        secondSegmentationType = self.settings["datasets"][currentDataset]["observers"][secondObserver]["segmentationMode"]

        list = []

        if firstSegmentationType != secondSegmentationType:
            if self.isSegmentationTypeLowerLevel(firstSegmentationType, secondSegmentationType):
                list = self.getEqualAndLowerSegmentationTypes(firstSegmentationType)
            else:
                list = self.getEqualAndLowerSegmentationTypes(secondSegmentationType)
        else:
            list = self.getEqualAndLowerSegmentationTypes(firstSegmentationType)

        self.availableComparisonSegmentationTypes = list[::-1]
        self.comparisonSegmentationType = self.availableComparisonSegmentationTypes[0]

        self.ui.comparableSegmentationTypes.clear()
        self.ui.comparableSegmentationTypes.addItems(self.availableComparisonSegmentationTypes)
        self.ui.comparableSegmentationTypes.setCurrentText(self.availableComparisonSegmentationTypes[0])

    def onComparisonSegmentationTypeChange(self, item):
        self.comparisonSegmentationType = self.availableComparisonSegmentationTypes[item]

    def onCompareLabelsButton(self):
        file = self.currentLoadedNode.GetName().split(".mhd")[0]
        currentDataset = self.settings["savedDatasetAndObserverSelection"]["dataset"]
        currentObserver = self.settings["savedDatasetAndObserverSelection"]["observer"]

        currentObserverLabelpath = self.settings["datasets"][currentDataset]["observers"][currentObserver]["labelsPath"]
        currentObserverlabelFileSuffix = self.settings["datasets"][currentDataset]["observers"][currentObserver]["labelFileSuffix"]

        compareObserverLabelpath = self.settings["datasets"][currentDataset]["observers"][self.selectedComparableObserver]["labelsPath"]
        compareObserverlabelFileSuffix = self.settings["datasets"][currentDataset]["observers"][self.selectedComparableObserver]["labelFileSuffix"]

        currentObserverFilePath = os.path.join(currentObserverLabelpath, (file + currentObserverlabelFileSuffix + ".nrrd"))
        compareObserverFilePath = os.path.join(compareObserverLabelpath, (file + compareObserverlabelFileSuffix + ".nrrd"))

        # import labels
        labelCurrentObserver = sitk.GetArrayFromImage(sitk.ReadImage(currentObserverFilePath))
        labelCompareObserver = sitk.GetArrayFromImage(sitk.ReadImage(compareObserverFilePath))

        #Compare labels
        currentObserverSegmentationType = self.settings["datasets"][currentDataset]["observers"][currentObserver]["segmentationMode"]
        compareObserverSegmentationType = self.settings["datasets"][currentDataset]["observers"][self.selectedComparableObserver]["segmentationMode"]


        labelCurrentObserver = self.processSegmentationLabels(labelCurrentObserver, currentObserverSegmentationType, self.comparisonSegmentationType)
        labelCompareObserver = self.processSegmentationLabels(labelCompareObserver, compareObserverSegmentationType, self.comparisonSegmentationType)

        self.compareLabels(labelCurrentObserver, labelCompareObserver)

    def compareLabels(self, labelOne, labelTwo):
        comparison = numpy.where(numpy.equal(labelOne, labelTwo) == True, 2, 1)

        oneBackground = numpy.where(labelOne == 0, 0, 1)
        twoBackground = numpy.where(labelTwo == 0, 0, -1)

        comparison[numpy.equal(oneBackground, twoBackground) == True] = 0

        imageNode = slicer.util.getNode(self.currentLoadedNode.GetName())

        segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
        segmentationNode.SetName("Comparison")
        segmentationNode.CreateDefaultDisplayNodes()  # only needed for display
        segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(imageNode)

        segmentation = segmentationNode.GetSegmentation()
        displayNode = segmentationNode.GetDisplayNode()

        names = {
            "Different label": {
                "id": 1,
                "color": "#ff0000"
            },
            "Same label": {
                "id": 2,
                "color": "#00ff00"
            },
        }

        for key in names:
            color = names[key]["color"]
            id = names[key]["id"]

            if segmentation.GetSegment(key) is None:
                segmentation.AddEmptySegment(key)

            segment = segmentation.GetSegment(key)
            r, g, b = ImageColor.getcolor(color, "RGB")
            segment.SetColor(r / 255, g / 255, b / 255)
            displayNode.SetSegmentOpacity3D(key, 1)  # Set opacity of a single segment

            segmentId = segmentationNode.GetSegmentation().GetSegmentIdBySegmentName(key)
            segmentArray = slicer.util.arrayFromSegmentBinaryLabelmap(segmentationNode, key, imageNode)
            segmentArray[comparison == id] = 1  # create segment by simple thresholding of an image
            slicer.util.updateSegmentBinaryLabelmapFromArray(segmentArray, segmentationNode, segmentId, imageNode)


    def getLabelIdByName(self, segmentationType, name):
        return self.settings["labels"][segmentationType][name]["value"]

    def processSegmentationLabels(self, label, oldSegmentationType, newSegmentationType):
        if oldSegmentationType == "SegmentLevelDLNExport":
            label[label == 1] = 0
        else:
            label[label == self.getLabelIdByName(oldSegmentationType, "OTHER")] = 0

        if oldSegmentationType == "SegmentLevel" and newSegmentationType == "SegmentLevelDLNExport":
            #Remove not needed labels
            label[label == self.getLabelIdByName(oldSegmentationType, "OTHER")] = 0
            label[label == self.getLabelIdByName(oldSegmentationType, "AORTA_ASC")] = 0
            label[label == self.getLabelIdByName(oldSegmentationType, "AORTA_DSC")] = 0
            label[label == self.getLabelIdByName(oldSegmentationType, "AORTA_ARC")] = 0
            label[label == self.getLabelIdByName(oldSegmentationType, "VALVE_AORTIC")] = 0
            label[label == self.getLabelIdByName(oldSegmentationType, "VALVE_PULMONIC")] = 0
            label[label == self.getLabelIdByName(oldSegmentationType, "VALVE_TRICUSPID")] = 0
            label[label == self.getLabelIdByName(oldSegmentationType, "VALVE_MITRAL")] = 0
            label[label == self.getLabelIdByName(oldSegmentationType, "PAPILLAR_MUSCLE")] = 0
            label[label == self.getLabelIdByName(oldSegmentationType, "NFS_CACS")] = 0

            label[label == self.getLabelIdByName(oldSegmentationType, "RCA_PROXIMAL")] = self.getLabelIdByName(oldSegmentationType, "RCA_PROXIMAL") + 100
            label[label == self.getLabelIdByName(oldSegmentationType, "RCA_MID")] = self.getLabelIdByName(oldSegmentationType, "RCA_MID") + 100
            label[label == self.getLabelIdByName(oldSegmentationType, "RCA_DISTAL")] = self.getLabelIdByName(oldSegmentationType, "RCA_DISTAL") + 100
            label[label == self.getLabelIdByName(oldSegmentationType, "RCA_SIDE_BRANCH")] = self.getLabelIdByName(oldSegmentationType, "RCA_SIDE_BRANCH") + 100

            label[label == self.getLabelIdByName(oldSegmentationType, "LAD_PROXIMAL")] = self.getLabelIdByName(oldSegmentationType, "LAD_PROXIMAL") + 100
            label[label == self.getLabelIdByName(oldSegmentationType, "LAD_MID")] = self.getLabelIdByName(oldSegmentationType, "LAD_MID") + 100
            label[label == self.getLabelIdByName(oldSegmentationType, "LAD_DISTAL")] = self.getLabelIdByName(oldSegmentationType, "LAD_DISTAL") + 100
            label[label == self.getLabelIdByName(oldSegmentationType, "LAD_SIDE_BRANCH")] = self.getLabelIdByName(oldSegmentationType, "LAD_SIDE_BRANCH") + 100

            label[label == self.getLabelIdByName(oldSegmentationType, "LCX_PROXIMAL")] = self.getLabelIdByName(oldSegmentationType, "LCX_PROXIMAL") + 100
            label[label == self.getLabelIdByName(oldSegmentationType, "LCX_MID")] = self.getLabelIdByName(oldSegmentationType, "LCX_MID") + 100
            label[label == self.getLabelIdByName(oldSegmentationType, "LCX_DISTAL")] = self.getLabelIdByName(oldSegmentationType, "LCX_DISTAL") + 100
            label[label == self.getLabelIdByName(oldSegmentationType, "LCX_SIDE_BRANCH")] = self.getLabelIdByName(oldSegmentationType, "LCX_SIDE_BRANCH") + 100

            label[label == self.getLabelIdByName(oldSegmentationType, "RIM")] = self.getLabelIdByName(oldSegmentationType, "RIM") + 100

            #convert ids
            label[label == self.getLabelIdByName(oldSegmentationType, "LM_BIF_LAD_LCX")] = self.getLabelIdByName(newSegmentationType, "LM")
            label[label == self.getLabelIdByName(oldSegmentationType, "LM_BIF_LAD")] = self.getLabelIdByName(newSegmentationType, "LM")
            label[label == self.getLabelIdByName(oldSegmentationType, "LM_BIF_LCX")] = self.getLabelIdByName(newSegmentationType, "LM")
            label[label == self.getLabelIdByName(oldSegmentationType, "LM_BRANCH")] = self.getLabelIdByName(newSegmentationType, "LM")

            label[label == self.getLabelIdByName(oldSegmentationType, "RCA_PROXIMAL") + 100] = self.getLabelIdByName(
                newSegmentationType, "RCA_PROXIMAL")
            label[label == self.getLabelIdByName(oldSegmentationType, "RCA_MID") + 100] = self.getLabelIdByName(
                newSegmentationType, "RCA_MID")
            label[label == self.getLabelIdByName(oldSegmentationType, "RCA_DISTAL") + 100] = self.getLabelIdByName(
                newSegmentationType, "RCA_DISTAL")
            label[label == self.getLabelIdByName(oldSegmentationType, "RCA_SIDE_BRANCH") + 100] = self.getLabelIdByName(
                newSegmentationType, "RCA_SIDE_BRANCH")

            label[label == self.getLabelIdByName(oldSegmentationType, "LAD_PROXIMAL") + 100] = self.getLabelIdByName(
                newSegmentationType, "LAD_PROXIMAL")
            label[label == self.getLabelIdByName(oldSegmentationType, "LAD_MID") + 100] = self.getLabelIdByName(
                newSegmentationType, "LAD_MID")
            label[label == self.getLabelIdByName(oldSegmentationType, "LAD_DISTAL") + 100] = self.getLabelIdByName(
                newSegmentationType, "LAD_DISTAL")
            label[label == self.getLabelIdByName(oldSegmentationType, "LAD_SIDE_BRANCH") + 100] = self.getLabelIdByName(
                newSegmentationType, "LAD_SIDE_BRANCH")

            label[label == self.getLabelIdByName(oldSegmentationType, "LCX_PROXIMAL") + 100] = self.getLabelIdByName(
                newSegmentationType, "LCX_PROXIMAL")
            label[label == self.getLabelIdByName(oldSegmentationType, "LCX_MID") + 100] = self.getLabelIdByName(
                newSegmentationType, "LCX_MID")
            label[label == self.getLabelIdByName(oldSegmentationType, "LCX_DISTAL") + 100] = self.getLabelIdByName(
                newSegmentationType, "LCX_DISTAL")
            label[label == self.getLabelIdByName(oldSegmentationType, "LCX_SIDE_BRANCH") + 100] = self.getLabelIdByName(
                newSegmentationType, "LCX_SIDE_BRANCH")

            label[label == self.getLabelIdByName(oldSegmentationType, "RIM") + 100] = self.getLabelIdByName(
                newSegmentationType, "RIM")

        elif oldSegmentationType == "SegmentLevel" and newSegmentationType == "ArteryLevel":
            # Combines all lesions in each artery to one group
            # RCA
            label[(label >= 4) & (label <= 7)] = 4

            # LM
            label[(label >= 9) & (label <= 12)] = 2

            # LAD
            label[(label >= 14) & (label <= 17)] = 2

            # LCX
            label[(label >= 19) & (label <= 22)] = 3

            # RIM
            label[(label == 23)] = 2

            label[(label >= 5)] = 0

        elif oldSegmentationType == "SegmentLevel" and newSegmentationType == "ArteryLevelWithLM":
            # Combines all lesions in each artery to one group
            # RCA
            label[(label >= 4) & (label <= 7)] = 4

            # LAD
            label[(label >= 14) & (label <= 17)] = 2

            # LCX
            label[(label >= 19) & (label <= 22)] = 3

            # RIM
            label[(label == 23)] = 2

            # LM
            label[(label >= 9) & (label <= 12)] = 5

            label[(label >= 6)] = 0

        elif oldSegmentationType == "SegmentLevel" and newSegmentationType == "SegmentLevelOnlyArteries":
            label[label >= self.getLabelIdByName(oldSegmentationType, "AORTA_ASC")] = 0
            label[label == self.getLabelIdByName(oldSegmentationType, "LM_BIF_LAD_LCX")] = self.getLabelIdByName(oldSegmentationType, "LM_BRANCH")
            label[label == self.getLabelIdByName(oldSegmentationType, "LM_BIF_LAD")] = self.getLabelIdByName(oldSegmentationType, "LM_BRANCH")
            label[label == self.getLabelIdByName(oldSegmentationType, "LM_BIF_LCX")] = self.getLabelIdByName(oldSegmentationType, "LM_BRANCH")

        elif oldSegmentationType == "ArteryLevelWithLM" and newSegmentationType == "ArteryLevel":
            # LM
            label[label == 5] = 2
            label[(label > 5)] = 0

        elif oldSegmentationType == "SegmentLevelDLNExport" and newSegmentationType == "ArteryLevelWithLM":
            label[label == 2] = 102  # LM

            label[label == 3] = 103  # LAD PROX
            label[label == 4] = 104  # LAD MID
            label[label == 5] = 105  # LAD DIST
            label[label == 6] = 106  # LAD SIDE

            label[label == 7] = 107  # LCX PROX
            label[label == 8] = 108  # LCX MID
            label[label == 9] = 109  # LCX DIST
            label[label == 10] = 110  # LCX SIDE

            label[label == 11] = 111  # RCA PROX
            label[label == 12] = 112  # RCA MID
            label[label == 13] = 113  # RCA DIST
            label[label == 14] = 114  # RCA SIDE

            label[label == 15] = 115  # RIM

            # Combines all lesions in each artery to one group
            # RCA
            label[(label >= 111) & (label <= 114)] = 4

            # LAD
            label[(label >= 103) & (label <= 106)] = 2

            # LCX
            label[(label >= 107) & (label <= 110)] = 3

            # RIM
            label[(label == 115)] = 2

            # LM
            label[label == 102] = 5

            label[(label >= 6)] = 0

        elif oldSegmentationType == "SegmentLevelDLNExport" and newSegmentationType == "ArteryLevel":
            label[label == 2] = 102  # LM

            label[label == 3] = 103  # LAD PROX
            label[label == 4] = 104  # LAD MID
            label[label == 5] = 105  # LAD DIST
            label[label == 6] = 106  # LAD SIDE

            label[label == 7] = 107  # LCX PROX
            label[label == 8] = 108  # LCX MID
            label[label == 9] = 109  # LCX DIST
            label[label == 10] = 110  # LCX SIDE

            label[label == 11] = 111  # RCA PROX
            label[label == 12] = 112  # RCA MID
            label[label == 13] = 113  # RCA DIST
            label[label == 14] = 114  # RCA SIDE

            label[label == 15] = 115  # RIM

            # Combines all lesions in each artery to one group
            # RCA
            label[(label >= 111) & (label <= 114)] = 4

            # LAD
            label[(label >= 103) & (label <= 106)] = 2

            # LCX
            label[(label >= 107) & (label <= 110)] = 3

            # RIM
            label[(label == 115)] = 2

            # LM
            label[label == 102] = 2

            label[(label >= 5)] = 0

        return label

    def changeViewCreateView(self):
        layoutManager = slicer.app.layoutManager()
        layoutManager.setLayout(6)

## code for comparison

    def changeToComparisonView(self):
        ## create custom view
        threeViewLayout = """
               <layout type="horizontal">
                 <item>
                      <view class="vtkMRMLSliceNode" singletontag="Red">
                           <property name="orientation" action="default">Axial</property>
                           <property name="viewlabel" action="default">R</property>"
                           <property name="viewcolor" action="default">#F34A33</property>"
                     </view>
                 </item>
                 <item>
                      <view class="vtkMRMLSliceNode" singletontag="Yellow">
                           <property name="orientation" action="default">Axial</property>
                           <property name="viewlabel" action="default">Y</property>"
                           <property name="viewcolor" action="default">#EDD54C</property>"
                     </view>
                 </item>
                 <item>
                      <view class="vtkMRMLSliceNode" singletontag="Green">
                           <property name="orientation" action="default">Axial</property>
                           <property name="viewlabel" action="default">G</property>"
                           <property name="viewcolor" action="default">#6EB04B</property>"
                     </view>
                 </item>
               </layout>
               """

        # Built-in layout IDs are all below 100, so you can choose any large random number
        # for your custom layout ID.
        threeViewLayoutId = 200

        layoutManager = slicer.app.layoutManager()
        layoutManager.layoutLogic().GetLayoutNode().AddLayoutDescription(threeViewLayoutId, threeViewLayout)

        layoutManager.setLayout(threeViewLayoutId)

        nodes = slicer.util.getNodes("vtkMRMLSliceNode*")

        for node in nodes.values():
            node.SetOrientationToAxial()

    def createCompareObserversBox(self):
        currentSelectedDataset = self.settings["savedDatasetAndObserverSelection"]["dataset"]
        currentSelectedObserver = self.settings["savedDatasetAndObserverSelection"]["observer"]

        allObserversList = list(self.settings["datasets"][currentSelectedDataset]["observers"].keys())
        allObserversList.remove(currentSelectedObserver)

        self.ui.CompareObserver1Selector.clear()
        self.ui.CompareObserver1Selector.addItems(allObserversList)
        self.ui.CompareObserver1Selector.setCurrentText(allObserversList[0])
        self.comparisonObserver1 = allObserversList[0]

        secondObserverList = allObserversList
        secondObserverList.remove(self.comparisonObserver1)

        self.ui.CompareObserver2Selector.clear()
        self.ui.CompareObserver2Selector.addItems(secondObserverList)
        self.ui.CompareObserver2Selector.setCurrentText(secondObserverList[0])
        self.comparisonObserver2 = secondObserverList[0]

    def onComparisonChangeFirstObserver(self, id=None):
        currentSelectedDataset = self.settings["savedDatasetAndObserverSelection"]["dataset"]
        availableObservers = list(self.settings["datasets"][currentSelectedDataset]["observers"].keys())
        availableObservers.remove(self.settings["savedDatasetAndObserverSelection"]["observer"])

        self.comparisonObserver1 = availableObservers[id]

        secondObserverList = availableObservers
        secondObserverList.remove(self.comparisonObserver1)

        self.ui.CompareObserver2Selector.clear()
        self.ui.CompareObserver2Selector.addItems(secondObserverList)
        self.ui.CompareObserver2Selector.setCurrentText(secondObserverList[0])
        self.comparisonObserver2 = secondObserverList[0]

    def onComparisonChangeSecondObserver(self, id=None):
        currentSelectedDataset = self.settings["savedDatasetAndObserverSelection"]["dataset"]
        availableObservers = list(self.settings["datasets"][currentSelectedDataset]["observers"].keys())
        availableObservers.remove(self.settings["savedDatasetAndObserverSelection"]["observer"])
        availableObservers.remove( self.comparisonObserver1)

        self.comparisonObserver2 = availableObservers[id]

    def onComparisonSelectNextImage(self):
        slicer.mrmlScene.Clear()
        imageList = self.getImageList(self.selectedDatasetAndObserverSetting())
        self.loadImageToCompare(imageList["unlabeledImages"][0] + ".mhd")

    def onComparisonSelectImageToLoad(self):
        dataset = self.settings["savedDatasetAndObserverSelection"]["dataset"]
        imagesPath = self.settings["datasets"][dataset]["imagesPath"]

        # opens file selection window
        filepath = qt.QFileDialog.getOpenFileName(self.parent, 'Open files', imagesPath, "Files(*.mhd)")
        filename = filepath.split("/")[-1]

        self.loadImageToCompare(filename)

    def loadImageToCompare(self, filename):
        dataset = self.settings["savedDatasetAndObserverSelection"]["dataset"]
        imagesPath = self.settings["datasets"][dataset]["imagesPath"]

        self.clearCurrentViewedNode(True)
        self.ui.compareObserversEditor.setHidden(False)
        self.ui.comparisonLine1.setHidden(False)
        self.ui.comparisonLine2.setHidden(False)
        self.ui.comparisonSaveButton.setHidden(False)

        self.createColorTable()
        properties = {'Name': "CT_IMAGE"}

        self.currentLoadedNode = slicer.util.loadVolume(os.path.join(imagesPath, filename), properties=properties)
        self.currentLoadedNode.SetName(filename)

        slicer.util.setSliceViewerLayers(background=self.currentLoadedNode)
        self.currentLoadedNode.GetScalarVolumeDisplayNode().AutoWindowLevelOff()
        self.currentLoadedNode.GetScalarVolumeDisplayNode().SetWindowLevel(800, 180)

        self.loadComparisonLabels()
        self.changeToComparisonView()
        self.disableSegmentationInSpecificViews()

        self.ui.compareObserversEditor.setSegmentationNode(slicer.util.getNode("Comparison"))
        self.getSegmentEditorNode("compareEditor").SetMasterVolumeIntensityMask(True)
        self.getSegmentEditorNode("compareEditor").SetSourceVolumeIntensityMaskRange(float(lowerThresholdValue), 10000.0)

    def disableSegmentationInSpecificViews(self):
        observer1Segmentation = slicer.util.getNode(("Observer1Segmentation_" + self.comparisonObserver1))
        observer2Segmentation = slicer.util.getNode(("Observer2Segmentation_" + self.comparisonObserver2))
        comparisonSegmentation = slicer.util.getNode("Comparison")

        comparisonSegmentation.GetDisplayNode().SetDisplayableOnlyInView("vtkMRMLSliceNodeRed")

        if random.randint(1, 2) == 1:
            observer1Segmentation.GetDisplayNode().SetDisplayableOnlyInView("vtkMRMLSliceNodeYellow")
            observer2Segmentation.GetDisplayNode().SetDisplayableOnlyInView("vtkMRMLSliceNodeGreen")
        else:
            observer1Segmentation.GetDisplayNode().SetDisplayableOnlyInView("vtkMRMLSliceNodeGreen")
            observer2Segmentation.GetDisplayNode().SetDisplayableOnlyInView("vtkMRMLSliceNodeYellow")

        # Set linked slice views  in all existing slice composite nodes and in the default node
        sliceCompositeNodes = slicer.util.getNodesByClass("vtkMRMLSliceCompositeNode")
        defaultSliceCompositeNode = slicer.mrmlScene.GetDefaultNodeByClass("vtkMRMLSliceCompositeNode")
        if not defaultSliceCompositeNode:
            defaultSliceCompositeNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLSliceCompositeNode")
            defaultSliceCompositeNode.UnRegister(
                None)  # CreateNodeByClass is factory method, need to unregister the result to prevent memory leaks
            slicer.mrmlScene.AddDefaultNode(defaultSliceCompositeNode)
        sliceCompositeNodes.append(defaultSliceCompositeNode)
        for sliceCompositeNode in sliceCompositeNodes:
            sliceCompositeNode.SetLinkedControl(True)

    def loadComparisonLabels(self):
        dataset = self.settings["savedDatasetAndObserverSelection"]["dataset"]
        imageNodeName = self.currentLoadedNode.GetName()
        patientFileName = imageNodeName.split(".mhd")[0]

        observer1LabelPath = os.path.join(
            self.settings["datasets"][dataset]["observers"][self.comparisonObserver1]["labelsPath"],
            patientFileName + self.settings["datasets"][dataset]["observers"][self.comparisonObserver1][
                "labelFileSuffix"] + ".nrrd")

        observer2LabelPath = os.path.join(
            self.settings["datasets"][dataset]["observers"][self.comparisonObserver2]["labelsPath"],
            patientFileName + self.settings["datasets"][dataset]["observers"][self.comparisonObserver2][
                "labelFileSuffix"] + ".nrrd")

        # generate comparison mask
        # import labels
        observer1SegmentationArray = sitk.GetArrayFromImage(sitk.ReadImage(observer1LabelPath))
        observer2SegmentationArray = sitk.GetArrayFromImage(sitk.ReadImage(observer2LabelPath))

        # Compare labels
        observer1SegmentationType = self.settings["datasets"][dataset]["observers"][self.comparisonObserver1][
            "segmentationMode"]
        observer2SegmentationType = self.settings["datasets"][dataset]["observers"][self.comparisonObserver2][
            "segmentationMode"]

        if observer1SegmentationType == observer2SegmentationType:
            if observer1SegmentationType == "SegmentLevel":
                labelDescription = self.settings["labels"]["SegmentLevel"].copy()

                elementsToRemove = [
                    "LM_BIF_LAD_LCX",
                    "LM_BIF_LAD",
                    "LM_BIF_LCX",
                    "AORTA_ASC",
                    "AORTA_DSC",
                    "AORTA_ARC",
                    "VALVE_AORTIC",
                    "VALVE_PULMONIC",
                    "VALVE_TRICUSPID",
                    "VALVE_MITRAL",
                    "PAPILLAR_MUSCLE",
                    "NFS_CACS",
                ]

                for element in elementsToRemove:
                    labelDescription.pop(element)

                observer1Segmentation = self.processSegmentationLabels(observer1SegmentationArray,
                                                                       observer1SegmentationType,
                                                                       "SegmentLevelOnlyArteries")

                observer2Segmentation = self.processSegmentationLabels(observer2SegmentationArray,
                                                                       observer2SegmentationType,
                                                                       "SegmentLevelOnlyArteries")

                self.loadLabelFromArray(observer1SegmentationArray, ("Observer1Segmentation_" + self.comparisonObserver1), labelDescription)
                self.loadLabelFromArray(observer2SegmentationArray, ("Observer2Segmentation_" + self.comparisonObserver2), labelDescription)

                labelDescription["MISMATCH"] = {
                    'value': 100,
                    'color': "#ff0000"
                }

                self.createComparisonLabel(observer1Segmentation, observer2Segmentation, labelDescription)

            else:
                #TODO: Implement for all Segmentation Types
                print("Function only implemented for SegmentLevel")
        else:
            print("Segmentation Types not matching!")

    def createComparisonLabel(self, observer1Segmentation, observer2Segmentation, labelDescription):
        comparisonSegmentation = numpy.copy(observer1Segmentation)

        #finding differences using binary label
        binaryLabel = numpy.where(numpy.equal(observer1Segmentation, observer2Segmentation) == True, 2, 1)

        observer1Background = numpy.where(observer1Segmentation == 0, 0, 1)
        observer2Background = numpy.where(observer2Segmentation == 0, 0, -1)

        binaryLabel[numpy.equal(observer1Background, observer2Background) == True] = 0

        #add label to segmentation
        comparisonSegmentation[binaryLabel == 1] = 100

        imageNode = slicer.util.getNode(self.currentLoadedNode.GetName())

        segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
        segmentationNode.SetName("Comparison")
        segmentationNode.CreateDefaultDisplayNodes()  # only needed for display
        segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(imageNode)

        segmentation = segmentationNode.GetSegmentation()
        displayNode = segmentationNode.GetDisplayNode()

        for key in labelDescription:
            color = labelDescription[key]["color"]
            value = labelDescription[key]["value"]
            r, g, b = ImageColor.getcolor(color, "RGB")

            if segmentation.GetSegment(key) is None:
                segmentation.AddEmptySegment(key)

            segment = segmentation.GetSegment(key)

            segment.SetColor(r / 255, g / 255, b / 255)
            displayNode.SetSegmentOpacity3D(key, 1)

            segmentId = segmentationNode.GetSegmentation().GetSegmentIdBySegmentName(key)
            segmentArray = slicer.util.arrayFromSegmentBinaryLabelmap(segmentationNode, key, imageNode)

            if key == "OTHER":
                segmentArray[slicer.util.arrayFromVolume(imageNode) >= lowerThresholdValue] = 1
                segmentArray[comparisonSegmentation > self.settings["labels"]["SegmentLevel"][key]["value"]] = 0

            segmentArray[comparisonSegmentation == value] = 1  # create segment by simple thresholding of an image
            slicer.util.updateSegmentBinaryLabelmapFromArray(segmentArray, segmentationNode, segmentId, imageNode)

    def loadLabelFromArray(self, labelArray, labelName, labelDescription):
        uniqueKeys = numpy.unique(labelArray)

        imageNode = slicer.util.getNode(self.currentLoadedNode.GetName())

        segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
        segmentationNode.SetName(labelName)
        segmentationNode.CreateDefaultDisplayNodes()  # only needed for display
        segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(imageNode)

        segmentationNode = slicer.util.getNode(labelName)
        segmentation = segmentationNode.GetSegmentation()
        displayNode = segmentationNode.GetDisplayNode()

        for key in labelDescription:
            color = labelDescription[key]["color"]
            value = labelDescription[key]["value"]
            r, g, b = ImageColor.getcolor(color, "RGB")

            #improves speed ! only transversing elements that a segmented!
            if (value in uniqueKeys) or (key == "OTHER"):
                if segmentation.GetSegment(key) is None:
                    segmentation.AddEmptySegment(key)

                segment = segmentation.GetSegment(key)

                segment.SetColor(r / 255, g / 255, b / 255)  # red
                displayNode.SetSegmentOpacity3D(key, 1)  # Set opacity of a single segment

                segmentId = segmentationNode.GetSegmentation().GetSegmentIdBySegmentName(key)
                segmentArray = slicer.util.arrayFromSegmentBinaryLabelmap(segmentationNode, key, imageNode)

                if key == "OTHER":
                    segmentArray[slicer.util.arrayFromVolume(imageNode) >= lowerThresholdValue] = 1
                    segmentArray[labelArray > labelDescription[key]["value"]] = 0

                segmentArray[labelArray == value] = 1  # create segment by simple thresholding of an image

                slicer.util.updateSegmentBinaryLabelmapFromArray(segmentArray, segmentationNode, segmentId, imageNode)

    def getImageList(self, datasetSettings):
        self.checkIfDependenciesAreInstalled()
        pandas = importlib.import_module('pandas')

        imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer, labelFileSuffix = datasetSettings

        filterActive = False
        allFiles = []
        if self.settings["datasets"][dataset]["observers"][observer]["includedImageFilter"] != "":
            filterActive = True
            csv = pandas.read_csv(self.settings["datasets"][dataset]["observers"][observer]["includedImageFilter"])
            allFiles = csv['Filename'].tolist()

        files = {"allImages": [], "unlabeledImages": []}
        references = []

        for referenceFileName in sorted(filter(lambda x: os.path.isfile(os.path.join(labelsPath, x)),os.listdir(labelsPath))):
            name, extension = os.path.splitext(referenceFileName)
            if extension == ".nrrd" and os.path.isfile(os.path.join(imagesPath, name.split(labelFileSuffix)[0] + ".mhd")):
               references.append(name.split(labelFileSuffix)[0])

        for imageFileName in sorted(filter(lambda x: os.path.isfile(os.path.join(imagesPath, x)),os.listdir(imagesPath))):
            name, extension = os.path.splitext(imageFileName)
            if extension == ".mhd":
                if filterActive:
                    fileName = name + extension

                    if fileName in allFiles:
                        files["allImages"].append(name)

                        try:
                            references.index(name)
                        except ValueError:
                            files["unlabeledImages"].append(name)

                else:
                    files["allImages"].append(name)

                    try:
                        references.index(name)
                    except ValueError:
                        files["unlabeledImages"].append(name)

        return files

    def onSaveComparisonLabel(self):
        #check if label is complete!
        imageNode = slicer.util.getNode(self.currentLoadedNode.GetName())
        segmentationNode = slicer.util.getNode("Comparison")
        segmentId = segmentationNode.GetSegmentation().GetSegmentIdBySegmentName("MISMATCH")

        segmentArray = slicer.util.arrayFromSegmentBinaryLabelmap(segmentationNode, segmentId, imageNode)

        if len(numpy.unique(segmentArray)) == 1:
            dataset = self.settings["savedDatasetAndObserverSelection"]["dataset"]
            observer = self.settings["savedDatasetAndObserverSelection"]["observer"]
            savePath = self.settings["datasets"][dataset]["observers"][observer]["labelsPath"]
            filename = self.currentLoadedNode.GetName().split(".mhd")[0] + self.settings["datasets"][dataset]["observers"][observer]["labelFileSuffix"] +".nrrd"

            segmentationNode = slicer.util.getNode("Comparison")

            labelmapVolumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
            labelmapVolumeNode.SetName("temporaryExportLabel")
            referenceVolumeNode = None  # it could be set to the master volume
            segmentIds = segmentationNode.GetSegmentation().GetSegmentIDs()  # export all segments
            slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(segmentationNode,
                                                                              segmentIds,
                                                                              labelmapVolumeNode, referenceVolumeNode,
                                                                              slicer.vtkSegmentation.EXTENT_REFERENCE_GEOMETRY,
                                                                              self.colorTableNode)

            volumeNode = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLLabelMapVolumeNode')
            slicer.util.exportNode(volumeNode, os.path.join(savePath, filename))
            slicer.mrmlScene.RemoveNode(labelmapVolumeNode)
            self.progressBarUpdate()

            print(f"Saved {filename}")

        else:
            print("Not all mismatched regions have been corrected! Check your segmentation for remaining red areas and try again!")

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

    def runThreshold(self, inputVolumeName, labelName, segmentationMode, settings, labelsPath, colorTableNode, differentLabelType):
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
                    slicer.util.updateSegmentBinaryLabelmapFromArray(segmentArray, segmentationNode, segmentId, imageNode)

            # converts label if other label is available
            if differentLabelType is not None and not os.path.isfile(os.path.join(labelsPath, labelName + '.nrrd')):
                if os.path.isfile(os.path.join(differentLabelType["labelPath"], labelName + '.nrrd')):
                    label = sitk.ReadImage(os.path.join(differentLabelType["labelPath"], labelName + '.nrrd'))
                    labelArray = sitk.GetArrayFromImage(label)

                    if differentLabelType["labelSegmentationMode"] == "ArteryLevelWithLM" and segmentationMode == "SegmentLevel":
                        self.convertLabelType(labelArray, 5, 'LM_BRANCH', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, 2, 'LAD_PROXIMAL', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, 4, "RCA_PROXIMAL", imageNode, segmentationNode)
                        self.convertLabelType(labelArray, 3, "LCX_PROXIMAL", imageNode, segmentationNode)

    def convertLabelType(self, oldLabelArray, oldArrayId, segmentIdName, imageNode, segmentationNode):
        segmentId = segmentationNode.GetSegmentation().GetSegmentIdBySegmentName(segmentIdName)
        otherId = segmentationNode.GetSegmentation().GetSegmentIdBySegmentName('OTHER')

        segmentArray = slicer.util.arrayFromSegmentBinaryLabelmap(segmentationNode, segmentId, imageNode)
        segmentArray[oldLabelArray == oldArrayId] = 1

        otherArray = slicer.util.arrayFromSegmentBinaryLabelmap(segmentationNode, otherId, imageNode)
        otherArray[oldLabelArray == oldArrayId] = 0

        slicer.util.updateSegmentBinaryLabelmapFromArray(segmentArray, segmentationNode, segmentId, imageNode)
        slicer.util.updateSegmentBinaryLabelmapFromArray(otherArray, segmentationNode, otherId, imageNode)

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

        with concurrent.futures.ThreadPoolExecutor() as executor:
            [executor.submit(self.processImages, filename, sliceStepDataframe)
             for filename in sorted(filter(lambda x: os.path.isfile(os.path.join(self.filepaths["referenceFolder"], x)),
                                           os.listdir(self.filepaths["referenceFolder"])))]

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