import os
import qt

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from PIL import ImageColor

import SimpleITK as sitk
import numpy
import random

import importlib

#Processing and exporting calcium scores
from CACSLabelerLib.CalciumScore import CalciumScore
from CACSLabelerLib.SettingsHandler import SettingsHandler
from CACSLabelerLib.SegmentationProcessor import SegmentationProcessor

#
# CACSLabeler
#

lowerThresholdValue = 130
imageFileExtension = ".mhd"
segmentationFileExtension = ".nrrd"

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
        import CACSLabelerLib.SegmentationProcessor

        importlib.reload(CACSLabelerLib.CalciumScore)
        importlib.reload(CACSLabelerLib.SettingsHandler)
        importlib.reload(CACSLabelerLib.SegmentationProcessor)

        from CACSLabelerLib.CalciumScore import CalciumScore
        from CACSLabelerLib.SettingsHandler import SettingsHandler
        from CACSLabelerLib.SegmentationProcessor import SegmentationProcessor

        # Now you can use the reloaded class
        self.settingsHandler = SettingsHandler()

    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        self.loadedVolumeNode = None #holds loaded volumes
        self.loadedSegmentationNode = None #holds loaded segmentation of above Volume
        self.comparisonObserver1 = None #holds segmentation of first observer when comparing
        self.comparisonObserver2 = None #holds segmentation of second observer when comparing
        self.selectedComparableObserver = None

        #used to add dependencies that are not shipped with 3dSlicer!
        self.checkIfDependenciesAreInstalled()

        # loading and processing settings json
        # All interaction with the settings is handled through the handler
        self.settingsHandler = SettingsHandler()

        self.colorTableNode = None
        self.createUI()
        self.createColorTable()

        self.customThreshold = False

    def checkIfLoadFilterExists(self):
        self.ui.progressBarLabelFilter.setHidden(True)
        self.ui.counterProgressFilter.setHidden(True)
        self.ui.progressBarFilter.setHidden(True)

        currentDataset, currentObserver = self.settingsHandler.getCurrentDatasetAndObserver()
        currentSettings = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", currentObserver])

        if 'loadFilter' in currentSettings:
            if os.path.isfile(currentSettings["loadFilter"]):
                self.ui.loadFilteredDataset.enabled = True

                self.ui.progressBarLabelFilter.setHidden(False)
                self.ui.counterProgressFilter.setHidden(False)
                self.ui.progressBarFilter.setHidden(False)

                return currentSettings["loadFilter"]
            else:
                self.ui.loadFilteredDataset.enabled = False
                return None
        else:
            self.ui.loadFilteredDataset.enabled = False
            return None

    def changeProgressFilter(self):
        filter = self.checkIfLoadFilterExists()
        pandas = importlib.import_module('pandas')
        csv = pandas.read_csv(filter)

        max = len(csv)
        currentValue = (csv['Done'] == 1).sum()

        self.ui.progressBarFilter.minimum = 0
        self.ui.progressBarFilter.maximum = max
        self.ui.progressBarFilter.value = currentValue

        self.ui.counterProgressFilter.text = str(currentValue) + " / " + str(max)

    def onLoadFilteredDataset(self):
        filter = self.checkIfLoadFilterExists()
        currentDataset, currentObserver = self.settingsHandler.getCurrentDatasetAndObserver()

        pandas = importlib.import_module('pandas')
        csv = pandas.read_csv(filter)

        # Find the index of the first row where 'Done' column equals 0
        index = csv.index[csv['Done'] == 0].tolist()[0]

        # Select the value of the 'Name' column in the first row where 'Done' equals 0
        filename = csv.loc[index, 'Filename']

        filename = filename.split("-label-lesion.nrrd")[0] + ".mhd"

        imagesPath = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "imagesPath"])

        self.loadVolumeToSlice(filename, imagesPath)
        self.onThresholdVolume()
        self.customFunctionLoader()

    def customFunctionLoader(self):
        volumeNode = slicer.util.getNode(self.loadedVolumeNode.GetName())

        currentDataset, currentObserver = self.settingsHandler.getCurrentDatasetAndObserver()
        referencePath = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", currentObserver, "labelsPath"])

        filename = self.loadedVolumeNode.GetName().split(".mhd")[0] + self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", currentObserver, "labelFileSuffix"]) + ".nrrd"

        referenceITK = sitk.ReadImage(os.path.join(referencePath, filename))
        referenceArray = sitk.GetArrayViewFromImage(referenceITK)

        # Get the segmentation node (assuming it's the only one loaded)
        segmentationNode = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLSegmentationNode')

        voxels = slicer.util.arrayFromVolume(volumeNode)

        # Create a new segment
        segment = slicer.vtkSegment()
        segment.SetName('TemporarySegment')
        segment.SetColor(1.0, 0.0, 0.0)  # RGB color

        # Add the segment to the segmentation node
        segmentation = segmentationNode.GetSegmentation()
        segmentation.AddSegment(segment)

        # Request an update of the display
        segmentationNode.Modified()

        segmentId = segmentationNode.GetSegmentation().GetSegmentIdBySegmentName('TemporarySegment')

        segmentArray = slicer.util.arrayFromSegmentBinaryLabelmap(segmentationNode, segmentId, volumeNode)
        segmentArray[voxels >= 130] = 1  # create segment by simple thresholding of an image
        segmentArray[referenceArray > 0] = 0  # create segment by simple thresholding of an image

        slicer.util.updateSegmentBinaryLabelmapFromArray(segmentArray, segmentationNode, segmentId, volumeNode)

        self.customThreshold = True

    def onTabChange(self, index):
        self.settingsHandler.changeContentByKey(["tabOpen"], index)

    def checkIfDependenciesAreInstalled(self):
        dependencies = ["pandas"]

        for dependency in dependencies:
            if importlib.util.find_spec(dependency) is None:
                if slicer.util.confirmOkCancelDisplay("This module requires '" + dependency + "' Python package. Click OK to install it now."):
                    slicer.util.pip_install(dependency)

    def checkIfSelectedDatasetAndObserverAreAvailable(self):
        currentDataset, currentObserver = self.settingsHandler.getCurrentDatasetAndObserver()
        available = self.settingsHandler.getAvailableDatasetsAndObservers()

        if currentDataset in available.keys():
            if currentObserver in available[currentDataset]:
                return

        #else change Dataset and Observer to default!
        self.changeSelectedDatasetAndObserver()

    def createUI(self):
        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/CACSLabeler.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        self.connectUIEvents()

        #checking if current observer and dataset are available!
        self.checkIfSelectedDatasetAndObserverAreAvailable()

        #used to prevent onChange
        self.datasetComboBoxEventBlocked = False
        self.observerComboBoxEventBlocked = False
        self.exportTypeComboBoxEventBlocked = False
        self.compareObserverComboBoxEventBlocked = False

        self.createEditorWidget(self.ui.embeddedSegmentEditorWidget, "createEditor")
        self.createEditorWidget(self.ui.compareObserversEditor, "compareEditor")

        self.ui.exportTypeComboBox.clear()
        self.ui.exportTypeComboBox.addItems(list(self.settingsHandler.getContentByKeys(["exportedLabels"]).keys()))
        self.ui.exportTypeComboBox.setCurrentText(self.settingsHandler.getContentByKeys(["exportType"]))

        self.createCompareObserversBox()
        self.ui.tabWidget.setCurrentIndex(self.settingsHandler.getContentByKeys(["tabOpen"]))

        if self.settingsHandler.getAvailableDatasetsAndObservers():
            self.datasetComboBoxEventBlocked = True
            self.observerComboBoxEventBlocked = True
            self.compareObserverComboBoxEventBlocked = True

            self.changeSelectedDatasetAndObserver()
            self.updateDatasetAndObserverDropdownSelection()

            self.datasetComboBoxEventBlocked = False
            self.observerComboBoxEventBlocked = False
            self.compareObserverComboBoxEventBlocked = False

            self.initializeMainUI()
        else:
            self.createMessagePopup("Settings file error!\nChange settings in JSON file!")

    def connectUIEvents(self):
        self.ui.exportFromReferenceFolder.connect('clicked(bool)', self.onExportFromReferenceFolderButtonClicked)
        self.ui.exportFromJsonFile.connect('clicked(bool)', self.onExportFromJSONFileButtonClicked)
        self.ui.loadVolumeButton.connect('clicked(bool)', self.onLoadButton)
        self.ui.thresholdVolumeButton.connect('clicked(bool)', self.onThresholdVolume)
        self.ui.selectNextUnlabeledImageButton.connect('clicked(bool)', self.onSelectNextUnlabeledImage)
        self.ui.saveButton.connect('clicked(bool)', self.onSaveButton)
        self.ui.compareLabelsButton.connect('clicked(bool)', self.onCompareLabelsButton)

        self.ui.datasetComboBox.connect("currentIndexChanged(int)", self.onChangeDataset)
        self.ui.observerComboBox.connect("currentIndexChanged(int)", self.onChangeObserver)
        self.ui.exportTypeComboBox.connect("currentIndexChanged(int)", self.onChangeExportType)
        self.ui.compareObserverComboBox.connect("currentIndexChanged(int)", self.onCompareObserverComboBoxChange)
        self.ui.comparableSegmentationTypes.connect("currentIndexChanged(int)", self.onComparisonSegmentationTypeChange)

        #tab Widget
        self.ui.comparisonSelectNextImageButton.connect('clicked(bool)', self.onComparisonSelectNextImage)
        self.ui.comparisonSelectNextImageToLoadButton.connect('clicked(bool)', self.onComparisonSelectImageToLoad)

        self.ui.CompareObserver1Selector.connect("currentIndexChanged(int)", self.onComparisonChangeFirstObserver)
        self.ui.CompareObserver2Selector.connect("currentIndexChanged(int)", self.onComparisonChangeSecondObserver)

        self.ui.comparisonSaveButton.connect('clicked(bool)', self.onSaveComparisonLabel)
        self.ui.tabWidget.currentChanged.connect(self.onTabChange)

        self.ui.loadFilteredDataset.connect('clicked(bool)', self.onLoadFilteredDataset)

    def createMessagePopup(self, message):
        slicer.util.infoDisplay(message)

    def createEditorWidget(self, editorObject, editorName):
        editorObject.setMRMLScene(slicer.mrmlScene)
        editorObject.setSegmentationNodeSelectorVisible(False)
        editorObject.setSourceVolumeNodeSelectorVisible(False)
        editorObject.setEffectNameOrder(['Paint', 'Erase'])
        editorObject.setEffectColumnCount(1)
        editorObject.unorderedEffectsVisible = False
        editorObject.setMRMLSegmentEditorNode(self.getSegmentEditorNode(editorName))
        editorObject.setSwitchToSegmentationsButtonVisible(False)

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

            self.settingsHandler.changeContentByKey(["exportType"], list(self.settingsHandler.getContentByKeys(["exportedLabels"]).keys())[exportTypeId])

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

        if self.checkIfLoadFilterExists() != None:
            self.changeProgressFilter()

    def onChangeObserver(self, item=None):
        self.clearCurrentViewedNode(True)

        if not self.observerComboBoxEventBlocked:
            self.datasetComboBoxEventBlocked = True
            self.observerComboBoxEventBlocked = True
            self.compareObserverComboBoxEventBlocked = True

            observer = self.settingsHandler.getAvailableDatasetsAndObservers()[self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])][item]

            self.changeSelectedDatasetAndObserver(self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"]),
                                                  observer)

            self.initializeMainUI()

            self.createObserverAvailableList()
            self.createCompareObserversBox()

            self.datasetComboBoxEventBlocked = False
            self.observerComboBoxEventBlocked = False
            self.compareObserverComboBoxEventBlocked = False

        if self.checkIfLoadFilterExists() !=  None:
            self.changeProgressFilter()

    def loadVolumeToSlice(self, filename, imagesPath):
        self.setViewOneWindow()

        self.createColorTable()
        properties = {'Name': filename}

        self.loadedVolumeNode = slicer.util.loadVolume(os.path.join(imagesPath, filename), properties=properties)
        self.loadedVolumeNode.SetName(filename)

        slicer.util.setSliceViewerLayers(background=self.loadedVolumeNode)
        self.loadedVolumeNode.GetScalarVolumeDisplayNode().AutoWindowLevelOff()
        self.loadedVolumeNode.GetScalarVolumeDisplayNode().SetWindowLevel(800, 180)

        # Activate buttons
        self.ui.thresholdVolumeButton.enabled = True
        self.ui.selectedVolumeTextField.text = filename
        self.ui.selectedVolumeTextField.cursorPosition = 0
        self.ui.selectedVolumeLabel.enabled = True

        if len(self.compareObserverAvailableList()) > 0:
            self.ui.compareCollapsibleButton.enabled = True

        self.checkIfOtherLabelIsAvailable(filename)

        self.ui.compareLabelsButton.enabled = False
        self.checkIfLabelCanBeCompared(filename)

    def onSelectNextUnlabeledImage(self):
        self.clearCurrentViewedNode(True)
        imageList = self.getImageList(self.selectedDatasetAndObserverSetting())

        dataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        imagesPath = self.settingsHandler.getContentByKeys(["datasets", dataset, "imagesPath"])
        filename = imageList["unlabeledImages"][0] + imageFileExtension

        if os.path.isfile(os.path.join(imagesPath, filename)):
            self.loadVolumeToSlice(filename, imagesPath)

    def onLoadButton(self):
        dataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        imagesPath = self.settingsHandler.getContentByKeys(["datasets", dataset, "imagesPath"])

        self.clearCurrentViewedNode(True)

        # opens file selection window
        filepath = qt.QFileDialog.getOpenFileName(self.parent, 'Open files', imagesPath, ("Files(*"+imageFileExtension+")"))
        filename = filepath.split("/")[-1]

        self.loadVolumeToSlice(filename, imagesPath)

    def checkIfOtherLabelIsAvailable(self, filename):
        differentLabelType = self.differentLabelType()

        labelFileName = filename.split(imageFileExtension)[0] + differentLabelType["labelFileSuffix"] + segmentationFileExtension
        file = os.path.join(differentLabelType["labelPath"], labelFileName)

        if differentLabelType is not None and os.path.isfile(file):
            self.ui.availableLabelType.text = differentLabelType["labelSegmentationMode"]
            self.ui.availableLabelType.cursorPosition = 0
            self.ui.availableLabel.enabled = True

    def onThresholdVolume(self):
        imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer, labelFileSuffix = self.selectedDatasetAndObserverSetting()

        #removes file extension
        inputVolumeName = self.loadedVolumeNode.GetName()

        labelName = os.path.splitext(inputVolumeName)[0] + labelFileSuffix + segmentationFileExtension

        differentLabelType = self.differentLabelType()

        self.runThreshold(inputVolumeName, labelName, segmentationMode, labelsPath, self.colorTableNode, differentLabelType)
        self.loadedSegmentationNode = slicer.util.getNode(labelName)

        self.ui.embeddedSegmentEditorWidget.setSegmentationNode(slicer.util.getNode(labelName))
        self.getSegmentEditorNode("createEditor").SetMasterVolumeIntensityMask(True)
        self.getSegmentEditorNode("createEditor").SetSourceVolumeIntensityMaskRange(float(lowerThresholdValue), 100000.0)

        #disable threshold button
        self.ui.thresholdVolumeButton.enabled = False

    def differentLabelType(self):
        imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer, labelFileSuffix = self.selectedDatasetAndObserverSetting()
        differentLabelType = None

        # checks if other label exists with other segmentation Type!
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

        dataset, observer = self.settingsHandler.getCurrentDatasetAndObserver()

        self.ui.currentObserverName.text = observer
        self.ui.currentObserverSegmentationType.text = self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer, "segmentationMode"])

    def clearCurrentViewedNode(self, changeAlert = False):
        if changeAlert:
            if self.loadedVolumeNode != None or len(slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")):
                if not slicer.util.confirmOkCancelDisplay(
                        "This will close current scene.  Please make sure you have saved your current work.\n"
                        "Are you sure to continue?"
                ):
                    return

        slicer.mrmlScene.Clear(0)
        self.ui.thresholdVolumeButton.enabled = False
        self.ui.selectedVolumeTextField.text = ""
        self.ui.selectedVolumeTextField.cursorPosition = 0
        self.ui.selectedVolumeLabel.enabled = False

        self.ui.availableLabelType.text = ""
        self.ui.availableLabelType.cursorPosition = 0
        self.ui.availableLabel.enabled = False
        self.loadedVolumeNode = None

        self.ui.labelsToBeChanged.text = ""
        self.ui.labelsToBeChanged.cursorPosition = 0

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
                        if self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "observer"]) in self.settingsHandler.getAvailableDatasetsAndObservers()[self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])]:
                            return
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
        datasetList = list(self.settingsHandler.getAvailableDatasetsAndObservers().keys())

        if len(datasetList) > 0:
            firstDataset = list(self.settingsHandler.getAvailableDatasetsAndObservers().keys())[0]

            observerList = self.settingsHandler.getAvailableDatasetsAndObservers()[firstDataset]

            if len(observerList) > 0:
                firstObserver = self.settingsHandler.getAvailableDatasetsAndObservers()[firstDataset][0]

                self.settingsHandler.changeContentByKey(["savedDatasetAndObserverSelection", "dataset"], firstDataset)
                self.settingsHandler.changeContentByKey(["savedDatasetAndObserverSelection", "observer"], firstObserver)

    def selectedDatasetAndObserverSetting(self):
        dataset, observer = self.settingsHandler.getCurrentDatasetAndObserver()

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
        exporter = CalciumScore(self.selectedDatasetAndObserverSetting())
        exporter.exportFromReferenceFolder()

    def onExportFromJSONFileButtonClicked(self):
        exporter = CalciumScore(self.selectedDatasetAndObserverSetting())
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
        try:
            imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer, labelFileSuffix = self.selectedDatasetAndObserverSetting()

            if self.customThreshold:
                # Get the segmentation node (assuming it's the only one loaded)
                segmentationNode = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLSegmentationNode')
                volumeNode = slicer.util.getNode(self.loadedVolumeNode.GetName())
                segmentId = segmentationNode.GetSegmentation().GetSegmentIdBySegmentName("TemporarySegment")
                segmentArray = slicer.util.arrayFromSegmentBinaryLabelmap(segmentationNode, "TemporarySegment", volumeNode)

                if len(numpy.unique(segmentArray)) == 1:
                    segmentation = segmentationNode.GetSegmentation()
                    # Find the segment ID by segment name
                    segmentId = segmentation.GetSegmentIdBySegmentName('TemporarySegment')

                    # Check if the segment exists
                    if segmentId:
                        # Remove the segment by its ID
                        segmentation.RemoveSegment(segmentId)
                else:
                    print("Not all mismatched regions have been corrected! Check your segmentation for remaining red areas and try again!")
                    slicer.util.infoDisplay("Not all mismatched regions have been corrected!\nCheck your segmentation for remaining red areas and try again!")
                    return


            labelmapVolumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
            labelmapVolumeNode.SetName("temporaryExportLabel")
            referenceVolumeNode = None  # it could be set to the master volume
            segmentIds = self.loadedSegmentationNode.GetSegmentation().GetSegmentIDs()  # export all segments
            slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(self.loadedSegmentationNode, segmentIds,
                                                                              labelmapVolumeNode, referenceVolumeNode,
                                                                              slicer.vtkSegmentation.EXTENT_REFERENCE_GEOMETRY,
                                                                              self.colorTableNode)

            filename = self.loadedSegmentationNode.GetName()

            volumeNode = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLLabelMapVolumeNode')
            slicer.util.exportNode(volumeNode, os.path.join(labelsPath, filename))

            slicer.mrmlScene.RemoveNode(labelmapVolumeNode)
            self.progressBarUpdate()
            self.clearCurrentViewedNode(False)
            print(f"Saved {filename} {labelsPath}")

            if self.customThreshold:
                self.customThreshold = False
                pandas = importlib.import_module('pandas')
                filter = self.checkIfLoadFilterExists()
                csv = pandas.read_csv(filter)
                # Change the value in the 'done' column where 'id' is 1
                csv.loc[csv['Filename'] == filename, 'Done'] = 1
                csv.to_csv(filter, index=False)

                self.changeProgressFilter()

        except Exception as error:
            # handle the exception
            print("An exception occurred:", error)


    def onCompareObserverComboBoxChange(self, item=None):
        if not self.compareObserverComboBoxEventBlocked:
            self.selectedComparableObserver = self.self.compareObserverAvailableList()[item]
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

            self.selectedComparableObserver = list[0]
        else:
            self.ui.compareObserverComboBox.enabled = False
            self.ui.compareObserverLabel.enabled = False
            self.ui.secondObserverSegmentationType.enabled = False

    def compareObserverAvailableList(self):
        currentDataset, currentObserver = self.settingsHandler.getCurrentDatasetAndObserver()
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
        if len(self.compareObserverAvailableList()) > 0:
            file = filename.split(imageFileExtension)[0]
            currentDataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
            labelsPath = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", self.selectedComparableObserver, "labelsPath"])
            labelFileSuffix = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", self.selectedComparableObserver, "labelFileSuffix"])

            fullLabelFilename = file + labelFileSuffix + segmentationFileExtension

            if os.path.isfile(os.path.join(labelsPath, fullLabelFilename)):
                self.ui.compareLabelsButton.enabled = True
            else:
                self.ui.compareLabelsButton.enabled = False

    def checkForComparableLabelSegmentationTypes(self, firstObserver, secondObserver):
        currentDataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        firstSegmentationType = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", firstObserver, "segmentationMode"])
        secondSegmentationType = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", secondObserver, "segmentationMode"])

        list = []

        processor = SegmentationProcessor()

        if firstSegmentationType != secondSegmentationType:
            if processor.isSegmentationTypeLowerLevel(firstSegmentationType, secondSegmentationType):
                list = processor.getEqualAndLowerSegmentationTypes(firstSegmentationType)
            else:
                list = processor.getEqualAndLowerSegmentationTypes(secondSegmentationType)
        else:
            list = processor.getEqualAndLowerSegmentationTypes(firstSegmentationType)

        self.availableComparisonSegmentationTypes = list[::-1]
        self.comparisonSegmentationType = self.availableComparisonSegmentationTypes[0]

        self.ui.comparableSegmentationTypes.clear()
        self.ui.comparableSegmentationTypes.addItems(self.availableComparisonSegmentationTypes)
        self.ui.comparableSegmentationTypes.setCurrentText(self.availableComparisonSegmentationTypes[0])

    def onComparisonSegmentationTypeChange(self, item):
        self.comparisonSegmentationType = self.availableComparisonSegmentationTypes[item]

    def onCompareLabelsButton(self):
        file = self.loadedVolumeNode.GetName().split(imageFileExtension)[0]

        currentDataset, currentObserver = self.settingsHandler.getCurrentDatasetAndObserver()

        currentObserverLabelpath = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", currentObserver, "labelsPath"])
        currentObserverlabelFileSuffix = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", currentObserver, "labelFileSuffix"])

        compareObserverLabelpath = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", self.selectedComparableObserver, "labelsPath"])
        compareObserverlabelFileSuffix = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", self.selectedComparableObserver, "labelFileSuffix"])

        currentObserverFilePath = os.path.join(currentObserverLabelpath, (file + currentObserverlabelFileSuffix + segmentationFileExtension))
        compareObserverFilePath = os.path.join(compareObserverLabelpath, (file + compareObserverlabelFileSuffix + segmentationFileExtension))

        # import labels
        labelCurrentObserver = sitk.GetArrayFromImage(sitk.ReadImage(currentObserverFilePath))
        labelCompareObserver = sitk.GetArrayFromImage(sitk.ReadImage(compareObserverFilePath))

        #Compare labels
        currentObserverSegmentationType = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", currentObserver, "segmentationMode"])
        compareObserverSegmentationType = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers", self.selectedComparableObserver, "segmentationMode"])

        processor = SegmentationProcessor()

        labelCurrentObserver = processor.convert(labelCurrentObserver, currentObserverSegmentationType, self.comparisonSegmentationType)
        labelCompareObserver = processor.convert(labelCompareObserver, compareObserverSegmentationType, self.comparisonSegmentationType)

        self.compareLabels(labelCurrentObserver, labelCompareObserver)

    def compareLabels(self, labelOne, labelTwo):
        comparison = numpy.where(numpy.equal(labelOne, labelTwo) == True, 2, 1)

        oneBackground = numpy.where(labelOne == 0, 0, 1)
        twoBackground = numpy.where(labelTwo == 0, 0, -1)

        comparison[numpy.equal(oneBackground, twoBackground) == True] = 0

        imageNode = slicer.util.getNode(self.loadedVolumeNode.GetName())

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

    def setViewOneWindow(self):
        layoutManager = slicer.app.layoutManager()
        layoutManager.setLayout(6)

    ## code for comparison logic

    def setViewThreeWindows(self):
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

        #set three layers
        #layoutManager.setLayout(threeViewLayoutId)
        layoutManager.setLayout(6) # red layer

        nodes = slicer.util.getNodes("vtkMRMLSliceNode*")

        for node in nodes.values():
            node.SetOrientationToAxial()

    def createCompareObserversBox(self):
        currentDataset, currentObserver = self.settingsHandler.getCurrentDatasetAndObserver()


        observers = self.settingsHandler.getContentByKeys(["datasets", currentDataset, "observers"])

        if observers is not None:
            allObserversList = list(observers.keys())
            allObserversList.remove(currentObserver)

            if len(allObserversList) >= 2:
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
        dataset, observer = self.settingsHandler.getCurrentDatasetAndObserver()

        availableObservers = list(self.settingsHandler.getContentByKeys(["datasets", dataset, "observers"]).keys())

        if len(availableObservers) >= 3:
            availableObservers.remove(observer)
            self.comparisonObserver1 = availableObservers[id]

            secondObserverList = availableObservers
            secondObserverList.remove(self.comparisonObserver1)

            self.ui.CompareObserver2Selector.clear()
            self.ui.CompareObserver2Selector.addItems(secondObserverList)
            self.ui.CompareObserver2Selector.setCurrentText(secondObserverList[0])
            self.comparisonObserver2 = secondObserverList[0]

    def onComparisonChangeSecondObserver(self, id=None):
        dataset, observer = self.settingsHandler.getCurrentDatasetAndObserver()

        availableObservers = list(self.settingsHandler.getContentByKeys(["datasets", dataset, "observers"]).keys())
        availableObservers.remove(observer)
        availableObservers.remove(self.comparisonObserver1)

        self.comparisonObserver2 = availableObservers[id]

    def getListOfAvailableLabels(self, dataset, observer):
        path = self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer, "labelsPath"])
        labelFileSuffix = self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer, "labelFileSuffix"])

        returnList = []

        for file in os.listdir(path):
            filenameWithoutExtensions = file.split(labelFileSuffix + segmentationFileExtension)[0]
            returnList.append(filenameWithoutExtensions)

        return returnList

    def onComparisonSelectNextImage(self):
        slicer.mrmlScene.Clear()

        datasetAndObserver = self.selectedDatasetAndObserverSetting()
        imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer, labelFileSuffix = datasetAndObserver

        #image list of observer comparing
        imageList = self.getImageList(datasetAndObserver)

        #finding common files between observer comparing and other 2 observers!
        filesObserver1 = self.getListOfAvailableLabels(dataset, self.comparisonObserver1)
        filesObserver2 = self.getListOfAvailableLabels(dataset, self.comparisonObserver2)

        intersectionBetweenObservers = numpy.intersect1d(filesObserver1, filesObserver2)
        intersectionUnlabeled = numpy.intersect1d(intersectionBetweenObservers, imageList["unlabeledImages"])

        if len(intersectionUnlabeled) > 0:
            self.loadImageToCompare(intersectionUnlabeled[0] + imageFileExtension)
        else:
            print("No common labels found! Check if labels exists for both observers that are being compared! Check if comparing observer does not contain the same images e.g. because of a filter.")

    def onComparisonSelectImageToLoad(self):
        dataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        imagesPath = self.settingsHandler.getContentByKeys(["datasets", dataset, "imagesPath"])

        # opens file selection window
        filepath = qt.QFileDialog.getOpenFileName(self.parent, 'Open files', imagesPath, "Files(*"+imageFileExtension+")")
        filename = filepath.split("/")[-1]

        self.loadImageToCompare(filename)

    def loadImageToCompare(self, filename):
        dataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        imagesPath = self.settingsHandler.getContentByKeys(["datasets", dataset, "imagesPath"])

        self.clearCurrentViewedNode(True)

        self.createColorTable()
        properties = {'Name': "CT_IMAGE"}

        self.loadedVolumeNode = slicer.util.loadVolume(os.path.join(imagesPath, filename), properties=properties)
        self.loadedVolumeNode.SetName(filename)

        slicer.util.setSliceViewerLayers(background=self.loadedVolumeNode)
        self.loadedVolumeNode.GetScalarVolumeDisplayNode().AutoWindowLevelOff()
        self.loadedVolumeNode.GetScalarVolumeDisplayNode().SetWindowLevel(800, 180)

        self.loadComparisonLabels()
        self.setViewThreeWindows()
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
        imageNodeName = self.loadedVolumeNode.GetName()
        patientFileName = imageNodeName.split(imageFileExtension)[0]

        observer1LabelPath = os.path.join(
            self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", self.comparisonObserver1, "labelsPath"]),
            patientFileName + self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", self.comparisonObserver1, "labelFileSuffix"]) + segmentationFileExtension)

        observer2LabelPath = os.path.join(
            self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", self.comparisonObserver2, "labelsPath"]),
            patientFileName + self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", self.comparisonObserver2, "labelFileSuffix"]) + segmentationFileExtension)

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

                processor = SegmentationProcessor()

                observer1Segmentation = processor.convert(observer1SegmentationArray,
                                                                       observer1SegmentationType,
                                                                       "SegmentLevelOnlyArteries")

                observer2Segmentation = processor.convert(observer2SegmentationArray,
                                                                       observer2SegmentationType,
                                                                       "SegmentLevelOnlyArteries")

                self.loadLabelFromArray(observer1SegmentationArray, "Observer1", labelDescription)
                self.loadLabelFromArray(observer2SegmentationArray, "Observer2", labelDescription)

                labelDescription["MISMATCH"] = {
                    'value': 100,
                    'color': "#ff0000"
                }

                self.createComparisonLabel(observer1Segmentation, observer2Segmentation, labelDescription)

            elif observer1SegmentationType == "17Segment":
                labelDescription = self.settingsHandler.getContentByKeys(["labels", "17Segment"]).copy()

                elementsToRemove = [
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

                processor = SegmentationProcessor()

                observer1Segmentation = processor.convert(observer1SegmentationArray,
                                                          observer1SegmentationType,
                                                          "17SegmentOnlyArteries")

                observer2Segmentation = processor.convert(observer2SegmentationArray,
                                                          observer2SegmentationType,
                                                          "17SegmentOnlyArteries")

                self.loadLabelFromArray(observer1SegmentationArray, "Observer1", labelDescription)
                self.loadLabelFromArray(observer2SegmentationArray, "Observer2", labelDescription)

                labelDescription["MISMATCH"] = {
                    'value': 100,
                    'color': "#ff0000"
                }

                self.createComparisonLabel(observer1Segmentation, observer2Segmentation, labelDescription)

            elif observer1SegmentationType == "ArteryLevelWithLM":
                labelDescription = self.settingsHandler.getContentByKeys(["labels", "ArteryLevelWithLM"]).copy()

                self.loadLabelFromArray(observer1SegmentationArray, "Observer1", labelDescription)
                self.loadLabelFromArray(observer2SegmentationArray, "Observer2", labelDescription)

                labelDescription["MISMATCH"] = {
                    'value': 100,
                    'color': "#ff0000"
                }

                self.createComparisonLabel(observer1SegmentationArray, observer2SegmentationArray, labelDescription)

            else:
                #TODO: Implement for all Segmentation Types
                print("Function only implemented for SegmentLevel")
        else:
            if (observer1SegmentationType == "17Segment" and observer2SegmentationType == "ArteryLevelWithLM") or (observer1SegmentationType == "ArteryLevelWithLM" and observer2SegmentationType == "17Segment"):

                if observer1SegmentationType == "17Segment":
                    print("observer1")
                    processor = SegmentationProcessor()
                    observer1SegmentationArray = processor.convert(observer1SegmentationArray,
                                                                   observer1SegmentationType, observer2SegmentationType)
                elif observer2SegmentationType == "17Segment":
                    print("observer2")
                    processor = SegmentationProcessor()
                    observer2SegmentationArray = processor.convert(observer2SegmentationArray,
                                                                   observer2SegmentationType, observer1SegmentationType)

                labelDescription = self.settingsHandler.getContentByKeys(["labels", "ArteryLevelWithLM"]).copy()

                self.loadLabelFromArray(observer1SegmentationArray, "Observer1", labelDescription)
                self.loadLabelFromArray(observer2SegmentationArray, "Observer2", labelDescription)

                labelDescription["MISMATCH"] = {
                     'value': 100,
                      'color': "#ff0000"
                }

                self.createComparisonLabel(observer1SegmentationArray, observer2SegmentationArray, labelDescription)

    def createComparisonLabel(self, observer1Segmentation, observer2Segmentation, labelDescription):
        comparisonSegmentation = numpy.copy(observer1Segmentation)

        # removes other label
        observer1Segmentation[observer1Segmentation == 1] = 0
        observer2Segmentation[observer2Segmentation == 1] = 0

        #finding differences using binary label
        binaryLabel = numpy.where(numpy.equal(observer1Segmentation, observer2Segmentation) == True, 2, 1)

        observer1Background = numpy.where(observer1Segmentation == 0, 0, 1)
        observer2Background = numpy.where(observer2Segmentation == 0, 0, -1)

        binaryLabel[numpy.equal(observer1Background, observer2Background) == True] = 0

        #add label to segmentation
        comparisonSegmentation[binaryLabel == 1] = 100

        imageNode = slicer.util.getNode(self.loadedVolumeNode.GetName())

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
                segmentArray[comparisonSegmentation > 1] = 0

            segmentArray[comparisonSegmentation == value] = 1  # create segment by simple thresholding of an image
            slicer.util.updateSegmentBinaryLabelmapFromArray(segmentArray, segmentationNode, segmentId, imageNode)

    def loadLabelFromArray(self, labelArray, labelName, labelDescription):
        uniqueKeys = numpy.unique(labelArray)

        imageNode = slicer.util.getNode(self.loadedVolumeNode.GetName())

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

            if labelFileSuffix:
                nameWithoutSuffix = name.split(labelFileSuffix)[0]
            else:
                nameWithoutSuffix = name

            if extension == segmentationFileExtension and os.path.isfile(os.path.join(imagesPath, nameWithoutSuffix + imageFileExtension)):
               references.append(nameWithoutSuffix)

        for imageFileName in sorted(filter(lambda x: os.path.isfile(os.path.join(imagesPath, x)),os.listdir(imagesPath))):
            name, extension = os.path.splitext(imageFileName)
            if extension == imageFileExtension:
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
        imageNode = slicer.util.getNode(self.loadedVolumeNode.GetName())
        segmentationNode = slicer.util.getNode("Comparison")
        segmentId = segmentationNode.GetSegmentation().GetSegmentIdBySegmentName("MISMATCH")

        segmentArray = slicer.util.arrayFromSegmentBinaryLabelmap(segmentationNode, segmentId, imageNode)

        if len(numpy.unique(segmentArray)) == 1:
            dataset = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
            observer = self.settingsHandler.getContentByKeys(["savedDatasetAndObserverSelection", "observer"])
            savePath = self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer, "labelsPath"])
            filename = self.loadedVolumeNode.GetName().split(imageFileExtension)[0] + self.settingsHandler.getContentByKeys(["datasets", dataset, "observers", observer, "labelFileSuffix"]) + segmentationFileExtension

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

        else:
            print("Not all mismatched regions have been corrected! Check your segmentation for remaining red areas and try again!")
            slicer.util.infoDisplay("Not all mismatched regions have been corrected!\nCheck your segmentation for remaining red areas and try again!")

    def runThreshold(self, inputVolumeName, labelName, segmentationMode, labelsPath, colorTableNode, differentLabelType):
        node = slicer.util.getFirstNodeByName(labelName)
        if node is None:
            print('----- Thresholding -----')
            print('Threshold value:', lowerThresholdValue)

            imageNode = slicer.util.getNode(inputVolumeName)

            segmentationNode = None
            segmentation = None

            # file exists
            if os.path.isfile(os.path.join(labelsPath, labelName)):
                volumeNode = slicer.util.loadVolume(os.path.join(labelsPath, labelName), {"labelmap": True})
                segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")  # import into new segmentation node
                segmentationNode.SetName(labelName)
                segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(imageNode)
                volumeNode.GetDisplayNode().SetAndObserveColorNodeID(
                    colorTableNode.GetID())  # just in case the custom color table has not been already associated with the labelmap volume
                slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(volumeNode, segmentationNode)

                slicer.mrmlScene.RemoveNode(volumeNode)
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

                if key == "OTHER" and not os.path.isfile(os.path.join(labelsPath, labelName)):
                    segmentId = segmentationNode.GetSegmentation().GetSegmentIdBySegmentName(key)
                    segmentArray = slicer.util.arrayFromSegmentBinaryLabelmap(segmentationNode, key, imageNode)
                    segmentArray[slicer.util.arrayFromVolume(
                        imageNode) >= lowerThresholdValue] = 1  # create segment by simple thresholding of an image
                    slicer.util.updateSegmentBinaryLabelmapFromArray(segmentArray, segmentationNode, segmentId,
                                                                     imageNode)

            converter = SegmentationProcessor()

            # converts label if other label is available
            if differentLabelType is not None and not os.path.isfile(os.path.join(labelsPath, labelName)):
                if os.path.isfile(os.path.join(differentLabelType["labelPath"], labelName)):
                    label = sitk.ReadImage(os.path.join(differentLabelType["labelPath"], labelName))
                    labelArray = sitk.GetArrayFromImage(label)

                    if differentLabelType["labelSegmentationMode"] == segmentationMode:
                        for key in self.settingsHandler.getContentByKeys(["labels", segmentationMode]):

                            if key != "OTHER":
                                self.convertLabelType(labelArray, converter.getLabelValueByName(segmentationMode, key), key, imageNode, segmentationNode)

                    if differentLabelType["labelSegmentationMode"] == "ArteryLevelWithLM" and segmentationMode == "SegmentLevel":
                        self.convertLabelType(labelArray, 5, 'LM_BRANCH', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, 2, 'LAD_PROXIMAL', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, 4, "RCA_PROXIMAL", imageNode, segmentationNode)
                        self.convertLabelType(labelArray, 3, "LCX_PROXIMAL", imageNode, segmentationNode)

                    if differentLabelType["labelSegmentationMode"] == "ArteryLevelWithLM" and segmentationMode == "17Segment":
                        self.convertLabelType(labelArray, 5, 'LM', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, 2, 'LAD_PROXIMAL', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, 4, "RCA_PROXIMAL", imageNode, segmentationNode)
                        self.convertLabelType(labelArray, 3, "LCX_PROXIMAL", imageNode, segmentationNode)

                    if differentLabelType["labelSegmentationMode"] == "SegmentLevel" and segmentationMode == "17Segment":
                        oldType = "SegmentLevel"

                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "RCA_PROXIMAL"),
                                              'RCA_PROXIMAL', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "RCA_MID"),
                                              'RCA_MID', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "RCA_DISTAL"),
                                              'RCA_DISTAL', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "RCA_SIDE_BRANCH"),
                                              'RCA_SIDE_PROXIMAL', imageNode, segmentationNode)

                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "LM_BIF_LAD_LCX"),
                                              'LM', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "LM_BIF_LAD"),
                                              'LM', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "LM_BIF_LCX"),
                                              'LM', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "LM_BRANCH"),
                                              'LM', imageNode, segmentationNode)

                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "LAD_PROXIMAL"),
                                              'LAD_PROXIMAL', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "LAD_MID"),
                                              'LAD_MID', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "LAD_DISTAL"),
                                              'LAD_DISTAL', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "LAD_SIDE_BRANCH"),
                                              'LAD_SIDE_D1', imageNode, segmentationNode)

                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "LCX_PROXIMAL"),
                                              'LCX_PROXIMAL', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "LCX_MID"),
                                              'LCX_MID', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "LCX_DISTAL"),
                                              'LCX_DISTAL', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "LCX_SIDE_BRANCH"),
                                              'LCX_SIDE_OM1', imageNode, segmentationNode)

                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "RIM"),
                                              'RIM', imageNode, segmentationNode)

                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "AORTA_ASC"),
                                              'AORTA_ASC', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "AORTA_DSC"),
                                              'AORTA_DSC', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "AORTA_ARC"),
                                              'AORTA_ARC', imageNode, segmentationNode)

                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "VALVE_AORTIC"),
                                              'VALVE_AORTIC', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "VALVE_PULMONIC"),
                                              'VALVE_PULMONIC', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "VALVE_TRICUSPID"),
                                              'VALVE_TRICUSPID', imageNode, segmentationNode)
                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "VALVE_MITRAL"),
                                              'VALVE_MITRAL', imageNode, segmentationNode)

                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "PAPILLAR_MUSCLE"),
                                              'PAPILLAR_MUSCLE', imageNode, segmentationNode)

                        self.convertLabelType(labelArray, converter.getLabelValueByName(oldType, "NFS_CACS"),
                                              'NFS_CACS', imageNode, segmentationNode)

                        # Adding Text
                        Text = ""

                        elements = numpy.unique(labelArray)

                        if converter.getLabelValueByName(oldType, 'LAD_SIDE_BRANCH') in elements:
                            Text = Text + " LAD_SIDE "

                        if converter.getLabelValueByName(oldType, 'LCX_SIDE_BRANCH') in elements:
                            Text = Text + " LCX_SIDE "

                        if converter.getLabelValueByName(oldType, 'LCX_DISTAL') in elements:
                            Text = Text + " LCX_DISTAL "

                        if converter.getLabelValueByName(oldType, 'RCA_SIDE_BRANCH') in elements:
                            Text = Text + " RCA_SIDE "

                        if converter.getLabelValueByName(oldType, 'RCA_DISTAL') in elements:
                            Text = Text + " RCA_DISTAL "

                        self.ui.labelsToBeChanged.text = Text
                        self.ui.labelsToBeChanged.cursorPosition = 0

    def convertLabelType(self, oldLabelArray, oldArrayId, segmentIdName, imageNode, segmentationNode):
        segmentId = segmentationNode.GetSegmentation().GetSegmentIdBySegmentName(segmentIdName)
        otherId = segmentationNode.GetSegmentation().GetSegmentIdBySegmentName('OTHER')

        segmentArray = slicer.util.arrayFromSegmentBinaryLabelmap(segmentationNode, segmentId, imageNode)
        segmentArray[oldLabelArray == oldArrayId] = 1

        otherArray = slicer.util.arrayFromSegmentBinaryLabelmap(segmentationNode, otherId, imageNode)
        otherArray[oldLabelArray == oldArrayId] = 0

        slicer.util.updateSegmentBinaryLabelmapFromArray(segmentArray, segmentationNode, segmentId, imageNode)
        slicer.util.updateSegmentBinaryLabelmapFromArray(otherArray, segmentationNode, otherId, imageNode)