from __main__ import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from socket import socket, AF_INET, SOCK_DGRAM
import socket
import unittest
import os
import SimpleITK as sitk
import sitkUtils as su
import EditorLib
import Editor
import LabelStatistics
from EditorLib.EditUtil import EditUtil
from glob import glob
import random
import sys
import os
import json
from SegmentEditor import SegmentEditorWidget
import numpy as np
dirname = os.path.dirname(os.path.abspath(__file__))
dir_src = os.path.dirname(os.path.dirname(dirname))
sys.path.append(dir_src)
from settings.settings import Settings
import time
from sys import platform
from SimpleITK import ConnectedComponentImageFilter

ALAction = dict({'ID': -1, 
                 'fp_image': '', 
                  'fp_label_lesion': '',
                  'fp_label': '',
                  'fp_label_lesion_pred': '',
                  'fp_label_pred': '',
                  'IDX': [[]],
                  'QUERY': (0,0),
                  'SLICE': -1,
                  'action': '', # 'LABEL_LESION', 'LABEL_REGION', 'LABEL_REGION_NEW', 'LABEL_LESION_NEW'
                  'MSG': '',
                  'COMMAND': '',
                  'STATUS': 'OPEN',         # OPEN, CLOSED
                  'UNCERTAINT': False}) 

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
    
class XALabelerModule(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "XALabelerModule" # TODO make this more human readable by adding spaces
    self.parent.categories = ["Examples"]
    self.parent.dependencies = []
    self.parent.contributors = ["John Doe (AnyWare Corp.)"] # replace with "Firstname Lastname (Organization)"
    self.parent.helpText = """
This is an example of scripted loadable module bundled in an extension.
It performs a simple thresholding on the input volume and optionally captures a screenshot.
"""
    self.parent.helpText += self.getDefaultModuleDocumentationLink()
    self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc.
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""" # replace with organization, grant and thanks.

#
# XALabelerModuleWidget
#
class XALabelerModuleWidget:
    def __init__(self, parent = None):
        self.currentRegistrationInterface = None
        self.changeIslandTool = None
        self.editUtil = EditorLib.EditUtil.EditUtil()
        #self.inputImageNode = None
        self.localCardiacEditorWidget = None
        self.settings=Settings()
        self.images=[]
        self.localXALEditorWidget = None
        self.refAction = ALAction.copy()
        self.REFValue = 200
        self.UCValue = 201
        self.continueLabeling = False

        if not parent:
            self.parent = slicer.qMRMLWidget()
            self.parent.setLayout(qt.QVBoxLayout())
            self.parent.setMRMLScene(slicer.mrmlScene)
        else:
            self.parent = parent
        self.layout = self.parent.layout()
        if not parent:
            self.setup()
            self.parent.show()
        
        # Settings filepath
        currentFile = os.path.dirname(os.path.abspath(__file__))
        self.filepath_settings = os.path.dirname(os.path.dirname(os.path.dirname(currentFile))) + '/data/settings.json'
        
    def nodeExist(self, name):
        nodes=slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
        nodeFound = False
        for node in nodes:
            if name==node.GetName():
                nodeFound = True
        return nodeFound

    def setup(self):
        # Instantiate and connect widgets ...
        if True:
            """Developer interface"""
            reloadCollapsibleButton = ctk.ctkCollapsibleButton()
            reloadCollapsibleButton.text = "Advanced - Reload && Test"
            reloadCollapsibleButton.collapsed = False
            self.layout.addWidget(reloadCollapsibleButton)
            reloadFormLayout = qt.QFormLayout(reloadCollapsibleButton)
            
            # reload button
            # (use this during development, but remove it when delivering
            #  your module to users)
            self.reloadButton = qt.QPushButton("Reload")
            self.reloadButton.toolTip = "Reload this module."
            self.reloadButton.name = "XALabelerModule Reload"
            reloadFormLayout.addWidget(self.reloadButton)
            self.reloadButton.connect('clicked()', self.onReload)

            # reload and test button
            # (use this during development, but remove it when delivering
            #  your module to users)
            self.reloadAndTestButton = qt.QPushButton("Reload and Test")
            self.reloadAndTestButton.toolTip = "Reload this module and then run the self tests."
            reloadFormLayout.addWidget(self.reloadAndTestButton)
            self.reloadAndTestButton.connect('clicked()', self.onReloadAndTest)

        # Collapsible button for Input Parameters
        self.measuresCollapsibleButton = ctk.ctkCollapsibleButton()
        self.measuresCollapsibleButton.text = "Refinement"
        self.layout.addWidget(self.measuresCollapsibleButton)

        # Collapsible button for Label Parameters
        self.labelsCollapsibleButton = ctk.ctkCollapsibleButton()
        self.labelsCollapsibleButton.text = "Label Parameters"
        #self.layout.addWidget(self.labelsCollapsibleButton)

        # Layout within the sample collapsible button
        self.measuresFormLayout = qt.QFormLayout(self.measuresCollapsibleButton)

        # Start client
        startButton = qt.QPushButton("START REFINEMENT")
        startButton.toolTip = "Start refinement"
        startButton.setStyleSheet("background-color: rgb(230,241,255)")
        self.measuresFormLayout.addRow(startButton)
        startButton.connect('clicked(bool)', self.onStartButtonClicked)
        self.startButton = startButton
        
        # Next button
        nextButton = qt.QPushButton("NEXT QUERY")
        nextButton.toolTip = "Get next query"
        nextButton.setStyleSheet("background-color: rgb(230,241,255)")
        nextButton.enabled = False
        self.measuresFormLayout.addRow(nextButton)
        nextButton.connect('clicked(bool)', self.onNextButtonClicked)
        self.nextButton = nextButton

        # SKIP button
        skipButton = qt.QPushButton("SKIP QUERY")
        skipButton.toolTip = "Skip query"
        skipButton.setStyleSheet("background-color: rgb(230,241,255)")
        skipButton.enabled = False
        self.measuresFormLayout.addRow(skipButton)
        skipButton.connect('clicked(bool)', self.onSkipButtonClicked)
        self.skipButton = skipButton
        
        # Save query button
        saveQueryButton = qt.QPushButton("SAVE QUERY")
        saveQueryButton.toolTip = "Save query"
        saveQueryButton.setStyleSheet("background-color: rgb(230,241,255)")
        saveQueryButton.enabled = False
        self.measuresFormLayout.addRow(saveQueryButton)
        saveQueryButton.connect('clicked(bool)', self.onSaveQueryButtonClicked)
        self.saveQueryButton = saveQueryButton
        
        # Stop client
        stopButton = qt.QPushButton("STOP REFINEMENT")
        stopButton.toolTip = "Stop refinement"
        stopButton.setStyleSheet("background-color: rgb(230,241,255)")
        stopButton.enabled = False
        self.measuresFormLayout.addRow(stopButton)
        stopButton.connect('clicked(bool)', self.onStopButtonClicked)
        self.stopButton = stopButton
        
        # Set albel
        label = qt.QLabel("Please solve action")
        self.measuresFormLayout.addRow(label)
        self.label = label
        
        
        
        
        # Collapsible button for Input Parameters
        self.measuresCollapsibleButton2 = ctk.ctkCollapsibleButton()
        self.measuresCollapsibleButton2.text = "Select additional refinement action"
        self.layout.addWidget(self.measuresCollapsibleButton2)
        
        # Layout within the sample collapsible button
        self.measuresFormLayoutH = qt.QFormLayout(self.measuresCollapsibleButton2)

        # LABEL_LESION_BUTTON
        LABEL_LESION_BUTTON = qt.QPushButton("Verify lesion label")
        LABEL_LESION_BUTTON.toolTip = "Stop refinement2"
        LABEL_LESION_BUTTON.setStyleSheet("background-color: rgb(230,241,255)")
        LABEL_LESION_BUTTON.enabled = False
        self.measuresFormLayoutH.addRow(LABEL_LESION_BUTTON)
        LABEL_LESION_BUTTON.connect('clicked(bool)', self.onLABEL_LESION_BUTTONClicked)
        self.LABEL_LESION_BUTTON = LABEL_LESION_BUTTON
        
        # LABEL_REGION_BUTTON
        LABEL_REGION_BUTTON = qt.QPushButton("Refine coronary artery region")
        LABEL_REGION_BUTTON.toolTip = "Stop refinement2"
        LABEL_REGION_BUTTON.setStyleSheet("background-color: rgb(230,241,255)")
        LABEL_REGION_BUTTON.enabled = False
        self.measuresFormLayoutH.addRow(LABEL_REGION_BUTTON)
        LABEL_REGION_BUTTON.connect('clicked(bool)', self.onLABEL_REGION_BUTTONClicked)
        self.LABEL_REGION_BUTTON = LABEL_REGION_BUTTON

        # LABEL_REGION_BUTTON
        LABEL_NEW_BUTTON = qt.QPushButton("Label new coronary artery region")
        LABEL_NEW_BUTTON.toolTip = "Stop refinement2"
        LABEL_NEW_BUTTON.setStyleSheet("background-color: rgb(230,241,255)")
        LABEL_NEW_BUTTON.enabled = False
        self.measuresFormLayoutH.addRow(LABEL_NEW_BUTTON)
        LABEL_NEW_BUTTON.connect('clicked(bool)', self.onLABEL_NEW_BUTTONClicked)
        self.LABEL_NEW_BUTTON = LABEL_NEW_BUTTON 
        
#        # LABEL_REGION_BUTTON
#        LABEL_REGION_NEW_BUTTON = qt.QPushButton("Label new coronary artery region")
#        LABEL_REGION_NEW_BUTTON.toolTip = "Stop refinement2"
#        LABEL_REGION_NEW_BUTTON.setStyleSheet("background-color: rgb(230,241,255)")
#        LABEL_REGION_NEW_BUTTON.enabled = False
#        self.measuresFormLayoutH.addRow(LABEL_REGION_NEW_BUTTON)
#        LABEL_REGION_NEW_BUTTON.connect('clicked(bool)', self.onLABEL_REGION_NEW_BUTTONClicked)
#        self.LABEL_REGION_NEW_BUTTON = LABEL_REGION_NEW_BUTTON 
#        
#        # LABEL_LESION_NEW_BUTTON
#        LABEL_LESION_NEW_BUTTON = qt.QPushButton("Label new lesions")
#        LABEL_LESION_NEW_BUTTON.toolTip = "Stop refinement2"
#        LABEL_LESION_NEW_BUTTON.setStyleSheet("background-color: rgb(230,241,255)")
#        LABEL_LESION_NEW_BUTTON.enabled = False
#        self.measuresFormLayoutH.addRow(LABEL_LESION_NEW_BUTTON)
#        LABEL_LESION_NEW_BUTTON.connect('clicked(bool)', self.onLABEL_LESION_NEW_BUTTONClicked)
#        self.LABEL_LESION_NEW_BUTTON = LABEL_LESION_NEW_BUTTON 

        # LABEL_LESION_NEW_BUTTON
        CONTINUE_BUTTON = qt.QPushButton("CONTINUE")
        CONTINUE_BUTTON.toolTip = "Continue labeling"
        CONTINUE_BUTTON.setStyleSheet("background-color: rgb(230,241,255)")
        CONTINUE_BUTTON.enabled = False
        self.measuresFormLayoutH.addRow(CONTINUE_BUTTON)
        CONTINUE_BUTTON.connect('clicked(bool)', self.onLABEL_CONTINUE_BUTTONClicked)
        self.CONTINUE_BUTTON = CONTINUE_BUTTON 
        
        # LABEL_LESION_NEW_BUTTON
        UNCERTAINTY_BUTTON = qt.QPushButton("Add UNCERTAIN label")
        UNCERTAINTY_BUTTON.toolTip = "Stop refinement2"
        UNCERTAINTY_BUTTON.setStyleSheet("background-color: rgb(230,241,255)")
        UNCERTAINTY_BUTTON.enabled = False
        self.measuresFormLayoutH.addRow(UNCERTAINTY_BUTTON)
        UNCERTAINTY_BUTTON.connect('clicked(bool)', self.onLABEL_UNCERTAINTY_BUTTONClicked)
        self.UNCERTAINTY_BUTTON = UNCERTAINTY_BUTTON    
        
        
#        # The Input Volume Selector
#        self.inputFrame = qt.QFrame(self.measuresCollapsibleButton)
#        self.inputFrame.setLayout(qt.QHBoxLayout())
#        self.measuresFormLayout.addRow(self.inputFrame)
#        
#        inputSelector = qt.QLabel("Input Volume: ", self.inputFrame)
#        self.inputFrame.layout().addWidget(inputSelector)
#        inputSelector = slicer.qMRMLNodeComboBox(self.inputFrame)
#        inputSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
#        inputSelector.addEnabled = False
#        inputSelector.removeEnabled = False
#        inputSelector.setMRMLScene( slicer.mrmlScene )
#        self.inputSelector = inputSelector
#        self.inputSelector.currentNodeChanged.connect(self.onCurrentNodeChanged)
#        self.measuresFormLayout.addRow(self.inputSelector)
#        #self.inputFrame.layout().addWidget(self.inputSelector)
#
#        # Collapsible button for Output Parameters
#        self.measuresCollapsibleButtonOutput = ctk.ctkCollapsibleButton()
#        self.measuresCollapsibleButtonOutput.text = "Output Parameters"
#        self.layout.addWidget(self.measuresCollapsibleButtonOutput)
#        
#        # Layout within the sample collapsible button
#        self.measuresFormLayoutOutput = qt.QFormLayout(self.measuresCollapsibleButtonOutput)
#
#        # Apply background growing 
#        bgGrowingButton = qt.QPushButton("Apply background growing")
#        bgGrowingButton.toolTip = "Apply background growi"
#        bgGrowingButton.setStyleSheet("background-color: rgb(230,241,255)")
#        bgGrowingButton.enabled = False
#        self.measuresFormLayoutOutput.addRow(bgGrowingButton)
#        bgGrowingButton.connect('clicked(bool)', self.onBgGrowingButtonButtonClicked)
#        self.bgGrowingButton = bgGrowingButton
#        
#        # Save output button
#        saveOutputButton = qt.QPushButton("Save output data")
#        saveOutputButton.toolTip = "Save data"
#        saveOutputButton.setStyleSheet("background-color: rgb(230,241,255)")
#        saveOutputButton.enabled = False
#        self.measuresFormLayoutOutput.addRow(saveOutputButton)
#        saveOutputButton.connect('clicked(bool)', self.onSaveOutputButtonClicked)
#        self.saveOutputButton = saveOutputButton
#        
#        # Delete scans button
#        deleteButton = qt.QPushButton("Delete data")
#        deleteButton.toolTip = "Delete data"
#        deleteButton.setStyleSheet("background-color: rgb(230,241,255)")
#        deleteButton.enabled = False
#        self.measuresFormLayoutOutput.addRow(deleteButton)
#        deleteButton.connect('clicked(bool)', self.onDeleteButtonClicked)
#        self.deleteButton = deleteButton
        
        # Add vertical spacer
        self.layout.addStretch(1)

        # sets the layout to Red Slice Only
        layoutManager = slicer.app.layoutManager()
        layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)
        self.layoutManager = layoutManager
        
        # Load color table
        dirname = os.path.dirname(os.path.abspath(__file__))
        filepath_colorTable = dirname + '\\CardiacAgatstonMeasuresLUT.ctbl'
        slicer.util.loadColorTable(filepath_colorTable)

        # Read settings file
        if os.path.isfile(self.filepath_settings):
            #self.writeSettings(self.filepath_settings)
            self.readSettings(self.filepath_settings)
        else:
            self.writeSettings(self.filepath_settings)
            self.readSettings(self.filepath_settings)
            
        dirname = os.path.dirname(os.path.abspath(__file__))
        filepath_colorTable = dirname + '/CardiacAgatstonMeasuresLUT.ctbl'
        
        if self.settings['MODE'] == 'CACS':
            self.settings['CACSTree'].createColorTable_CACS(filepath_colorTable)
        if self.settings['MODE'] == 'CACS_REF':
            self.settings['CACSTree'].createColorTable_CACS_REF(filepath_colorTable, self.REFValue, self.UCValue)
            
        #self.settings['CACSTree'].createColorTable_CACS_REF_LESION(filepath_colorTable, self.REFValue, self.UCValue)
        
        #self.settings['MODE'] = 'CACS'
        #self.settings['MODE'] = 'CACS_REF'
        
#        # Create color table
#        if self.settings['MODE']=='CACSTREE_CUMULATIVE':
#            self.settings['CACSTree'].createColorTable(filepath_colorTable)
#        elif self.settings['MODE']=='CACS':
#            self.settings['CACSTree'].createColorTable_CACS(filepath_colorTable)
#        elif self.settings['MODE']=='CACS_REF':
#            self.settings['CACSTree'].createColorTable_CACS_REF(filepath_colorTable)
#        else:
#            raise ValueError('MODE' + self.settings['MODE'] + 'does not exist!')
        
        # Load color table
        slicer.util.loadColorTable(filepath_colorTable)

    def onCurrentNodeChanged(self):
        # Create label
        inputImageNode = self.inputSelector.currentNode()
        if inputImageNode is not None:
            inputVolumeName = inputImageNode.GetName()
            calciumName = inputVolumeName + '-label'
            node_label = slicer.util.getFirstNodeByName(calciumName)
            if node_label is None and 'label' not in inputVolumeName and not inputVolumeName == '1':
                inputVolume = su.PullVolumeFromSlicer(inputVolumeName)
                labelImage = sitk.Image(inputVolume.GetSize(), sitk.sitkInt16)
                labelImage.CopyInformation(inputVolume)
                su.PushLabel(labelImage, calciumName)
                self.assignLabelLUT(calciumName)
        
        
    def writeSettings(self, filepath_settings):
        self.settings.writeSettings(filepath_settings)
    
    def readSettings(self, filepath_settings):
        self.settings.readSettings(filepath_settings)

    def assignLabelLUT(self, calciumName):
        # Set the color lookup table (LUT) to the custom CardiacAgatstonMeasuresLUT
        self.calciumLabelNode = slicer.util.getNode(calciumName)
        self.CardiacAgatstonMeasuresLUTNode = slicer.util.getNode(pattern='CardiacAgatstonMeasuresLUT')
        CardiacAgatstonMeasuresLUTID = self.CardiacAgatstonMeasuresLUTNode.GetID()
        calciumDisplayNode = self.calciumLabelNode.GetDisplayNode()
        calciumDisplayNode.SetAndObserveColorNodeID(CardiacAgatstonMeasuresLUTID)
    
    def startClient(self):
        print("Starting client")
        self.dest = ("127.0.0.1", 20001)
        self.bufferSize = 2048

    def onStartButtonClicked(self):
        # Start client
        self.startClient()
        self.nextButton.enabled = True
        self.skipButton.enabled = True
        self.saveQueryButton.enabled = True
        self.stopButton.enabled = True
        #self.LABEL_LESION_BUTTON.enabled = True
        #self.LABEL_REGION_BUTTON.enabled = True
        #self.LABEL_NEW_BUTTON.enabled = True
        self.UNCERTAINTY_BUTTON.enabled = True

    def onStopButtonClicked(self):
        # Save output
        self.saveOutput(overwrite=False)
        self.nextButton.enabled = False
        self.skipButton.enabled = False
        self.saveQueryButton.enabled = False
        self.stopButton.enabled = False
        self.LABEL_LESION_BUTTON.enabled = False
        self.LABEL_REGION_BUTTON.enabled = False
        self.LABEL_NEW_BUTTON.enabled = False
        self.UNCERTAINTY_BUTTON.enabled = False
        #self.LABEL_LESION_NEW_BUTTON.enabled = False
        #self.LABEL_REGION_NEW_BUTTON.enabled = False
        
    def onLABEL_LESION_BUTTONClicked(self):
        refAction = self.refAction
        refAction['action'] = 'LABEL_LESION'
        self.refine_lesion(refAction)
        
    def onLABEL_REGION_BUTTONClicked(self):
        refAction = self.refAction
        refAction['action'] = 'LABEL_REGION'
        self.refine_region(refAction)
        
    def onLABEL_NEW_BUTTONClicked(self):
        refAction = self.refAction
        refAction['action'] = 'LABEL_NEW'
        self.refine_region_new(refAction)

    def onLABEL_LESION_NEW_BUTTONClicked(self):
        refAction = self.refAction
        refAction['action'] = 'LABEL_LESION_NEW'
        self.refine_lesion_new(refAction)
    
    def onLABEL_CONTINUE_BUTTONClicked(self):
        self.continueLabeling = True
        self.CONTINUE_BUTTON.enabled = False
        self.editUtil.toggleLabelOutline
        self.refine_lesion(self.refAction, use_pred=True)
        
    def onLABEL_UNCERTAINTY_BUTTONClicked(self):
        print('onLABEL_UNCERTAINTY_BUTTONClicked')
        refAction = self.refAction
        refAction['UNCERTAINT'] = True
        
    def onNextButtonClicked(self):
        # Start client
        #msg = ("NEXT").encode('utf-8')
        #msg = (refAction_str).encode('utf-8')
        self.refAction['COMMAND'] = self.refAction['COMMAND'] + 'NEXT'
        self.refAction['STATUS'] = 'SOLVED'
        ALAction_str = json.dumps(self.refAction)
        msg = (ALAction_str).encode('utf-8')
        
        UDPClientSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        UDPClientSocket.settimeout(30)
        print('Sending NEXT command')
        UDPClientSocket.sendto(msg, self.dest)

        try:
            msgFromServer = UDPClientSocket.recvfrom(self.bufferSize)
            msg = msgFromServer[0]
            refAction = json.loads(msg)
            self.refAction = refAction
            print('Processing query: ', refAction['QUERY'])
        except:
            print('Could not get next query. Please check the server!')
            
        if self.refAction['action'] == '':
            pass
        elif self.refAction['action'] == 'LABEL_LESION':
            self.refine_lesion(refAction, use_pred=False, save=True)
        elif self.refAction['action'] == 'LABEL_REGION':
            self.refine_region(refAction, save=True)
        elif self.refAction['action'] == 'LABEL_NEW':
            self.refine_new(refAction, save=True)
        else:
            raise ValueError('Action: ' + refAction['action'] + ' does not exist.')
            
    def onSkipButtonClicked(self):

        self.refAction['COMMAND'] = self.refAction['COMMAND'] + 'NEXT'
        self.refAction['STATUS'] = 'SKIPED'
        ALAction_str = json.dumps(self.refAction)
        msg = (ALAction_str).encode('utf-8')
        
        UDPClientSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
        UDPClientSocket.settimeout(10)
        print('Sending NEXT command')
        UDPClientSocket.sendto(msg, self.dest)

        try:
            msgFromServer = UDPClientSocket.recvfrom(self.bufferSize)
            msg = msgFromServer[0]
            refAction = json.loads(msg)
            self.refAction = refAction
        except:
            print('Could not get next query. Please check the server!')
            
        if self.refAction['action'] == '':
            pass
        elif self.refAction['action'] == 'LABEL_LESION':
            self.refine_lesion(refAction, use_pred=False, save=False)
        elif self.refAction['action'] == 'LABEL_REGION':
            self.refine_region(refAction, save=False, showREFValue=True)
        elif self.refAction['action'] == 'LABEL_NEW':
            self.refine_new(refAction, save=False)
        else:
            raise ValueError('Action: ' + refAction['action'] + ' does not exist.')
    
    def onSaveQueryButtonClicked(self):
        self.saveOutput(overwrite=False)

    def refine_new(self, refAction, save=True):
        print('refine_new')
        self.nextButton.enabled = False
        self.skipButton.enabled = False
        self.saveQueryButton.enabled = False
        self.CONTINUE_BUTTON.enabled = True

        
        self.continueLabeling = False
        self.refine_region(refAction, save=save, showREFValue=False)
 
    def refine_region(self, refAction, use_pred=True, save=True, showREFValue=True):
        print('refine_region')
        # Save all existing nodes
        filepath = refAction['fp_image'].encode("utf-8")
        _, imagename,_ = splitFilePath(filepath)
        
        self.deleteNodesREFValue()
        if save:
            self.saveOutput(overwrite=False)
        self.deleteNodes(imagename)
 
        imageFound = self.nodeExist(imagename)
              
        # Load image
        if not imageFound:
            #self.saveOutput(overwrite=False)  
            print('Loading: ' + filepath)
            properties={'name': imagename}
            node = slicer.util.loadVolume(filepath, returnNode=True, properties=properties)[1]
            node.SetName(imagename)  

        if use_pred:
            filepath_label_org = refAction['fp_label_pred'].encode("utf-8")
            filepath_label = self.load_label_lesion_pred(filepath_label_org)
            _, labelname,_ = splitFilePath(filepath_label)
        else:
            filepath_label_org = refAction['fp_label'].encode("utf-8")
            if filepath_label_org=='':
                filepath_label = self.load_label_lesion_pred(filepath_label_org)
                _, labelname,_ = splitFilePath(filepath_label)
            else:
                filepath_label = filepath_label_org
                _, labelname,_ = splitFilePath(filepath_label)
                
#        # Load label
#        if use_pred
#            filepath_label_org = refAction['fp_label_pred'].encode("utf-8")
#            _, labelname,_ = splitFilePath(filepath_label_org)
#            folder, labelname,_ = splitFilePath(filepath_label_org)
#            filepath_label_list = sorted(glob(os.path.join(folder, labelname + '-*.nrrd')))
#            if len(filepath_label_list)>0:
#                filepath_label = filepath_label_list[-1]
#            else:
#                filepath_label = filepath_label_org
#        else:
        
        label_im = sitk.ReadImage(filepath_label)
        print('Loading: ' + filepath_label)
        label = sitk.GetArrayFromImage(label_im)

        IDX = refAction['IDX']
        sliceNumber = refAction['SLICE']

        labelFound = self.nodeExist(labelname)

        # Create binary mask
        mask = np.zeros(label.shape)
        IDX = refAction['IDX']
        SLICE = int(refAction['SLICE'])
        NumPixel = len(IDX[0])
        for p in range(NumPixel):
            x=IDX[0][p]
            y=IDX[1][p]
            mask[SLICE, x, y] = 1

        # Set label
        if not labelFound:
            if showREFValue:
                label = label * (1-mask) + self.REFValue * mask
            labelSitk = sitk.GetImageFromArray(label)
            labelSitk.CopyInformation(label_im)
            node = su.PushVolumeToSlicer(labelSitk, name=labelname, className='vtkMRMLLabelMapVolumeNode')
            node.SetName(labelname)
            slicer.util.setSliceViewerLayers(label = node, foreground = node, foregroundOpacity = 0.3, labelOpacity = 0.0)
            self.assignLabelLUT(labelname)
        else:
            node = slicer.mrmlScene.GetFirstNodeByName(labelname)
            label_node = slicer.util.arrayFromVolume(node)
            label = label_node * (1-mask) + label * mask
            slicer.util.updateVolumeFromArray(node, label)
            self.assignLabelLUT(labelname)
            
        # Show action
        self.label.setText('ACTION: ' + refAction['action'])

        # Change view
        red = self.layoutManager.sliceWidget('Red')
        redLogic = red.sliceLogic()
        offset = redLogic.GetSliceOffset()
        origen = label_im.GetOrigin()
        offset = origen[2] + sliceNumber * 3.0
        redLogic.SetSliceOffset(offset)
        
        # Creates and adds the custom Editor Widget to the module
        if self.localXALEditorWidget is None:
            self.localXALEditorWidget = XALEditorWidget(parent=self.parent, showVolumesFrame=False, settings=self.settings)
            self.localXALEditorWidget.setup()
            self.localXALEditorWidget.enter()
        self.localXALEditorWidget.toolsBox.UCchangeIslandButton.setEnabled(False)
        
        # Set LowerPaintThreshold
        self.lowerThresholdValue = -5000
        self.upperThresholdValue = 5000
        self.setLowerPaintThreshold()
        
    def load_label_lesion_pred(self, filepath_label_org):
        _, labelname,_ = splitFilePath(filepath_label_org)
        folder, labelname,_ = splitFilePath(filepath_label_org)
        filepath_label_list = sorted(glob(os.path.join(folder, labelname + '-*.nrrd')))
        if len(filepath_label_list)>0:
            filepath_label = filepath_label_list[-1]
        else:
            filepath_label = filepath_label_org
        return filepath_label
        
    def refine_lesion(self, refAction, use_pred=False, save=True):
        print('refine_lesion')
        # Load label
        if use_pred:
            filepath_label_org = refAction['fp_label_lesion_pred'].encode("utf-8")
            filepath_label = self.load_label_lesion_pred(filepath_label_org)
            _, labelname,_ = splitFilePath(filepath_label)
        else:
            filepath_label_org = refAction['fp_label_lesion'].encode("utf-8")
            if filepath_label_org=='':
                filepath_label = self.load_label_lesion_pred(filepath_label_org)
                _, labelname,_ = splitFilePath(filepath_label)
            else:
                filepath_label = filepath_label_org
                _, labelname,_ = splitFilePath(filepath_label)
            
        filepath = refAction['fp_image'].encode("utf-8")
        _, imagename,_ = splitFilePath(filepath)
        
        self.deleteNodesREFValue()
        if save:
            self.saveOutput(overwrite=False)
        self.deleteNodes(imagename)

        imageFound = self.nodeExist(imagename)

        # Load image
        if not imageFound:
            print('Loading: ' + filepath)
            properties={'name': imagename}
            node = slicer.util.loadVolume(filepath, returnNode=True, properties=properties)[1]
            node.SetName(imagename)        
            
        label_im = sitk.ReadImage(filepath_label)
        print('Loading: ' + filepath_label)
        label = sitk.GetArrayFromImage(label_im)
        
        # Create binary mask
        mask = np.zeros(label.shape)
        IDX = refAction['IDX']
        SLICE = int(refAction['SLICE'])
        NumPixel = len(IDX[0])
        for p in range(NumPixel):
            x=IDX[0][p]
            y=IDX[1][p]
            mask[SLICE, x, y] = 1

        labelFound = self.nodeExist(labelname)

        # Set label
        if not labelFound:
            if not use_pred:
                label = label * mask
            label = sitk.GetImageFromArray(label)
            label.CopyInformation(label_im)
            node = su.PushVolumeToSlicer(label, name=labelname, className='vtkMRMLLabelMapVolumeNode')
            node.SetName(labelname)
            slicer.util.setSliceViewerLayers(label = node, foreground = node, foregroundOpacity = 0.0, labelOpacity = 1.0)
            self.assignLabelLUT(labelname)
        else:
            node = slicer.mrmlScene.GetFirstNodeByName(labelname)
            label_node = slicer.util.arrayFromVolume(node)
            label = label_node * (1-mask) + label * mask
            slicer.util.updateVolumeFromArray(node, label)
            self.assignLabelLUT(labelname)

        # Show action
        self.label.setText('ACTION: ' + refAction['action'])
        
        # Change view
        red = self.layoutManager.sliceWidget('Red')
        redLogic = red.sliceLogic()
        offset = redLogic.GetSliceOffset()
        origen = label_im.GetOrigin()
        offset = origen[2] + SLICE * 3.0
        redLogic.SetSliceOffset(offset)
        
        # Creates and adds the custom Editor Widget to the module
        if self.localXALEditorWidget is None:
            self.localXALEditorWidget = XALEditorWidget(parent=self.parent, showVolumesFrame=False, settings=self.settings)
            self.localXALEditorWidget.setup()
            self.localXALEditorWidget.enter()
        self.localXALEditorWidget.toolsBox.UCchangeIslandButton.setEnabled(True)
        
    
        # Set LowerPaintThreshold
        self.lowerThresholdValue = 130
        self.upperThresholdValue = 1000
        self.setLowerPaintThreshold()
        
        self.nextButton.enabled = True
        self.skipButton.enabled = True
        self.saveQueryButton.enabled = True
        
    def refine_lesion_close(self):
        if self.localXALEditorWidget is not None:
            self.localXALEditorWidget.close()

    
    def setLowerPaintThreshold(self):
        # sets parameters for paint specific to KEV threshold level
        parameterNode = self.editUtil.getParameterNode()
        parameterNode.SetParameter("LabelEffect,paintOver","1")
        parameterNode.SetParameter("LabelEffect,paintThreshold","1")
        parameterNode.SetParameter("LabelEffect,paintThresholdMin","{0}".format(self.lowerThresholdValue))
        parameterNode.SetParameter("LabelEffect,paintThresholdMax","{0}".format(self.upperThresholdValue))

    def deleteNodesREFValue(self):
        nodes=slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
        for node in nodes:
            arr = slicer.util.arrayFromVolume(node)
            REFValueExist = (arr==self.REFValue).sum()
            if REFValueExist>0:
                slicer.mrmlScene.RemoveNode(node)
                

                
                
    def deleteNodes(self, delete_exception=[]):
        nodes=slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
        for node in nodes:
            nodename=node.GetName()
            if not any([name==nodename for name in delete_exception]):
                slicer.mrmlScene.RemoveNode(node)
    
    def onDeleteButtonClicked(self):
        # Deleta all old nodes
        self.deleteNodes()
        
        
#    def onDeleteButtonClicked(self):
#        # Deleta all old nodes
#        nodes=slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
#        for node in nodes:
#            slicer.mrmlScene.RemoveNode(node)
            
    def filterBG(self, image):
        # Filter labeled background
        arr = sitk.GetImageFromArray(image)
        compFilter = ConnectedComponentImageFilter()
        labeled_sitk = compFilter.Execute(arr==0)
        labeled = sitk.GetArrayFromImage(labeled_sitk)
        ncomponents = labeled.max()
        # Extract backgound index
        idx_max=-1
        pix_sum=-1
        for c in range(1,ncomponents+1):
            labeledc = labeled==c
            if labeledc.sum()>pix_sum:
                pix_sum = labeledc.sum()
                idx_max = c
        mask_bg = (labeled==idx_max)*1
        # Combine FG mask and BG mask
        mask_fg = image
        mask_fg[mask_fg==1]=0
        mask = mask_bg + mask_fg
        return mask
            
#    def filterBG(self, image):
#        image = image.astype(np.uint8)
#        _,imageThr = cv2.threshold(image,0.5,1,cv2.THRESH_BINARY)
#        contours, _ = cv2.findContours(imageThr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
#        mask = np.zeros(image.shape, dtype=np.uint8)
#        mask = cv2.drawContours(mask, contours, -1, (1), -1)
#        mask = 1-mask
#        return mask
        
    def onBgGrowingButtonButtonClicked(self):
        volumeNodes = slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
        for node in volumeNodes:
            volume_name = node.GetName()
            if 'label' in volume_name:
                arr = slicer.util.arrayFromVolume(node)
                image_sitk = su.PullVolumeFromSlicer(node)
                for i in range(0,arr.shape[0]):
                    image = arr[i,:,:]
                    if image.sum()>0: 
                        mask = self.filterBG(image)
                        #image = image + mask
                        image = mask
                    arr[i,:,:] = image
                sitkImageOutput = sitk.GetImageFromArray(arr)
                sitkImageOutput.CopyInformation(image_sitk)
                _ = su.PushVolumeToSlicer(sitkImageOutput,node)

    def onSaveOutputButtonClicked(self):
        self.saveOutput(overwrite=True)
        
    def outputFilepathSave(self, volume_name, folderpath_output):

        filename = volume_name
        SeriesInstanceUID = filename.split('_')[1] .split('-')[0]
        label=[]
        lesion=[]
        label_pred=[]
        lesion_pred=[]
        
        labelfiles = glob(folderpath_output + '/*.nrrd')
        SeriesInstanceUIDLabel=[]
        for labelfile in labelfiles:
            SeriesInstanceUIDLabel.append(splitFilePath(labelfile)[1].split('_')[1] .split('-')[0])
            
        for j,labelid in enumerate(SeriesInstanceUIDLabel):
            labelfile = labelfiles[j]
            #SeriesInstanceUIDLabel = splitFilePath(labelfile)[1].split('_')[1] .split('-')[0]
            if SeriesInstanceUID == labelid:
                if 'lesion-pred' in labelfile:
                    lesion_pred.append(labelfile)
                elif 'label-pred' in labelfile:
                    label_pred.append(labelfile)
                elif 'lesion' in labelfile:
                    lesion.append(labelfile)
                elif 'label' in labelfile:
                    label.append(labelfile)
                else:
                    raise ValueError('Filepath not correct!')
      
        if 'lesion-pred' in filename:
            if len(lesion_pred)>1:
                num = len(lesion_pred)-1
                num_str = "{:02n}".format(num)
                filepathSave = folderpath_output + '/' + volume_name[0:-3] + '-' + num_str +'.nrrd'
            else:
                num_str = "{:02n}".format(0)
                filepathSave = folderpath_output + '/' + volume_name + '-' + num_str +'.nrrd'
        elif 'label-pred' in filename:
            if len(label_pred)>1:
                num = len(label_pred)-1
                num_str = "{:02n}".format(num)
                filepathSave = folderpath_output + '/' + volume_name[0:-3] + '-' + num_str +'.nrrd'
            else:
                num_str = "{:02n}".format(0)
                filepathSave = folderpath_output + '/' + volume_name + '-' + num_str +'.nrrd'
        elif 'lesion' in filename:
            if len(lesion)>1:
                num = len(lesion)-1
                num_str = "{:02n}".format(num)
                filepathSave = folderpath_output + '/' + volume_name[0:-3] + '-' + num_str +'.nrrd'
            else:
                num_str = "{:02n}".format(0)
                filepathSave = folderpath_output + '/' + volume_name + '-' + num_str +'.nrrd'
        elif 'label' in filename:
            if len(label)>1:
                num = len(label)-1
                num_str = "{:02n}".format(num)
                filepathSave = folderpath_output + '/' + volume_name[0:-3] + '-' + num_str +'.nrrd'
            else:
                num_str = "{:02n}".format(0)
                filepathSave = folderpath_output + '/' + volume_name + '-' + num_str +'.nrrd'
        else:
            raise ValueError('Filepath not correct!')

        return filepathSave
            
 
    def saveOutput(self, overwrite=True):
        # Save references
        folderpath_output = self.settings['folderpath_references']
        volumeNodes = slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
        for node in volumeNodes:
            volume_name = node.GetName()
            if 'label' in volume_name:
                #filename_output = volume_name
                filepath = folderpath_output + '/' + volume_name + '.nrrd'
                if not overwrite:
                    filepath = self.outputFilepathSave(volume_name, folderpath_output)
                slicer.util.saveNode(node, filepath)
                print('Saveing reference to: ' + filepath)

    def onReload(self,moduleName="XALabelerModule"):
        """Generic reload method for any scripted module.
            ModuleWizard will subsitute correct default moduleName.
            Note: customized for use in CardiacAgatstonModule
            """

        import imp, sys, os, slicer

        # selects default tool to stop the ChangeIslandTool
        if self.localCardiacEditorWidget:
            self.localCardiacEditorWidget.exit()

        # clears the mrml scene
        slicer.mrmlScene.Clear(0)

        globals()[moduleName] = slicer.util.reloadScriptedModule(moduleName)

    def onReloadAndTest(self,moduleName="XALabelerModule"):
        try:
            self.onReload()
            evalString = 'globals()["%s"].%sTest()' % (moduleName, moduleName)
            tester = eval(evalString)
            tester.runTest()
        except Exception, e:
            import traceback
            traceback.print_exc()
            qt.QMessageBox.warning(slicer.util.mainWindow(),
              "Reload and Test", 'Exception!\n\n' + str(e) +
                                 "\n\nSee Python Console for Stack Trace")
            
    def cleanup(self):
        pass

#
# XALabelerModuleLogic
#
class XALEditorWidget(Editor.EditorWidget):
    def __init__(self, parent=None, showVolumesFrame=None, settings=None):
        self.settings = settings
        super(XALEditorWidget, self).__init__(parent=parent, showVolumesFrame=showVolumesFrame)
        
    def createEditBox(self):
        self.editLabelMapsFrame.collapsed = False
        self.editBoxFrame = qt.QFrame(self.effectsToolsFrame)
        self.editBoxFrame.objectName = 'EditBoxFrame'
        self.editBoxFrame.setLayout(qt.QVBoxLayout())
        self.effectsToolsFrame.layout().addWidget(self.editBoxFrame)
        self.toolsBox = XALEditBox(self.settings, self.editBoxFrame, optionsFrame=self.effectOptionsFrame)

    def installShortcutKeys(self):
        """Turn on editor-wide shortcuts.  These are active independent
        of the currently selected effect."""
        Key_Escape = 0x01000000 # not in PythonQt
        Key_Space = 0x20 # not in PythonQt
        self.shortcuts = []
        keysAndCallbacks = (
            ('z', self.toolsBox.undoRedo.undo),
            ('y', self.toolsBox.undoRedo.redo),
            ('h', self.editUtil.toggleCrosshair),
            ('o', self.editUtil.toggleLabelOutline),
            ('t', self.editUtil.toggleForegroundBackground),
            (Key_Escape, self.toolsBox.defaultEffect),
            ('p', lambda : self.toolsBox.selectEffect('PaintEffect')),
            ('1', self.toolsBox.onOTHERChangeIslandButtonClicked),
            #('2', self.toolsBox.onLMchangeIslandButtonClicked),
            ('3', self.toolsBox.onLADchangeIslandButtonClicked),
            ('4', self.toolsBox.onLCXchangeIslandButtonClicked),
            ('5', self.toolsBox.onRCAchangeIslandButtonClicked),
            )
        for key,callback in keysAndCallbacks:
            shortcut = qt.QShortcut(slicer.util.mainWindow())
            shortcut.setKey( qt.QKeySequence(key) )
            shortcut.connect( 'activated()', callback )
            self.shortcuts.append(shortcut)
            
class XALEditBox(EditorLib.EditBox):
    def __init__(self, settings, *args, **kwargs):
        self.settings = settings
        super(XALEditBox, self).__init__(*args, **kwargs)
        
    # create the edit box
    def create(self):

        self.findEffects()

        self.mainFrame = qt.QFrame(self.parent)
        self.mainFrame.objectName = 'MainFrame'
        vbox = qt.QVBoxLayout()
        self.mainFrame.setLayout(vbox)
        self.parent.layout().addWidget(self.mainFrame)

        #
        # the buttons
        #
        self.rowFrames = []
        self.actions = {}
        self.buttons = {}
        self.icons = {}
        self.callbacks = {}

        CACSTreeDict = self.settings['CACSTreeDict'][self.settings['MODE']][0]
        self.CACSTreeDict = CACSTreeDict

        # The Default Label Selector
        color = CACSTreeDict['OTHER']['COLOR']
        color_str = 'background-color: rgb(' + str(color[0]) + ',' + str(color[1]) + ',' + str(color[2]) + ')'
        OTHERChangeIslandButton = qt.QPushButton("OTEHR")
        OTHERChangeIslandButton.toolTip = "Label - OTEHR"
        OTHERChangeIslandButton.setStyleSheet(color_str)
        self.mainFrame.layout().addWidget(OTHERChangeIslandButton)
        OTHERChangeIslandButton.connect('clicked(bool)', self.onOTHERChangeIslandButtonClicked)

        # The Input Left Arterial Descending (LAD) Label Selector
        color = CACSTreeDict['CC']['LAD']['COLOR']
        color_str = 'background-color: rgb(' + str(color[0]) + ',' + str(color[1]) + ',' + str(color[2]) + ')'
        LADchangeIslandButton = qt.QPushButton("LAD")
        LADchangeIslandButton.toolTip = "Label - Left Arterial Descending (LAD)"
        LADchangeIslandButton.setStyleSheet(color_str)
        self.mainFrame.layout().addWidget(LADchangeIslandButton)
        LADchangeIslandButton.connect('clicked(bool)', self.onLADchangeIslandButtonClicked)

        # The Input Left Circumflex (LCX) Label Selector
        color = CACSTreeDict['CC']['LCX']['COLOR']
        color_str = 'background-color: rgb(' + str(color[0]) + ',' + str(color[1]) + ',' + str(color[2]) + ')'
        LCXchangeIslandButton = qt.QPushButton("LCX")
        LCXchangeIslandButton.toolTip = "Label - Left Circumflex (LCX)"
        LCXchangeIslandButton.setStyleSheet(color_str)
        self.mainFrame.layout().addWidget(LCXchangeIslandButton)
        LCXchangeIslandButton.connect('clicked(bool)', self.onLCXchangeIslandButtonClicked)

        # The Input Right Coronary Artery (RCA) Label Selector
        color = CACSTreeDict['CC']['RCA']['COLOR']
        color_str = 'background-color: rgb(' + str(color[0]) + ',' + str(color[1]) + ',' + str(color[2]) + ')'
        RCAchangeIslandButton = qt.QPushButton("RCA")
        RCAchangeIslandButton.toolTip = "Label - Right Coronary Artery (RCA)"
        RCAchangeIslandButton.setStyleSheet(color_str)
        self.mainFrame.layout().addWidget(RCAchangeIslandButton)
        RCAchangeIslandButton.connect('clicked(bool)', self.onRCAchangeIslandButtonClicked)

        # The UNCERTAINTY (UC) Label Selector
        color = CACSTreeDict['CC']['UC']['COLOR']
        color_str = 'background-color: rgb(' + str(color[0]) + ',' + str(color[1]) + ',' + str(color[2]) + ')'
        UCchangeIslandButton = qt.QPushButton("UNCERTAINTY")
        UCchangeIslandButton.toolTip = "Label - UNCERTAINTY (UC)"
        UCchangeIslandButton.setStyleSheet(color_str)
        self.mainFrame.layout().addWidget(UCchangeIslandButton)
        UCchangeIslandButton.connect('clicked(bool)', self.onUCchangeIslandButtonClicked)

        
        # create all of the buttons
        # createButtonRow() ensures that only effects in self.effects are exposed,
        self.createButtonRow( ("PreviousCheckPoint", "NextCheckPoint",
                               "DefaultTool", "PaintEffect", "EraseLabel","ChangeIslandEffect"),
                              rowLabel="Undo/Redo/Default: " )

        extensions = []
        for k in slicer.modules.editorExtensions:
            extensions.append(k)
        self.createButtonRow( extensions )
        #
        # the labels
        #
        self.toolsActiveToolFrame = qt.QFrame(self.parent)
        self.toolsActiveToolFrame.setLayout(qt.QHBoxLayout())
        self.parent.layout().addWidget(self.toolsActiveToolFrame)
        self.toolsActiveTool = qt.QLabel(self.toolsActiveToolFrame)
        self.toolsActiveTool.setText( 'Active Tool:' )
        self.toolsActiveTool.setStyleSheet("background-color: rgb(232,230,235)")
        self.toolsActiveToolFrame.layout().addWidget(self.toolsActiveTool)
        self.toolsActiveToolName = qt.QLabel(self.toolsActiveToolFrame)
        self.toolsActiveToolName.setText( '' )
        self.toolsActiveToolName.setStyleSheet("background-color: rgb(232,230,235)")
        self.toolsActiveToolFrame.layout().addWidget(self.toolsActiveToolName)

        #self.LMchangeIslandButton = LMchangeIslandButton
        self.LADchangeIslandButton = LADchangeIslandButton
        self.LCXchangeIslandButton = LCXchangeIslandButton
        self.RCAchangeIslandButton = RCAchangeIslandButton
        self.OTHERChangeIslandButton = OTHERChangeIslandButton
        self.UCchangeIslandButton = UCchangeIslandButton

        vbox.addStretch(1)

        self.updateUndoRedoButtons()
        self._onParameterNodeModified(EditUtil.getParameterNode())

    def onOTHERChangeIslandButtonClicked(self):
        self.changeIslandButtonClicked(self.CACSTreeDict['OTHER']['VALUE'])
        
    def onLADchangeIslandButtonClicked(self):
        self.changeIslandButtonClicked(self.CACSTreeDict['CC']['LAD']['VALUE'])

    def onLCXchangeIslandButtonClicked(self):
        self.changeIslandButtonClicked(self.CACSTreeDict['CC']['LCX']['VALUE'])

    def onRCAchangeIslandButtonClicked(self):
        self.changeIslandButtonClicked(self.CACSTreeDict['CC']['RCA']['VALUE'])

    def onUCchangeIslandButtonClicked(self):
        self.changeIslandButtonClicked(self.CACSTreeDict['CC']['UC']['VALUE'])
        

    def changeIslandButtonClicked(self, label):
        self.selectEffect("PaintEffect")
        EditUtil.setLabel(label)
        