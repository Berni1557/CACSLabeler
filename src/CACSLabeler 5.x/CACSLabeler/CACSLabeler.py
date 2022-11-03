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

#importing custom packages
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
dirname = os.path.dirname(os.path.abspath(__file__))
dir_src = os.path.dirname(os.path.dirname(dirname))
sys.path.append(dir_src)

from settings.settings import Settings

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
    #import torch
    #import cc3d

def splitFilePath(filepath):
    """ Split filepath into folderpath, filename and file extension

    :param filepath: Filepath
    :type filepath: str
    """
    #folderpath, _ = ntpath.split(filepath)
    folderpath = os.path.dirname(filepath)
    head, file_extension = os.path.splitext(filepath)
    filename = os.path.basename(head)
    return folderpath, filename, file_extension

class Image:
    def __init__(self, fip_image=None, fip_ref=None, settings=None):
        if fip_image is None and fip_ref is not None:
            _, ref_name, _ = splitFilePath(fip_ref)
            if len(ref_name.split('_')) == 1:
                if settings['MODE'] == 'CACS_ORCASCORE':
                    PatientID = ''
                    SeriesInstanceUID = ref_name.split('-')[0][0:-1]
                    image_name = SeriesInstanceUID
                else:
                    PatientID = ''
                    SeriesInstanceUID = ref_name.split('-')[0]
                    image_name = SeriesInstanceUID
            else:
                PatientID = ref_name.split('_')[0]
                SeriesInstanceUID = ref_name.split('_')[1].split('-')[0]
                image_name = PatientID + '_' + SeriesInstanceUID

            self.fip_ref = fip_ref
            self.ref_name = ref_name

            self.fip_image = ''
            self.image_name = image_name

            self.PatientID = PatientID
            self.SeriesInstanceUID = SeriesInstanceUID

        if fip_image is not None and fip_ref is None:
            _, image_name, _ = splitFilePath(fip_image)
            if len(image_name.split('_')) == 1:
                PatientID = ''
                SeriesInstanceUID = image_name
            else:
                PatientID = image_name.split('_')[0]
                SeriesInstanceUID = image_name.split('_')[1]
                image_name = PatientID + '_' + SeriesInstanceUID

            self.fip_ref = None
            self.ref_name = image_name + '-label-lesion'

            self.fip_image = ''
            self.image_name = image_name

            self.PatientID = PatientID
            self.SeriesInstanceUID = SeriesInstanceUID

        self.scores = []
        self.arteries_dict = dict()
        self.arteries_sum = dict()

    def findImage(self, images, dataset):
        if dataset == 'ORCASCORE':
            for image in images:
                _, name, _ = splitFilePath(image)
                if self.image_name == name[0:-3]:
                    self.fip_image = image
        else:
            for image in images:
                _, name, _ = splitFilePath(image)
                if self.image_name == name:
                    self.fip_image = image

    def setRef_name(self, ref_name):
        if len(ref_name.split('_')) == 1:
            PatientID = ''
            SeriesInstanceUID = ref_name.split('-')[0]
            image_name = SeriesInstanceUID
        else:
            PatientID = ref_name.split('_')[0]
            SeriesInstanceUID = ref_name.split('_')[1].split('-')[0]
            image_name = PatientID + '_' + SeriesInstanceUID

        self.PatientID = PatientID
        self.SeriesInstanceUID = SeriesInstanceUID
        self.image_name = image_name
        self.ref_name = ref_name

    def scoreExist(self, scorename):
        for s in self.scores:
            if s['NAME'] == scorename:
                return True
        return False

    def deleteScore(self, scorename):
        for i, s in enumerate(self.scores):
            if s['NAME'] == scorename:
                del self.scores[i]
                return True
        return False

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
        self._parameterNode = None
        self._updatingGUIFromParameterNode = False

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

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
        # (in the selected parameter node).
        self.ui.inputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.outputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.imageThresholdSliderWidget.connect("valueChanged(double)", self.updateParameterNodeFromGUI)
        self.ui.invertOutputCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
        self.ui.invertedOutputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)

        # Buttons
        self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)

        #######################
        # Own Code            #
        #######################
        self.ui.datasetComboBox.addItems(["DISCHARGE", "CADMAN", "OrCaScore"])
        self.ui.observerComboBox.addItems(["ST", "FB", "LU"])

        self.ui.loadVolumesButton.connect('clicked(bool)', self.onLoadInputButton)
        self.ui.exportFromFolder.connect('clicked(bool)', self.logic.onExportButtonClicked)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

    def cleanup(self):
        """
        Called when the application closes and the module widget is destroyed.
        """
        self.removeObservers()

    def enter(self):
        """
        Called each time the user opens this module.
        """
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self):
        """
        Called each time the user opens a different module.
        """
        # Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
        self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

    def onSceneStartClose(self, caller, event):
        """
        Called just before the scene is closed.
        """
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event):
        """
        Called just after the scene is closed.
        """
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self):
        """
        Ensure parameter node exists and observed.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

        # Select default input nodes if nothing is selected yet to save a few clicks for the user
        if not self._parameterNode.GetNodeReference("InputVolume"):
            firstVolumeNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
            if firstVolumeNode:
                self._parameterNode.SetNodeReferenceID("InputVolume", firstVolumeNode.GetID())

    def setParameterNode(self, inputParameterNode):
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """

        if inputParameterNode:
            self.logic.setDefaultParameters(inputParameterNode)

        # Unobserve previously selected parameter node and add an observer to the newly selected.
        # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
        # those are reflected immediately in the GUI.
        if self._parameterNode is not None:
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self._parameterNode = inputParameterNode
        if self._parameterNode is not None:
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

        # Initial GUI update
        self.updateGUIFromParameterNode()

    def updateGUIFromParameterNode(self, caller=None, event=None):
        """
        This method is called whenever parameter node is changed.
        The module GUI is updated to show the current state of the parameter node.
        """

        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
        self._updatingGUIFromParameterNode = True

        # Update node selectors and sliders
        self.ui.inputSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputVolume"))
        self.ui.outputSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputVolume"))
        self.ui.invertedOutputSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputVolumeInverse"))
        self.ui.imageThresholdSliderWidget.value = float(self._parameterNode.GetParameter("Threshold"))
        self.ui.invertOutputCheckBox.checked = (self._parameterNode.GetParameter("Invert") == "true")

        # Update buttons states and tooltips
        if self._parameterNode.GetNodeReference("InputVolume") and self._parameterNode.GetNodeReference("OutputVolume"):
            self.ui.applyButton.toolTip = "Compute output volume"
            self.ui.applyButton.enabled = True
        else:
            self.ui.applyButton.toolTip = "Select input and output volume nodes"
            self.ui.applyButton.enabled = False

        # All the GUI updates are done
        self._updatingGUIFromParameterNode = False

    def updateParameterNodeFromGUI(self, caller=None, event=None):
        """
        This method is called when the user makes any change in the GUI.
        The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
        """

        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch

        self._parameterNode.SetNodeReferenceID("InputVolume", self.ui.inputSelector.currentNodeID)
        self._parameterNode.SetNodeReferenceID("OutputVolume", self.ui.outputSelector.currentNodeID)
        self._parameterNode.SetParameter("Threshold", str(self.ui.imageThresholdSliderWidget.value))
        self._parameterNode.SetParameter("Invert", "true" if self.ui.invertOutputCheckBox.checked else "false")
        self._parameterNode.SetNodeReferenceID("OutputVolumeInverse", self.ui.invertedOutputSelector.currentNodeID)

        self._parameterNode.EndModify(wasModified)

    def onApplyButton(self):
        """
        Run processing when user clicks "Apply" button.
        """
        with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):

            # Compute output
            self.logic.process(self.ui.inputSelector.currentNode(), self.ui.outputSelector.currentNode(),
                               self.ui.imageThresholdSliderWidget.value, self.ui.invertOutputCheckBox.checked)

            # Compute inverted output (if needed)
            if self.ui.invertedOutputSelector.currentNode():
                # If additional output volume is selected then result with inverted threshold is written there
                self.logic.process(self.ui.inputSelector.currentNode(), self.ui.invertedOutputSelector.currentNode(),
                                   self.ui.imageThresholdSliderWidget.value, not self.ui.invertOutputCheckBox.checked, showResult=False)


    def onLoadInputButton(self):
        print("load input button")

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

    def onExportButtonClicked(self):
        exporter = ScoreExport()
        exporter.export()

        print("Export started")

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
        self.calculationMode = "3d"

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

        self.arteryId = {}

        for key in self.Items:
            if isinstance(self.Items[key], int):
                self.arteryId[self.Items[key]] = key

        self.exportJson = {}

    def runExportProcess(self, filename, sliceStepDataframe, exportList):
        referenceFilePath = self.filepaths["referenceFolder"] + filename

        file = self.processFilename(filename)
        imageFilePath = self.filepaths["imageFolder"] + file[1] + ".mhd"

        sliceThickness = sliceStepDataframe.loc[(sliceStepDataframe['patient_id'] == file[2])].slice_thickness.item()

        exportList.append(self.exportScore(imageFilePath, referenceFilePath, sliceThickness))
        print("Exported " + filename)

        dataframe = pandas.DataFrame.from_records(exportList)
        dataframe.to_csv(self.filepaths["exportFileCSV"], index=False, sep=';')

        if self.calculationMode == '3d':
            with open(self.filepaths["exportFileJSON"], 'w', encoding='utf-8') as file:
                json.dump(self.exportJson, file, ensure_ascii=False, indent=4, cls=NpEncoder)

    def export(self):
        sliceStepDataframe = pandas.read_csv(self.filepaths["sliceStepFile"], dtype={'patient_id': 'string'})

        exportList = []

        total = timeit.default_timer()
        #threads = []

        for filename in os.listdir(self.filepaths["referenceFolder"]):
            if filename.endswith(".nrrd"):
                self.runExportProcess(filename, sliceStepDataframe, exportList)
        #        thread = threading.Thread(target=self.runExportProcess, args=[filename, sliceStepDataframe, exportList])
        #        thread.start()
        #        threads.append(thread)

        #for thread in threads:
        #    thread.join()

        print("total", timeit.default_timer() - total)

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

        return (fileName, fileId, PatientID, SeriesInstanceUID)

    def label(self, referenceTemporaryCopy, uniqueId, structureConnections2d, iterator, connectedElements2d):
        labeled_array, num_features = ndi.label((referenceTemporaryCopy == uniqueId).astype(int),
                                                structure=structureConnections2d)
        return numpy.where(labeled_array > 0, labeled_array + iterator, 0).astype(connectedElements2d.dtype)

    def findLesions(self, reference):
        # preprocessing label
        referenceTemporaryCopy = reference.copy()
        referenceTemporaryCopy[referenceTemporaryCopy < 2] = 0

        # NFS
        referenceTemporaryCopy[referenceTemporaryCopy == 24] = 35

        if False:
            pass
            # Combines all lesions in arteries into one group
            # RCA
            #referenceTemporaryCopy[(referenceTemporaryCopy >= 4) & (referenceTemporaryCopy <= 7)] = 3

            # LM
            #referenceTemporaryCopy[(referenceTemporaryCopy >= 9) & (referenceTemporaryCopy <= 12)] = 8

            # LAD
            #referenceTemporaryCopy[(referenceTemporaryCopy >= 14) & (referenceTemporaryCopy <= 17)] = 13

            # LCX
            #referenceTemporaryCopy[(referenceTemporaryCopy >= 19) & (referenceTemporaryCopy <= 22)] = 18

            # RIM
            # referenceTemporaryCopy[(referenceTemporaryCopy == 23)] = 23

            # AORTA
            #referenceTemporaryCopy[(referenceTemporaryCopy >= 26) & (referenceTemporaryCopy <= 28)] = 25

        if self.calculationMode == "3d":
            structure = numpy.array([[[0, 0, 0],
                                       [0, 1, 0],
                                       [0, 0, 0]],

                                      [[0, 1, 0],
                                       [1, 1, 1],
                                       [0, 1, 0]],

                                      [[0, 0, 0],
                                       [0, 1, 0],
                                       [0, 0, 0]]])

        elif self.calculationMode == "2d":
            structure = numpy.array([[[0, 0, 0],
                                       [0, 0, 0],
                                       [0, 0, 0]],

                                      [[0, 1, 0],
                                       [1, 1, 1],
                                       [0, 1, 0]],

                                      [[0, 0, 0],
                                       [0, 0, 0],
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

        return (connectedElements, len(numpy.unique(connectedElements)) - 1)

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

        sliceNumber = 0
        #threads = []
        for slice in slicesDict:
        #    thread = threading.Thread(target=self.jsonSliceLoop, args=[patientID, seriesInstanceUID, it, lesion, slice, sliceNumber, slicesDict])
        #    thread.start()
        #    threads.append(thread)
            self.jsonSliceLoop(patientID, seriesInstanceUID, it, lesion, slice, sliceNumber, slicesDict)

            sliceNumber += 1

        #for thread in threads:
        #    thread.join()

    def jsonSliceLoop(self, patientID, seriesInstanceUID, it, lesion, slice, sliceNumber, slicesDict):
        sliceArray = lesion[numpy.in1d(lesion[:, 0], slice)]

        #needed to check if lesions are seperated in 2d but connected in 3d
        maxCoordinate = 513#max(max(sliceArray[:, 1:2])) + 1

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

        self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceNumber] = {}
        self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceNumber]["voxelCount2D"] = slicesDict[slice]
        self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceNumber]["labeledAs"] = {}

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

            self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceNumber]["labeledAs"] = labelsSummary
            self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceNumber]["maxAttenuation"] = None
        else:
            self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceNumber]["maxAttenuation"] = max(max(sliceArray[:, 3:4]))

            arteryId = sliceArray[:, 4:5]
            arteries, arteryCount = numpy.unique(arteryId, return_counts=True)
            arteryDict = dict(zip(arteries, arteryCount))

            for artery in arteryDict:
                self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceNumber]["labeledAs"][self.arteryId[artery]] = arteryDict[artery]

    def calculateLesions(self, image, reference, connectedElements3d, patientID, seriesInstanceUID):
        lesionPositionList = []

        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = [executor.submit(self.lesionPositionListEntry, connectedElements3d, index, image, reference) for index in range(1, connectedElements3d[1] + 1)]

            for future in concurrent.futures.as_completed(results):
                lesionPositionList.append(future.result())

        it = 0
        #threads = []
        for lesion in lesionPositionList:
        #    thread = threading.Thread(target=self.jsonLesionLoop, args=[lesion, it, patientID, seriesInstanceUID])
        #    thread.start()
        #    threads.append(thread)
            self.jsonLesionLoop(lesion, it, patientID, seriesInstanceUID)

            it += 1

        #for thread in threads:
        #    thread.join()

    def agatstonScore(self, voxelLength, voxelCount, attenuation, ratio):
        score = 0.0

        if (voxelLength != None) and (voxelCount != None) and (attenuation != None) and (ratio != None):
            voxelArea = voxelLength * voxelLength
            lesionArea = voxelArea * voxelCount

            if attenuation >= 130: #check if 1mm
                score = lesionArea * self.densityFactor(attenuation) * ratio

        return score

    def calculateScore(self, image, reference, patientID, seriesInstanceUID):
        connectedElements = self.findLesions(reference)

        if self.calculationMode == "3d":
            self.calculateLesions(image, reference, connectedElements, patientID, seriesInstanceUID)

            total = {}

            total["PatientID"] = patientID
            total["SeriesInstanceUID"] = seriesInstanceUID

            for key in self.Items:
                total[key] = 0.0

            for lesionsJson in self.exportJson[patientID][seriesInstanceUID]["lesions"]:
                for sliceJson in self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"]:
                    attenuation = self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["maxAttenuation"]

                    if attenuation is not None:
                        for arteryJson in self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["labeledAs"]:
                            voxelCount = self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["labeledAs"][arteryJson]
                            voxelLength = self.exportJson[patientID][seriesInstanceUID]["voxelLength"]

                            score = self.agatstonScore(voxelLength, voxelCount, attenuation, self.exportJson[patientID][seriesInstanceUID]["sliceRatio"])

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

        elif self.calculationMode == "2d":
            lesionArray = []

            with concurrent.futures.ThreadPoolExecutor() as executor:
                results = [executor.submit(self.searchLesionPosition, connectedElements, image, reference, index) for index in
                           range(1, connectedElements[1] + 1)]

                for future in concurrent.futures.as_completed(results):
                    lesionArray.append(future.result())

            export = []

            for elements in lesionArray:
                array = numpy.array(elements)
                maxDensity = max(array.max(axis=1))

                arteryId = array[:, 1:2]
                unique, counts = numpy.unique(arteryId, return_counts=True)
                count = dict(zip(unique, counts))

                exportedScores = {}

                for item in count:
                    # ratio if slice thickness is not 3mm
                    voxelLength = self.exportJson[patientID][seriesInstanceUID]["voxelLength"]
                    exportedScores[item] = self.agatstonScore(voxelLength, count[item], maxDensity, self.exportJson[patientID][seriesInstanceUID]["sliceRatio"])

                export.append(exportedScores)

            return export

    def exportScore(self, ctImagePath, labelPath, sliceThickness):
        # Exporting CSV
        file = self.processFilename(labelPath)

        ctImage = sitk.ReadImage(ctImagePath)
        labelImage = sitk.ReadImage(labelPath)

        # Convert the image to a numpy array first and then shuffle the dimensions to get axis in the order z,y,x
        ctImageArray = sitk.GetArrayFromImage(ctImage)
        labelImageArray = sitk.GetArrayFromImage(labelImage)

        # Read the spacing along each dimension
        spacing = numpy.array(list(reversed(ctImage.GetSpacing())))

        exportData = {}
        exportData["PatientID"] = file[2]
        exportData["SeriesInstanceUID"] = file[3]

        self.exportJson[file[2]] = {}
        self.exportJson[file[2]][file[3]] = {}
        self.exportJson[file[2]][file[3]]["sliceRatio"] = sliceThickness / 3.0
        self.exportJson[file[2]][file[3]]["voxelLength"] = spacing[1]  # voxel length in mm
        self.exportJson[file[2]][file[3]]["lesions"] = {}

        if self.calculationMode == "3d":
            return self.calculateScore(ctImageArray, labelImageArray, file[2], file[3])
        elif self.calculationMode == "2d":
            combinedAgatstonScores = self.combineSlicesScores(
                self.calculateScore(ctImageArray, labelImageArray, file[2], file[3]))

            for key in self.Items:
                content = self.Items[key]
                if isinstance(content, list):
                    total = 0.0
                    for element in content:
                        if element in combinedAgatstonScores:
                            total += combinedAgatstonScores[element]

                    exportData[key] = total

                elif isinstance(content, int):
                    if content in combinedAgatstonScores:
                        exportData[key] = combinedAgatstonScores[content]
                    else:
                        exportData[key] = 0.0

            return exportData

    def searchLesionPosition(self, array, image, reference, index):
        # gives position in 3d space where value equals the index => all voxels of a lesion in 2d space
        positionArray = numpy.array(list(zip(*numpy.where(array[0] == index))))
        dataArray = []

        for element in positionArray:
            dataArray.append(
                [
                    image[element[0]][element[1]][element[2]],
                    reference[element[0]][element[1]][element[2]]
                ]
            )

        return dataArray

    def densityFactor(self, maxDensity):
        if maxDensity >= 130 and maxDensity <= 199:
            return 1
        if maxDensity >= 200 and maxDensity <= 299:
            return 2
        if maxDensity >= 300 and maxDensity <= 399:
            return 3
        if maxDensity >= 400:
            return 4

    def combineSlicesScores(self, scores):
        totalScore = {}

        for items in scores:
            if items:
                for key in items:
                    if key in totalScore:
                        totalScore[key] = totalScore[key] + items[key]
                    else:
                        totalScore[key] = items[key]

        return totalScore

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
