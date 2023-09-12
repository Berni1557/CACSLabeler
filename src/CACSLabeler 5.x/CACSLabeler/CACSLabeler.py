import os
from pathlib import Path
import qt

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from PIL import ImageColor

import SimpleITK as sitk
import numpy
import json

import vtk
import random

import sys

from scipy.ndimage import label
from scipy import ndimage as ndi

import importlib

#Processing and exporting calcium scores
from CACSLabelerLib.CalciumScore import CalciumScore
from CACSLabelerLib.SettingsHandler import SettingsHandler

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

        #clears screen on reload
        slicer.mrmlScene.Clear(0)

        self.reload()

    def reload(self):
        # on load!
        import CACSLabelerLib.SettingsHandler
        import CACSLabelerLib.CalciumScore

        importlib.reload(CACSLabelerLib.CalciumScore)
        importlib.reload(CACSLabelerLib.SettingsHandler)

        from CACSLabelerLib.CalciumScore import CalciumScore
        from CACSLabelerLib.SettingsHandler import SettingsHandler

        # Now you can use the reloaded class
        self.settingsHandler = SettingsHandler()

    def initializeUI(self):
        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/CACSLabeler.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        self.defaultUI()
        self.connectUIEvents()

    def connectUIEvents(self):
        self.ui.exportFromReferenceFolder.connect('clicked(bool)', self.onExportFromReferenceFolderButtonClicked)
        self.ui.exportFromJsonFile.connect('clicked(bool)', self.onExportFromJSONFileButtonClicked)
        self.ui.loadVolumeButton.connect('clicked(bool)', self.onLoadButton)
        self.ui.thresholdVolumeButton.connect('clicked(bool)', self.onThresholdVolume)
        self.ui.selectNextUnlabeledImageButton.connect('clicked(bool)', self.onSelectNextUnlabeledImage)
        self.ui.saveButton.connect('clicked(bool)', self.onSaveButton)
        self.ui.compareLabelsButton.connect('clicked(bool)', self.onCompareLabelsButton)

    def createMessagePopup(self, message):
        slicer.util.infoDisplay(message)

    def defaultUI(self):
        pass
        #self.ui.settingsCollapsibleButton.setHidden(False)
        #self.ui.tabWidget.setHidden(True)
        #self.ui.exportCollapsibleButton.setHidden(True)

        # self.ui.inputCollapsibleButton.setHidden(hide)
        # self.ui.exportCollapsibleButton.setHidden(hide)
        # self.ui.compareCollapsibleButton.setHidden(hide)
        #
        # self.ui.datasetComboBox.setHidden(hide)
        # self.ui.datasetLabel.setHidden(hide)
        # self.ui.observerComboBox.setHidden(hide)
        # self.ui.observerLabel.setHidden(hide)

    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        #used to add dependencies that are not shipped with 3dSlicer!
        self.checkIfDependenciesAreInstalled()

        self.initializeUI()

        #loading and processing settings json
        #All interaction with the settings is handled through the handler
        self.settingsHandler = SettingsHandler()

        if self.settingsHandler.getAvailableDatasetsAndObservers():
            self.changeSelectedDatasetAndObserver()
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
            self.createMessagePopup("Settings file error!\nChange settings in JSON file!")

        self.colorTableNode = None
        self.createColorTable()

        self.createEditorWidget(self.ui.embeddedSegmentEditorWidget, "createEditor")
        self.createEditorWidget(self.ui.compareObserversEditor, "compareEditor")

        self.ui.comparisonLine1.setHidden(True)
        self.ui.comparisonLine2.setHidden(True)
        self.ui.comparisonSaveButton.setHidden(True)

        self.ui.saveButton.setHidden(True)

        self.availableExportTypes = list(self.settingsHandler.getContentByKeys(["exportedLabels"]).keys()) #TODO!

        self.ui.exportTypeComboBox.clear()
        self.ui.exportTypeComboBox.addItems(self.availableExportTypes)
        self.ui.exportTypeComboBox.setCurrentText(self.settingsHandler.getContentByKeys(["exportType"]))

        #Init Comparison
        self.comparisonObserver1 = None
        self.comparisonObserver2 = None

        self.ui.comparisonSelectNextImageButton.connect('clicked(bool)', self.onComparisonSelectNextImage)
        self.ui.comparisonSelectNextImageToLoadButton.connect('clicked(bool)', self.onComparisonSelectImageToLoad)

        self.createCompareObserversBox()

        self.ui.CompareObserver1Selector.connect("currentIndexChanged(int)", self.onComparisonChangeFirstObserver)
        self.ui.CompareObserver2Selector.connect("currentIndexChanged(int)", self.onComparisonChangeSecondObserver)

        self.ui.comparisonSaveButton.connect('clicked(bool)', self.onSaveComparisonLabel)
        self.ui.tabWidget.currentChanged.connect(self.onTabChange)
        self.ui.tabWidget.setCurrentIndex(self.settingsHandler.getContentByKeys(["tabOpen"]))

    def onTabChange(self, index):
        self.settingsHandler.changeContentByKey(["tabOpen"], index)

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
        editorObject.setEffectColumnCount(1)
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

            self.settingsHandler.changeContentByKey(["exportType"], self.availableExportTypes[exportTypeId])

            self.exportTypeComboBoxEventBlocked = False

    def onChangeDataset(self, datasetListId=None):
        self.clearCurrentViewedNode(True)

        #protect from triggering during change
        if not self.datasetComboBoxEventBlocked:
            self.datasetComboBoxEventBlocked = True
            self.observerComboBoxEventBlocked = True
            self.compareObserverComboBoxEventBlocked = True

            newDataset = list(self.settingsHandler.getAvailableDatasetsAndObservers().keys())[datasetListId]
            self.changeSelectedDatasetAndObserver(newDataset)
            self.updateDatasetAndObserverDropdownSelection()
            self.initializeMainUI()
            self.createCompareObserversBox()

            self.datasetComboBoxEventBlocked = False
            self.observerComboBoxEventBlocked = False
            self.compareObserverComboBoxEventBlocked = False

    def onChangeObserver(self, item=None):
        self.clearCurrentViewedNode(True)

        if not self.observerComboBoxEventBlocked:
            self.datasetComboBoxEventBlocked = True
            self.observerComboBoxEventBlocked = True
            self.compareObserverComboBoxEventBlocked = True

            self.changeSelectedDatasetAndObserver(self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"]),
                                                  self.settingsHandler.getAvailableDatasetsAndObservers()[self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])][item])
            self.initializeMainUI()

            self.createObserverAvailableList()
            self.createCompareObserversBox()

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

        dataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        imagesPath = self.settingsHandler.getContentByKeys(["datasets", dataset, "imagesPath"])
        filename = imageList["unlabeledImages"][0] + ".mhd"

        if os.path.isfile(os.path.join(imagesPath, filename)):
            self.loadVolumeToSlice(filename, imagesPath)

    def onLoadButton(self):
        dataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        imagesPath = self.settingsHandler.getContentByKeys(["datasets", dataset, "imagesPath"])

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

        self.runThreshold(inputVolumeName, labelName, segmentationMode, labelsPath, self.colorTableNode, differentLabelType)
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
        if "differentSegmentationModeLabels" in self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer]):
            if "labelsPath" in self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer, "differentSegmentationModeLabels"])\
                    and "segmentationMode" in self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer, "differentSegmentationModeLabels"]):
                differentLabelType = {
                    "labelPath": self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer, "differentSegmentationModeLabels", "labelsPath"]),
                    "labelSegmentationMode": self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer, "differentSegmentationModeLabels", "segmentationMode"]),
                    "labelFileSuffix": self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer, "differentSegmentationModeLabels", "labelFileSuffix"])
                }

        return differentLabelType

    def initializeMainUI(self):
        self.clearCurrentViewedNode()
        self.progressBarUpdate()

        observer = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "observer"])
        dataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        self.ui.currentObserverName.text = observer
        self.ui.currentObserverSegmentationType.text = self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer, "segmentationMode"])

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

    def changeSelectedDatasetAndObserver(self, dataset = None, observer = None):
        if dataset is None and observer is None:
            if (self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection"])) \
                and ("dataset" in self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection"])) \
                and ("observer" in self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection"])):

                if self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"]) in self.settingsHandler.getAvailableDatasetsAndObservers():
                    try:
                        self.settingsHandler.getAvailableDatasetsAndObservers()[self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])].index(self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "observer"]))
                        return
                    except ValueError:
                        pass
        else:
            if dataset in self.settingsHandler.getAvailableDatasetsAndObservers():
                self.settingsHandler.changeContentByKey(["savedDatasetAndObserverSelection", "dataset"], dataset)
                try:
                    self.settingsHandler.getAvailableDatasetsAndObservers()[dataset].index(observer)
                    self.settingsHandler.changeContentByKey(["savedDatasetAndObserverSelection","observer"], observer)
                    return
                except ValueError:
                    #if no observer selected select first available
                    self.settingsHandler.changeContentByKey(["savedDatasetAndObserverSelection", "observer"], self.settingsHandler.getAvailableDatasetsAndObservers()[dataset][0])
                    return

        # if not already selected in settings selecting first element
        firstDataset = list(self.settingsHandler.getAvailableDatasetsAndObservers().keys())[0]
        firstObserver = self.settingsHandler.getAvailableDatasetsAndObservers()[firstDataset][0]

        self.settingsHandler.changeContentByKey(["savedDatasetAndObserverSelection", "dataset"], firstDataset)
        self.settingsHandler.changeContentByKey(["savedDatasetAndObserverSelection", "observer"], firstObserver)

    def selectedDatasetAndObserverSetting(self):
        dataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        observer = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "observer"])

        imagesPath = self.settingsHandler.getContentByKeys(["datasets", dataset, "imagesPath"])
        labelsPath = self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer, "labelsPath"])
        segmentationMode = self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer, "segmentationMode"])
        sliceStepFile = self.settingsHandler.getContentByKeys(["datasets", dataset, "sliceStepFile"])
        exportFolder = self.settingsHandler.getContentByKeys(["exportFolder"])
        labelFileSuffix = self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer, "labelFileSuffix"])

        return imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer, labelFileSuffix

    def updateDatasetAndObserverDropdownSelection(self):
        self.ui.datasetComboBox.clear()
        self.ui.datasetComboBox.addItems(list(self.settingsHandler.getAvailableDatasetsAndObservers().keys()))

        self.ui.datasetComboBox.setCurrentText(self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"]))

        self.ui.observerComboBox.clear()
        self.ui.observerComboBox.addItems(self.settingsHandler.getAvailableDatasetsAndObservers()[self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])])
        self.ui.observerComboBox.setCurrentText(self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "observer"]))

        self.createObserverAvailableList()

    def onExportFromReferenceFolderButtonClicked(self):
        exporter = CalciumScore(self.selectedDatasetAndObserverSetting(), self.settings)
        exporter.exportFromReferenceFolder()

    def onExportFromJSONFileButtonClicked(self):
        exporter = CalciumScore(self.selectedDatasetAndObserverSetting(), self.settings)
        exporter.exportFromJSONFile()

    def createColorTable(self):
        imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer, labelFileSuffix = self.selectedDatasetAndObserverSetting()
        segmentNamesToLabels = []

        for key in self.settingsHandler.getContentByKeys(["labels", segmentationMode]):

            value = self.settingsHandler.getContentByKeys(["labels", segmentationMode, key, "value"])
            color = self.settingsHandler.getContentByKeys(["labels", segmentationMode, key, "color"])

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
        currentDataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        segmentationType = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", observer, "segmentationMode"])

        self.ui.secondObserverSegmentationType.text = segmentationType

        self.checkForComparableLabelSegmentationTypes(self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "observer"]), observer)

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
        currentDataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        currentObserver = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "observer"])
        currentSegmentationType = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", currentObserver, "segmentationMode"])

        comparableObservers = []

        for observer in self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers"]):
            if observer != currentObserver:
                segmentationModeOfObserver = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", observer, "segmentationMode"])

                if (currentSegmentationType == "SegmentLevel") and (segmentationModeOfObserver == "SegmentLevel" or segmentationModeOfObserver == "SegmentLevelDLNExport"):
                    comparableObservers.append(observer)

                if (currentSegmentationType == "SegmentLevelDLNExport") and (segmentationModeOfObserver == "SegmentLevel" or segmentationModeOfObserver == "SegmentLevelDLNExport"):
                    comparableObservers.append(observer)

        return comparableObservers

    def checkIfLabelCanBeCompared(self, filename):
        file = filename.split(".mhd")[0]
        currentDataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        labelsPath = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", self.selectedComparableObserver, "labelsPath"])
        labelFileSuffix = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", self.selectedComparableObserver, "labelFileSuffix"])

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
        currentDataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        firstSegmentationType = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", firstObserver, "segmentationMode"])
        secondSegmentationType = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", secondObserver, "segmentationMode"])

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
        currentDataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        currentObserver = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "observer"])

        currentObserverLabelpath = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", currentObserver, "labelsPath"])
        currentObserverlabelFileSuffix = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", currentObserver, "labelFileSuffix"])

        compareObserverLabelpath = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", self.selectedComparableObserver, "labelsPath"])
        compareObserverlabelFileSuffix = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", self.selectedComparableObserver, "labelFileSuffix"])

        currentObserverFilePath = os.path.join(currentObserverLabelpath, (file + currentObserverlabelFileSuffix + ".nrrd"))
        compareObserverFilePath = os.path.join(compareObserverLabelpath, (file + compareObserverlabelFileSuffix + ".nrrd"))

        # import labels
        labelCurrentObserver = sitk.GetArrayFromImage(sitk.ReadImage(currentObserverFilePath))
        labelCompareObserver = sitk.GetArrayFromImage(sitk.ReadImage(compareObserverFilePath))

        #Compare labels
        currentObserverSegmentationType = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", currentObserver, "segmentationMode"])
        compareObserverSegmentationType = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", self.selectedComparableObserver, "segmentationMode"])


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
        return self.settingsHandler.getContentByKeys(["labels", segmentationType, name, "value"])

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
        currentSelectedDataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        currentSelectedObserver = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "observer"])

        allObserversList = list(self.settingsHandler.getContentByKeys(["datasets", currentSelectedDataset, "observers"]).keys())
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
        currentSelectedDataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        availableObservers = list(self.settingsHandler.getContentByKeys(["datasets", currentSelectedDataset, "observers"]).keys())
        availableObservers.remove(self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "observer"]))

        self.comparisonObserver1 = availableObservers[id]

        secondObserverList = availableObservers
        secondObserverList.remove(self.comparisonObserver1)

        self.ui.CompareObserver2Selector.clear()
        self.ui.CompareObserver2Selector.addItems(secondObserverList)
        self.ui.CompareObserver2Selector.setCurrentText(secondObserverList[0])
        self.comparisonObserver2 = secondObserverList[0]

    def onComparisonChangeSecondObserver(self, id=None):
        currentSelectedDataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        availableObservers = list(self.settingsHandler.getContentByKeys(["datasets", currentSelectedDataset, "observers"]).keys())
        availableObservers.remove(self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "observer"]))
        availableObservers.remove( self.comparisonObserver1)

        self.comparisonObserver2 = availableObservers[id]

    def onComparisonSelectNextImage(self):
        slicer.mrmlScene.Clear()
        imageList = self.getImageList(self.selectedDatasetAndObserverSetting())
        self.loadImageToCompare(imageList["unlabeledImages"][0] + ".mhd")

    def onComparisonSelectImageToLoad(self):
        dataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        imagesPath = self.settingsHandler.getContentByKeys(["datasets", dataset, "imagesPath"])

        # opens file selection window
        filepath = qt.QFileDialog.getOpenFileName(self.parent, 'Open files', imagesPath, "Files(*.mhd)")
        filename = filepath.split("/")[-1]

        self.loadImageToCompare(filename)

    def loadImageToCompare(self, filename):
        dataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        imagesPath = self.settingsHandler.getContentByKeys(["datasets", dataset, "imagesPath"])

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
        observer1Segmentation = slicer.util.getNode("Observer1")
        observer2Segmentation = slicer.util.getNode("Observer2")
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
        dataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        imageNodeName = self.currentLoadedNode.GetName()
        patientFileName = imageNodeName.split(".mhd")[0]

        observer1LabelPath = os.path.join(
            self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", self.comparisonObserver1, "labelsPath"]),
            patientFileName + self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", self.comparisonObserver1, "labelFileSuffix"]) + ".nrrd")

        observer2LabelPath = os.path.join(
            self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", self.comparisonObserver2, "labelsPath"]),
            patientFileName + self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", self.comparisonObserver2, "labelFileSuffix"]) + ".nrrd")

        # generate comparison mask
        # import labels
        observer1SegmentationArray = sitk.GetArrayFromImage(sitk.ReadImage(observer1LabelPath))
        observer2SegmentationArray = sitk.GetArrayFromImage(sitk.ReadImage(observer2LabelPath))

        # Compare labels
        observer1SegmentationType = self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", self.comparisonObserver1, "segmentationMode"])
        observer2SegmentationType = self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", self.comparisonObserver2, "segmentationMode"])

        if observer1SegmentationType == observer2SegmentationType:
            if observer1SegmentationType == "SegmentLevel":
                labelDescription = self.settingsHandler.getContentByKeys(["labels", "SegmentLevel"]).copy()

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

                self.loadLabelFromArray(observer1SegmentationArray, "Observer1", labelDescription)
                self.loadLabelFromArray(observer2SegmentationArray, "Observer2", labelDescription)

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
                segmentArray[comparisonSegmentation > self.settingsHandler.getContentByKeys(["labels", "SegmentLevel", key, "value"])] = 0

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
        if self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer, "includedImageFilter"]) != "":
            filterActive = True
            csv = pandas.read_csv(self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer, "includedImageFilter"]))
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
            dataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
            observer = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "observer"])
            savePath = self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer, "labelsPath"])
            filename = self.currentLoadedNode.GetName().split(".mhd")[0] + self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer, "labelFileSuffix"]) +".nrrd"

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


            print(f"Saved {filename}")


            self.progressBarUpdate()
            self.clearCurrentViewedNode(False)
            self.ui.compareObserversEditor.setHidden(True)
            self.ui.comparisonLine1.setHidden(True)
            self.ui.comparisonLine2.setHidden(True)
            self.ui.comparisonSaveButton.setHidden(True)

        else:
            print("Not all mismatched regions have been corrected! Check your segmentation for remaining red areas and try again!")
            slicer.util.infoDisplay("Not all mismatched regions have been corrected!\nCheck your segmentation for remaining red areas and try again!")

    def runThreshold(self, inputVolumeName, labelName, segmentationMode, labelsPath, colorTableNode,
                     differentLabelType):
        node = slicer.util.getFirstNodeByName(labelName)
        if node is None:
            print('----- Thresholding -----')
            print('Threshold value:', lowerThresholdValue)

            imageNode = slicer.util.getNode(inputVolumeName)

            segmentationNode = None
            segmentation = None

            # file exists
            if os.path.isfile(os.path.join(labelsPath, labelName + '.nrrd')):
                loadedVolumeNode = slicer.util.loadVolume(os.path.join(labelsPath, labelName + '.nrrd'),
                                                          {"labelmap": True})
                segmentationNode = slicer.mrmlScene.AddNewNodeByClass(
                    "vtkMRMLSegmentationNode")  # import into new segmentation node
                segmentationNode.SetName(labelName)
                segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(imageNode)
                loadedVolumeNode.GetDisplayNode().SetAndObserveColorNodeID(
                    colorTableNode.GetID())  # just in case the custom color table has not been already associated with the labelmap volume
                slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(loadedVolumeNode,
                                                                                      segmentationNode)

                slicer.mrmlScene.RemoveNode(loadedVolumeNode)
            else:
                segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
                segmentationNode.SetName(labelName)
                segmentationNode.CreateDefaultDisplayNodes()  # only needed for display
                segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(imageNode)

            segmentation = segmentationNode.GetSegmentation()
            displayNode = segmentationNode.GetDisplayNode()

            for key in self.settingsHandler.getContentByKeys(["labels", segmentationMode]):
                color = self.settingsHandler.getContentByKeys(["labels", segmentationMode, key, "color"])

                if segmentation.GetSegment(key) is None:
                    segmentation.AddEmptySegment(key)

                segment = segmentation.GetSegment(key)

                r, g, b = ImageColor.getcolor(color, "RGB")
                segment.SetColor(r / 255, g / 255, b / 255)  # red
                displayNode.SetSegmentOpacity3D(key, 1)  # Set opacity of a single segment

                if key == "OTHER" and not os.path.isfile(os.path.join(labelsPath, labelName + '.nrrd')):
                    segmentId = segmentationNode.GetSegmentation().GetSegmentIdBySegmentName(key)
                    segmentArray = slicer.util.arrayFromSegmentBinaryLabelmap(segmentationNode, key, imageNode)
                    segmentArray[slicer.util.arrayFromVolume(
                        imageNode) >= lowerThresholdValue] = 1  # create segment by simple thresholding of an image
                    slicer.util.updateSegmentBinaryLabelmapFromArray(segmentArray, segmentationNode, segmentId,
                                                                     imageNode)

            # converts label if other label is available
            if differentLabelType is not None and not os.path.isfile(os.path.join(labelsPath, labelName + '.nrrd')):
                if os.path.isfile(os.path.join(differentLabelType["labelPath"], labelName + '.nrrd')):
                    label = sitk.ReadImage(os.path.join(differentLabelType["labelPath"], labelName + '.nrrd'))
                    labelArray = sitk.GetArrayFromImage(label)

                    if differentLabelType[
                        "labelSegmentationMode"] == "ArteryLevelWithLM" and segmentationMode == "SegmentLevel":
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