# -*- coding: utf-8 -*-
import os
import json
from collections import OrderedDict
from CACSTree.CACSTree import CACSTree

# Settings
class Settings:
    def __init__(self):
        self.settingsDict=None
        
    def __getitem__(self, key):
        return self.settingsDict[key]

    def __setitem__(self, key, value):
        self.settingsDict[key] = value

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
                self.checkSettings(settings)
                settings = OrderedDict(settings)
                # CreateCACSTree
                settings['CACSTree'] = CACSTree()
                settings['CACSTree'].createTree(settings['CACSTreeDict'])
                self.settingsDict = settings
        else:
            print('Settings file:' + filepath_settings + 'does not exist')
            
        # Check if folders exist
        if not os.path.isdir(self.settingsDict['folderpath_images']):
            raise ValueError("Folderpath of image " + self.settingsDict['folderpath_images'] + ' does not exist')
        if not os.path.isdir(self.settingsDict['folderpath_references']):
            raise ValueError("Folderpath of references " + self.settingsDict['folderpath_references'] + ' does not exist')

    def writeSettings(self, filepath_settings):
        """ Write settings into setting file

        :param filepath_settings: Filepath to settings file
        :type filepath_settings: str
        """
        
        CACSTreeDict = CACSTree.initCACSTreeDict()
        
        columns_CACSTREE_CUMULATIVE = ['PatientID', 'SeriesInstanceUID', 'CC', 
                             'RCA', 'RCA_PROXIMAL', 'RCA_MID', 'RCA_DISTAL',
                             'LM', 'LM_BIF_LAD_LCX', 'LM_BIF_LAD', 'LM_BIF_LCX', 'LM_BRANCH',
                             'LAD', 'LAD_PROXIMAL', 'LAD_MID', 'LAD_DISTAL', 'LAD_SIDE_BRANCH',
                             'LCX', 'LCX_PROXIMAL', 'LCX_MID', 'LCX_DISTAL', 'LCX_SIDE_BRANCH',
                             'RIM']

        columns_CACS = ['PatientID', 'SeriesInstanceUID', 'CC', 'RCA', 'LAD', 'LCX']

        # Initialize settings
#        settingsDefault = {'folderpath_images': 'H:/cloud/cloud_data/Projects/DL/Code/src/datasets/DISCHARGE/data_cacs/Images',
#                           'folderpath_references': 'H:/cloud/cloud_data/Projects/DL/Code/src/datasets/DISCHARGE/data_cacs/References',
#                           'filepath_export': 'H:/cloud/cloud_data/Projects/CACSLabeler/code/data/export.json',
#                           'folderpath_export_csv': 'H:/cloud/cloud_data/Projects/CACSLabeler/code/data/export_csv',
#                           'filter_input': '(*.mhd)',
#                           'CalciumScores': ['AGATSTON_SCORE', 'VOLUME_SCORE', 'DENSITY_SCORE', 'NUMLESION_SCORE', 'LESIONVOLUME_SCORE'],
#                           'filter_input_by_reference': False,
#                           'filter_reference_with': ['-label.'],
#                           'filter_reference_without': ['label-lesion.'],
#                           'CACSTreeDict': CACSTreeDict,
#                           'columns_CACSTREE_CUMULATIVE': columns_CACSTREE_CUMULATIVE,
#                           'columns_CACS': columns_CACS,
#                           'MODE': 'CACSTREE_CUMULATIVE'} # MODE can be 'CACS','CACSTREE' or 'CACSTREE_CUMULATIVE'

        settingsDefault = {'folderpath_images': '/mnt/SSD2/cloud_data/Projects/DL/Code/src/datasets/DISCHARGE/data_cacs/Images',
                           'folderpath_references': '/mnt/SSD2/cloud_data/Projects/DL/Code/src/datasets/DISCHARGE/data_cacs/References',
                           'folderpath_export': '/mnt/SSD2/cloud_data/Projects/CACSLabeler/code/data/export',
                           'filter_input': '(*.mhd)',
                           'CalciumScores': ['AGATSTON_SCORE', 'VOLUME_SCORE', 'DENSITY_SCORE', 'NUMLESION_SCORE', 'LESIONVOLUME_SCORE'],
                           'filter_input_by_reference': False,
                           'filter_reference_with': ['-label.'],
                           'filter_reference_without': ['label-lesion.'],
                           'CACSTreeDict': CACSTreeDict,
                           'columns_CACSTREE_CUMULATIVE': columns_CACSTREE_CUMULATIVE,
                           'columns_CACS': columns_CACS,
                           'MODE': 'CACS'} # MODE can be 'CACS','CACSTREE' or 'CACSTREE_CUMULATIVE'
                           
        print('Writing setting to ' + filepath_settings)
        with open(filepath_settings, 'a') as file:
            file.write(json.dumps(settingsDefault, indent=4, encoding='utf-8'))
        self.settingsDict = settingsDefault
        
    def checkSettings(self, settings):
        for key in settings.keys():
            value = settings[key]
            if isinstance(value, str):
                if "\\" in value:
                    raise ValueError("Backslash not allowed in settings file")
