import qt
import os
import vtk

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

from slicer import vtkMRMLScalarVolumeNode


#
# CardiacCT
#

class CardiacCT(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "CardiacCT"  # TODO: make this more human readable by adding spaces
        self.parent.categories = ["Cardiac Computed Tomography"]  # TODO: set categories (folders where the module shows up in the module selector)
        self.parent.dependencies = []  # TODO: add here list of module names that this module requires
        self.parent.contributors = ["(Charité - Universitätsmedizin Berlin)"]  # TODO: replace with "Firstname Lastname (Organization)"
        # TODO: update with short description of the module and a link to online module documentation
        self.parent.helpText = """
        This is an example of scripted loadable module bundled in an extension.
        See more information in <a href="https://github.com/organization/projectname#CardiacCT">module documentation</a>.
        """
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = """
        This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
        and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
        """

class CardiacCTWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None) -> None:
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation

        # clears screen on reload
        slicer.mrmlScene.Clear(0)

    def setup(self) -> None:
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/CardiacCT.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        self.connectEvents()

        #Loaded Files
        self.loadedFiles = {}

    def connectEvents(self):
        self.ui.loadImagesButton.connect('clicked(bool)', self.loadImages)
        self.ui.saveSegmentationsButton.connect('clicked(bool)', self.saveSegmentations)

    def getMHDFileInDirectory(self, path):
        return [file for file in os.listdir(path) if file.endswith(".mhd")]

    def getFiles(self):
        filepath = qt.QFileDialog.getExistingDirectory()

        pathCACSImage = os.path.join(filepath, "CACS", "Image")
        pathCTAImage = os.path.join(filepath, "CTA", "Image")
        pathCACSSegmentations = os.path.join(filepath, "CACS", "Segmentations")
        pathCTASegmentations = os.path.join(filepath, "CTA", "Segmentations")

        if os.path.isdir(pathCACSImage) and os.path.isdir(pathCTAImage) and os.path.isdir(pathCACSSegmentations) and os.path.isdir(pathCTASegmentations):
            ctaImages = self.getMHDFileInDirectory(pathCTAImage)
            cacsImages = self.getMHDFileInDirectory(pathCACSImage)

            if len(ctaImages) == 1 and len(cacsImages) == 1:
                self.loadedFiles["CACS"] = os.path.join(pathCACSImage,cacsImages[0])
                self.loadedFiles["CTA"] = os.path.join(pathCTAImage,ctaImages[0])

                self.loadedFiles["Paths"] = {}
                self.loadedFiles["Paths"]["CTA"] = {}
                self.loadedFiles["Paths"]["CACS"] = {}

                self.loadedFiles["Paths"]["CTA"]["Image"] = pathCTAImage
                self.loadedFiles["Paths"]["CACS"]["Image"] = pathCACSImage
                self.loadedFiles["Paths"]["CTA"]["Segmentations"] = pathCTASegmentations
                self.loadedFiles["Paths"]["CACS"]["Segmentations"] = pathCACSSegmentations

        else:
            print("Folder structure not as expected!")

    def changeSlicerViews(self):
        # set view
        layoutManager = slicer.app.layoutManager()
        layoutManager.setLayout(29)

        nodes = slicer.util.getNodes("vtkMRMLSliceNode*")

        for node in nodes.values():
            node.SetOrientationToAxial()

    def loadImages(self):
        self.getFiles()

        if self.loadedFiles:
            #CTA Image
            self.imageNodeCTA = slicer.util.loadVolume(self.loadedFiles["CTA"])
            self.imageNodeCTA.SetName("CTA")
            self.imageNodeCTA.GetScalarVolumeDisplayNode().AutoWindowLevelOff()
            self.imageNodeCTA.GetScalarVolumeDisplayNode().SetWindowLevel(1500, 450)

            #create segmentation
            self.createSegmentationForImage(self.imageNodeCTA, "CTA_Anatomical", "Red")
            self.createSegmentationForImage(self.imageNodeCTA, "CTA_Lesions", "Red")

            # CACS Image
            self.imageNodeCACS = slicer.util.loadVolume(self.loadedFiles["CACS"])
            self.imageNodeCACS.SetName("CACS")
            self.imageNodeCACS.GetScalarVolumeDisplayNode().AutoWindowLevelOff()
            self.imageNodeCACS.GetScalarVolumeDisplayNode().SetWindowLevel(800, 180)

            self.createSegmentationForImage(self.imageNodeCACS, "CACS_Anatomical", "Yellow")
            self.createSegmentationForImage(self.imageNodeCACS, "CACS_Lesions", "Yellow")

            #Change views
            self.changeSlicerViews()

            redViewer = slicer.app.layoutManager().sliceWidget("Red")
            yellowViewer = slicer.app.layoutManager().sliceWidget("Yellow")

            # Set the volumes for Red and Yellow views
            redViewer.sliceLogic().GetSliceCompositeNode().SetBackgroundVolumeID(self.imageNodeCTA.GetID())
            yellowViewer.sliceLogic().GetSliceCompositeNode().SetBackgroundVolumeID(self.imageNodeCACS.GetID())

            # Update the views
            redViewer.sliceController().fitSliceToBackground()
            yellowViewer.sliceController().fitSliceToBackground()

            self.initializeEditorWidgets()
        else:
            print("Error while loading files!")

    def createSegmentationForImage(self, imageNode, name, displayInView):
        segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
        segmentationNode.SetName(name)
        segmentationNode.CreateDefaultDisplayNodes()  # only needed for display
        segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(imageNode)

        viewId = "vtkMRMLSliceNode" + displayInView
        segmentationNode.GetDisplayNode().SetDisplayableOnlyInView(viewId)

    def createEditorWidget(self, uiElement, editorNodeName, assignedSegmentation):
        uiElement.setMRMLScene(slicer.mrmlScene)
        uiElement.unorderedEffectsVisible = False
        uiElement.setEffectNameOrder(['Paint', 'Erase'])
        uiElement.setEffectColumnCount(1)
        uiElement.setMRMLSegmentEditorNode(self.getSegmentEditorNode(editorNodeName))
        uiElement.setSegmentationNode(slicer.util.getNode(assignedSegmentation))

        for element in uiElement.children():
            elementToHide = ["SpecifyGeometryButton", "Show3DButton", "SwitchToSegmentationsButton"]

            #hides elements from segmentation Editor Widget
            if element.objectName in elementToHide:
                element.hide()

            # add on Click event to effect button
            if element.objectName == "EffectsGroupBox":
                effects = ["Paint", "Erase"]

                for effect in element.children():
                    if effect.objectName in effects:
                        effect.connect('clicked(bool)', lambda: self.onClick(editorNodeName))

        # uiElement.setSegmentationNodeSelectorVisible(False)
        # uiElement.setSourceVolumeNodeSelectorVisible(False)
        # uiElement.setSwitchToSegmentationsButtonVisible(False)

    def onClick(self, editorName):
        # used to prevent multiple editor effects from being active!
        if editorName == "CTA_EditorAnatomical":

            self.ui.CACSEditorWidgetAnatomical.setActiveEffectByName(None)
            self.ui.CTAEditorWidgetLesions.setActiveEffectByName(None)
            self.ui.CACSEditorWidgetLesions.setActiveEffectByName(None)
        elif editorName == "CACS_EditorAnatomical":
            self.ui.CTAEditorWidgetAnatomical.setActiveEffectByName(None)

            self.ui.CTAEditorWidgetLesions.setActiveEffectByName(None)
            self.ui.CACSEditorWidgetLesions.setActiveEffectByName(None)
        elif editorName == "CTA_EditorLesions":
            self.ui.CTAEditorWidgetAnatomical.setActiveEffectByName(None)
            self.ui.CACSEditorWidgetAnatomical.setActiveEffectByName(None)

            self.ui.CACSEditorWidgetLesions.setActiveEffectByName(None)
        elif editorName == "CACS_EditorLesions":
            self.ui.CTAEditorWidgetAnatomical.setActiveEffectByName(None)
            self.ui.CACSEditorWidgetAnatomical.setActiveEffectByName(None)
            self.ui.CTAEditorWidgetLesions.setActiveEffectByName(None)


    def getSegmentEditorNode(self, editorNodeName):
        segmentEditorNode = slicer.mrmlScene.GetSingletonNode(editorNodeName, "vtkMRMLSegmentEditorNode")
        if segmentEditorNode is None:
            segmentEditorNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLSegmentEditorNode")
            segmentEditorNode.UnRegister(None)
            segmentEditorNode.SetSingletonTag(editorNodeName)
            segmentEditorNode = slicer.mrmlScene.AddNode(segmentEditorNode)
        return segmentEditorNode

    def initializeEditorWidgets(self):
        self.createEditorWidget(self.ui.CTAEditorWidgetAnatomical, "CTA_EditorAnatomical", "CTA_Anatomical")
        self.createEditorWidget(self.ui.CACSEditorWidgetAnatomical, "CACS_EditorAnatomical", "CACS_Anatomical")
        self.createEditorWidget(self.ui.CTAEditorWidgetLesions, "CTA_EditorLesions", "CTA_Lesions")
        self.createEditorWidget(self.ui.CACSEditorWidgetLesions, "CACS_EditorLesions", "CACS_Lesions")

    def exportSegmentationToFile(self, nodeName, path):
        segmentationNode = slicer.util.getNode(nodeName)
        labelmapVolumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
        labelmapVolumeNode.SetName("temporaryExportLabel")
        referenceVolumeNode = None  # it could be set to the master volume
        segmentIds = segmentationNode.GetSegmentation().GetSegmentIDs()  # export all segments

        colorTableNode = None # TODO custom colorTableNode!

        slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(segmentationNode,
                                                                          segmentIds,
                                                                          labelmapVolumeNode, referenceVolumeNode,
                                                                          slicer.vtkSegmentation.EXTENT_REFERENCE_GEOMETRY,
                                                                          colorTableNode)

        volumeNode = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLLabelMapVolumeNode')
        slicer.util.exportNode(volumeNode, os.path.join(path, nodeName + ".nrrd"))
        slicer.mrmlScene.RemoveNode(labelmapVolumeNode)

    def saveSegmentations(self):
        if self.loadedFiles:
            # TODO: Export function not finished!
            # TODO: Error if no segmentation labels were added!
            self.exportSegmentationToFile("CTA_Anatomical", self.loadedFiles["Paths"]["CTA"]["Segmentations"])
            self.exportSegmentationToFile("CTA_Lesions", self.loadedFiles["Paths"]["CTA"]["Segmentations"])

            self.exportSegmentationToFile("CACS_Lesions", self.loadedFiles["Paths"]["CACS"]["Segmentations"])
            self.exportSegmentationToFile("CACS_Anatomical", self.loadedFiles["Paths"]["CACS"]["Segmentations"])

        else:
            print("No files loaded!")

