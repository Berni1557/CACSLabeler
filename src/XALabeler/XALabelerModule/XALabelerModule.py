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
import qt
from qt import QWidget, QVBoxLayout, QLabel, QPixmap, QGridLayout, QImage, QColor, QPainter, QTransform, QPen, QPoint, QRect, QBrush, QPolygon

class PrototypeWindow(QWidget):
    """
    This "window" is a QWidget. If it has no parent,
    it will appear as a free-floating window.
    """

    def __init__(self):
        super(PrototypeWindow, self).__init__()

        self.im = QPixmap("/mnt/SSD2/cloud_data/Projects/CACSLabeler/code/data/tmp/image.png")
        self.label = QLabel()
        self.label.setPixmap(self.im)

        self.grid = QGridLayout()
        self.grid.addWidget(self.label,1,1)
        self.setLayout(self.grid)

        self.setGeometry(50,50,320,200)
        self.setWindowTitle("Prototypes")
        #self.show()
    
    def updatePrototype(self, actionlist, action):
        if action['action']=='LABEL_REGION':
            fip_tmp = "/mnt/SSD2/cloud_data/Projects/CACSLabeler/code/data/tmp/image.png"
            image_proto = np.zeros((512,512*3), dtype=np.uint16)
            image_proto_overlay = np.zeros((512,512*3), dtype=np.uint16)
            k=0
            for act in actionlist:
                if act['MSG']==action['MSG'] and not(act['fp_image']==action['fp_image'] and act['SLICE']==action['SLICE']):
                    print('found')
                    filepath_image = act['fp_image'].encode("utf-8")
                    imageSitk = sitk.ReadImage(filepath_image)
                    image = sitk.GetArrayFromImage(imageSitk)
                    image_slice= image[act['SLICE']]
                    s0 = 30900
                    s1 = 34500
                    b = s0
                    a = 65535/(s1-s0)
                    image_slice_norm = a * ((image_slice+32767) - b)
                    image_slice_norm = image_slice_norm.astype(np.uint16)
                    # Insert image
                    image_proto[0:512,k*512:(k+1)*512] = image_slice_norm
                    IDX = act['IDX']
                    IDX0 = IDX[0]
                    IDX1 = IDX[1]
                    IDX1 = [k*512+x for x in IDX1]
                    image_proto[IDX0,IDX1] = 65535         
                    # Import label
                    filepath_label = act['fp_label_pred'].encode("utf-8")
                    print('filepath_label', filepath_label)
                    labelSitk = sitk.ReadImage(filepath_label)
                    label = sitk.GetArrayFromImage(labelSitk)
                    for c in range(1,4):
                        labelC = label[act['SLICE'],:,:]==c
                        IDXL = np.where(labelC)
                        IDX0L = IDXL[0]
                        IDX1L = IDXL[1]
                        IDX1L = [k*512+x for x in IDX1L]
                        image_proto_overlay[IDX0L,IDX1L] = c 
                    k=k+1
            
            # Write image to temporal png image
            image_proto_im = sitk.GetImageFromArray(image_proto)
            sitk.WriteImage(image_proto_im, fip_tmp)             
            # Read temporal image as QPixmap 
            self.im = QPixmap(fip_tmp)
            # Set color
            imageq = QPixmap.toImage(self.im)
            colorim = imageq.convertToFormat(QImage.Format_ARGB32)
            for x in range(512):
                for y in range(512*3):
                    if image_proto[x,y] == 65535:
                        colorim.setPixel(y, x, QColor(255, 0, 0, 255).rgba())
                        
            # Set color overlay
            overlayIm = imageq.copy()
            overlay = overlayIm.convertToFormat(QImage.Format_ARGB32)
            transparency = 15
            for x in range(512):
                for y in range(512*3):
                    if image_proto_overlay[x,y] == 1:
                        overlay.setPixel(y, x, QColor(0, 255, 0, transparency).rgba())
                    elif image_proto_overlay[x,y] == 2:
                        overlay.setPixel(y, x, QColor(255, 204, 0, transparency).rgba())
                    elif image_proto_overlay[x,y] == 3:
                        overlay.setPixel(y, x, QColor(204, 0, 204, transparency).rgba())
                    elif image_proto_overlay[x,y] == 4:
                        overlay.setPixel(y, x, QColor(165, 0, 33, transparency).rgba())
                    else:
                        overlay.setPixel(y, x, QColor(0, 0, 0, 0).rgba())

            painter = QPainter()
            painter.begin(colorim)
            rect = QRect(0,0,512*3,512)
            painter.drawImage(rect, overlay)
            painter.end()
            pixmap = QPixmap.fromImage(colorim)
            self.im = pixmap
            self.label.setPixmap(self.im)
            self.show()
                
                         
# Temporal Settings
LABEL_NEW_REGION_FLAG = False

ALAction = dict({'ID': -1, 
                 'fp_image': '', 
                 'fp_label': '',
                 'fp_label_lesion': '',
                 'fp_label_pred': '',
                 'fp_label_lesion_pred': '',
                 'fp_label_refine': '',
                 'fp_label_lesion_refine': '',
                 'IDX': [[]],
                 'QUERY': (0,0),
                 'SLICE': -1,
                 'action': '', # 'LABEL_LESION', 'LABEL_REGION', 'LABEL_NEW' /   'LABEL_REGION_NEW', 'LABEL_LESION_NEW'
                 'MSG': '',
                 'AUTO': '',
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
        #self.refAction = ALAction.copy()
        self.refAction = None
        self.REFValue = 200
        self.UCValue = 201
        self.continueLabeling = False
        self.label_org = None
        self.ActionList = None
        self.fp_label_lesion_refine_pev = None
        self.actionSelected = 'ALL'

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
        self.filepath_settings = os.path.dirname(os.path.dirname(os.path.dirname(currentFile))) + '/data/settings_XALabeler.json'
        
        self.prototypWindow = PrototypeWindow()
        
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
        
        # Add action selector
        actionSelector = qt.QComboBox()
        actionSelector.addItems(['ALL', 'LABEL_LESION', 'LABEL_REGION', 'LABEL_NEW_REGION', 'LABEL_NEW'])
        actionSelector.setCurrentIndex(0)
        actionSelector.toolTip = "Select refinement action"
        actionSelector.setVisible(True)
        actionSelector.currentIndexChanged.connect(self.onActionSelectorChanged)
        self.measuresFormLayout.addRow(actionSelector)
        self.actionSelector = actionSelector
        
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
        LABEL_REGION_BUTTON.toolTip = "Refine coronary artery region"
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
        LOADCTA_BUTTON = qt.QPushButton("LOAD CTA")
        LOADCTA_BUTTON.toolTip = "Load CTA"
        LOADCTA_BUTTON.setStyleSheet("background-color: rgb(230,241,255)")
        LOADCTA_BUTTON.enabled = False
        self.measuresFormLayoutH.addRow(LOADCTA_BUTTON)
        LOADCTA_BUTTON.connect('clicked(bool)', self.onLOADCTA_BUTTONClicked)
        self.LOADCTA_BUTTON = LOADCTA_BUTTON 
        
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
        #self.UNCERTAINTY_BUTTON.enabled = True

    def onStopButtonClicked(self):
        # Save output
        #self.saveOutput(overwrite=False)
        self.nextButton.enabled = False
        self.skipButton.enabled = False
        self.saveQueryButton.enabled = False
        self.stopButton.enabled = False
        self.LABEL_LESION_BUTTON.enabled = False
        self.LABEL_REGION_BUTTON.enabled = False
        self.LABEL_NEW_BUTTON.enabled = False
        #self.UNCERTAINTY_BUTTON.enabled = False
        #self.LABEL_LESION_NEW_BUTTON.enabled = False
        #self.LABEL_REGION_NEW_BUTTON.enabled = False
        
    def onActionSelectorChanged(self):
        self.actionSelected = self.actionSelector.currentText
        
    def onLABEL_LESION_BUTTONClicked(self):
        refAction = self.refAction
        refAction['action'] = 'LABEL_LESION'
        self.LABEL_LESION_BUTTON.enabled = False
        self.LABEL_REGION_BUTTON.enabled = True
        self.LABEL_NEW_BUTTON.enabled = True
        self.refine_lesion(refAction)
        
    def onLABEL_REGION_BUTTONClicked(self):
        refAction = self.refAction
        refAction['action'] = 'LABEL_REGION'
        self.LABEL_LESION_BUTTON.enabled = True
        self.LABEL_REGION_BUTTON.enabled = False
        self.LABEL_NEW_BUTTON.enabled = True
        self.refine_region(refAction, mask_SLICE=True)
        
    def onLABEL_NEW_BUTTONClicked(self):
        refAction = self.refAction
        refAction['action'] = 'LABEL_NEW'
        self.LABEL_LESION_BUTTON.enabled = False
        self.LABEL_REGION_BUTTON.enabled = False
        self.LABEL_NEW_BUTTON.enabled = False
        self.refine_new(refAction)

#    def onLABEL_LESION_NEW_BUTTONClicked(self):
#        refAction = self.refAction
#        refAction['action'] = 'LABEL_LESION_NEW'
#        self.LABEL_LESION_BUTTON.enabled = False
#        self.LABEL_REGION_BUTTON.enabled = True
#        self.LABEL_NEW_BUTTON.enabled = True
#        self.refine_lesion_new(refAction)
#    
    def onLABEL_CONTINUE_BUTTONClicked(self):
        self.continueLabeling = True
        self.CONTINUE_BUTTON.enabled = False
        self.editUtil.toggleLabelOutline
        self.saveAction(self.refAction, save_new='LABEL')
        self.refine_lesion(self.refAction, use_pred=True, save=True, saveDiff=True, mask_SLICE=True)

    def onLOADCTA_BUTTONClicked(self):
        pass
      
    def updateActionPath(self, refAction):
        #print('refAction123', refAction)
        
        folderManagerAction = self.settings['folderManagerAction']
        # Update image path
        _, filename, ext = splitFilePath(refAction['fp_image'])
        refAction['fp_image'] = os.path.join(self.settings['folderpath_images'], filename + ext)
        # Update reference
        folderpathRef = os.path.join(folderManagerAction, 'reference')
        folderpathPredict = os.path.join(folderManagerAction, 'predict')
        if refAction['action']=='LABEL_NEW':
            # Update label path
            #print('fp_label_predX', refAction['fp_label_pred'])
            _, filename, ext = splitFilePath(refAction['fp_label_pred'])
            refAction['fp_label'] = os.path.join(folderpathPredict, filename + ext)
            #print('filepath_label1234', refAction['fp_label'])
            # Update lesion path
            _, filename, ext = splitFilePath(refAction['fp_label_lesion_pred'])
            refAction['fp_label_lesion'] = os.path.join(folderpathPredict, filename + ext)
        else:
            # Update label path
            _, filename, ext = splitFilePath(refAction['fp_label'])
            refAction['fp_label'] = os.path.join(folderpathRef, filename + ext)
            # Update lesion path
            _, filename, ext = splitFilePath(refAction['fp_label_lesion'])
            refAction['fp_label_lesion'] = os.path.join(folderpathRef, filename + ext)
        # Update refine
        folderpathRefine = os.path.join(folderManagerAction, 'refine')
        # Update label_refine path
        _, filename, ext = splitFilePath(refAction['fp_label_refine'])
        refAction['fp_label_refine'] = os.path.join(folderpathRefine, filename + ext)
        # Update lesion path
        _, filename, ext = splitFilePath(refAction['fp_label_lesion_refine'])
        refAction['fp_label_lesion_refine'] = os.path.join(folderpathRefine, filename + ext)
        # Update prediction
        folderpathPred = os.path.join(folderManagerAction, 'predict')

        # Update label_refine path
        if refAction['fp_label_pred']:
            _, filename, ext = splitFilePath(refAction['fp_label_pred'])
            refAction['fp_label_pred'] = os.path.join(folderpathPred, filename + ext)
        else:
            _, filename, ext = splitFilePath(refAction['fp_label'])
            refAction['fp_label_pred'] = os.path.join(folderpathPred, filename + '-pred' + ext)
        # Update lesion path
        if refAction['fp_label_lesion_pred']:
            _, filename, ext = splitFilePath(refAction['fp_label_lesion_pred'])
            refAction['fp_label_lesion_pred'] = os.path.join(folderpathPred, filename + ext)
        else:
            _, filename, ext = splitFilePath(refAction['fp_label_lesion'])
            refAction['fp_label_lesion_pred'] = os.path.join(folderpathPred, filename + '-pred' + ext)
        return refAction
        
    def saveAction(self, refAction, save_new='LESION'):
        if refAction is not None and (refAction['STATUS']=='SOLVED' or save_new=='LABEL'):
            #self.deleteNodesREFValue()
            filepath = refAction['fp_image'].encode("utf-8")
            _, imagename,_ = splitFilePath(filepath)
            if refAction['action'] == 'LABEL_LESION':
                fp_save = refAction['fp_label_lesion_refine']
            elif refAction['action'] == 'LABEL_REGION':
                fp_save = refAction['fp_label_refine']
            elif refAction['action'] == 'LABEL_NEW_REGION':
                fp_save = refAction['fp_label_refine']
            elif refAction['action'] == 'LABEL_NEW':
                if save_new=='LESION':
                    fp_save = refAction['fp_label_lesion_refine']
                else:
                    fp_save = refAction['fp_label_refine']
            else:
                raise ValueError('Action: ' + refAction['action'] + ' does not exist.')
            self.updateDiffOutput()
            self.saveOutputRefine(filepath_refine=fp_save)
            self.deleteNodes(imagename)
        
    def onNextButtonClicked(self):
        
        #self.window1.show()
        
        # Update action
        if self.refAction is not None:
            self.refAction['STATUS'] = 'SOLVED'
        
        # Save current action and delete nodes
        if self.refAction is not None:
            self.saveAction(self.refAction)
        
        # Check if server is used
        if self.settings['ServerRefinement']:
            # Start client
            self.refAction['COMMAND'] = self.refAction['COMMAND'] + 'NEXT'
            #self.refAction['STATUS'] = 'SOLVED'
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
                server_error = False
            except:
                print('Could not get next query. Please check the server!')
                server_error = True
            print('fp_label_pred01', refAction['fp_label_pred'])
            refAction['folderpath_output'],_ ,_ = splitFilePath(refAction['fp_label_pred'])
        else:
            if self.ActionList is None:
                # Read action list
                self.ActionList = self.loadActionFile(folderManagerAction=self.settings['folderManagerAction'])
            else:
                # Save action list
                self.ActionList[self.refAction_idx] = self.refAction
                self.saveActionFile(self.ActionList, folderManagerAction=self.settings['folderManagerAction'])
            
            # Collect action statistic
            action_stat = dict({'LABEL_LESION':0, 'LABEL_REGION':0, 'LABEL_NEW_REGION':0, 'LABEL_NEW':0})
            for idx,action in enumerate(self.ActionList):
                if action['action']=='LABEL_LESION' and action['STATUS']=='OPEN':
                    action_stat['LABEL_LESION'] += 1
                if action['action']=='LABEL_REGION' and action['STATUS']=='OPEN':
                    action_stat['LABEL_REGION'] += 1
                if action['action']=='LABEL_NEW_REGION' and action['STATUS']=='OPEN':
                    action_stat['LABEL_NEW_REGION'] += 1
                if action['action']=='LABEL_NEW' and action['STATUS']=='OPEN':
                    action_stat['LABEL_NEW'] += 1
            print('Action: ' + str(action_stat))
            
            # Get next action
            new_action=False
            for idx,action in enumerate(self.ActionList):
                #if action['STATUS']=='OPEN':
                #if action['STATUS']=='OPEN' and idx>250:
                if action['STATUS']=='OPEN' and (action['action']==self.actionSelected or self.actionSelected=='ALL'):
                    print('Processing: ' + str(idx) + '/' + str(len(self.ActionList)))
                    self.refAction = self.updateActionPath(action)
                    self.refAction_idx = idx
                    new_action = True
                    break
            if not new_action:
                return
            server_error = False

        if not server_error:
            if self.refAction['action'] == '':
                pass
            elif self.refAction['action'] == 'LABEL_LESION':
                self.LABEL_LESION_BUTTON.enabled = False
                self.LABEL_REGION_BUTTON.enabled = True
                self.LABEL_NEW_BUTTON.enabled = True
                self.refine_lesion(self.refAction, use_pred=False, save=True, saveDiff=True)
            elif self.refAction['action'] == 'LABEL_REGION':
                self.LABEL_LESION_BUTTON.enabled = True
                self.LABEL_REGION_BUTTON.enabled = False
                self.LABEL_NEW_BUTTON.enabled = True
                self.refine_region(self.refAction, save=True, saveDiff=True, mask_SLICE=True)
            elif self.refAction['action'] == 'LABEL_NEW_REGION':
                self.LABEL_LESION_BUTTON.enabled = True
                self.LABEL_REGION_BUTTON.enabled = False
                self.LABEL_NEW_BUTTON.enabled = True
                self.refine_region(self.refAction, save=True, saveDiff=True, mask_SLICE=True)
            elif self.refAction['action'] == 'LABEL_NEW':
                self.LABEL_LESION_BUTTON.enabled = False
                self.LABEL_REGION_BUTTON.enabled = False
                self.LABEL_NEW_BUTTON.enabled = False
                self.refine_new(self.refAction, save=True)
            else:
                raise ValueError('Action: ' + refAction['action'] + ' does not exist.')
            
    def onSkipButtonClicked(self):
        
        if self.settings['ServerRefinement']:
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
                server_error = False
            except:
                print('Could not get next query. Please check the server!')
                server_error = True
                
            refAction['folderpath_output'],_ ,_ = splitFilePath(refAction['fp_label_pred'])
        else:
            if self.ActionList is None:
                # Read action list
                self.ActionList = self.loadActionFile(folderManagerAction=self.settings['folderManagerAction'])
            else:
                # Save action list
                self.refAction['STATUS'] = 'SKIPED'
                self.ActionList[self.refAction_idx] = self.refAction
                self.saveActionFile(self.ActionList, folderManagerAction=self.settings['folderManagerAction'])
                
            # Get next action
            for idx,action in enumerate(self.ActionList):
                if action['STATUS']=='OPEN':
                    self.refAction = self.updateActionPath(action)
                    self.refAction_idx = idx
                    break
            server_error = False
            
        if not server_error:
            if self.refAction['action'] == '':
                pass
            elif self.refAction['action'] == 'LABEL_LESION':
                self.LABEL_LESION_BUTTON.enabled = False
                self.LABEL_REGION_BUTTON.enabled = True
                self.LABEL_NEW_BUTTON.enabled = True
                self.refine_lesion(refAction, use_pred=False, save=False, saveDiff=True)
            elif self.refAction['action'] == 'LABEL_REGION':
                self.LABEL_LESION_BUTTON.enabled = True
                self.LABEL_REGION_BUTTON.enabled = False
                self.LABEL_NEW_BUTTON.enabled = True
                self.refine_region(refAction, save=False, showREFValue=True, saveDiff=True, mask_SLICE=True)
            elif self.refAction['action'] == 'LABEL_NEW_REGION':
                self.LABEL_LESION_BUTTON.enabled = True
                self.LABEL_REGION_BUTTON.enabled = False
                self.LABEL_NEW_BUTTON.enabled = True
                self.refine_region(refAction, save=False, showREFValue=True, saveDiff=True, mask_SLICE=True)
            elif self.refAction['action'] == 'LABEL_NEW':
                self.LABEL_LESION_BUTTON.enabled = False
                self.LABEL_REGION_BUTTON.enabled = False
                self.LABEL_NEW_BUTTON.enabled = False
                self.refine_new(refAction, save=False)
            else:
                raise ValueError('Action: ' + refAction['action'] + ' does not exist.')
    
    def onSaveQueryButtonClicked(self):
        self.saveOutput(overwrite=False)

    def refine_new(self, refAction, save=True):
        #print('refine_new')
        #print('LABEL_NEW_REGION', LABEL_NEW_REGION)
        if LABEL_NEW_REGION_FLAG:
            self.nextButton.enabled = False
            self.skipButton.enabled = False
            self.saveQueryButton.enabled = False
            self.CONTINUE_BUTTON.enabled = True
            self.continueLabeling = False
            self.refine_region(refAction, save=save, showREFValue=False, saveDiff=True, mask_SLICE=True)
        else:
            self.continueLabeling = True
            self.CONTINUE_BUTTON.enabled = False
            self.editUtil.toggleLabelOutline
            self.saveAction(self.refAction, save_new='LABEL')
            self.refine_lesion(self.refAction, use_pred=True, save=True, saveDiff=True, mask_SLICE=True)
        
    def load_label_list(self, filepath_label_list):
        label_list = filepath_label_list
        ref = None
        for labelfile in label_list:
            labeltmp = sitk.ReadImage(labelfile)
            labeltmp_arr = sitk.GetArrayFromImage(labeltmp)
            if ref is None:
                ref = labeltmp_arr
            else:
                refnew = labeltmp_arr
                ref[refnew>0] = refnew[refnew>0]
        label = sitk.GetImageFromArray(ref)
        label.CopyInformation(labeltmp)
        return label

 
    def refine_region(self, refAction, use_pred=True, save=True, showREFValue=True, saveDiff=False, mask_SLICE=False):
        print('refine_region')
        # Save all existing nodes
        filepath = refAction['fp_image'].encode("utf-8")
        _, imagename,_ = splitFilePath(filepath)
        
        # Visualize prototypWindow
        self.prototypWindow.updatePrototype(self.ActionList, refAction)
        
        #self.fp_label_refine_prev = refAction['fp_label_refine'].encode("utf-8")
        #print('fp_label_refine_pev123', self.fp_label_refine_prev)
        
        #print('save', save)
        #print('saveDiff', saveDiff)
        #self.deleteNodesREFValue()
#        if save:
#            if saveDiff:
#                self.updateDiffOutput()
#            #self.saveOutput(overwrite=False, folderpath_output=refAction['folderpath_output'])
#            self.saveOutputRefine(filepath_refine=self.fp_label_refine_prev)
#        self.deleteNodes(imagename)
 
        imageFound = self.nodeExist(imagename)
              
        # Load image
        if not imageFound:
            #self.saveOutput(overwrite=False)  
            print('Loading: ' + filepath)
            properties={'name': imagename}
            node = slicer.util.loadVolume(filepath, returnNode=True, properties=properties)[1]
            node.SetName(imagename)  
        
        

#        if use_pred:
#            filepath_label_org = refAction['fp_label_pred'].encode("utf-8")
#            filepath_label, filepath_label_list = self.load_label_lesion_pred(filepath_label_org)
#            _, labelname,_ = splitFilePath(filepath_label)
#        else:
#            filepath_label_org = refAction['fp_label'].encode("utf-8")
#            if filepath_label_org=='':
#                filepath_label, filepath_label_list = self.load_label_lesion_pred(filepath_label_org)
#                _, labelname,_ = splitFilePath(filepath_label)
#            else:
#                filepath_label = filepath_label_org
#                _, labelname,_ = splitFilePath(filepath_label)
#                filepath_label_list = [filepath_label]
                
        # Load image_org
        #self.label_org = sitk.ReadImage(filepath_label)
        #self.label_org = self.load_label_list(filepath_label_list)
        #filepath_label = refAction['fp_label'].encode("utf-8")
        #print('filepath_label123', filepath_label)
        filepath_label = refAction['fp_label_pred'].encode("utf-8")
        self.label_org = sitk.ReadImage(filepath_label)
        
        _, labelname,_ = splitFilePath(filepath_label)
        #print('labelname123', labelname)
        
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
        
        #label_im = sitk.ReadImage(filepath_label)
        #label_im = self.load_label_list(filepath_label_list)
        label_im = sitk.ReadImage(filepath_label)
        print('Loading: ' + filepath_label)
        label = sitk.GetArrayFromImage(label_im)

        IDX = refAction['IDX']
        sliceNumber = refAction['SLICE']

        labelFound = self.nodeExist(labelname)

        # Create binary mask
        mask = np.zeros(label.shape)
        #print('mask123', mask.shape)
        
        
        IDX = refAction['IDX']
        SLICE = int(refAction['SLICE'])
        #print('IDX123', IDX)
        #print('SLICE123', SLICE)
        if mask_SLICE:
            #for p in range(len(IDX[0])):
            for p in range(0,len(IDX[0]),2):
                x=IDX[0][p]
                y=IDX[1][p]
                mask[SLICE, x, y] = 1
            mask_slice = np.zeros(label.shape)
            mask_slice[SLICE,:,:] = np.ones((label.shape[1],label.shape[2]))
        else:
            mask_slice = np.ones(label.shape)

#        print('labelFound', labelFound)
#        print('showREFValue', showREFValue)
#        print('mask_slice', mask_slice.shape)
        # Set label
        if not labelFound:
            if showREFValue:
                #label = label * (1-mask) + self.REFValue * mask
                label = label * (1-mask) + 0 * mask
            label = label * mask_slice
            labelSitk = sitk.GetImageFromArray(label)
            labelSitk.CopyInformation(label_im)
            node = su.PushVolumeToSlicer(labelSitk, name=labelname, className='vtkMRMLLabelMapVolumeNode')
            node.SetName(labelname)
            slicer.util.setSliceViewerLayers(label = node, foreground = node, foregroundOpacity = 0.1, labelOpacity = 0.0)
            self.assignLabelLUT(labelname)
        else:
            node = slicer.mrmlScene.GetFirstNodeByName(labelname)
            label_node = slicer.util.arrayFromVolume(node)
            label = label_node * (1-mask) + label * mask
            label = label * mask_slice
            slicer.util.updateVolumeFromArray(node, label)
            self.assignLabelLUT(labelname)
            #print('updateVolumeFromArray')
            
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
            self.localXALEditorWidget = XALEditorWidget(parent=self.parent, showVolumesFrame=False, settings=self.settings, widget=self)
            self.localXALEditorWidget.setup()
            self.localXALEditorWidget.enter()
        self.localXALEditorWidget.toolsBox.UCchangeIslandButton.setEnabled(False)
        
        # Set LowerPaintThreshold
        self.lowerThresholdValue = -5000
        self.upperThresholdValue = 5000
        self.setLowerPaintThreshold()
        
    def load_label_lesion_pred(self, filepath_label_org):
        folder, labelname,_ = splitFilePath(filepath_label_org)
        filepath_label_list = glob(os.path.join(folder, labelname + '*.nrrd'))
        filepath_label_list = sorted(filepath_label_list)
        filepath_label_list = sorted(filepath_label_list, key=len, reverse=False)
        if len(filepath_label_list)>0:
            filepath_label = filepath_label_list[-1]
        else:
            filepath_label = filepath_label_org
        return filepath_label, filepath_label_list
        
    def loadActionFile(self, folderManagerAction='/mnt/SSD2/cloud_data/Projects/CACSLabeler/code/data/tmp'):
        ActionFilePath = os.path.join(folderManagerAction, 'manager', 'action', 'data', 'ActionFile.json')
        # Load ActionFile
        with open(ActionFilePath) as json_file:
            action_list = json.load(json_file)
        return action_list

    def saveActionFile(self, action_list, folderManagerAction='/mnt/SSD2/cloud_data/Projects/CACSLabeler/code/data/tmp'):
        ActionFilePath = os.path.join(folderManagerAction, 'manager', 'action', 'data', 'ActionFile.json')  
        # Save action list to json
        with open(ActionFilePath, 'w') as file:
            file.write(json.dumps(action_list, indent=4))
            
            
    def refine_lesion(self, refAction, use_pred=False, save=True, saveDiff=False, mask_SLICE=False):
        #print('refine_lesion')
        # Load label
#        if use_pred:
#            filepath_label_org = refAction['fp_label_lesion_pred'].encode("utf-8")
#            filepath_label, filepath_label_list = self.load_label_lesion_pred(filepath_label_org)
#            _, labelname,_ = splitFilePath(filepath_label)
#        else:
#            filepath_label_org = refAction['fp_label_lesion'].encode("utf-8")
#            if filepath_label_org=='':
#                filepath_label, filepath_label_list = self.load_label_lesion_pred(filepath_label_org)
#                _, labelname,_ = splitFilePath(filepath_label)
#            else:
#                filepath_label = filepath_label_org
#                _, labelname,_ = splitFilePath(filepath_label)
#                filepath_label_list = [filepath_label]

        #print('fp_image123', refAction['fp_image'])
        filepath = refAction['fp_image'].encode("utf-8")
        _, imagename,_ = splitFilePath(filepath)
        
        
#        self.fp_label_lesion_refine_pev = refAction['fp_label_lesion_refine'].encode("utf-8")
#        #print('fp_label_lesion_refine_pev123', self.fp_label_lesion_refine_pev)
#        
#        self.deleteNodesREFValue()
#        if save:
#            if saveDiff:
#                self.updateDiffOutput()
#            #self.saveOutput(overwrite=False, folderpath_output=refAction['folderpath_output'])
#            self.saveOutputRefine(filepath_refine=self.fp_label_lesion_refine_pev)
#        self.deleteNodes(imagename)

        imageFound = self.nodeExist(imagename)

        # Load image
        if not imageFound:
            print('Loading: ' + filepath)
            properties={'name': imagename}
            node = slicer.util.loadVolume(filepath, returnNode=True, properties=properties)[1]
            node.SetName(imagename)        
            
        #label_im = sitk.ReadImage(filepath_label)
        #label_im = self.load_label_list(filepath_label_list)
        
        filepath_label = refAction['fp_label_lesion'].encode("utf-8")
        label_im = sitk.ReadImage(filepath_label)
        print('Loading: ' + filepath_label)
        label = sitk.GetArrayFromImage(label_im)
        
        # Load image_org
        #self.label_org = sitk.ReadImage(filepath_label)
        #self.label_org = self.load_label_list(filepath_label_list)
        self.label_org = sitk.ReadImage(filepath_label)
        
        # Create binary mask
        mask = np.zeros(label.shape)
        IDX = refAction['IDX']
        SLICE = int(refAction['SLICE'])
        NumPixel = len(IDX[0])
        for p in range(NumPixel):
            x=IDX[0][p]
            y=IDX[1][p]
            mask[SLICE, x, y] = 1
        
        # Create mask_slice
        IDX = refAction['IDX']
        SLICE = int(refAction['SLICE'])
        if mask_SLICE:
            for p in range(len(IDX[0])):
                x=IDX[0][p]
                y=IDX[1][p]
                mask[SLICE, x, y] = 1
            mask_slice = np.zeros(label.shape)
            mask_slice[SLICE,:,:] = np.ones((label.shape[1],label.shape[2]))
        else:
            mask_slice = np.ones(label.shape)
        
        #print('mask', mask.sum())
        #print('IDX', IDX)
        #print('SLICE', IDX)
        
        _, labelname,_ = splitFilePath(filepath_label)
        labelFound = self.nodeExist(labelname)

        # Set label
        if not labelFound:
            if not use_pred:
                label = label * mask
            label = label * mask_slice
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
            label = label * mask_slice
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
            self.localXALEditorWidget = XALEditorWidget(parent=self.parent, showVolumesFrame=False, settings=self.settings, widget=self)
            self.localXALEditorWidget.setup()
            self.localXALEditorWidget.enter()
        self.localXALEditorWidget.toolsBox.UCchangeIslandButton.setEnabled(True)
        
    
        # Set LowerPaintThreshold
        self.lowerThresholdValue = 130
        self.upperThresholdValue = 100000
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
            
 
    def saveOutput(self, overwrite=True, folderpath_output=None):
        # Save references
        if folderpath_output is None:
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

    def saveOutputRefine(self, filepath_refine=None):
        # Save refinement
        print('saveOutputRefine')
        volumeNodes = slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
        for node in volumeNodes:
            print('node', node)
            volume_name = node.GetName()
            if 'label' in volume_name:
                slicer.util.saveNode(node, filepath_refine)
                print('Saveing refinement to: ' + filepath_refine)
                
    def updateDiffOutput(self):
        volumeNodes = slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
        for node in volumeNodes:
            volume_name = node.GetName()
            if 'label' in volume_name:
                arr = sitk.GetArrayFromImage(su.PullVolumeFromSlicer(node))
                arr_org = sitk.GetArrayFromImage(self.label_org)
                arr_diff = np.zeros(arr_org.shape)
                arr_diff[arr!=arr_org] = arr[arr!=arr_org]
                slicer.util.updateVolumeFromArray(node, arr_diff)
        

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
    def __init__(self, parent=None, showVolumesFrame=None, settings=None, widget=None):
        self.settings = settings
        self.widget = widget
        super(XALEditorWidget, self).__init__(parent=parent, showVolumesFrame=showVolumesFrame)
        
    def createEditBox(self):
        self.editLabelMapsFrame.collapsed = False
        self.editBoxFrame = qt.QFrame(self.effectsToolsFrame)
        self.editBoxFrame.objectName = 'EditBoxFrame'
        self.editBoxFrame.setLayout(qt.QVBoxLayout())
        self.effectsToolsFrame.layout().addWidget(self.editBoxFrame)
        self.toolsBox = XALEditBox(self.settings, self.editBoxFrame, optionsFrame=self.effectOptionsFrame)
        
    def nextCase(self):
        self.widget.onNextButtonClicked()

    def installShortcutKeys(self):
        print('installShortcutKeys')
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
            ('n', self.nextCase),
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
        