# -*- coding: utf-8 -*-


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
                