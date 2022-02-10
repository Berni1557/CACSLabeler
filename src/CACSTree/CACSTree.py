# -*- coding: utf-8 -*-
import os, sys
from collections import defaultdict, OrderedDict
import numpy as np

class Lesion():
    def __init__(self, name, parent, color, value):
        self.name = name
        self.parent = parent
        self.color = color
        self.value = value

class CACSTree():
    def __init__(self):
        self.lesionList=[]
        
    def createTree(self, settings):            
        CACSTreeDict = settings['CACSTreeDict'][settings['MODE']][0]
        self.root = Lesion(name='CACSTreeDict', parent=None, color=CACSTreeDict['COLOR'], value=CACSTreeDict['VALUE'])
        self.lesionList.append(self.root)
        self.addChildren(CACSTreeDict, 'CACSTreeDict')
        
    def addChildren(self, parent, parent_name):
        for key in parent.keys():
            key = key.encode("utf-8")
            #print('key', key)
            if not key =='COLOR' and not key =='VALUE':
                lesion = Lesion(name=key, parent=parent_name, color = parent[key]['COLOR'], value = parent[key]['VALUE'])
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

    def getValueByName(self, name):
        for idx, lesion in enumerate(self.lesionList):
            if lesion.name == name:
                return lesion.value
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
            #f.write(str(idx) + ' ' + lesion.name + ' ' + color_str + '\n')
            value_str = lesion.value
            f.write(str(value_str) + ' ' + lesion.name + ' ' + color_str + '\n')
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

            
    def createColorTable_CACS_REF(self, filepath_colorTable, REFValue, UCValue):
        CACS_dict = OrderedDict([('CACSTreeDict', 0), ('OTHER', 1), ('LAD', 2), ('LCX', 3), ('RCA', 4)])
        f = open(filepath_colorTable, 'w')
        f.write('# Color\n')
        f.close()
        for key in CACS_dict.keys():
            lesion = self.getLesionByName(key)
            #color_str = str(lesion.color[0]) + ' ' + str(lesion.color[1]) + ' ' + str(lesion.color[2]) + ' ' + str(lesion.color[3])
            f = open(filepath_colorTable, 'a')
            color_str = str(lesion.color[0]) + ' ' + str(lesion.color[1]) + ' ' + str(lesion.color[2]) + ' ' + str(lesion.color[3])
            f.write(str(CACS_dict[key]) + ' ' + lesion.name + ' ' + color_str + '\n')
            f.close()
            
        # Add REF color
        f = open(filepath_colorTable, 'a')
        color_str = str(10) + ' ' + str(10) + ' ' + str(250) + ' ' + str(255)
        f.write(str(REFValue) + ' ' + 'REF' + ' ' + color_str + '\n')
        color_str = str(50) + ' ' + str(50) + ' ' + str(100) + ' ' + str(255)
        f.write(str(UCValue) + ' ' + 'UC' + ' ' + color_str + '\n')
        f.close()
 
#    def createColorTable_CACS_REF_LESION(self, filepath_colorTable, REFValue):
#        CACS_dict = OrderedDict([('CACSTreeDict', 0), ('OTHER', 1), ('LAD', 2), ('LCX', 3), ('RCA', 4)])
#        f = open(filepath_colorTable, 'w')
#        f.write('# Color\n')
#        f.close()
#        for key in CACS_dict.keys():
#            lesion = self.getLesionByName(key)
#            #color_str = str(lesion.color[0]) + ' ' + str(lesion.color[1]) + ' ' + str(lesion.color[2]) + ' ' + str(lesion.color[3])
#            f = open(filepath_colorTable, 'a')
#            color_str = str(lesion.color[0]) + ' ' + str(lesion.color[1]) + ' ' + str(lesion.color[2]) + ' ' + str(lesion.color[3])
#            f.write(str(CACS_dict[key]) + ' ' + lesion.name + ' ' + color_str + '\n')
#            f.close()
#            
#        # Add REF color
#        f = open(filepath_colorTable, 'a')
#        color_str = str(10) + ' ' + str(10) + ' ' + str(250) + ' ' + str(255)
#        f.write(str(REFValue) + ' ' + 'REF' + ' ' + color_str + '\n')
#        f.close()     
        
    @staticmethod
    def initCACSTreeDict():
        print('initCACSTreeDict')
        
        treeList = dict()
            
        # Create tree tree_V01
        columns_CACSTREE = ['PatientID', 'SeriesInstanceUID', 'CC', 
                 'RCA', 'RCA_PROXIMAL', 'RCA_MID', 'RCA_DISTAL', 'RCA_SIDE_BRANCH',
                 'LM', 'LM_BIF_LAD_LCX', 'LM_BIF_LAD', 'LM_BIF_LCX', 'LM_BRANCH',
                 'LAD', 'LAD_PROXIMAL', 'LAD_MID', 'LAD_DISTAL', 'LAD_SIDE_BRANCH',
                 'LCX', 'LCX_PROXIMAL', 'LCX_MID', 'LCX_DISTAL', 'LCX_SIDE_BRANCH',
                 'RIM']
                 
        OTHER = OrderedDict([('COLOR', (0, 255, 0, 255)), ('VALUE', 1)])
        
        RCA_PROXIMAL = OrderedDict([('COLOR', (204, 0, 0, 255)), ('VALUE', 4)])
        RCA_MID = OrderedDict([('COLOR', (255,0,0, 255)), ('VALUE', 5)])
        RCA_DISTAL = OrderedDict([('COLOR', (255,80,80, 255)), ('VALUE', 6)])
        RCA_SIDE_BRANCH = OrderedDict([('COLOR', (255,124,128, 255)), ('VALUE', 7)])
        RCA = OrderedDict([('RCA_PROXIMAL', RCA_PROXIMAL), ('RCA_MID', RCA_MID), 
                           ('RCA_DISTAL', RCA_DISTAL), ('RCA_SIDE_BRANCH', RCA_SIDE_BRANCH), ('COLOR', (165,0,33, 255)), ('VALUE', 3)])
        
        LM_BIF_LAD_LCX = OrderedDict([('COLOR', (11,253,224, 255)), ('VALUE', 9)])
        LM_BIF_LAD = OrderedDict([('COLOR', (26,203,238, 255)), ('VALUE', 10)])
        LM_BIF_LCX = OrderedDict([('COLOR', (32,132,130, 255)), ('VALUE', 11)])
        LM_BRANCH = OrderedDict([('COLOR', (255,204,102, 255)), ('VALUE', 12)])
        LM = OrderedDict([('LM_BIF_LAD_LCX', LM_BIF_LAD_LCX), ('LM_BIF_LAD', LM_BIF_LAD), 
                           ('LM_BIF_LCX', LM_BIF_LCX), ('LM_BRANCH', LM_BRANCH), ('COLOR', (12,176,198, 255)), ('VALUE', 8)])
        
        LAD_PROXIMAL = OrderedDict([('COLOR', (255,153,155, 255)), ('VALUE', 14)])
        LAD_MID = OrderedDict([('COLOR', (255,255,0, 255)), ('VALUE', 15)])
        LAD_DISTAL = OrderedDict([('COLOR', (204,255,51, 255)), ('VALUE', 16)])
        LAD_SIDE_BRANCH = OrderedDict([('COLOR', (11,253,244, 255)), ('VALUE', 17)])
        LAD = OrderedDict([('LAD_PROXIMAL', LAD_PROXIMAL), ('LAD_MID', LAD_MID), ('LAD_DISTAL', LAD_DISTAL), ('LAD_SIDE_BRANCH', LAD_SIDE_BRANCH), ('COLOR', (255,204,0, 255)), ('VALUE', 13)])
        
        RIM = OrderedDict([('COLOR', (255,51,153, 255)), ('VALUE', 23)])
        
        LCX_PROXIMAL = OrderedDict([('COLOR', (255,0,255, 255)), ('VALUE', 19)])
        LCX_MID = OrderedDict([('COLOR', (255,102,255, 255)), ('VALUE', 20)])
        LCX_DISTAL = OrderedDict([('COLOR', (255,153,255, 255)), ('VALUE', 21)])
        LCX_SIDE_BRANCH = OrderedDict([('COLOR', (255,204,255, 255)), ('VALUE', 22)])
        LCX = OrderedDict([('LCX_PROXIMAL', LCX_PROXIMAL), ('LCX_MID', LCX_MID), ('LCX_DISTAL', LCX_DISTAL), ('LCX_SIDE_BRANCH', LCX_SIDE_BRANCH), ('COLOR', (204,0,204, 255)), ('VALUE', 18)])

        CC = OrderedDict([('RCA', RCA), ('LM', LM), ('LAD', LAD), ('LCX', LCX), ('RIM', RIM), ('COLOR', (165, 0, 33, 255)), ('VALUE', 22)])
        
        AORTA_ASC = OrderedDict([('COLOR', (72,63,255, 255)), ('VALUE', 26)])
        AORTA_DSC = OrderedDict([('COLOR', (12,0,246, 255)), ('VALUE', 27)])
        AORTA_ARC = OrderedDict([('COLOR', (139,133,255, 255)), ('VALUE', 28)])
        AORTA = OrderedDict([('AORTA_ASC', AORTA_ASC), ('AORTA_DSC', AORTA_DSC), ('AORTA_ARC', AORTA_ARC), ('COLOR', (9,0,188, 255)), ('VALUE', 25)])


        VALVE_AORTIC = OrderedDict([('COLOR', (0,102,0, 255)), ('VALUE', 30)])
        VALVE_PULMONIC = OrderedDict([('COLOR', (51,153,102, 255)), ('VALUE', 31)])
        VALVE_TRICUSPID = OrderedDict([('COLOR', (0,153,0, 255)), ('VALUE', 32)])
        VALVE_MITRAL = OrderedDict([('COLOR', (0,204,0, 255)), ('VALUE', 33)])
        
        VALVES = OrderedDict([('VALVE_AORTIC', VALVE_AORTIC), ('VALVE_PULMONIC', VALVE_PULMONIC),
                              ('VALVE_TRICUSPID', VALVE_TRICUSPID), ('VALVE_MITRAL', VALVE_MITRAL), ('COLOR', (4,68,16, 255)), ('VALUE', 29)])
        
        STERNUM = OrderedDict([('COLOR', (167,149,75, 255)), ('VALUE', -1)])
        VERTEBRA = OrderedDict([('COLOR', (198,185,128, 255)), ('VALUE', -1)])
        COSTA = OrderedDict([('COLOR', (216,207,168, 255)), ('VALUE', -1)])
        BONE = OrderedDict([('STERNUM', STERNUM), ('VERTEBRA', VERTEBRA), ('COSTA', COSTA), ('COLOR', (102,51,0, 255)), ('VALUE', -1)])
        
        TRACHEA = OrderedDict([('COLOR', (204,236,255, 255)), ('VALUE', -1)])
        BRONCHUS = OrderedDict([('COLOR', (255,255,204, 255))])
        NODULE_CALCIFIED  = OrderedDict([('COLOR', (204,255,204, 255)), ('VALUE', -1)])
        LUNG_ARTERY = OrderedDict([('COLOR', (255,204,204, 255)), ('VALUE', -1)])
        LUNG_VESSEL_NFS = OrderedDict([('COLOR', (153,204,255, 255)), ('VALUE', -1)])
        LUNG_PARENCHYMA = OrderedDict([('COLOR', (153,255,204, 255)), ('VALUE', -1)])

        LUNG = OrderedDict([('TRACHEA', TRACHEA), ('BRONCHUS', BRONCHUS),
                            ('NODULE_CALCIFIED', NODULE_CALCIFIED), ('LUNG_ARTERY', LUNG_ARTERY),
                            ('LUNG_VESSEL_NFS', LUNG_VESSEL_NFS),  ('LUNG_PARENCHYMA', LUNG_PARENCHYMA), ('COLOR', (204,255,255, 255)), ('VALUE', -1)])
        
        
        NCC = OrderedDict([('AORTA', AORTA), ('VALVES', VALVES), ('BONE', BONE), ('LUNG', LUNG), ('COLOR', (102, 0, 102, 255)), ('VALUE', -1)])    

        CACSTreeDict = OrderedDict([('OTHER', OTHER), ('CC', CC), ('NCC', NCC), ('COLOR', (0,0,0,0)), ('VALUE', -1)])
        #treeList['tree_V01'] = (CACSTreeDict, columns_CACSTREE)
        

                             
        # Create tree tree_V02
        columns_CACSTREE = ['PatientID', 'SeriesInstanceUID','CC', 
                 'RCA', 'RCA_PROXIMAL', 'RCA_MID', 'RCA_DISTAL', 'RCA_SIDE_BRANCH',
                 'LM', 'LM_BIF_LAD_LCX', 'LM_BIF_LAD', 'LM_BIF_LCX', 'LM_BRANCH',
                 'LAD', 'LAD_PROXIMAL', 'LAD_MID', 'LAD_DISTAL', 'LAD_SIDE_BRANCH',
                 'LCX', 'LCX_PROXIMAL', 'LCX_MID', 'LCX_DISTAL', 'LCX_SIDE_BRANCH',
                 'RIM',
                 'NCC',
                 'AORTA', 'AORTA_ASC', 'AORTA_DSC', 'AORTA_ARC',
                 'VALVES', 'VALVE_AORTIC', 'VALVE_PULMONIC', 'VALVE_TRICUSPID', 'VALVE_MITRAL',
                 'PAPILLAR_MUSCLE', 'NFS_CACS'
                 ]
                 
        OTHER = OrderedDict([('COLOR', (0, 255, 0, 255)), ('VALUE', 1)])
        
        RCA_PROXIMAL = OrderedDict([('COLOR', (204, 0, 0, 255)), ('VALUE', 4)])
        RCA_MID = OrderedDict([('COLOR', (255,0,0, 255)), ('VALUE', 5)])
        RCA_DISTAL = OrderedDict([('COLOR', (255,80,80, 255)), ('VALUE', 6)])
        RCA_SIDE_BRANCH = OrderedDict([('COLOR', (255,124,128, 255)), ('VALUE', 7)])
        RCA = OrderedDict([('RCA_PROXIMAL', RCA_PROXIMAL), ('RCA_MID', RCA_MID), 
                           ('RCA_DISTAL', RCA_DISTAL), ('RCA_SIDE_BRANCH', RCA_SIDE_BRANCH), ('COLOR', (165,0,33, 255)), ('VALUE', 3)])
        
        LM_BIF_LAD_LCX = OrderedDict([('COLOR', (11,253,224, 255)), ('VALUE', 9)])
        LM_BIF_LAD = OrderedDict([('COLOR', (26,203,238, 255)), ('VALUE', 10)])
        LM_BIF_LCX = OrderedDict([('COLOR', (32,132,130, 255)), ('VALUE', 11)])
        LM_BRANCH = OrderedDict([('COLOR', (255,204,102, 255)), ('VALUE', 12)])
        LM = OrderedDict([('LM_BIF_LAD_LCX', LM_BIF_LAD_LCX), ('LM_BIF_LAD', LM_BIF_LAD), 
                           ('LM_BIF_LCX', LM_BIF_LCX), ('LM_BRANCH', LM_BRANCH), ('COLOR', (12,176,198, 255)), ('VALUE', 8)])
        
        LAD_PROXIMAL = OrderedDict([('COLOR', (255,153,155, 255)), ('VALUE', 14)])
        LAD_MID = OrderedDict([('COLOR', (255,255,0, 255)), ('VALUE', 15)])
        LAD_DISTAL = OrderedDict([('COLOR', (204,255,51, 255)), ('VALUE', 16)])
        LAD_SIDE_BRANCH = OrderedDict([('COLOR', (11,253,244, 255)), ('VALUE', 17)])
        LAD = OrderedDict([('LAD_PROXIMAL', LAD_PROXIMAL), ('LAD_MID', LAD_MID), ('LAD_DISTAL', LAD_DISTAL), ('LAD_SIDE_BRANCH', LAD_SIDE_BRANCH), ('COLOR', (255,204,0, 255)), ('VALUE', 13)])
        
        RIM = OrderedDict([('COLOR', (255,51,153, 255)), ('VALUE', 23)])
        
        LCX_PROXIMAL = OrderedDict([('COLOR', (255,0,255, 255)), ('VALUE', 19)])
        LCX_MID = OrderedDict([('COLOR', (255,102,255, 255)), ('VALUE', 20)])
        LCX_DISTAL = OrderedDict([('COLOR', (255,153,255, 255)), ('VALUE', 21)])
        LCX_SIDE_BRANCH = OrderedDict([('COLOR', (255,204,255, 255)), ('VALUE', 22)])
        LCX = OrderedDict([('LCX_PROXIMAL', LCX_PROXIMAL), ('LCX_MID', LCX_MID), ('LCX_DISTAL', LCX_DISTAL), ('LCX_SIDE_BRANCH', LCX_SIDE_BRANCH), ('COLOR', (204,0,204, 255)), ('VALUE', 18)])

        CC = OrderedDict([('RCA', RCA), ('LM', LM), ('LAD', LAD), ('LCX', LCX), ('RIM', RIM), ('COLOR', (165, 0, 33, 255)), ('VALUE', 2)])
        
        AORTA_ASC = OrderedDict([('COLOR', (72,63,255, 255)), ('VALUE', 26)])
        AORTA_DSC = OrderedDict([('COLOR', (12,0,246, 255)), ('VALUE', 27)])
        AORTA_ARC = OrderedDict([('COLOR', (139,133,255, 255)), ('VALUE', 28)])
        AORTA = OrderedDict([('AORTA_ASC', AORTA_ASC), ('AORTA_DSC', AORTA_DSC), ('AORTA_ARC', AORTA_ARC), ('COLOR', (9,0,188, 255)), ('VALUE', 25)])


        VALVE_AORTIC = OrderedDict([('COLOR', (0,102,0, 255)), ('VALUE', 30)])
        VALVE_PULMONIC = OrderedDict([('COLOR', (51,153,102, 255)), ('VALUE', 31)])
        VALVE_TRICUSPID = OrderedDict([('COLOR', (0,153,0, 255)), ('VALUE', 32)])
        VALVE_MITRAL = OrderedDict([('COLOR', (0,204,0, 255)), ('VALUE', 33)])
        
        VALVES = OrderedDict([('VALVE_AORTIC', VALVE_AORTIC), ('VALVE_PULMONIC', VALVE_PULMONIC),
                              ('VALVE_TRICUSPID', VALVE_TRICUSPID), ('VALVE_MITRAL', VALVE_MITRAL), ('COLOR', (4,68,16, 255)), ('VALUE', 29)])
        
        PAPILLAR_MUSCLE = OrderedDict([('COLOR', (167,149,75, 255)), ('VALUE', 34)])
        NFS_CACS  = OrderedDict([('COLOR', (216,207,168, 255)), ('VALUE', 35)])
  
        NCC = OrderedDict([('AORTA', AORTA), ('VALVES', VALVES), ('PAPILLAR_MUSCLE', PAPILLAR_MUSCLE), ('NFS_CACS', NFS_CACS), ('COLOR', (102, 0, 102, 255)), ('VALUE', 24)])
        CACSTreeDict = OrderedDict([('OTHER', OTHER), ('CC', CC), ('NCC', NCC), ('COLOR', (0,0,0,0)), ('VALUE', 0)])
        treeList['CACSTREE_CUMULATIVE'] = (CACSTreeDict, columns_CACSTREE)


        # Create CACS tree for CACS
        columns_CACSTREE = ['PatientID', 'SeriesInstanceUID','CC', 'RCA', 'LAD', 'LCX']        
        OTHER = OrderedDict([('COLOR', (0, 255, 0, 255)), ('VALUE', 1)])
        RCA = OrderedDict([('COLOR', (165,0,33, 255)), ('VALUE', 4)])
        LAD = OrderedDict([('COLOR', (255,204,0, 255)), ('VALUE', 2)])
        LCX = OrderedDict([('COLOR', (204,0,204, 255)), ('VALUE', 3)])
        CC = OrderedDict([('RCA', RCA), ('LAD', LAD), ('LCX', LCX), ('COLOR', (165, 0, 33, 255)), ('VALUE', -1)])
        CACSTreeDict = OrderedDict([('OTHER', OTHER), ('CC', CC), ('COLOR', (0,0,0,0)), ('VALUE', 0)])
        treeList['CACS'] = (CACSTreeDict, columns_CACSTREE)   
        
        
        # Create CACS tree for CACS_ORCASCORE
        columns_CACSTREE = ['PatientID', 'SeriesInstanceUID','CC', 'RCA', 'LAD', 'LCX']        
        OTHER = OrderedDict([('COLOR', (0, 255, 0, 255)), ('VALUE', 0)])
        RCA = OrderedDict([('COLOR', (165,0,33, 255)), ('VALUE', 3)])
        LAD = OrderedDict([('COLOR', (255,204,0, 255)), ('VALUE', 1)])
        LCX = OrderedDict([('COLOR', (204,0,204, 255)), ('VALUE', 2)])
        CC = OrderedDict([('RCA', RCA), ('LAD', LAD), ('LCX', LCX), ('COLOR', (165, 0, 33, 255)), ('VALUE', -1)])
        CACSTreeDict = OrderedDict([('OTHER', OTHER), ('CC', CC), ('COLOR', (0,0,0,0)), ('VALUE', 0)])
        treeList['CACS_ORCASCORE'] = (CACSTreeDict, columns_CACSTREE)

        # Create CACS tree for CACS_REF
        columns_CACSTREE = ['PatientID', 'SeriesInstanceUID','CC', 'RCA', 'LAD', 'LCX', 'UC']        
        OTHER = OrderedDict([('COLOR', (0, 255, 0, 255)), ('VALUE', 1)])
        RCA = OrderedDict([('COLOR', (165,0,33, 255)), ('VALUE', 4)])
        LAD = OrderedDict([('COLOR', (255,204,0, 255)), ('VALUE', 2)])
        LCX = OrderedDict([('COLOR', (204,0,204, 255)), ('VALUE', 3)])
        REF = OrderedDict([('COLOR', (10,10,250, 255)), ('VALUE', 200)])
        UC = OrderedDict([('COLOR', (50,50,100, 255)), ('VALUE', 201)])
        CC = OrderedDict([('RCA', RCA), ('LAD', LAD), ('LCX', LCX), ('UC', UC), ('COLOR', (165, 0, 33, 255)), ('VALUE', -1)])
        CACSTreeDict = OrderedDict([('OTHER', OTHER), ('CC', CC), ('COLOR', (0,0,0,0)), ('VALUE', 0)])
        treeList['CACS_REF'] = (CACSTreeDict, columns_CACSTREE)

        # Create CACS tree for CACS_4
        columns_CACSTREE = ['PatientID', 'SeriesInstanceUID', 'LM', 'RCA', 'LAD', 'LCX']        
        OTHER = OrderedDict([('COLOR', (0, 255, 0, 255)), ('VALUE', 1)])
        LM = OrderedDict([('COLOR', (50,165,33, 255)), ('VALUE', 5)])
        RCA = OrderedDict([('COLOR', (165,0,33, 255)), ('VALUE', 4)])
        LAD = OrderedDict([('COLOR', (255,204,0, 255)), ('VALUE', 2)])
        LCX = OrderedDict([('COLOR', (204,0,204, 255)), ('VALUE', 3)])
        #CC = OrderedDict([('RCA', RCA), ('LAD', LAD), ('LCX', LCX), ('LM', LM), ('COLOR', (165, 0, 33, 255)), ('VALUE', -1)])
        #CACSTreeDict = OrderedDict([('CC', CC), ('OTHER', OTHER), ('LM', LM), ('RCA', RCA), ('LAD', LAD), ('LCX', LCX), ('COLOR', (0,0,0,0)), ('VALUE', 0)])
        CACSTreeDict = OrderedDict([('OTHER', OTHER), ('LM', LM), ('RCA', RCA), ('LAD', LAD), ('LCX', LCX), ('COLOR', (0,0,0,0)), ('VALUE', 0)])
        treeList['CACS_4'] = (CACSTreeDict, columns_CACSTREE)

        
        # Create CACS tree for LESION
        columns_CACSTREE = ['PatientID', 'SeriesInstanceUID']  
        #OTHER = OrderedDict([('COLOR', (0, 255, 0, 255)), ('VALUE', 1)])
        
        OTHER = OrderedDict([('COLOR', (0, 255, 0, 255)), ('VALUE', 1)])
        CACSTreeDict = OrderedDict([('1', OTHER), ('COLOR', (0,0,0,0)), ('VALUE', 0)])
        for i in range(2,30):
            color = list(np.random.choice(range(256), size=3))
            d = OrderedDict([('COLOR', (color[0],color[1],color[2], 255)), ('VALUE', i)])
            CACSTreeDict.update({str(i): d})
            
            
#        OTHER = OrderedDict([('COLOR', (0, 255, 0, 255)), ('VALUE', 1)])
#        LM = OrderedDict([('COLOR', (50,165,33, 255)), ('VALUE', 5)])
#        RCA = OrderedDict([('COLOR', (165,0,33, 255)), ('VALUE', 4)])
#        LAD = OrderedDict([('COLOR', (255,204,0, 255)), ('VALUE', 2)])
#        LCX = OrderedDict([('COLOR', (204,0,204, 255)), ('VALUE', 3)])
        #CC = OrderedDict([('RCA', RCA), ('LAD', LAD), ('LCX', LCX), ('LM', LM), ('COLOR', (165, 0, 33, 255)), ('VALUE', -1)])
        #CACSTreeDict = OrderedDict([('CC', CC), ('OTHER', OTHER), ('LM', LM), ('RCA', RCA), ('LAD', LAD), ('LCX', LCX), ('COLOR', (0,0,0,0)), ('VALUE', 0)])
        #CACSTreeDict = OrderedDict([('OTHER', OTHER), ('LM', LM), ('RCA', RCA), ('LAD', LAD), ('LCX', LCX), ('COLOR', (0,0,0,0)), ('VALUE', 0)])
        print('CACSTreeDictLESION', CACSTreeDict)
        treeList['LESION'] = (CACSTreeDict, columns_CACSTREE)
        
        return treeList