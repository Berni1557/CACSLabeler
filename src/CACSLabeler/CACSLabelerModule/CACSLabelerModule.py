from __main__ import vtk, qt, ctk, slicer
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
from slicer.ScriptedLoadableModule import ScriptedLoadableModule
import unittest
import os
import SimpleITK as sitk
import sitkUtils as su
import EditorLib
import Editor
import LabelStatistics
from collections import defaultdict, OrderedDict
from EditorLib.EditUtil import EditUtil
from glob import glob
import random
import numpy as np
from SimpleITK import ConnectedComponentImageFilter
import json
import sys
import time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from CalciumScores.Agatston import Agatston
from CalciumScores.VolumeScore import VolumeScore
from CalciumScores.DensityScore import DensityScore
from CalciumScores.NumLesions import NumLesions
from CalciumScores.LesionVolume import LesionVolume
from collections import defaultdict, OrderedDict
import imp
imp.reload(sys.modules['CalciumScores'])
import csv 
from CACSTree import CACSTree, Lesion

############## CACSLabelerModule ##############

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

   

class CACSLabelerModule(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "CACSLabelerModule"
    self.parent.categories = ["Examples"]
    self.parent.dependencies = []
    self.parent.contributors = ["Bernhard Foellmer, Charite"] # replace with "Firstname Lastname (Organization)"
    self.parent.helpText = """
                            This is an example of scripted loadable module bundled in an extension.
                            It performs a simple thresholding on the input volume and optionally captures a screenshot.
                            """
    self.parent.helpText += self.getDefaultModuleDocumentationLink()
    self.parent.acknowledgementText = """
                            This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc.
                            and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
                            """ # replace with organization, grant and thanks.

# CACSLabelerModuleWidget
class CACSLabelerModuleWidget:
    def __init__(self, parent = None):
        self.currentRegistrationInterface = None
        self.changeIslandTool = None
        self.editUtil = EditorLib.EditUtil.EditUtil()
        self.inputImageNode = None
        self.localCardiacEditorWidget = None
        self.filepath_settings = None
        self.settings=None

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

        #
        # Reload and Test area
        #
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
            self.reloadButton.name = "CACSLabelerModule Reload"
            reloadFormLayout.addWidget(self.reloadButton)
            self.reloadButton.connect('clicked()', self.onReload)

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
        self.labelsFormLayout = qt.QFormLayout(self.labelsCollapsibleButton)

        # Load input button
        loadInputButton = qt.QPushButton("Load input data")
        loadInputButton.toolTip = "Load data to label"
        loadInputButton.setStyleSheet("background-color: rgb(230,241,255)")
        loadInputButton.connect('clicked(bool)', self.onLoadInputButtonClicked)
        self.loadInputButton = loadInputButton
        self.measuresFormLayout.addRow(self.loadInputButton)

        # Export calcium scores all refereences
        exportButtonRef = qt.QPushButton("Export Calcium Scores from references folder")
        exportButtonRef.toolTip = "Export Calcium Scores from references folder"
        exportButtonRef.setStyleSheet("background-color: rgb(230,241,255)")
        exportButtonRef.enabled = True
        exportButtonRef.connect('clicked(bool)', self.onExportScoreButtonRefClicked)
        self.exportButtonRef = exportButtonRef
        #self.parent.layout().addWidget(self.exportButtonRef)
        self.measuresFormLayout.addRow(self.exportButtonRef)
        
        # The Input Volume Selector
        self.inputFrame = qt.QFrame(self.measuresCollapsibleButton)
        self.inputFrame.setLayout(qt.QHBoxLayout())
        self.measuresFormLayout.addRow(self.inputFrame)
        self.inputSelector = qt.QLabel("Input Volume: ", self.inputFrame)
        self.inputFrame.layout().addWidget(self.inputSelector)
        self.inputSelector = slicer.qMRMLNodeComboBox(self.inputFrame)
        self.inputSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
        self.inputSelector.addEnabled = False
        self.inputSelector.removeEnabled = False
        self.inputSelector.setMRMLScene( slicer.mrmlScene )
        self.inputFrame.layout().addWidget(self.inputSelector)

        self.RadioButtonsFrame = qt.QFrame(self.measuresCollapsibleButton)
        self.RadioButtonsFrame.setLayout(qt.QHBoxLayout())
        self.measuresFormLayout.addRow(self.RadioButtonsFrame)
        self.KEV80 = qt.QRadioButton("80 KEV", self.RadioButtonsFrame)
        self.KEV80.setToolTip("Select 80 KEV.")
        self.KEV80.checked = False
        self.KEV80.enabled = False
        self.RadioButtonsFrame.layout().addWidget(self.KEV80)
        self.KEV120 = qt.QRadioButton("120 KEV", self.RadioButtonsFrame)
        self.KEV120.setToolTip("Select 120 KEV.")
        self.KEV120.checked = False
        self.KEV120.enabled = False
        self.RadioButtonsFrame.layout().addWidget(self.KEV120)

        # Threshold button
        thresholdButton = qt.QPushButton("Threshold Volume")
        thresholdButton.toolTip = "Threshold the selected Input Volume"
        thresholdButton.setStyleSheet("background-color: rgb(230,241,255)")
        self.measuresFormLayout.addRow(thresholdButton)
        thresholdButton.connect('clicked(bool)', self.onThresholdButtonClicked)

        # Add vertical spacer
        self.layout.addStretch(1)

        # Set local var as instance attribute
        self.thresholdButton = thresholdButton

        # sets the layout to Red Slice Only
        layoutManager = slicer.app.layoutManager()
        layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

        # Save button
        self.saveButton = qt.QPushButton("Save")
        self.saveButton.toolTip = "Save data."
        self.saveButton.setStyleSheet("background-color: rgb(230,241,255)")
        self.saveButton.enabled = False
        self.parent.layout().addWidget(self.saveButton)
        self.saveButton.connect('clicked()', self.onSaveOutputButtonClicked)

        # Delete scans button
        deleteButton = qt.QPushButton("Delete data")
        deleteButton.toolTip = "Delete data"
        deleteButton.setStyleSheet("background-color: rgb(230,241,255)")
        deleteButton.connect('clicked(bool)', self.onDeleteButtonClicked)
        self.deleteButton = deleteButton
        self.parent.layout().addWidget(self.deleteButton)

        # Compute calcium scores
        scoreButton = qt.QPushButton("Calculate Calcium Scores")
        scoreButton.toolTip = "Compute Cacium scores"
        scoreButton.setStyleSheet("background-color: rgb(230,241,255)")
        scoreButton.enabled = False
        scoreButton.connect('clicked(bool)', self.onScoreButtonClicked)
        self.scoreButton = scoreButton
        self.parent.layout().addWidget(self.scoreButton)
        
        # Add scores
        self.calciumScores = [Agatston(), VolumeScore(), DensityScore(), NumLesions(), LesionVolume()]

        # Export calcium scores
        exportButton = qt.QPushButton("Export Calcium Scores")
        exportButton.toolTip = "Export Cacium scores"
        exportButton.setStyleSheet("background-color: rgb(230,241,255)")
        exportButton.enabled = False
        exportButton.connect('clicked(bool)', self.onExportScoreButtonClicked)
        self.exportButton = exportButton
        self.parent.layout().addWidget(self.exportButton)
        
        # Read settings file
        if os.path.isfile(self.filepath_settings):
            #self.writeSettings(self.filepath_settings)
            self.readSettings(self.filepath_settings)
        else:
            self.writeSettings(self.filepath_settings)
            self.readSettings(self.filepath_settings)
            
        
        dirname = os.path.dirname(os.path.abspath(__file__))
        filepath_colorTable = dirname + '/CardiacAgatstonMeasuresLUT.ctbl'
        
        # Create color table
        if self.settings['MODE']=='CACSTREE_CUMULATIVE':
            self.createColorTable(filepath_colorTable, self.settings['CACSTree'])
        else:
            self.createColorTable_CACS(filepath_colorTable, self.settings['CACSTree'])
        
        # Load color table
        slicer.util.loadColorTable(filepath_colorTable)
    
    def createColorTable(self, filepath_colorTable, CACSTree):
        f = open(filepath_colorTable, 'w')
        f.write('# Color\n')
        f.close()
        for idx, lesion in enumerate(CACSTree.lesionList):
            f = open(filepath_colorTable, 'a')
            color_str = str(lesion.color[0]) + ' ' + str(lesion.color[1]) + ' ' + str(lesion.color[2]) + ' ' + str(lesion.color[3])
            f.write(str(idx) + ' ' + lesion.name + ' ' + color_str + '\n')
            f.close()

    def createColorTable_CACS(self, filepath_colorTable, CACSTree):
        print('filepath_colorTable', filepath_colorTable)
        CACS_dict = OrderedDict([('CACSTreeDict', 0), ('OTHER', 1), ('LAD', 2), ('LCX', 3), ('RCA', 4)])
        f = open(filepath_colorTable, 'w')
        f.write('# Color\n')
        f.close()
        for key in CACS_dict.keys():
            lesion = CACSTree.getLesionByName(key)
            color_str = str(lesion.color[0]) + ' ' + str(lesion.color[1]) + ' ' + str(lesion.color[2]) + ' ' + str(lesion.color[3])
            f = open(filepath_colorTable, 'a')
            color_str = str(lesion.color[0]) + ' ' + str(lesion.color[1]) + ' ' + str(lesion.color[2]) + ' ' + str(lesion.color[3])
            f.write(str(CACS_dict[key]) + ' ' + lesion.name + ' ' + color_str + '\n')
            f.close()

    def initCACSTreeDict(self):
        
        OTHER = OrderedDict([('COLOR', (0, 255, 0, 255))])
        
        RCA_PROXIMAL = OrderedDict([('COLOR', (204, 0, 0, 255))])
        RCA_MID = OrderedDict([('COLOR', (255,0,0, 255))])
        RCA_DISTAL = OrderedDict([('COLOR', (255,80,80, 255))])
        RCA_SIDE_BRANCH = OrderedDict([('COLOR', (255,124,128, 255))])
        RCA = OrderedDict([('RCA_PROXIMAL', RCA_PROXIMAL), ('RCA_MID', RCA_MID), 
                                ('RCA_DISTAL', RCA_DISTAL), ('RCA_SIDE_BRANCH', RCA_SIDE_BRANCH), ('COLOR', (165,0,33, 255))])
        
        LM_BIF_LAD_LCX = OrderedDict([('COLOR', (11,253,224, 255))])
        LM_BIF_LAD = OrderedDict([('COLOR', (26,203,238, 255))])
        LM_BIF_LCX = OrderedDict([('COLOR', (32,132,130, 255))])
        LM_BRANCH = OrderedDict([('COLOR', (255,204,102, 255))])
        LM = OrderedDict([('LM_BIF_LAD_LCX', LM_BIF_LAD_LCX), ('LM_BIF_LAD', LM_BIF_LAD), 
                           ('LM_BIF_LCX', LM_BIF_LCX), ('LM_BRANCH', LM_BRANCH), ('COLOR', (12,176,198, 255))])
        
        LAD_PROXIMAL = OrderedDict([('COLOR', (255,153,155, 255))])
        LAD_MID = OrderedDict([('COLOR', (255,255,0, 255))])
        LAD_DISTAL = OrderedDict([('COLOR', (204,255,51, 255))])
        LAD_SIDE_BRANCH = OrderedDict([('COLOR', (11,253,244, 255))])
        LAD = OrderedDict([('LAD_PROXIMAL', LAD_PROXIMAL), ('LAD_MID', LAD_MID), ('LAD_DISTAL', LAD_DISTAL), ('LAD_SIDE_BRANCH', LAD_SIDE_BRANCH), ('COLOR', (255,204,0, 255))])
        
        LCX_PROXIMAL = OrderedDict([('COLOR', (255,0,255, 255))])
        LCX_MID = OrderedDict([('COLOR', (255,102,255, 255))])
        LCX_DISTAL = OrderedDict([('COLOR', (255,153,255, 255))])
        LCX_SIDE_BRANCH = OrderedDict([('COLOR', (255,204,255, 255))])
        LCX = OrderedDict([('LCX_PROXIMAL', LCX_PROXIMAL), ('LCX_MID', LCX_MID), ('LCX_DISTAL', LCX_DISTAL), ('LCX_SIDE_BRANCH', LCX_SIDE_BRANCH), ('COLOR', (204,0,204, 255))])

        CC = OrderedDict([('RCA', RCA), ('LM', LM), ('LAD', LAD), ('LCX', LCX), ('COLOR', (165, 0, 33, 255))])
        
        AORTA_ASC = OrderedDict([('COLOR', (72,63,255, 255))])
        AORTA_DSC = OrderedDict([('COLOR', (12,0,246, 255))])
        AORTA_ARC = OrderedDict([('COLOR', (139,133,255, 255))])
        AORTA = OrderedDict([('AORTA_ASC', AORTA_ASC), ('AORTA_DSC', AORTA_DSC), ('AORTA_ARC', AORTA_ARC), ('COLOR', (9,0,188, 255))])


        VALVE_AORTIC = OrderedDict([('COLOR', (0,102,0, 255))])
        VALVE_PULMONIC = OrderedDict([('COLOR', (51,153,102, 255))])
        VALVE_TRICUSPID = OrderedDict([('COLOR', (0,153,0, 255))])
        VALVE_MITRAL = OrderedDict([('COLOR', (0,204,0, 255))])
        
        VALVES = OrderedDict([('VALVE_AORTIC', VALVE_AORTIC), ('VALVE_PULMONIC', VALVE_PULMONIC),
                              ('VALVE_TRICUSPID', VALVE_TRICUSPID), ('VALVE_MITRAL', VALVE_MITRAL), ('COLOR', (4,68,16, 255))])
        
        STERNUM = OrderedDict([('COLOR', (167,149,75, 255))])
        VERTEBRA = OrderedDict([('COLOR', (198,185,128, 255))])
        COSTA = OrderedDict([('COLOR', (1,58,61, 255))])
        BONE = OrderedDict([('STERNUM', STERNUM), ('VERTEBRA', VERTEBRA), ('COSTA', COSTA), ('COLOR', (102,51,0, 255))])
        
        TRACHEA = OrderedDict([('COLOR', (204,236,255, 255))])
        BRONCHUS = OrderedDict([('COLOR', (255,255,204, 255))])
        NODULE_CALCIFIED  = OrderedDict([('COLOR', (204,255,204, 255))])
        LUNG_ARTERY = OrderedDict([('COLOR', (255,204,204, 255))])
        LUNG_VESSEL_NFS = OrderedDict([('COLOR', (153,204,255, 255))])
        LUNG_PARENCHYMA = OrderedDict([('COLOR', (153,255,204, 255))])

        LUNG = OrderedDict([('TRACHEA', TRACHEA), ('BRONCHUS', BRONCHUS),
                            ('NODULE_CALCIFIED', NODULE_CALCIFIED), ('LUNG_ARTERY', LUNG_ARTERY),
                            ('LUNG_VESSEL_NFS', LUNG_VESSEL_NFS),  ('LUNG_PARENCHYMA', LUNG_PARENCHYMA), ('COLOR', (204,255,255, 255))])
        
        
        NCC = OrderedDict([('AORTA', AORTA), ('VALVES', VALVES), ('BONE', BONE), ('LUNG', LUNG), ('COLOR', (102, 0, 102, 255))])    

        CACSTreeDict = OrderedDict([('OTHER', OTHER), ('CC', CC), ('NCC', NCC), ('COLOR', (0,0,0,0))])
        
        
        return CACSTreeDict
        
    def writeSettings(self, filepath_settings):
        """ Write settings into setting file

        :param filepath_settings: Filepath to settings file
        :type filepath_settings: str
        """
        
        CACSTreeDict = self.initCACSTreeDict()
        
        # Initialize settings
        settingsDefault = {'folderpath_images': 'H:/cloud/cloud_data/Projects/DL/Code/src/datasets/DISCHARGE/data_cacs/Images',
                           'folderpath_references': 'H:/cloud/cloud_data/Projects/DL/Code/src/datasets/DISCHARGE/data_cacs/References',
                           'filepath_export': 'H:/cloud/cloud_data/Projects/CACSLabeler/code/data/export.json',
                           'folderpath_export_csv': 'H:/cloud/cloud_data/Projects/CACSLabeler/code/data/export_csv',
                           'filter_input': '(*.mhd)',
                           'CalciumScores': ['AGATSTON_SCORE', 'VOLUME_SCORE', 'DENSITY_SCORE', 'NUMLESION_SCORE', 'LESIONVOLUME_SCORE'],
                           'filter_input_by_reference': False,
                           'filter_reference_with': ['-label.'],
                           'filter_reference_without': ['label-lesion.'],
                           'CACSTreeDict': CACSTreeDict,
                           'MODE': 'CACSTREE_CUMULATIVE'} # MODE can be 'CACS','CACSTREE' or 'CACSTREE_CUMULATIVE'
                           
        print('Writing setting to ' + filepath_settings)
        with open(filepath_settings, 'a') as file:
            file.write(json.dumps(settingsDefault, indent=4, encoding='utf-8'))
        self.settings = settingsDefault

    def readSettings(self, filepath_settings):
        """ Read settings from setting file

        :param filepath_settings: Filepath to settings file
        :type filepath_settings: str
        """
        
        def _decode_list(data):
            rv = []
            for item in data:
                if isinstance(item, unicode):
                    item = item.encode('utf-8')
                elif isinstance(item, list):
                    item = _decode_list(item)
                elif isinstance(item, dict):
                    item = _decode_dict(item)
                rv.append(item)
            return rv
            
        def _decode_dict(data):
            rv = {}
            for key, value in data.iteritems():
                if isinstance(key, unicode):
                    key = key.encode('utf-8')
                if isinstance(value, unicode):
                    value = value.encode('utf-8')
                elif isinstance(value, list):
                    value = _decode_list(value)
                elif isinstance(value, dict):
                    value = _decode_dict(value)
                rv[key] = value
            return rv
    
        if os.path.isfile(filepath_settings):
            print('Reading setting from ' + filepath_settings)
            with open(filepath_settings) as f:
                settings = json.load(f, object_hook=_decode_dict, object_pairs_hook=OrderedDict)
                settings = OrderedDict(settings)
                # CreateCACSTree
                settings['CACSTree'] = CACSTree()
                settings['CACSTree'].createTree(settings['CACSTreeDict'])
                self.settings = settings
        else:
            print('Settings file:' + filepath_settings + 'does not exist')
            
        # Check if folders exist
        if not os.path.isdir(self.settings['folderpath_images']):
            raise ValueError("Folderpath of image " + self.settings['folderpath_images'] + ' does not exist')
        if not os.path.isdir(self.settings['folderpath_references']):
            raise ValueError("Folderpath of references " + self.settings['folderpath_references'] + ' does not exist')
            
            
            

    def onDeleteButtonClicked(self):
        """ Delete all images in slicer

        """
        # Deleta all old nodes
        nodes=slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
        for node in nodes:
            slicer.mrmlScene.RemoveNode(node)

    def get_arteries_dict(self):
        arteries = self.settings['CACSTree'].getLesionNames()
        arteries_dict = OrderedDict()
        for k, key in enumerate(arteries):
            if k>1:
                arteries_dict[key]=k
        return arteries_dict
        
        
    def onScoreButtonClicked(self):
        # Get image and imageLabel
        inputVolumeName = self.inputImageNode.GetName()
        inputVolumeNameLabel = inputVolumeName + '-label-lesion'
        inputVolume = su.PullVolumeFromSlicer(inputVolumeName)
        inputVolumeLabel = su.PullVolumeFromSlicer(inputVolumeNameLabel)
        
        start = time.time()

        # Compute calcium scores
        
        if self.settings['MODE']=='CACSTREE_CUMULATIVE':
            arteries_dict = self.get_arteries_dict()
            arteries_sum = OrderedDict()
            arteries_sum['RCA'] = self.settings['CACSTree'].getChildrenNamesByName('RCA')
            arteries_sum['LM'] = self.settings['CACSTree'].getChildrenNamesByName('LM')
            arteries_sum['LAD'] = self.settings['CACSTree'].getChildrenNamesByName('LAD')
            arteries_sum['LCX'] = self.settings['CACSTree'].getChildrenNamesByName('LCX')
            arteries_sum['AORTA'] = self.settings['CACSTree'].getChildrenNamesByName('AORTA')
            arteries_sum['VALVES'] = self.settings['CACSTree'].getChildrenNamesByName('VALVES')
            arteries_sum['BONE'] = self.settings['CACSTree'].getChildrenNamesByName('BONE')
            arteries_sum['LUNG'] = self.settings['CACSTree'].getChildrenNamesByName('LUNG')
            arteries_sum['CC'] = self.settings['CACSTree'].getChildrenNamesByName('CC')
            arteries_sum['NCC'] = self.settings['CACSTree'].getChildrenNamesByName('NCC')
        elif self.settings['MODE']=='CACS':
            arteries_dict = OrderedDict()
            arteries_dict['LAD'] = 2
            arteries_dict['LCX'] = 3
            arteries_dict['RCA'] = 4
            arteries_sum = OrderedDict()
            arteries_sum['CC'] = ['LAD', 'LCX', 'RCA']
            
        self.calciumScoresResult=[]
        for score in self.calciumScores:
            for scorename in self.settings['CalciumScores']:
                if score.name in scorename:
                    s = score.compute(inputVolume, inputVolumeLabel, arteries_dict=arteries_dict, arteries_sum=arteries_sum)
                    score.show()
                    self.calciumScoresResult.append(s)
        print('Computation time', time.time() - start)
    
    def export_csv(self):
        for score in self.calciumScores:
            score.export_csv(self.settings, self.calciumScoresResult)

        
    def onExportScoreButtonClicked(self):
        # Export labels
        arteries_dict = self.get_arteries_dict()
        arteries_sum = OrderedDict()
        if self.settings['MODE']=='CACSTREE_CUMULATIVE':
            arteries_sum['RCA'] = self.settings['CACSTree'].getChildrenNamesByName('RCA')
            arteries_sum['LM'] = self.settings['CACSTree'].getChildrenNamesByName('LM')
            arteries_sum['LAD'] = self.settings['CACSTree'].getChildrenNamesByName('LAD')
            arteries_sum['LCX'] = self.settings['CACSTree'].getChildrenNamesByName('LCX')
            arteries_sum['AORTA'] = self.settings['CACSTree'].getChildrenNamesByName('AORTA')
            arteries_sum['VALVES'] = self.settings['CACSTree'].getChildrenNamesByName('VALVES')
            arteries_sum['BONE'] = self.settings['CACSTree'].getChildrenNamesByName('BONE')
            arteries_sum['LUNG'] = self.settings['CACSTree'].getChildrenNamesByName('LUNG')
            arteries_sum['CC'] = self.settings['CACSTree'].getChildrenNamesByName('CC')
            arteries_sum['NCC'] = self.settings['CACSTree'].getChildrenNamesByName('NCC')
        elif self.settings['MODE']=='CACS':
            arteries_dict = OrderedDict()
            arteries_dict['LAD'] = 2
            arteries_dict['LCX'] = 3
            arteries_dict['RCA'] = 4
            arteries_sum = OrderedDict()
            arteries_sum['CC'] = ['LAD', 'LCX', 'RCA']

        filepath_export = self.settings['filepath_export']
        volumeNodes = slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
        self.calciumScoresResult=[]
        for node in volumeNodes:
            volume_name = node.GetName()
            if 'label' in volume_name:
                # Compute calcium scores
                scoreResult=[]
                for score in self.calciumScores:
                    for scorename in self.settings['CalciumScores']:
                        if score.name == scorename:
                            inputVolumeNameLabel = volume_name
                            inputVolumeName = inputVolumeNameLabel[0:-13]
                            inputVolumeLabel = su.PullVolumeFromSlicer(inputVolumeNameLabel)
                            inputVolume = su.PullVolumeFromSlicer(inputVolumeName)
                            s = score.compute(inputVolume, inputVolumeLabel, arteries_dict, arteries_sum)
                            scoreResult.append(s)
                self.calciumScoresResult.append({'ImageName':volume_name, 'Scores': scoreResult})
        
        # Export information
        print('Exporting:')
        for res in self.calciumScoresResult:
            print(res['ImageName'])
        
        # Load json if exist
        if os.path.exists(filepath_export):
            with open(filepath_export) as f:
                calciumScoresResult = json.load(f)
            self.calciumScoresResult = calciumScoresResult + self.calciumScoresResult
            
        # Save json
        with open(filepath_export, 'w') as file:
            file.write(json.dumps(self.calciumScoresResult, indent=4)) # use `json.loads` to do the reverse
            
        # Save csv
        self.export_csv()
        
    def onExportScoreButtonRefClicked(self):
        
        references = glob(self.settings['folderpath_references'] + '/*-label-lesion.nrrd')
        images = glob(self.settings['folderpath_images'] + '/*.mhd')
        for ref in references[0:2]:
            _,refname,_ = splitFilePath(ref)
            name = refname[0:-13]
            for im in images:
                if name in im:
                    break

            # Read image
            properties={'Name': name}
            node = slicer.util.loadVolume(im, returnNode=True, properties=properties)[1]
            node.SetName(name)
            # Read reference
            properties={'Name': refname}
            node = slicer.util.loadVolume(ref, returnNode=True, properties=properties)[1]
            node.SetName(refname)
            # Export score
            self.onExportScoreButtonClicked()
            # Delete node
            self.onDeleteButtonClicked()
            
 
    def onSaveOutputButtonClicked(self):
        # Save
        folderpath_output = self.settings['folderpath_references']
        volumeNodes = slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
        for node in volumeNodes:
            volume_name = node.GetName()
            if 'label' in volume_name:
                filename_output = volume_name
                filepath = folderpath_output + '/' + filename_output + '.nrrd'
                slicer.util.saveNode(node, filepath)
                print('Saveing reference to: ', filepath)

    def filter_by_reference(self, filepaths, filepaths_ref, filter_reference_with, filter_reference_without):
        filenames_filt=[]
        for f in filepaths:
            _,fname,_ = splitFilePath(f)
            ref_same = False
            ref_with = False
            ref_without = False
            for ref in filepaths_ref:
                _,refname,_ = splitFilePath(ref)
                ref_same = fname in refname
                if ref_same:
                    ref_with = ref_with or all([x in ref for x in filter_reference_with])
                    ref_without = ref_without or any([x in ref for x in filter_reference_without])
            if ref_with and not ref_without:
                filenames_filt.append(f)
        return filenames_filt
                    
        
    def onLoadInputButtonClicked(self):
                   
        if self.settings['filter_input_by_reference']:
            
            filter_input = self.settings['filter_input'].decode('utf-8')[1:-1]
            filepaths = glob(self.settings['folderpath_images'] + '/' + filter_input)
            filepaths_ref = glob(self.settings['folderpath_references'] + '/*.nrrd')
            
            # Filter files by filter_reference_with and filter_reference_without
            filenames_filt = self.filter_by_reference(filepaths, filepaths_ref, self.settings['filter_reference_with'], self.settings['filter_reference_without'])

            filter_input_ref = ''
            for f in filenames_filt:
                _,fname,_ = splitFilePath(f)
                filter_input_ref = filter_input_ref + fname + '.mhd '
            if len(filenames_filt)>0:
                filter_input_ref = '(' + filter_input_ref + ')'
            else:
                filter_input_ref = '(_)'
                
            filenames = qt.QFileDialog.getOpenFileNames(self.parent, 
                                                   'Open files', 
                                                   self.settings['folderpath_images'],
                                                   filter_input_ref)
            
        else:
            filenames = qt.QFileDialog.getOpenFileNames(self.parent, 
                                                   'Open files', 
                                                   self.settings['folderpath_images'],
                                                   self.settings['filter_input'])
        
        # Read images
        imagenames = []
        for filepath in filenames:
            _, name,_ = splitFilePath(filepath)
            properties={'Name': name}
            node = slicer.util.loadVolume(filepath, returnNode=True, properties=properties)[1]
            node.SetName(name)
            imagenames.append(name)
            
        # Enable radio button
        self.KEV80.enabled = True
        self.KEV120.enabled = True
        
    def onThresholdButtonClicked(self):
        if not self.KEV120.checked and not self.KEV80.checked:
            qt.QMessageBox.warning(slicer.util.mainWindow(),
                "Select KEV", "The KEV (80 or 120) must be selected to continue.")
            return

        self.inputImageNode = self.inputSelector.currentNode()
        inputVolumeName = self.inputImageNode.GetName()
        
        # Threshold image
        self.CACSLabelerModuleLogic = CACSLabelerModuleLogic(self.KEV80.checked, self.KEV120.checked, inputVolumeName)
        self.CACSLabelerModuleLogic.runThreshold()
        
        # View thresholded image as label map and image as background image in red widget
        node = slicer.util.getFirstNodeByName(self.CACSLabelerModuleLogic.calciumName[0:-13])
        slicer.util.setSliceViewerLayers(background=node)
        
        # Set slicer offset
        slicer.util.resetSliceViews()

        # Creates and adds the custom Editor Widget to the module
        if self.localCardiacEditorWidget is None:
            self.localCardiacEditorWidget = CardiacEditorWidget(parent=self.parent, showVolumesFrame=False, settings=self.settings)
            self.localCardiacEditorWidget.setup()
            self.localCardiacEditorWidget.enter()

        # Activate Save Button
        self.saveButton.enabled = True
        self.scoreButton.enabled = True
        self.exportButton.enabled = True

    def onReload(self,moduleName="CACSLabelerModule"):
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

    def onReloadAndTest(self,moduleName="CACSLabelerModule"):
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
# CACSLabelerModuleLogic
#
class CACSLabelerModuleLogic:
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget
    """
    def __init__(self, KEV80=False, KEV120=False, inputVolumeName=None):
        self.lowerThresholdValue = None
        self.upperThresholdValue = 5000
        self.editUtil = EditorLib.EditUtil.EditUtil()
        self.KEV80 = KEV80
        self.KEV120 = KEV120
        self.inputVolumeName = inputVolumeName
        self.calciumLabelNode = None
        self.CardiacAgatstonMeasuresLUTNode = None

    def runThreshold(self):

        # Sets minimum threshold value based on KEV80 or KEV120
        if self.KEV80:
            print('!!! Method for KEV80 not implemented !!!')
        elif self.KEV120:
            self.lowerThresholdValue = 130
            #calciumName = "{0}_120KEV_{1}HU_Calcium_Label".format(self.inputVolumeName, self.lowerThresholdValue)
            calciumName = "{0}-label-lesion".format(self.inputVolumeName)
        
        # Check if node already exists
        node = slicer.util.getFirstNodeByName(calciumName)
        if node is None:
            print('----- Thresholding -----')
            print('Threshold value:', self.lowerThresholdValue)
            inputVolume = su.PullVolumeFromSlicer(self.inputVolumeName)
            thresholdImage = sitk.BinaryThreshold(inputVolume, self.lowerThresholdValue, self.upperThresholdValue)
            castedThresholdImage = sitk.Cast(thresholdImage, sitk.sitkInt16)
            su.PushLabel(castedThresholdImage, calciumName)
        self.assignLabelLUT(calciumName)
        self.setLowerPaintThreshold()
        self.calciumName=calciumName
        self.calciumNode = su.PullVolumeFromSlicer(calciumName)
            #self.addObserver(self.calciumNode, vtk.vtkCommand.ModifiedEvent, self.test02)

    def setLowerPaintThreshold(self):
        # sets parameters for paint specific to KEV threshold level
        parameterNode = self.editUtil.getParameterNode()
        parameterNode.SetParameter("LabelEffect,paintOver","1")
        parameterNode.SetParameter("LabelEffect,paintThreshold","1")
        parameterNode.SetParameter("LabelEffect,paintThresholdMin","{0}".format(self.lowerThresholdValue))
        parameterNode.SetParameter("LabelEffect,paintThresholdMax","{0}".format(self.upperThresholdValue))
        
        #parameterNode.GetParameter()
        #print

    def assignLabelLUT(self, calciumName):
        # Set the color lookup table (LUT) to the custom CardiacAgatstonMeasuresLUT
        self.calciumLabelNode = slicer.util.getNode(calciumName)
        self.CardiacAgatstonMeasuresLUTNode = slicer.util.getNode(pattern='CardiacAgatstonMeasuresLUT')
        CardiacAgatstonMeasuresLUTID = self.CardiacAgatstonMeasuresLUTNode.GetID()
        calciumDisplayNode = self.calciumLabelNode.GetDisplayNode()
        calciumDisplayNode.SetAndObserveColorNodeID(CardiacAgatstonMeasuresLUTID)

#    def setLowerPaintThreshold(self):
#        # sets parameters for paint specific to KEV threshold level
#        parameterNode = self.editUtil.getParameterNode()
#        parameterNode.SetParameter("LabelEffect,paintOver","1")
#        parameterNode.SetParameter("LabelEffect,paintThreshold","1")
#        parameterNode.SetParameter("LabelEffect,paintThresholdMin","{0}".format(self.lowerThresholdValue))
#        parameterNode.SetParameter("LabelEffect,paintThresholdMax","{0}".format(self.upperThresholdValue))

    def hasImageData(self,volumeNode):
        """This is a dummy logic method that
        returns true if the passed in volume
        node has valid image data
        """
        if not volumeNode:
            print('no volume node')
            return False
        if volumeNode.GetImageData() == None:
            print('no image data')
            return False
        return True

    def hasCorrectLUTData(self,lutNode):
        """This is a dummy logic method that
        returns true if the passed in LUT
        node has valid LUT table data
        """
        if not lutNode:
            print('no Cardiac LUT node')
            return False
        number = lutNode.GetLookupTable().GetNumberOfAvailableColors()
        if number == 7:
            return True
        else:
            print('there should be 7 colors in LUT table, there are %s'%number)
            return False

    def delayDisplay(self,message,msec=1000):
        #
        # logic version of delay display
        #
        print(message)
        self.info = qt.QDialog()
        self.infoLayout = qt.QVBoxLayout()
        self.info.setLayout(self.infoLayout)
        self.label = qt.QLabel(message,self.info)
        self.infoLayout.addWidget(self.label)
        qt.QTimer.singleShot(msec, self.info.close)
        self.info.exec_()

    def takeScreenshot(self,name,description,type=-1):
        # show the message even if not taking a screen shot
        self.delayDisplay(description)

        if self.enableScreenshots == 0:
            return

        lm = slicer.app.layoutManager()
        # switch on the type to get the requested window
        widget = 0
        if type == -1:
            # full window
            widget = slicer.util.mainWindow()
        elif type == slicer.qMRMLScreenShotDialog().FullLayout:
            # full layout
            widget = lm.viewport()
        elif type == slicer.qMRMLScreenShotDialog().ThreeD:
            # just the 3D window
            widget = lm.threeDWidget(0).threeDView()
        elif type == slicer.qMRMLScreenShotDialog().Red:
            # red slice window
            widget = lm.sliceWidget("Red")
        elif type == slicer.qMRMLScreenShotDialog().Yellow:
            # yellow slice window
            widget = lm.sliceWidget("Yellow")
        elif type == slicer.qMRMLScreenShotDialog().Green:
            # green slice window
            widget = lm.sliceWidget("Green")

        # grab and convert to vtk image data
        qpixMap = qt.QPixmap().grabWidget(widget)
        qimage = qpixMap.toImage()
        imageData = vtk.vtkImageData()
        slicer.qMRMLUtils().qImageToVtkImageData(qimage,imageData)

        annotationLogic = slicer.modules.annotations.logic()
        annotationLogic.CreateSnapShot(name, description, type, self.screenshotScaleFactor, imageData)

    def run(self,inputVolume,outputVolume,enableScreenshots=0,screenshotScaleFactor=1):
        """
        Run the actual algorithm
        """

        self.delayDisplay('Running the aglorithm')

        self.enableScreenshots = enableScreenshots
        self.screenshotScaleFactor = screenshotScaleFactor

        self.takeScreenshot('CardiacAgatstonMeasures-Start','Start',-1)

        return True

class CardiacEditorWidget(Editor.EditorWidget):
    def __init__(self, parent=None, showVolumesFrame=None, settings=None):
        self.settings = settings
        super(CardiacEditorWidget, self).__init__(parent=parent, showVolumesFrame=showVolumesFrame)
        
    def createEditBox(self):
        self.editLabelMapsFrame.collapsed = False
        self.editBoxFrame = qt.QFrame(self.effectsToolsFrame)
        self.editBoxFrame.objectName = 'EditBoxFrame'
        self.editBoxFrame.setLayout(qt.QVBoxLayout())
        self.effectsToolsFrame.layout().addWidget(self.editBoxFrame)
        self.toolsBox = CardiacEditBox(self.settings, self.editBoxFrame, optionsFrame=self.effectOptionsFrame)
        
        #parameterNode = self.editUtil.getParameterNode()
        #print('parameterNode', parameterNode.GetParameterNames())
        #propagationMode = parameterNode.GetParameter("propagationMode")
        #print('propagationMode', propagationMode)
        #effect = parameterNode.GetParameter("effect")
        #print('effect', effect)
        #name = parameterNode.GetParameterName(0, 0)
        #print('name', name)
        
        #print('toolsBox', self.toolsBox)
        #print('effectOptionsFrame', self.effectOptionsFrame)
        #self.effectOptionsFrame.setEnabled(False)
        
        #child = self.effectOptionsFrame.findChildren(qt.QCheckBox)
        #print('child', child)
        
        #print('self.effectsToolsFrame123', self.effectsToolsFrame)
        
        
#        n=parameterNode
#        for groupIndex in range(n.GetNumberOfParameterGroups()):
#            for parameterIndex in range(n.GetNumberOfParametersInGroup(groupIndex)):
#                print('Parameter ({0}/{1}): {2} ({3})'.format(groupIndex, parameterIndex, n.GetParameterName(groupIndex, parameterIndex), n.GetParameterLabel(groupIndex, parameterIndex)))
#
#                
#                
#    def installShortcutKeys(self):
#        """Turn on editor-wide shortcuts.  These are active independent
#        of the currently selected effect."""
#        Key_Escape = 0x01000000 # not in PythonQt
#        Key_Space = 0x20 # not in PythonQt
#        self.shortcuts = []
#        keysAndCallbacks = (
#            ('z', self.toolsBox.undoRedo.undo),
#            ('y', self.toolsBox.undoRedo.redo),
#            ('h', self.editUtil.toggleCrosshair),
#            ('o', self.editUtil.toggleLabelOutline),
#            ('t', self.editUtil.toggleForegroundBackground),
#            (Key_Escape, self.toolsBox.defaultEffect),
#            ('p', lambda : self.toolsBox.selectEffect('PaintEffect')),
#            ('1', self.toolsBox.onDefaultChangeIslandButtonClicked),
#            #('2', self.toolsBox.onLMchangeIslandButtonClicked),
#            ('3', self.toolsBox.onLADchangeIslandButtonClicked),
#            ('4', self.toolsBox.onLCXchangeIslandButtonClicked),
#            ('5', self.toolsBox.onRCAchangeIslandButtonClicked),
#            )
#        for key,callback in keysAndCallbacks:
#            shortcut = qt.QShortcut(slicer.util.mainWindow())
#            shortcut.setKey( qt.QKeySequence(key) )
#            shortcut.connect( 'activated()', callback )
#            self.shortcuts.append(shortcut)

class CardiacEditBox(EditorLib.EditBox):
    def __init__(self, settings, *args, **kwargs):
        self.settings = settings
        super(CardiacEditBox, self).__init__(*args, **kwargs)

    # create the edit box
    def create(self):

        self.findEffects()

        self.rowFrames = []
        self.actions = {}
        self.buttons = {}
        self.icons = {}
        self.callbacks = {}

        if self.settings['MODE']=='CACSTREE_CUMULATIVE' or self.settings['MODE']=='CACSTREE':
            self.mainFrame = qt.QFrame(self.parent)
            self.mainFrame.objectName = 'TreeFrame'
            vbox = qt.QVBoxLayout()
            self.mainFrame.setLayout(vbox)
            self.parent.layout().addWidget(self.mainFrame)
            
            def addCombo(CACSTreeDict, NumCombos):
                for i in range(NumCombos):
                    combo = qt.QComboBox()
                    if i==0:
                        items = list(CACSTreeDict.keys())
                        items = [x for x in items if not x=='COLOR']
                        combo.addItems(items)
                        combo.setCurrentIndex(items.index('OTHER'))
                        combo.toolTip = "Label - Default"
                        color = CACSTreeDict['OTHER']['COLOR']
                        color_str = 'background-color: rgb(' + str(color[0]) + ',' + str(color[1]) + ',' + str(color[2]) + ')'
                        combo.setStyleSheet(color_str)
                        combo.setVisible(True)
                        combo.setAccessibleName(str(i))
                    else:
                        combo.addItems([''])
                        combo.toolTip = "Label - Default"
                        combo.setStyleSheet("background-color: rgb(100,100,100)")
                        combo.setVisible(False)
                        combo.setAccessibleName(str(i))
                        
                    #combo.currentIndexChanged.connect(self.selectionchange)
                    combo.currentIndexChanged.connect(self.selectionChangeFunc(i))
                    self.mainFrame.layout().addWidget(combo)
                    self.comboList.append(combo)

            # Create combo boxes
            CACSTreeDict = self.settings['CACSTreeDict']
            self.comboList = []
            addCombo(CACSTreeDict, NumCombos=5)
        
        ####################################################
        else:
            self.mainFrame = qt.QFrame(self.parent)
            self.mainFrame.objectName = 'MainFrame'
            vbox = qt.QVBoxLayout()
            self.mainFrame.setLayout(vbox)
            self.parent.layout().addWidget(self.mainFrame)
            CACSTreeDict = self.settings['CACSTreeDict']
            
            # The OTHER Label Selector
            color = CACSTreeDict['OTHER']['COLOR']
            color_str = 'background-color: rgb(' + str(color[0]) + ',' + str(color[1]) + ',' + str(color[2]) + ')'
            OTHERChangeIslandButton = qt.QPushButton("OTHER")
            OTHERChangeIslandButton.toolTip = "Label - OTHER"
            OTHERChangeIslandButton.setStyleSheet(color_str)
            self.mainFrame.layout().addWidget(OTHERChangeIslandButton)
            OTHERChangeIslandButton.connect('clicked(bool)', self.onOTHERChangeIslandButtonClicked)
    
            # The Input Left Arterial Descending (LAD) Label 
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
            
            self.LADchangeIslandButton = LADchangeIslandButton
            self.LCXchangeIslandButton = LCXchangeIslandButton
            self.RCAchangeIslandButton = RCAchangeIslandButton
            self.OTHERChangeIslandButton = OTHERChangeIslandButton

        # create all of the buttons
        # createButtonRow() ensures that only effects in self.effects are exposed,
        self.createButtonRow( ("PreviousCheckPoint", "NextCheckPoint",
                               "DefaultTool", "PaintEffect", "EraseLabel","ChangeIslandEffect"),
                              rowLabel="Undo/Redo/Default: " )

        extensions = []
        for k in slicer.modules.editorExtensions:
            #print('extension', k)
            extensions.append(k)
        self.createButtonRow( extensions )
        
        #print('effectButtons', self.editorBuiltins["PaintEffect"])
        #print('currentTools', self.currentTools)
        
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
        self.toolsActiveToolName.setText( 'ToolsActiveToolName' )
        self.toolsActiveToolName.setStyleSheet("background-color: rgb(232,230,235)")
        self.toolsActiveToolFrame.layout().addWidget(self.toolsActiveToolName)
        vbox.addStretch(1)

        self.updateUndoRedoButtons()
        self._onParameterNodeModified(EditUtil.getParameterNode())

    def selectionChangeFunc(self, comboIdx):
        #print('currentTools123', self.currentTools)
        CACSTree = self.settings['CACSTree']
        comboIdx = comboIdx
        def selectionChange(idx):

            if idx>-1:
                combo = self.comboList[comboIdx]
                value = combo.itemText(idx).encode('utf8')
                
                childrens = CACSTree.getChildrenByName(value)
                if len(childrens) > 0:
                    k=0
                    while len(childrens) > 0:
                        k=k+1
                        if self.settings['MODE']=='CACSTREE_CUMULATIVE':
                            items = [x.name for x in childrens]
                        else:
                            items = ['UNDEFINED'] + [x.name for x in childrens]
                        self.comboList[comboIdx+k].clear()
                        self.comboList[comboIdx+k].addItems(items)
                        self.comboList[comboIdx+k].setVisible(True)
                        value = items[0]
                        childrens = CACSTree.getChildrenByName(value)
                else:
                    for i in range(comboIdx+1, len(self.comboList)):
                        self.comboList[i].setVisible(False)
                        
#                childrens = CACSTree.getChildrenByName(value)
#                if len(childrens) > 0:
#                    if self.settings['MODE']=='CACSTREE_CUMULATIVE':
#                        items = [x.name for x in childrens]
#                    else:
#                        items = ['UNDEFINED'] + [x.name for x in childrens]
#                    self.comboList[comboIdx+1].clear()
#                    self.comboList[comboIdx+1].addItems(items)
#                    self.comboList[comboIdx+1].setVisible(True)
#                else:
#                    for i in range(comboIdx+1, len(self.comboList)):
#                        self.comboList[i].setVisible(False)

                # Update label
                if self.settings['MODE']=='CACSTREE_CUMULATIVE':
                    if len(childrens) > 0:
                        value = childrens[0].name
                        label = CACSTree.getIndexByName(value)
                    else:
                        label = CACSTree.getIndexByName(value)
                else:
                    label = CACSTree.getIndexByName(value)

                if label is not None:
                    # ChangeIsland
                    self.selectEffect("PaintEffect")
                    EditUtil.setLabel(label)
                    # Update color
                    color = CACSTree.getColorByName(value)
                    color_str = 'background-color: rgb(' + str(color[0]) + ',' + str(color[1]) + ',' + str(color[2]) + ')'
                    combo.setStyleSheet(color_str)
                    label = CACSTree.getIndexByName(value)
                    self.selectEffect("PaintEffect")
                    EditUtil.setLabel(label)
                if value=='UNDEFINED':
                    comboUp = self.comboList[comboIdx-1]
                    valueUp = comboUp.currentText
                    color = CACSTree.getColorByName(valueUp)
                    color_str = 'background-color: rgb(' + str(color[0]) + ',' + str(color[1]) + ',' + str(color[2]) + ')'
                    combo.setStyleSheet(color_str)
                    self.selectEffect("PaintEffect")
                    label = CACSTree.getIndexByName(valueUp)
                    EditUtil.setLabel(label)

        return selectionChange
        

    def onTestButtonClicked1(self):
        print('onTestButtonClicked1')

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

