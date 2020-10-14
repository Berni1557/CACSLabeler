#Test
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
from collections import defaultdict
from EditorLib.EditUtil import EditUtil
from glob import glob
import random
import numpy as np
from SimpleITK import ConnectedComponentImageFilter
import csv

#import csv
#csv_columns = ['No','Name','Country']
#dict_data = [
#{'No': 1, 'Name': 'Alex', 'Country': 'India'},
#{'No': 2, 'Name': 'Ben', 'Country': 'USA'},
#{'No': 3, 'Name': 'Shri Ram', 'Country': 'India'},
#{'No': 4, 'Name': 'Smith', 'Country': 'USA'},
#{'No': 5, 'Name': 'Yuva Raj', 'Country': 'India'},
#]
#csv_file = "H:/cloud/cloud_data/Projects/CACSLabeler/code/data/export.csv"
#try:
#    with open(csv_file, 'w') as csvfile:
#        writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
#        writer.writeheader()
#        for data in dict_data:
#            writer.writerow(data)
#except IOError:
#    print("I/O error")

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
        self.filepath_settings = os.path.dirname(os.path.dirname(os.path.dirname(currentFile))) + '\\data\\settings.txt'

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

            # reload and test button
            # (use this during development, but remove it when delivering
            #  your module to users)
#            self.reloadAndTestButton = qt.QPushButton("Reload and Test")
#            self.reloadAndTestButton.toolTip = "Reload this module and then run the self tests."
#            reloadFormLayout.addWidget(self.reloadAndTestButton)
#            self.reloadAndTestButton.connect('clicked()', self.onReloadAndTest)


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

#        # Settings filepath
#        currentFile = os.path.dirname(os.path.abspath(__file__))
#        self.filepath_settings = os.path.dirname(os.path.dirname(os.path.dirname(currentFile))) + '\\data\\settings.txt'
#

#        f1 = os.path.dirname(os.path.dirname(os.path.dirname(f)))
#        f2 = f1 + '\\data\\settings.txt'
#        print('f2',f2)
#        print('isfile', os.path.isfile(f2))
#
#        print('f', f + '\\..\\..\\..\\data\\settings.txt')
#        print('isfile', os.path.isfile(f))
#        print('dir', os.path.dirname(os.path.dirname(os.path.dirname(f))))
#
#        self.fileSettingsEdit = qt.QLineEdit()
#        self.measuresFormLayout.addRow(self.fileSettingsEdit)
#        self.fileSettingsEdit.setText('Select settings file')
        # Check if settings file exist


        # Load input button
        loadInputButton = qt.QPushButton("Load input data")
        loadInputButton.toolTip = "Load data to label"
        loadInputButton.setStyleSheet("background-color: rgb(230,241,255)")
        loadInputButton.connect('clicked(bool)', self.onLoadInputButtonClicked)
        self.loadInputButton = loadInputButton
        self.measuresFormLayout.addRow(self.loadInputButton)

        # Select data source
        self.RadioButtonsFrame = qt.QFrame(self.measuresCollapsibleButton)
        self.RadioButtonsFrame.setLayout(qt.QHBoxLayout())
        self.measuresFormLayout.addRow(self.RadioButtonsFrame)
        dataSourceButton = qt.QRadioButton("Select data with weak label.", self.RadioButtonsFrame)
        dataSourceButton.setToolTip("Select data with weak label.")
        dataSourceButton.checked = False
        self.dataSourceButton = dataSourceButton
        self.measuresFormLayout.addRow(self.dataSourceButton)

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

        # Radio Buttons for Selecting 80 KEV or 120 KEV
#        self.RadioButtonsFrame = qt.QFrame(self.measuresCollapsibleButton)
#        self.RadioButtonsFrame.setLayout(qt.QHBoxLayout())
#        self.measuresFormLayout.addRow(self.RadioButtonsFrame)

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

        #self.fileDilaog = qt.QFileDialog.getExistingDirectory()
        #filepath = self.measuresFormLayout.addRow(self.fileDilaog)
#        self.fileEdit = qt.QLineEdit()
#        self.measuresFormLayout.addRow(self.fileEdit)

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

        # Compute agatston score
        agatstonButton = qt.QPushButton("Compute Agatston")
        agatstonButton.toolTip = "Compute Agatsto"
        agatstonButton.setStyleSheet("background-color: rgb(230,241,255)")
        agatstonButton.enabled = False
        agatstonButton.connect('clicked(bool)', self.onAgatstonButtonClicked)
        self.agatstonButton = agatstonButton
        self.parent.layout().addWidget(self.agatstonButton)

        # Read settings file
        if os.path.isfile(self.filepath_settings):
            self.readSettings(self.filepath_settings)
        else:
            self.writeSettings(self.filepath_settings)


    def writeSettings(self, filepath_settings):
        """ Write settings into setting file

        :param filepath_settings: Filepath to settings file
        :type filepath_settings: str
        """

        # Initialize settings
        settings = {'folderpath_input': 'H:/cloud/cloud_data/Projects/DL/Code/src/experiments/EXP001/data/data_cacs',
                    'folderpath_output': 'H:/cloud/cloud_data/Projects/DL/Code/src/experiments/EXP001/data/data_cacs'}

        # Write settings to file
        f = open(filepath_settings, "a")
        for key,value in settings.items():
            f.write(key + ':' + value + "\n")
        f.close()
        self.settings = settings

    def readSettings(self, filepath_settings):
        """ Read settings from setting file

        :param filepath_settings: Filepath to settings file
        :type filepath_settings: str
        """

        if os.path.isfile(filepath_settings):
            print('Reading setting')
            settings=dict()
            f = open(filepath_settings, "r")
            lines = f.readlines()
            for l in lines:
                s = l[0:-2].split(':')
                key = s[0]
                value = l[0:-1][len(key)+1:]
                settings[key]=value
            f.close()
            self.settings = settings
        else:
            print('Settings file:' + filepath_settings + 'does not exist')

    def onDeleteButtonClicked(self):
        """ Delete all images in slicer

        """
        # Deleta all old nodes
        nodes=slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
        for node in nodes:
            slicer.mrmlScene.RemoveNode(node)

    def densityFactor(self, value):
        """ Compute density weigt factor for agatston score based on maximum HU value of a lesion

        :param value: Maximum HU value of a lesion
        :type value: int
        """
        if value<130:
            densfactor=0
        elif value>=130 and value<199:
            densfactor=1
        elif value>=199 and value<299:
            densfactor=2
        elif value>=299 and value<399:
            densfactor=3
        else:
            densfactor=4
        return densfactor

    def CACSGrading(self, value):
        """ Compute agatston grading from agatston score

        :param value: Agatston score
        :type value: float
        """
        if value>1 and value<=10:
            grading = 'minimal'
        elif value>10 and value<=100:
            grading = 'mild'
        elif value>100 and value<=400:
            grading = 'moderate'
        elif value>400:
            grading = 'severe'
        else:
            grading='zero'
        return grading

    def computeAgatston(self, image, imageLabel, pixelVolume):
        """ Compute agatston score from image and image label

        :param image: Image
        :type image: np.ndarray
        :param imageLabel: Image label
        :type imageLabel: np.ndarray
        :param pixelVolume: Volume of apixel
        :type pixelVolume: float
        """

        # Neighborhood of connected components (6-connectivity)
        structure = np.zeros((3,3,3))
        structure[1,1,1] = 1
        structure[2,1,1] = 1
        structure[1,2,1] = 1
        structure[1,1,2] = 1
        structure[0,1,1] = 1
        structure[1,0,1] = 1
        structure[1,1,0] = 1

        # Iterate over arteries
        agatston = defaultdict(lambda: None, {'LAD': 0, 'LCX': 0, 'RCX': 0})
        for k, key in enumerate(agatston.keys()):
            # Extract binary mask of lesions from one artery
            imageLabelA = imageLabel==(k+2)
            image_sitk = sitk.GetImageFromArray(imageLabelA.astype(np.uint8))
            # Extract connected components
            compFilter = ConnectedComponentImageFilter()
            labeled_sitk = compFilter.Execute(image_sitk)
            labeled = sitk.GetArrayFromImage(labeled_sitk)
            ncomponents = labeled.max()
            agatstonArtery = 0
            # Iterate over lesions from an artery
            for c in range(1,ncomponents+1):
                labeledc = labeled==c
                image_mask = image * labeledc
                # Extract maximum HU of alesion
                attenuation = image_mask.max()
                volume = labeledc.sum() * pixelVolume
                # Calculate density weigt factor
                densfactor = self.densityFactor(attenuation)
                # Calculate agatston score for a lesion
                agatstonLesion = volume * densfactor
                agatstonArtery = agatstonArtery + agatstonLesion
            agatston[key] = agatstonArtery
        agatstonScore = np.array(agatston.values()).sum()
        agatston['AgatstonScore'] = agatstonScore
        return agatston

    def exportAgatston(self, agatstonDict, filepath_csv):
        #try:
        csv_columns = agatstonDict[0].keys()
        with open(filepath_csv, 'w') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
            writer.writeheader()
            for data in agatstonDict:
                writer.writerow(data)
        #except IOError:
        #    print("I/O error")

    def onAgatstonButtonClicked(self):
        inputVolumeName = self.inputImageNode.GetName()
        inputVolumeNameLabel = inputVolumeName + '-label-lesion'
        inputVolume = su.PullVolumeFromSlicer(inputVolumeName)
        inputVolumeLabel = su.PullVolumeFromSlicer(inputVolumeNameLabel)
        image = sitk.GetArrayFromImage(inputVolume)
        imageLabel = sitk.GetArrayFromImage(inputVolumeLabel)
        spacing = inputVolume.GetSpacing()
        pixelVolume = spacing[0]*spacing[1]*spacing[2]
        agatston = self.computeAgatston(image, imageLabel, pixelVolume)
        agatstonGrading = self.CACSGrading(agatston['AgatstonScore'])
        agatston['SerisInstanceUID'] = inputVolumeName

        # Print calcium scoring
        print('---------------------------')
        print('----- Agatston score per Artery-----')
        for key,value in agatston.items():
            print(key,value)
        print('----- Agatston score-----')
        print(agatston['AgatstonScore'])
        print('----- Agatston grading-----')
        print(agatstonGrading)
        print('---------------------------')

        # Sort keys
        #key_list = ['SerisInstanceUID', 'AgatstonScore', 'LAD', 'LXC', 'RCX']
        #agatston1 = dict([(key, agatston[key]) for key in key_list if key in agatston])

        #print('agatston1', agatston1)
        # Export agatston results
        filepath_csv = '/Users/marchiggins/Desktop/Hausarbeit/Agatston_Score/Results/Export.csv'
        agatstonDict = [agatston]
        self.exportAgatston(agatstonDict, filepath_csv)


    def onSaveOutputButtonClicked(self):
        print ('onSaveOutputButtonClicked')
        # Save
        folderpath_output = '/Users/marchiggins/Desktop/Hausarbeit/Agatston_Score/Output'
        volumeNodes = slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
        for node in volumeNodes:
            volume_name = node.GetName()
            if 'label' in volume_name:
                print('volume_name', volume_name)
                filename_output = volume_name
                filepath = folderpath_output + '/' + filename_output + '.nrrd'
                slicer.util.saveNode(node, filepath)

    def onLoadInputButtonClicked(self):

        # Deleta all old nodes
        nodes=slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
        for node in nodes:
            slicer.mrmlScene.RemoveNode(node)

        # Filter filpath by existing labels
        NumImages = 1
        #folderpath_input = self.settings['folderpath_input']
        import os
        #print(os.path.dirname(os.path.abspath(__file__)))
        folderpath_input = "/Users/marchiggins/Desktop/Hausarbeit/Agatston_Score/Input"
        #print(os.path.isdir(folderpath_input))
        print(folderpath_input)
        filepathList_input_all = glob(folderpath_input + '/*.mhd')
        filepathList_label = glob(folderpath_input + '/*-label-lesion.nrrd')
        filepathList_input=[]
        for f0 in filepathList_input_all:
            found = False
            for f1 in filepathList_label:
                if f1.split('-')[0] in f0:
                    found = True
            if not found:
                filepathList_input.append(f0)

        # Filter if weak label exist
        if self.dataSourceButton.checked:
            filepathList_input_filt=[]
            filepathList_label_weak = glob(folderpath_input + '/*-label.nrrd')
            for f0 in filepathList_input:
                found = False
                for f1 in filepathList_label_weak:
                    if f1.split('-')[0] in f0:
                        found = True
                if found:
                    filepathList_input_filt.append(f0)
            filepathList_input = filepathList_input_filt

        self.filepathList_input = filepathList_input
        random.shuffle(self.filepathList_input)

        for filepath in  self.filepathList_input[0:NumImages]:
            _, name,_ = splitFilePath(filepath)
            properties={'Name': name}
            node = slicer.util.loadVolume(filepath, returnNode=True, properties=properties)[1]
            node.SetName(name)

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

        self.CACSLabelerModuleLogic = CACSLabelerModuleLogic(self.KEV80.checked, self.KEV120.checked, inputVolumeName)
        self.CACSLabelerModuleLogic.runThreshold()

        #self.thresholdButton.enabled = False

        # Creates and adds the custom Editor Widget to the module
        self.localCardiacEditorWidget = CardiacEditorWidget(parent=self.parent, showVolumesFrame=False)
        self.localCardiacEditorWidget.setup()
        self.localCardiacEditorWidget.enter()

        # Adds Label Statistics Widget to Module
#        self.localLabelStatisticsWidget = CardiacStatisticsWidget(self.KEV120, self.KEV80,
#                                                             self.localCardiacEditorWidget,
#                                                             parent=self.parent)
        #self.localLabelStatisticsWidget.setup()

        # Activate Save Button
        self.saveButton.enabled = True
        self.agatstonButton.enabled = True

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
        lutPath = os.path.join('/Users/marchiggins/Desktop/Hausarbeit/Code/CACSLabeler-main/src/CACSLabeler/CACSLabelerModule/CardiacAgatstonMeasuresLUT.ctbl')
        slicer.util.loadColorTable(lutPath)

    def runThreshold(self):

        # Sets minimum threshold value based on KEV80 or KEV120
        if self.KEV80:
            print('!!! Method for KEV80 not implemented !!!')
        elif self.KEV120:
            self.lowerThresholdValue = 130
            #calciumName = "{0}_120KEV_{1}HU_Calcium_Label".format(self.inputVolumeName, self.lowerThresholdValue)
            calciumName = "{0}-label-lesion".format(self.inputVolumeName)

        print('----- Thresholding -----')
        print('Threshold value:', self.lowerThresholdValue)
        inputVolume = su.PullVolumeFromSlicer(self.inputVolumeName)
        thresholdImage = sitk.BinaryThreshold(inputVolume, self.lowerThresholdValue, self.upperThresholdValue)
        castedThresholdImage = sitk.Cast(thresholdImage, sitk.sitkInt16)
        su.PushLabel(castedThresholdImage, calciumName)
        self.assignLabelLUT(calciumName)
        self.setLowerPaintThreshold()

    def assignLabelLUT(self, calciumName):
        # Set the color lookup table (LUT) to the custom CardiacAgatstonMeasuresLUT
        self.calciumLabelNode = slicer.util.getNode(calciumName)
        self.CardiacAgatstonMeasuresLUTNode = slicer.util.getNode(pattern='CardiacAgatstonMeasuresLUT')
        CardiacAgatstonMeasuresLUTID = self.CardiacAgatstonMeasuresLUTNode.GetID()
        calciumDisplayNode = self.calciumLabelNode.GetDisplayNode()
        calciumDisplayNode.SetAndObserveColorNodeID(CardiacAgatstonMeasuresLUTID)

    def setLowerPaintThreshold(self):
        # sets parameters for paint specific to KEV threshold level
        parameterNode = self.editUtil.getParameterNode()
        parameterNode.SetParameter("LabelEffect,paintOver","1")
        parameterNode.SetParameter("LabelEffect,paintThreshold","1")
        parameterNode.SetParameter("LabelEffect,paintThresholdMin","{0}".format(self.lowerThresholdValue))
        parameterNode.SetParameter("LabelEffect,paintThresholdMax","{0}".format(self.upperThresholdValue))

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

class CACSLabelerModuleTest(unittest.TestCase):
    """
    This is the test case for your scripted module.
    """

    def delayDisplay(self,message,msec=1000):
        """This utility method displays a small dialog and waits.
        This does two things: 1) it lets the event loop catch up
        to the state of the test so that rendering and widget updates
        have all taken place before the test continues and 2) it
        shows the user/developer/tester the state of the test
        so that we'll know when it breaks.
        """
        print(message)
        self.info = qt.QDialog()
        self.infoLayout = qt.QVBoxLayout()
        self.info.setLayout(self.infoLayout)
        self.label = qt.QLabel(message,self.info)
        self.infoLayout.addWidget(self.label)
        qt.QTimer.singleShot(msec, self.info.close)
        self.info.exec_()

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        self.delayDisplay("Closing the scene")
        layoutManager = slicer.app.layoutManager()
        layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)
        slicer.mrmlScene.Clear(0)

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_CardiacAgatstonMeasures1()
        self.test_CardiacAgatstonMeasures2()
        self.test_CardiacAgatstonMeasures3()

    def test_CardiacAgatstonMeasures1(self):
        """ Ideally you should have several levels of tests.  At the lowest level
        tests sould exercise the functionality of the logic with different inputs
        (both valid and invalid).  At higher levels your tests should emulate the
        way the user would interact with your code and confirm that it still works
        the way you intended.
        One of the most important features of the tests is that it should alert other
        developers when their changes will have an impact on the behavior of your
        module.  For example, if a developer removes a feature that you depend on,
        your test should break so they know that the feature is needed.
        """

        self.delayDisplay("Starting Test Part 1 - Importing heart scan")

        try:
            #
            # first, get some data
            #
            m = slicer.util.mainWindow()
            m.moduleSelector().selectModule('CACSLabelerModule')

            import urllib
            downloads = (
                ('http://www.na-mic.org/Wiki/images/4/4e/CardiacAgatstonMeasures_TutorialContestSummer2014.zip',
                 'CardiacAgatstonMeasures_TutorialContestSummer2014.zip'),
                )

            self.delayDisplay("Downloading")

            for url,name in downloads:
              filePath = os.path.join(slicer.app.temporaryPath, name)
              if not os.path.exists(filePath) or os.stat(filePath).st_size == 0:
                print('Requesting download %s from %s...\n' % (name, url))
                urllib.urlretrieve(url, filePath)
            self.delayDisplay('Finished with download\n')

            self.delayDisplay("Unzipping to  %s" % (slicer.app.temporaryPath))
            zipFilePath = os.path.join(slicer.app.temporaryPath, 'CardiacAgatstonMeasures_TutorialContestSummer2014.zip')
            extractPath = os.path.join(slicer.app.temporaryPath, 'CardiacAgatstonMeasures_TutorialContestSummer2014')
            qt.QDir().mkpath(extractPath)
            self.delayDisplay("Using extract path  %s" % (extractPath))
            applicationLogic = slicer.app.applicationLogic()
            applicationLogic.Unzip(zipFilePath, extractPath)

            self.delayDisplay("Loading CardiacAgatstonMeasuresTestInput.nii.gz")
            inputImagePath = os.path.join(extractPath, 'CardiacAgatstonMeasuresTestInput.nii.gz')
            slicer.util.loadVolume(inputImagePath)
            volumeNode = slicer.util.getNode(pattern="CardiacAgatstonMeasuresTestInput")
            logic = CACSLabelerModuleLogic()
            self.assertTrue( logic.hasImageData(volumeNode) )
            self.delayDisplay('Finished with downloading and loading CardiacAgatstonMeasuresTestInput.nii.gz')

            CardiacAgatstonMeasuresLUTNode = slicer.util.getNode(pattern='CardiacAgatstonMeasuresLUT')
            if not CardiacAgatstonMeasuresLUTNode:
                self.delayDisplay("Loading CardiacAgatstonMeasuresLUT.ctbl")
                lutPath = os.path.join(extractPath, 'CardiacAgatstonMeasuresLUT.ctbl')
                slicer.util.loadColorTable(lutPath)
                CardiacAgatstonMeasuresLUTNode = slicer.util.getNode(pattern="CardiacAgatstonMeasuresLUT")
            logic = CACSLabelerModuleLogic()
            self.assertTrue( logic.hasCorrectLUTData(CardiacAgatstonMeasuresLUTNode) )
            self.delayDisplay('Finished with downloading and loading CardiacAgatstonMeasuresLUT.ctbl')

            self.delayDisplay('Test Part 1 passed!\n')
        except Exception, e:
            import traceback
            traceback.print_exc()
            self.delayDisplay('Test caused exception!\n' + str(e))

    def test_CardiacAgatstonMeasures2(self):
        """ Level two test. Tests if the thresholded label
        image is created and if CardiacAgatstonMeasuresLUT file was
        imported correctly.
        """
        self.delayDisplay("Starting Test Part 2 - Thresholding")

        try:
            widget = slicer.modules.CardiacAgatstonMeasuresWidget
            self.delayDisplay("Opened CardiacAgatstonMeasuresWidget")

            widget.KEV120.setChecked(1)
            self.delayDisplay("Checked the KEV120 button")

            widget.onThresholdButtonClicked()
            self.delayDisplay("Threshold button selected")

            logic = CACSLabelerModuleLogic()

            labelNode = slicer.util.getNode(pattern="CardiacAgatstonMeasuresTestInput_120KEV_130HU_Calcium_Label")
            self.assertTrue( logic.hasImageData(labelNode) )
            self.delayDisplay("Thresholded label created and pushed to Slicer")

            self.delayDisplay('Test Part 2 passed!\n')
        except Exception, e:
            import traceback
            traceback.print_exc()
            self.delayDisplay('Test caused exception!\n' + str(e))

    def test_CardiacAgatstonMeasures3(self):
        """ Level three test. Tests if the Editor tools
        and five label buttons work properly.
        """
        self.delayDisplay("Starting Test Part 3 - Paint and Statistics")

        try:
            widget = slicer.modules.CardiacAgatstonMeasuresWidget
            self.delayDisplay("Opened CardiacAgatstonMeasuresWidget")

            # toolsBox = widget.localCardiacEditorWidget.toolsBox
            # toolsBox.onLCXchangeIslandButtonClicked()

            #
            # got to the editor and do some drawing
            #
            self.delayDisplay("Paint some things")
            editUtil = EditorLib.EditUtil.EditUtil()
            lm = slicer.app.layoutManager()
            paintEffect = EditorLib.PaintEffectOptions()
            paintEffect.setMRMLDefaults()
            paintEffect.__del__()
            sliceWidget = lm.sliceWidget('Red')
            paintTool = EditorLib.PaintEffectTool(sliceWidget)
            editUtil.setLabel(5)
            (x, y) = self.rasToXY((38,165,-122), sliceWidget)
            paintTool.paintAddPoint(x, y)
            paintTool.paintApply()
            editUtil.setLabel(3)
            (x, y) = self.rasToXY((12.5,171,-122), sliceWidget)
            paintTool.paintAddPoint(x, y)
            paintTool.paintApply()
            paintTool.cleanup()
            paintTool = None
            self.delayDisplay("Painted calcium for LAD and RCA labels")

            self.delayDisplay("Apply pressed - calculating Agatston scores/statistics")
            widget.localLabelStatisticsWidget.onApply()

            scores = widget.localLabelStatisticsWidget.logic.AgatstonScoresPerLabel
            testScores = {0: 0, 1: 0, 2: 0, 3: 2.8703041076660174,
                          4: 0, 5: 45.22903442382816, 6: 48.099338531494176}
            self.assertTrue( scores == testScores )
            self.delayDisplay("Agatston scores/statistics are correct")

            self.delayDisplay("Test Part 3 passed!\n")

        except Exception, e:
            import traceback
            traceback.print_exc()
            self.delayDisplay('Test caused exception!\n' + str(e))

    def rasToXY(self, rasPoint, sliceWidget):
        sliceLogic = sliceWidget.sliceLogic()
        sliceNode = sliceLogic.GetSliceNode()
        rasToXY = vtk.vtkMatrix4x4()
        rasToXY.DeepCopy(sliceNode.GetXYToRAS())
        rasToXY.Invert()
        xyzw = rasToXY.MultiplyPoint(rasPoint+(1,))
        x = int(round(xyzw[0]))
        y = int(round(xyzw[1]))
        return x, y

class CardiacStatisticsWidget(LabelStatistics.LabelStatisticsWidget):
    def __init__(self, KEV120, KEV80, localCardiacEditorWidget, parent=None):
        self.chartOptions = ("Agatston Score", "Count", "Volume mm^3", "Volume cc", "Min", "Max", "Mean", "StdDev")
        if not parent:
            self.parent = slicer.qMRMLWidget()
            self.parent.setLayout(qt.QVBoxLayout())
            self.parent.setMRMLScene(slicer.mrmlScene)
        else:
            self.parent = parent
        self.logic = None
        self.grayscaleNode = None
        self.labelNode = None
        self.fileName = None
        self.fileDialog = None
        self.KEV120 = KEV120
        self.KEV80 = KEV80
        self.localCardiacEditorWidget = localCardiacEditorWidget
        if not parent:
            self.setup()
            self.grayscaleSelector.setMRMLScene(slicer.mrmlScene)
            self.labelSelector.setMRMLScene(slicer.mrmlScene)
            self.parent.show()

    def setup(self):

        # Set the grayscaleNode and labelNode to the current active volume and label
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        self.grayscaleNode = slicer.util.getNode(selectionNode.GetActiveVolumeID())
        #self.labelNode = slicer.util.getNode(selectionNode.GetActiveLabelVolumeID())

        #ID = selectionNode.GetActiveLabelVolumeID()
        volumeNodes = slicer.util.getNodesByClass('vtkMRMLScalarVolumeNode')
        volume = volumeNodes[1]
        volume_id = volume.GetID()

        #print('ID', volume_id)
        self.labelNode = slicer.util.getNode(volume_id)

#        # Apply button
#        self.applyButton = qt.QPushButton("Apply")
#        self.applyButton.toolTip = "Calculate Statistics."
#        self.applyButton.setStyleSheet("background-color: rgb(230,241,255)")
#        self.applyButton.enabled = True
#        self.parent.layout().addWidget(self.applyButton)

        # model and view for stats table
        self.view = qt.QTableView()
        self.view.sortingEnabled = True
        self.parent.layout().addWidget(self.view)

        # Chart button
        self.chartFrame = qt.QFrame()
        self.chartFrame.setLayout(qt.QHBoxLayout())
        self.parent.layout().addWidget(self.chartFrame)
        self.chartButton = qt.QPushButton("Chart")
        self.chartButton.toolTip = "Make a chart from the current statistics."
        self.chartFrame.layout().addWidget(self.chartButton)
        self.chartOption = qt.QComboBox()
        self.chartOption.addItems(self.chartOptions)
        self.chartFrame.layout().addWidget(self.chartOption)
        self.chartIgnoreZero = qt.QCheckBox()
        self.chartIgnoreZero.setText('Ignore Zero')
        self.chartIgnoreZero.checked = False
        self.chartIgnoreZero.setToolTip('Do not include the zero index in the chart to avoid dwarfing other bars')
        self.chartFrame.layout().addWidget(self.chartIgnoreZero)
        self.chartFrame.enabled = False



        # Add vertical spacer
        self.parent.layout().addStretch(1)

        # connections
        #self.applyButton.connect('clicked()', self.onApply)
        self.chartButton.connect('clicked()', self.onChart)


    def onApply(self):
        """Calculate the label statistics
        """
        # selects default tool to stop the ChangeIslandTool
        self.localCardiacEditorWidget.toolsBox.selectEffect("DefaultTool")

        self.applyButton.text = "Working..."
        # TODO: why doesn't processEvents alone make the label text change?
        self.applyButton.repaint()
        slicer.app.processEvents()
        volumesLogic = slicer.modules.volumes.logic()
        warnings = volumesLogic.CheckForLabelVolumeValidity(self.grayscaleNode, self.labelNode)
        resampledLabelNode = None
        if warnings != "":
            if 'mismatch' in warnings:
                resampledLabelNode = volumesLogic.ResampleVolumeToReferenceVolume(self.labelNode, self.grayscaleNode)
                self.logic = CardiacLabelStatisticsLogic(self.grayscaleNode, resampledLabelNode, self.KEV120, self.KEV80)
            else:
                qt.QMessageBox.warning(slicer.util.mainWindow(),
                    "Label Statistics", "Volumes do not have the same geometry.\n%s" % warnings)
                return
        else:
            self.logic = CardiacLabelStatisticsLogic(self.grayscaleNode, self.labelNode, self.KEV120, self.KEV80)
        self.populateStats()
        if resampledLabelNode:
            slicer.mrmlScene.RemoveNode(resampledLabelNode)
        self.chartFrame.enabled = True
        self.saveButton.enabled = True
        self.applyButton.text = "Apply"



    def onDirSelected(self, dirName):
        # saves the current scene to selected folder
        l = slicer.app.applicationLogic()
        l.SaveSceneToSlicerDataBundleDirectory(dirName, None)

        # saves the csv files to selected folder
        csvFileName = os.path.join(dirName, "{0}_Agatston_Scores.csv".format(os.path.split(dirName)[1]))
        self.logic.saveStats(csvFileName)

    def populateStats(self):
        if not self.logic:
            return
        displayNode = self.labelNode.GetDisplayNode()
        colorNode = displayNode.GetColorNode()
        lut = colorNode.GetLookupTable()
        self.items = []
        self.model = qt.QStandardItemModel()
        self.view.setModel(self.model)
        self.view.verticalHeader().visible = False
        row = 0
        for i in self.logic.labelStats["Labels"]:
            color = qt.QColor()
            rgb = lut.GetTableValue(i)
            color.setRgb(rgb[0]*255,rgb[1]*255,rgb[2]*255)
            item = qt.QStandardItem()
            item.setData(color,qt.Qt.DecorationRole)
            item.setToolTip(colorNode.GetColorName(i))
            self.model.setItem(row,0,item)
            self.items.append(item)
            col = 1
            for k in self.logic.keys:
                item = qt.QStandardItem()
                if k == "Label Name":
                    item.setData(self.logic.labelStats[i,k],qt.Qt.DisplayRole)
                else:
                    # set data as float with Qt::DisplayRole
                    item.setData(float(self.logic.labelStats[i,k]),qt.Qt.DisplayRole)
                item.setToolTip(colorNode.GetColorName(i))
                self.model.setItem(row,col,item)
                self.items.append(item)
                col += 1
            row += 1

        self.view.setColumnWidth(0,30)
        self.model.setHeaderData(0,1," ")
        col = 1
        for k in self.logic.keys:
            self.view.setColumnWidth(col,15*len(k))
            self.model.setHeaderData(col,1,k)
            col += 1

class CardiacLabelStatisticsLogic(LabelStatistics.LabelStatisticsLogic):
    """Implement the logic to calculate label statistics.
      Nodes are passed in as arguments.
      Results are stored as 'statistics' instance variable.
      """

    def __init__(self, grayscaleNode, labelNode, KEV120, KEV80, fileName=None):
        #import numpy

        self.keys = ("Index", "Label Name", "Agatston Score", "Count", "Volume mm^3", "Volume cc", "Min", "Max", "Mean", "StdDev")
        cubicMMPerVoxel = reduce(lambda x,y: x*y, labelNode.GetSpacing())
        ccPerCubicMM = 0.001

        # TODO: progress and status updates
        # this->InvokeEvent(vtkLabelStatisticsLogic::StartLabelStats, (void*)"start label stats")

        self.labelStats = {}
        self.labelStats['Labels'] = []

        stataccum = vtk.vtkImageAccumulate()
        if vtk.VTK_MAJOR_VERSION <= 5:
            stataccum.SetInput(labelNode.GetImageData())
        else:
            stataccum.SetInputConnection(labelNode.GetImageDataConnection())
        stataccum.Update()
        lo = int(stataccum.GetMin()[0])
        hi = int(stataccum.GetMax()[0])

        displayNode = labelNode.GetDisplayNode()
        colorNode = displayNode.GetColorNode()

        self.colorNode = colorNode

        self.labelNode = labelNode
        self.grayscaleNode = grayscaleNode
        self.KEV80 = KEV80
        self.KEV120 = KEV120
        self.calculateAgatstonScores()

        for i in xrange(lo,7):
            # skip indices 0 (background) and 1 (default threshold pixels)
            # because these are not calcium and do not have an Agatston score
            if i == 0 or i == 1:
                continue

            # this->SetProgress((float)i/hi);
            # std::string event_message = "Label "; std::stringstream s; s << i; event_message.append(s.str());
            # this->InvokeEvent(vtkLabelStatisticsLogic::LabelStatsOuterLoop, (void*)event_message.c_str());

            # logic copied from slicer3 LabelStatistics
            # to create the binary volume of the label
            # //logic copied from slicer2 LabelStatistics MaskStat
            # // create the binary volume of the label
            thresholder = vtk.vtkImageThreshold()
            if vtk.VTK_MAJOR_VERSION <= 5:
                thresholder.SetInput(labelNode.GetImageData())
            else:
                thresholder.SetInputConnection(labelNode.GetImageDataConnection())
            thresholder.SetInValue(1)
            thresholder.SetOutValue(0)
            thresholder.ReplaceOutOn()
            if i != 6:
                thresholder.ThresholdBetween(i,i)
            else: # label 6 is the total calcium pixels in labels 2, 3, 4 and 5
                thresholder.ThresholdBetween(2,5)
            thresholder.SetOutputScalarType(grayscaleNode.GetImageData().GetScalarType())
            thresholder.Update()

            # this.InvokeEvent(vtkLabelStatisticsLogic::LabelStatsInnerLoop, (void*)"0.25");

            #  use vtk's statistics class with the binary labelmap as a stencil
            stencil = vtk.vtkImageToImageStencil()
            if vtk.VTK_MAJOR_VERSION <= 5:
                stencil.SetInput(thresholder.GetOutput())
            else:
                stencil.SetInputConnection(thresholder.GetOutputPort())
            stencil.ThresholdBetween(1, 1)

            # this.InvokeEvent(vtkLabelStatisticsLogic::LabelStatsInnerLoop, (void*)"0.5")

            stat1 = vtk.vtkImageAccumulate()
            if vtk.VTK_MAJOR_VERSION <= 5:
                stat1.SetInput(grayscaleNode.GetImageData())
                stat1.SetStencil(stencil.GetOutput())
            else:
                stat1.SetInputConnection(grayscaleNode.GetImageDataConnection())
                stencil.Update()
                stat1.SetStencilData(stencil.GetOutput())
            stat1.Update()

            # this.InvokeEvent(vtkLabelStatisticsLogic::LabelStatsInnerLoop, (void*)"0.75")

            if stat1.GetVoxelCount() > 0:
                # add an entry to the LabelStats list
                self.labelStats["Labels"].append(i)
                self.labelStats[i,"Index"] = i
                self.labelStats[i,"Label Name"] = colorNode.GetColorName(i)
                self.labelStats[i,"Agatston Score"] = self.AgatstonScoresPerLabel[i]
                self.labelStats[i,"Count"] = stat1.GetVoxelCount()
                self.labelStats[i,"Volume mm^3"] = self.labelStats[i,"Count"] * cubicMMPerVoxel
                self.labelStats[i,"Volume cc"] = self.labelStats[i,"Volume mm^3"] * ccPerCubicMM
                self.labelStats[i,"Min"] = stat1.GetMin()[0]
                self.labelStats[i,"Max"] = stat1.GetMax()[0]
                self.labelStats[i,"Mean"] = stat1.GetMean()[0]
                self.labelStats[i,"StdDev"] = stat1.GetStandardDeviation()[0]

            # this.InvokeEvent(vtkLabelStatisticsLogic::LabelStatsInnerLoop, (void*)"1")

        # this.InvokeEvent(vtkLabelStatisticsLogic::EndLabelStats, (void*)"end label stats")

    def calculateAgatstonScores(self):

        #Just temporary code, will calculate statistics and show in table
        print "Calculating Statistics"
        calcium = su.PullVolumeFromSlicer(self.labelNode.GetName())
        all_labels = [0, 1, 2, 3, 4, 5, 6]
        heart = su.PullVolumeFromSlicer(self.grayscaleNode.GetName())
        sliceAgatstonPerLabel = self.computeSlicewiseAgatstonScores(calcium, heart, all_labels)
        #print sliceAgatstonPerLabel
        self.computeOverallAgatstonScore(sliceAgatstonPerLabel)

    def computeOverallAgatstonScore(self, sliceAgatstonPerLabel):
        self.AgatstonScoresPerLabel = {}
        # labels 0 and 1 should not have an Agatston score
        self.AgatstonScoresPerLabel[0] = 0
        self.AgatstonScoresPerLabel[1] = 0
        for (label, scores) in sliceAgatstonPerLabel.items():
            labelScore =  sum(scores)
            self.AgatstonScoresPerLabel[label] = labelScore
        # label 6 is the total of all of labels 2 - 5
        self.AgatstonScoresPerLabel[6] = sum(self.AgatstonScoresPerLabel.values())

    def KEV2AgatstonIndex(self, kev):
        AgatstonIndex = 0.0
        if self.KEV120.checked:
            if kev >= 130:   #range = 130-199
                AgatstonIndex = 1.0
            if kev >= 200:   #range = 200-299
                AgatstonIndex = 2.0
            if kev >= 300:   #range = 300-399
                AgatstonIndex = 3.0
            if kev >= 400:   #range >= 400
                AgatstonIndex = 4.0
        elif self.KEV80.checked:
            if kev >= 167:   #range = 167-265
                AgatstonIndex = 1.0
            if kev >= 266:   #range = 266-407
                AgatstonIndex = 2.0
            if kev >= 408:   #range = 408-550
                AgatstonIndex = 3.0
            if kev >= 551:   #range >= 551
                AgatstonIndex = 4.0
        return AgatstonIndex

    def computeSlicewiseAgatstonScores(self, calcium, heart, all_labels):
        sliceAgatstonPerLabel=dict() ## A dictionary { labels : [AgatstonValues] }
        ##Initialize Dictionary entries with empty list
        for label in all_labels:
            if label == 0 or label == 1:
                continue
            sliceAgatstonPerLabel[label]=list()

        for label in all_labels:
            if label == 0 or label == 1:
                continue
            binaryThresholdFilterImage = sitk.BinaryThreshold(calcium, label, label)
            ConnectedComponentImage = sitk.ConnectedComponent(binaryThresholdFilterImage)
            RelabeledComponentImage = sitk.RelabelComponent(ConnectedComponentImage)
            ImageSpacing = RelabeledComponentImage.GetSpacing()
            ImageIndex = range(0, RelabeledComponentImage.GetSize()[2])
            for index in ImageIndex:
                slice_calcium = RelabeledComponentImage[:,:,index]
                slice_img = heart[:,:,index]
                slice_ls = sitk.LabelStatisticsImageFilter()
                slice_ls.Execute(slice_img,slice_calcium)
                if sitk.Version().MajorVersion() > 0 or sitk.Version().MinorVersion() >= 9:
                    compontent_labels = slice_ls.GetLabels()
                else: #if sitk version < 0.9 then use older function call GetValidLabels
                    compontent_labels = slice_ls.GetValidLabels()
                for sublabel in compontent_labels:
                    if sublabel == 0:
                        continue
                    AgatstonValue = 0.0
                    if slice_ls.HasLabel(sublabel):
                        slice_count = slice_ls.GetCount(sublabel)
                        slice_area = slice_count*ImageSpacing[0]*ImageSpacing[1]
                        slice_max = slice_ls.GetMaximum(sublabel)
                        slice_Agatston = slice_area * self.KEV2AgatstonIndex( slice_max )
                        AgatstonValue = slice_Agatston

                    sliceAgatstonPerLabel[label].append(AgatstonValue)
        return sliceAgatstonPerLabel

class CardiacEditorWidget(Editor.EditorWidget):

    def createEditBox(self):
        self.editLabelMapsFrame.collapsed = False
        self.editBoxFrame = qt.QFrame(self.effectsToolsFrame)
        self.editBoxFrame.objectName = 'EditBoxFrame'
        self.editBoxFrame.setLayout(qt.QVBoxLayout())
        self.effectsToolsFrame.layout().addWidget(self.editBoxFrame)
        self.toolsBox = CardiacEditBox(self.editBoxFrame, optionsFrame=self.effectOptionsFrame)

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
            ('1', self.toolsBox.onDefaultChangeIslandButtonClicked),
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

class CardiacEditBox(EditorLib.EditBox):

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

        # The Default Label Selector
        defaultChangeIslandButton = qt.QPushButton("Default")
        defaultChangeIslandButton.toolTip = "Label - Default"
        defaultChangeIslandButton.setStyleSheet("background-color: rgb(81,208,35)")
        self.mainFrame.layout().addWidget(defaultChangeIslandButton)
        defaultChangeIslandButton.connect('clicked(bool)', self.onDefaultChangeIslandButtonClicked)

        # The Input Left Main (LM) Label Selector
#        LMchangeIslandButton = qt.QPushButton("LM")
#        LMchangeIslandButton.toolTip = "Label - Left Main (LM)"
#        LMchangeIslandButton.setStyleSheet("background-color: rgb(220,0,250)")
#        self.mainFrame.layout().addWidget(LMchangeIslandButton)
#        LMchangeIslandButton.connect('clicked(bool)', self.onLMchangeIslandButtonClicked)

        # The Input Left Arterial Descending (LAD) Label Selector
        LADchangeIslandButton = qt.QPushButton("LAD")
        LADchangeIslandButton.toolTip = "Label - Left Arterial Descending (LAD)"
        LADchangeIslandButton.setStyleSheet("background-color: rgb(246,243,48)")
        self.mainFrame.layout().addWidget(LADchangeIslandButton)
        LADchangeIslandButton.connect('clicked(bool)', self.onLADchangeIslandButtonClicked)

        # The Input Left Circumflex (LCX) Label Selector
        LCXchangeIslandButton = qt.QPushButton("LCX")
        LCXchangeIslandButton.toolTip = "Label - Left Circumflex (LCX)"
        LCXchangeIslandButton.setStyleSheet("background-color: rgb(94,170,200)")
        self.mainFrame.layout().addWidget(LCXchangeIslandButton)
        LCXchangeIslandButton.connect('clicked(bool)', self.onLCXchangeIslandButtonClicked)

        # The Input Right Coronary Artery (RCA) Label Selector
        RCAchangeIslandButton = qt.QPushButton("RCA")
        RCAchangeIslandButton.toolTip = "Label - Right Coronary Artery (RCA)"
        RCAchangeIslandButton.setStyleSheet("background-color: rgb(222,60,30)")
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
        self.defaultChangeIslandButton = defaultChangeIslandButton

        vbox.addStretch(1)

        self.updateUndoRedoButtons()
        #self._onParameterNodeModified(self.editUtil.getParameterNode())
        self._onParameterNodeModified(EditUtil.getParameterNode())

#    def onLMchangeIslandButtonClicked(self):
#        self.changeIslandButtonClicked(2)

    def onLADchangeIslandButtonClicked(self):
        self.changeIslandButtonClicked(2)

    def onLCXchangeIslandButtonClicked(self):
        self.changeIslandButtonClicked(3)

    def onRCAchangeIslandButtonClicked(self):
        self.changeIslandButtonClicked(4)

    def onDefaultChangeIslandButtonClicked(self):
        self.changeIslandButtonClicked(1)

    def changeIslandButtonClicked(self, label):
        #self.selectEffect("ChangeIslandEffect")
        self.selectEffect("PaintEffect")
        #self.editUtil.setLabel(label)
        EditUtil.setLabel(label)
