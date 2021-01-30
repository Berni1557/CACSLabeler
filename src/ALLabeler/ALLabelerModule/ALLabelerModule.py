from __main__ import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
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
from SegmentEditor import SegmentEditorWidget
import numpy as np
dirname = os.path.dirname(os.path.abspath(__file__))
dir_src = os.path.dirname(os.path.dirname(dirname))
sys.path.append(dir_src)
from settings.settings import Settings
from SimpleITK import ConnectedComponentImageFilter
# Import cv2
#dir_cv = dir_src + '/ALLabeler/ALLabeler-site-packages/cv2'
#sys.path.append(dir_cv)
#import cv2

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
    
class ALLabelerModule(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "ALLabelerModule" # TODO make this more human readable by adding spaces
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
# ALLabelerModuleWidget
#
class ALLabelerModuleWidget:
    def __init__(self, parent = None):
        self.currentRegistrationInterface = None
        self.changeIslandTool = None
        self.editUtil = EditorLib.EditUtil.EditUtil()
        #self.inputImageNode = None
        self.localCardiacEditorWidget = None
        self.settings=Settings()
        self.images=[]
        self.localALEditorWidget = None

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
            self.reloadButton.name = "ALLabelerModule Reload"
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
        self.measuresCollapsibleButton.text = "Input Parameters"
        self.layout.addWidget(self.measuresCollapsibleButton)

        # Collapsible button for Label Parameters
        self.labelsCollapsibleButton = ctk.ctkCollapsibleButton()
        self.labelsCollapsibleButton.text = "Label Parameters"
        #self.layout.addWidget(self.labelsCollapsibleButton)

        # Layout within the sample collapsible button
        self.measuresFormLayout = qt.QFormLayout(self.measuresCollapsibleButton)

        # Load input button
        loadInputButton = qt.QPushButton("Load input data")
        loadInputButton.toolTip = "Load data to label"
        loadInputButton.setStyleSheet("background-color: rgb(230,241,255)")
        self.measuresFormLayout.addRow(loadInputButton)
        loadInputButton.connect('clicked(bool)', self.onLoadInputButtonClicked)
        self.loadInputButton = loadInputButton
        
        # The Input Volume Selector
        self.inputFrame = qt.QFrame(self.measuresCollapsibleButton)
        self.inputFrame.setLayout(qt.QHBoxLayout())
        self.measuresFormLayout.addRow(self.inputFrame)
        
        inputSelector = qt.QLabel("Input Volume: ", self.inputFrame)
        self.inputFrame.layout().addWidget(inputSelector)
        inputSelector = slicer.qMRMLNodeComboBox(self.inputFrame)
        inputSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
        inputSelector.addEnabled = False
        inputSelector.removeEnabled = False
        inputSelector.setMRMLScene( slicer.mrmlScene )
        self.inputSelector = inputSelector
        self.inputSelector.currentNodeChanged.connect(self.onCurrentNodeChanged)
        self.measuresFormLayout.addRow(self.inputSelector)
        #self.inputFrame.layout().addWidget(self.inputSelector)

        # Collapsible button for Output Parameters
        self.measuresCollapsibleButtonOutput = ctk.ctkCollapsibleButton()
        self.measuresCollapsibleButtonOutput.text = "Output Parameters"
        self.layout.addWidget(self.measuresCollapsibleButtonOutput)
        
        # Layout within the sample collapsible button
        self.measuresFormLayoutOutput = qt.QFormLayout(self.measuresCollapsibleButtonOutput)

        # Apply background growing 
        bgGrowingButton = qt.QPushButton("Apply background growing")
        bgGrowingButton.toolTip = "Apply background growi"
        bgGrowingButton.setStyleSheet("background-color: rgb(230,241,255)")
        bgGrowingButton.enabled = False
        self.measuresFormLayoutOutput.addRow(bgGrowingButton)
        bgGrowingButton.connect('clicked(bool)', self.onBgGrowingButtonButtonClicked)
        self.bgGrowingButton = bgGrowingButton
        
        # Save output button
        saveOutputButton = qt.QPushButton("Save output data")
        saveOutputButton.toolTip = "Save data"
        saveOutputButton.setStyleSheet("background-color: rgb(230,241,255)")
        saveOutputButton.enabled = False
        self.measuresFormLayoutOutput.addRow(saveOutputButton)
        saveOutputButton.connect('clicked(bool)', self.onSaveOutputButtonClicked)
        self.saveOutputButton = saveOutputButton
        
        # Delete scans button
        deleteButton = qt.QPushButton("Delete data")
        deleteButton.toolTip = "Delete data"
        deleteButton.setStyleSheet("background-color: rgb(230,241,255)")
        deleteButton.enabled = False
        self.measuresFormLayoutOutput.addRow(deleteButton)
        deleteButton.connect('clicked(bool)', self.onDeleteButtonClicked)
        self.deleteButton = deleteButton
        
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
        
        # Set MODE to 'CACS'
        self.settings['MODE'] = 'CACS'
        
        # Create color table
        if self.settings['MODE']=='CACSTREE_CUMULATIVE':
            self.settings['CACSTree'].createColorTable(filepath_colorTable)
        else:
            self.settings['CACSTree'].createColorTable_CACS(filepath_colorTable)
        
        # Load color table
        slicer.util.loadColorTable(filepath_colorTable)

    def onCurrentNodeChanged(self):
        
        # Load reference if load_reference_if_exist is true and reference file exist and no label node exist
        if self.settings['load_reference_if_exist']:
            inputImageNode = self.inputSelector.currentNode()
            if inputImageNode is not None:
                inputVolumeName = inputImageNode.GetName()
                calciumName = inputVolumeName + '-label'
                node_label = slicer.util.getFirstNodeByName(calciumName)
                if node_label is None and 'label' not in inputVolumeName and not inputVolumeName == '1':
                    calciumName = inputVolumeName + '-label'
                    filepath_ref = os.path.join(self.settings['folderpath_references'], calciumName + '.nrrd')
                    properties={'name': calciumName, 'labelmap': True}
                    if os.path.isfile(filepath_ref):
                        node_label = slicer.util.loadVolume(filepath_ref, returnNode=True, properties=properties)[1]
                        node_label.SetName(calciumName)
                        self.assignLabelLUT(calciumName)
                        self.inputSelector.setCurrentNode(inputImageNode)
                        #slicer.util.setSliceViewerLayers(background = inputImageNode, foreground = node_label, foregroundOpacity = 0.3, labelOpacity = 0.0)
       
        # Create label if not exist
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
                self.inputSelector.setCurrentNode(inputImageNode)
        
        # Set slicer offset
        slicer.util.resetSliceViews()
        
        # Change visualization
        if inputImageNode is not None:
            sliceNumber = 30
            red = self.layoutManager.sliceWidget('Red')
            redLogic = red.sliceLogic()
            offset = redLogic.GetSliceOffset()
            #origen = label_im.GetOrigin()
            origen = inputImageNode.GetOrigin()
            offset = origen[2] + sliceNumber * 3.0
            redLogic.SetSliceOffset(offset)
        if inputImageNode is not None and node_label is not None:
            slicer.util.setSliceViewerLayers(label = node_label, background = inputImageNode, foreground = node_label, foregroundOpacity = 0.3, labelOpacity = 1.0)
        if inputImageNode is not None and node_label is None:
            slicer.util.setSliceViewerLayers(background = inputImageNode)

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
        
    def onLoadInputButtonClicked(self):
        
        # Deleta all old nodes
        if self.settings['show_input_if_ref_found'] or self.settings['show_input_if_ref_not_found']:
            files_ref = glob(self.settings['folderpath_references'] + '/*label.nrrd')
            filter_input = self.settings['filter_input'].decode('utf-8')
            filter_input_list = filter_input.split('(')[1].split(')')[0].split(',')
            filter_input_list = [x.replace(" ", "") for x in filter_input_list]

            # Collect filenames
            files=[]
            for filt in filter_input_list:
                files = files + glob(self.settings['folderpath_images'] + '/' + filt)
            filter_input_ref = ''
            for f in files:
                _,fname,_ = splitFilePath(f)
                ref_found = any([fname in ref for ref in files_ref])
                #print('ref_found', ref_found)
                if ref_found and self.settings['show_input_if_ref_found']:
                    filter_input_ref = filter_input_ref + fname + '.mhd '
                if not ref_found and self.settings['show_input_if_ref_not_found']:
                    filter_input_ref = filter_input_ref + fname + '.mhd '

            filenames = qt.QFileDialog.getOpenFileNames(self.parent, 'Open files', self.settings['folderpath_images'],filter_input_ref)
        else:
            filenames = qt.QFileDialog.getOpenFileNames(self.parent, 'Open files', self.settings['folderpath_images'],self.settings['filter_input'])
        
        # Read images
        imagenames = []
        for filepath in filenames:
            _, name,_ = splitFilePath(filepath)
            properties={'name': name}
            node = slicer.util.loadVolume(filepath, returnNode=True, properties=properties)[1]
            slicer.util.setSliceViewerLayers(background=node)
            imagenames.append(name)
            self.inputSelector.setCurrentNode(node)

        if len(filenames)>0:
            self.bgGrowingButton.enabled = True
            self.saveOutputButton.enabled = True
            self.deleteButton.enabled = True

            # Creates and adds the custom Editor Widget to the module
            if self.localALEditorWidget is None:
                self.localALEditorWidget = ALEditorWidget(parent=self.parent, showVolumesFrame=False, settings=self.settings)
                self.localALEditorWidget.setup()
                self.localALEditorWidget.enter()

    def onDeleteButtonClicked(self):
        print ('onDeleteButtonClicked')
        # Deleta all old nodes
        nodes=slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
        for node in nodes:
            slicer.mrmlScene.RemoveNode(node)
            
            
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
        mask_fg[mask_fg==1]=1
        mask = mask_bg + mask_fg
        return mask
        
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
        # Save references
        folderpath_output = self.settings['folderpath_references']
        volumeNodes = slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
        for node in volumeNodes:
            volume_name = node.GetName()
            if 'label' in volume_name:
                filename_output = volume_name
                filepath = folderpath_output + '/' + filename_output + '.nrrd'
                slicer.util.saveNode(node, filepath)
                print('Saveing reference to: ' + filepath)

    def onReload(self,moduleName="ALLabelerModule"):
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

    def onReloadAndTest(self,moduleName="ALLabelerModule"):
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
# ALLabelerModuleLogic
#
class ALEditorWidget(Editor.EditorWidget):
    def __init__(self, parent=None, showVolumesFrame=None, settings=None):
        self.settings = settings
        super(ALEditorWidget, self).__init__(parent=parent, showVolumesFrame=showVolumesFrame)
        
    def createEditBox(self):
        self.editLabelMapsFrame.collapsed = False
        self.editBoxFrame = qt.QFrame(self.effectsToolsFrame)
        self.editBoxFrame.objectName = 'EditBoxFrame'
        self.editBoxFrame.setLayout(qt.QVBoxLayout())
        self.effectsToolsFrame.layout().addWidget(self.editBoxFrame)
        self.toolsBox = ALEditBox(self.settings, self.editBoxFrame, optionsFrame=self.effectOptionsFrame)

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
            
class ALEditBox(EditorLib.EditBox):
    def __init__(self, settings, *args, **kwargs):
        self.settings = settings
        super(ALEditBox, self).__init__(*args, **kwargs)
        
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

        vbox.addStretch(1)

        self.updateUndoRedoButtons()
        self._onParameterNodeModified(EditUtil.getParameterNode())

    def onOTHERChangeIslandButtonClicked(self):
        self.changeIslandButtonClicked(1)
        
    def onLADchangeIslandButtonClicked(self):
        self.changeIslandButtonClicked(2)

    def onLCXchangeIslandButtonClicked(self):
        self.changeIslandButtonClicked(3)

    def onRCAchangeIslandButtonClicked(self):
        self.changeIslandButtonClicked(4)

    def changeIslandButtonClicked(self, label):
        self.selectEffect("PaintEffect")
        EditUtil.setLabel(label)
        