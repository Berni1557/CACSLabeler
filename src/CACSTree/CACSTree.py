# -*- coding: utf-8 -*-
import os, sys
from collections import defaultdict, OrderedDict

class Lesion():
    def __init__(self, name, parent, color):
        self.name = name
        self.parent = parent
        self.color = color

class CACSTree():
    def __init__(self):
        self.lesionList=[]
        
    def createTree(self, CACSTreeDict):
        self.root = Lesion(name='CACSTreeDict', parent=None, color=CACSTreeDict['COLOR'])
        self.lesionList.append(self.root)
        self.addChildren(CACSTreeDict, 'CACSTreeDict')
        
    def addChildren(self, parent, parent_name):
        for key in parent.keys():
            key = key.encode("utf-8")
            if not key =='COLOR':
                lesion = Lesion(name=key, parent=parent_name, color = parent[key]['COLOR'])
                self.lesionList.append(lesion)
                self.addChildren(parent[key], key)
                    
    def getChildrenByName(self, name):
        childrens = []
        parent = ''
        for lesion in self.lesionList:
            if lesion.name == name:
                parent = lesion.name
                break
        if not parent == '':
            for lesion in self.lesionList:
                if lesion.parent == parent:
                    childrens.append(lesion)
        return childrens
        
    def getChildrenNamesByName(self, name):
        childrens = []
        parent = ''
        for lesion in self.lesionList:
            if lesion.name == name:
                parent = lesion.name
                break
        if not parent == '':
            for lesion in self.lesionList:
                if lesion.parent == parent:
                    childrens.append(lesion.name)
        return childrens
        
    def getIndexByName(self, name):
        idx=0
        for idx, lesion in enumerate(self.lesionList):
            if lesion.name == name:
                return idx
                
    def getLesionNames(self):
        namelist = []
        for idx, lesion in enumerate(self.lesionList):
            namelist.append(lesion.name)
        return namelist
                
    def getColorByName(self, name):
        for idx, lesion in enumerate(self.lesionList):
            if lesion.name == name:
                return lesion.color
        return None

    def getLesionByName(self, name):
        for idx, lesion in enumerate(self.lesionList):
            if lesion.name == name:
                return lesion
        return None                
            
    def createColorTable(self, filepath_colorTable):
        f = open(filepath_colorTable, 'w')
        f.write('# Color\n')
        f.close()
        for idx, lesion in enumerate(self.lesionList):
            f = open(filepath_colorTable, 'a')
            color_str = str(lesion.color[0]) + ' ' + str(lesion.color[1]) + ' ' + str(lesion.color[2]) + ' ' + str(lesion.color[3])
            f.write(str(idx) + ' ' + lesion.name + ' ' + color_str + '\n')
            f.close()
    
    def createColorTable_CACS(self, filepath_colorTable):
        CACS_dict = OrderedDict([('CACSTreeDict', 0), ('OTHER', 1), ('LAD', 2), ('LCX', 3), ('RCA', 4)])
        f = open(filepath_colorTable, 'w')
        f.write('# Color\n')
        f.close()
        for key in CACS_dict.keys():
            lesion = self.getLesionByName(key)
            color_str = str(lesion.color[0]) + ' ' + str(lesion.color[1]) + ' ' + str(lesion.color[2]) + ' ' + str(lesion.color[3])
            f = open(filepath_colorTable, 'a')
            color_str = str(lesion.color[0]) + ' ' + str(lesion.color[1]) + ' ' + str(lesion.color[2]) + ' ' + str(lesion.color[3])
            f.write(str(CACS_dict[key]) + ' ' + lesion.name + ' ' + color_str + '\n')
            f.close()

    @staticmethod
    def initCACSTreeDict():
        
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
        
        RIM = OrderedDict([('COLOR', (255,51,153, 255))])
        
        LCX_PROXIMAL = OrderedDict([('COLOR', (255,0,255, 255))])
        LCX_MID = OrderedDict([('COLOR', (255,102,255, 255))])
        LCX_DISTAL = OrderedDict([('COLOR', (255,153,255, 255))])
        LCX_SIDE_BRANCH = OrderedDict([('COLOR', (255,204,255, 255))])
        LCX = OrderedDict([('LCX_PROXIMAL', LCX_PROXIMAL), ('LCX_MID', LCX_MID), ('LCX_DISTAL', LCX_DISTAL), ('LCX_SIDE_BRANCH', LCX_SIDE_BRANCH), ('COLOR', (204,0,204, 255))])

        CC = OrderedDict([('RCA', RCA), ('LM', LM), ('LAD', LAD), ('LCX', LCX), ('RIM', RIM), ('COLOR', (165, 0, 33, 255))])
        
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
        COSTA = OrderedDict([('COLOR', (216,207,168, 255))])
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