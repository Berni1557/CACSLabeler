import logging
import os

import numpy as np
import vtk
import qt

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

import concurrent.futures
import SimpleITK as sitk
import numpy
import json

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

#install needed dependencies if not available
try:
    import pandas
    from scipy.ndimage import label
    from scipy import ndimage as ndi

except ModuleNotFoundError as e:
    moduleName = e.name
    if slicer.util.confirmOkCancelDisplay(
            "This module requires '"+moduleName+"' Python package. Click OK to install it now."):
        slicer.util.pip_install(moduleName)

    from scipy.ndimage import label
    import pandas
    #from termcolor import colored
    #import torch
    #import cc3d

#
# CACSLabeler
#

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

        self.ui.exportFromReferenceFolder.connect('clicked(bool)', self.logic.onExportFromReferenceFolderButtonClicked)
        self.ui.exportFromJsonFile.connect('clicked(bool)', self.logic.onExportFromJSONFileButtonClicked)
        self.ui.loadVolumeButton.connect('clicked(bool)', self.onLoadButton)
        self.ui.thresholdVolumeButton.connect('clicked(bool)', self.onThresholdVolume)

        self.topLevelPath = Path(__file__).absolute().parent.parent.parent.parent
        self.dataPath = os.path.join(Path(__file__).absolute().parent.parent.parent.parent, "data")

        # Loads Settings
        self.settingsPath = os.path.join(self.dataPath, "settings_CACSLabeler5.x.json")
        self.settings = None
        self.availableDatasetsAndObservers = {}

        self.loadSettings()
        self.loadDatasetSettings()
        self.selectDatasetAndObserver()
        self.saveSettings()
        self.mainUIHidden(False)
        self.updateDatasetAndObserverDropdownSelection()

        # after first updateDatasetAndObserverDropdownSelection to prevent call on automatic selection
        self.datasetComboBoxEventBlocked = False
        self.ui.datasetComboBox.connect("currentIndexChanged(int)", self.onChangeDataset)
        self.observerComboBoxEventBlocked = False
        self.ui.observerComboBox.connect("currentIndexChanged(int)", self.onChangeObserver)

        self.currentLoadedNode = None
        self.initializeMainUI()

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

    def onChangeDataset(self, datasetListId=None):
        if self.currentLoadedNode or len(slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")):
            if not slicer.util.confirmOkCancelDisplay(
                    "This will close current scene.  Please make sure you have saved your current work.\n"
                    "Are you sure to continue?"
            ):
                return

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
        if self.currentLoadedNode or len(slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")):
            if not slicer.util.confirmOkCancelDisplay(
                    "This will close current scene.  Please make sure you have saved your current work.\n"
                    "Are you sure to continue?"
            ):
                return

        if not self.observerComboBoxEventBlocked:
            self.datasetComboBoxEventBlocked = True
            self.observerComboBoxEventBlocked = True

            self.selectDatasetAndObserver(self.settings["savedDatasetAndObserverSelection"]["dataset"], self.availableDatasetsAndObservers[self.settings["savedDatasetAndObserverSelection"]["dataset"]][item])
            self.saveSettings()
            self.initializeMainUI()

            self.datasetComboBoxEventBlocked = False
            self.observerComboBoxEventBlocked = False

    def onLoadButton(self):
        # TODO: filter input files
        # # Deleta all old nodes
        # if self.settings['show_input_if_ref_found'] or self.settings['show_input_if_ref_not_found']:
        #     # files_ref = glob(self.settings['folderpath_references'] + '/*label-lesion.nrrd')
        #     files_ref = glob(self.settings['folderpath_references'] + '/*-label.nrrd')
        #     filter_input = self.settings['filter_input'].decode('utf-8')
        #     filter_input_list = filter_input.split('(')[1].split(')')[0].split(',')
        #     filter_input_list = [x.replace(" ", "") for x in filter_input_list]
        #     filter_input_list = [x.encode('utf8') for x in filter_input_list]
        #
        #     # Collect filenames
        #     files = []
        #     for filt in filter_input_list:
        #         # print('filt', filt)
        #         files = files + glob(self.settings['folderpath_images'] + '/' + filt)
        #
        #     filepaths_label_ref = glob(self.settings['folderpath_references'] + '/*.nrrd')
        #     filter_reference_with = self.settings['filter_reference_with']
        #     filter_reference_without = self.settings['filter_reference_without']
        #     files = self.filter_by_reference(files, filepaths_label_ref, filter_reference_with,
        #                                      filter_reference_without)
        #     filter_input_ref = ''
        #     for f in files:
        #         _, fname, _ = splitFilePath(f)
        #         ref_found = any([fname in ref for ref in files_ref])
        #         if ref_found and self.settings['show_input_if_ref_found']:
        #             filter_input_ref = filter_input_ref + fname + '.mhd '
        #         if not ref_found and self.settings['show_input_if_ref_not_found']:
        #             filter_input_ref = filter_input_ref + fname + '.mhd '
        #
        #     filenames = qt.QFileDialog.getOpenFileNames(self.parent, 'Open files', self.settings['folderpath_images'],
        #                                                 filter_input_ref)
        # else:

        # TODO: from settings file
        settings_imagePath = "/Users/***REMOVED***/Desktop/OrCaScore/images/"

        if self.currentLoadedNode or len(slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode")):
            if not slicer.util.confirmOkCancelDisplay(
                    "This will close current scene.  Please make sure you have saved your current work.\n"
                    "Are you sure to continue?"
            ):
                return

        self.clearCurrentViewedNode()

        # opens file selection window
        filepath = qt.QFileDialog.getOpenFileName(self.parent, 'Open files', settings_imagePath, "Files(*.mhd)")

        # TODO: change function to return all parts of the name
        filename = filepath.split("/")[-1]
        properties = {'Name': filename}

        self.currentLoadedNode = slicer.util.loadVolume(filepath, properties=properties)
        self.currentLoadedNode.SetName(filename)

        #Activate buttons
        self.ui.RadioButton120keV.enabled = True
        self.ui.thresholdVolumeButton.enabled = True
        self.ui.selectedVolumeTextField.text = filename
        self.ui.selectedVolumeTextField.cursorPosition = 0

    def onThresholdVolume(self):
        if not self.ui.RadioButton120keV.checked:
            qt.QMessageBox.warning(slicer.util.mainWindow(),"Select KEV", "The KEV (80 or 120) must be selected to continue.")
            return

        settings_load_reference_if_exist = True
        settings_folderpath_references = "/Users/***REMOVED***/Desktop/OrCaScore/testRef"

        #removes file extension
        inputVolumeName = os.path.splitext(self.currentLoadedNode.GetName())[0]

        # Load reference if load_reference_if_exist is true and reference file exist and no label node exist
        if settings_load_reference_if_exist:
            if self.currentLoadedNode is not None:
                labelName = inputVolumeName + '-label-lesion'
                nodeLabel = slicer.util.getFirstNodeByName(labelName)

                if nodeLabel is None and 'label' not in inputVolumeName and not inputVolumeName == '1': #Todo check this expression
                    labelFilePath = os.path.join(settings_folderpath_references, labelName + '.nrrd')

                    properties = {'name': labelName, 'labelmap': True}
                    if os.path.isfile(labelFilePath):
                        nodeLabel = slicer.util.loadVolume(labelFilePath, properties=properties)
                        nodeLabel.SetName(labelName)


        #             filepath_ref = os.path.join(self.settings['folderpath_references'], calciumName + '.nrrd')
        #
        #             if os.path.isfile(filepath_ref):
        #                 node_label = slicer.util.loadVolume(filepath_ref, returnNode=True, properties=properties)[1]
        #                 node_label.SetName(calciumName)
        #                 # self.CACSLabelerModuleLogic.assignLabelLUT(calciumName)
        #                 # self.CACSLabelerModuleLogic.calciumName = calciumName
        #
        # # Threshold image
        # self.CACSLabelerModuleLogic = CACSLabelerModuleLogic(self.KEV80.checked, self.KEV120.checked, inputVolumeName)
        # self.CACSLabelerModuleLogic.runThreshold()
        # self.CACSLabelerModuleLogic.setLowerPaintThreshold()
        #
        # # View thresholded image as label map and image as background image in red widget
        # # node = slicer.util.getFirstNodeByName(self.CACSLabelerModuleLogic.calciumName[0:-13])
        # nodes = slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
        # for n in nodes:
        #     if n.GetName() == self.CACSLabelerModuleLogic.calciumName[0:-13]:
        #         node = n
        #         break
        # slicer.util.setSliceViewerLayers(background=node)
        #
        # # Set ref_name
        # name = self.CACSLabelerModuleLogic.calciumName[0:-13]
        # for image in self.imagelist:
        #     if image.image_name == name:
        #         image.ref_name = node.GetName() + '-label-lesion'
        #
        # # Set slicer offset
        # slicer.util.resetSliceViews()
        #
        # # Creates and adds the custom Editor Widget to the module
        # if self.localCardiacEditorWidget is None:
        #     self.localCardiacEditorWidget = CardiacEditorWidget(parent=self.parent, showVolumesFrame=False,
        #                                                         settings=self.settings)
        #     self.localCardiacEditorWidget.setup()
        #     self.localCardiacEditorWidget.enter()
        #
        # # Activate Save Button
        # self.saveButton.enabled = True
        # self.scoreButton.enabled = True
        # self.exportButton.enabled = True

    def initializeMainUI(self):
        self.clearCurrentViewedNode()
        self.progressBarUpdate()

    def clearCurrentViewedNode(self):
        slicer.mrmlScene.Clear(0)
        self.ui.RadioButton120keV.enabled = False
        self.ui.thresholdVolumeButton.enabled = False
        self.ui.selectedVolumeTextField.text = ""
        self.ui.selectedVolumeTextField.cursorPosition = 0

    def progressBarUpdate(self):
        images = self.logic.getImageList(self.selectedDatasetAndObserverSetting())
        self.ui.progressBar.minimum = 0
        self.ui.progressBar.maximum = len(images["allImages"])
        self.ui.progressBar.value = len(images["allImages"]) - len(images["unlabeledImages"])

        self.ui.completedCountText.text = str(len(images["allImages"]) - len(images["unlabeledImages"])) + " / " + str(len(images["allImages"]))

    def loadSettings(self):
        with open(self.settingsPath, 'r', encoding='utf-8') as file:
            self.settings = None
            self.settings = json.load(file)

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

                            # Options: ArteryLevel, SegmentLevel
                            if self.settings["datasets"][dataset]["observers"][observer]["segmentationMode"] == "ArteryLevel" or self.settings["datasets"][dataset]["observers"][observer]["segmentationMode"] == "SegmentLevel":
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

        return imagesPath, labelsPath, segmentationMode

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

    def changeSettings(self):
        pass

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

    def onExportFromReferenceFolderButtonClicked(self):
        exporter = ScoreExport()
        exporter.exportFromReferenceFolder()

    def onExportFromJSONFileButtonClicked(self):
        exporter = ScoreExport()
        exporter.exportFromJSONFile()

    def runThreshold(self):
        pass

    def getImageList(self, datasetSettings):
        imagesPath, labelsPath, segmentationMode = datasetSettings

        files = {"allImages": [], "unlabeledImages": []}
        references = []

        for referenceFileName in sorted(filter(lambda x: os.path.isfile(os.path.join(labelsPath, x)),os.listdir(labelsPath))):
            name, extension = os.path.splitext(referenceFileName)
            if extension == ".nrrd":
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
    def __init__(self):
        self.filepaths = {
            "imageFolder": "",
            "referenceFolder": "",
            "sliceStepFile": "",
            "exportFileCSV": "",
            "exportFileJSON": ""
        }

        self.dataset = "OrCaScore"

        # Options: ArteryLevel, SegmentLevel
        self.exportType = "SegmentLevel"

        if self.exportType == "SegmentLevel":
            self.Items = {
            "CC": [
                4, 5, 6, 7,  # RCA
                9, 10, 11, 12,  # LM
                14, 15, 16, 17,  # LAD
                19, 20, 21, 22,  # LCX
                23,  # RIM
            ],
            "RCA": [4, 5, 6, 7],
            "RCA_PROXIMAL": 4,
            "RCA_MID": 5,
            "RCA_DISTAL": 6,
            "RCA_SIDE_BRANCH": 7,
            "LM": [9, 10, 11, 12],
            "LM_BIF_LAD_LCX": 9,
            "LM_BIF_LAD": 10,
            "LM_BIF_LCX": 11,
            "LM_BRANCH": 12,
            "LAD": [14, 15, 16, 17],
            "LAD_PROXIMAL": 14,
            "LAD_MID": 15,
            "LAD_DISTAL": 16,
            "LAD_SIDE_BRANCH": 17,
            "LCX": [19, 20, 21, 22],
            "LCX_PROXIMAL": 19,
            "LCX_MID": 20,
            "LCX_DISTAL": 21,
            "LCX_SIDE_BRANCH": 22,
            "RIM": 23,
            "NCC": [
                26, 27, 28,  # AORTA
                30, 31, 32, 33,  # VALVES
                24, 35,  # NFS_CACS
                34, #PAPILLAR_MUSCLE
            ],
            "AORTA": [26, 27, 28],
            "AORTA_ASC": 26,
            "AORTA_DSC": 27,
            "AORTA_ARC": 28,
            "VALVES": [30, 31, 32, 33],
            "VALVE_AORTIC": 30,
            "VALVE_PULMONIC": 31,
            "VALVE_TRICUSPID": 32,
            "VALVE_MITRAL": 33,
            "PAPILLAR_MUSCLE": 34,
            "NFS_CACS": 35,
        }
        elif self.exportType == "ArteryLevel":
            self.Items = {
                "CC": [
                    2, 3, 4
                ],
                "RCA": 4,
                "LAD": 2,
                "LCX": 3,
            }

        self.arteryId = {}

        for key in self.Items:
            if isinstance(self.Items[key], int):
                self.arteryId[self.Items[key]] = key

        self.exportJson = {}
        self.exportList = []

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
        dataframe = pandas.DataFrame.from_records(self.exportList)
        dataframe.to_csv(self.filepaths["exportFileCSV"], index=False, sep=';')

        if createJson:
            with open(self.filepaths["exportFileJSON"], 'w', encoding='utf-8') as file:
                #explicit copy to prevent race condition
                json.dump(dict(self.exportJson), file, ensure_ascii=False, indent=4, cls=NpEncoder)

    def exportFromReferenceFolder(self):
        sliceStepDataframe = pandas.read_csv(self.filepaths["sliceStepFile"], dtype={'patient_id': 'string'})

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

        if self.exportType == "ArteryLevel":
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

        tempComponentAnalysis = np.zeros(shape=(maxCoordinate,maxCoordinate))
        tempAttenuation = np.zeros(shape=(maxCoordinate, maxCoordinate))
        tempLabel = np.zeros(shape=(maxCoordinate, maxCoordinate))

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
        processedFilename = self.processFilename(self.filepaths["referenceFolder"] + filename)

        image = sitk.ReadImage(self.filepaths["imageFolder"] + processedFilename[1] + ".mhd")
        label = sitk.ReadImage(self.filepaths["referenceFolder"] + filename)

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
