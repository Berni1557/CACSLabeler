# -*- coding: utf-8 -*-
# Reference: V. Sandfort and D. A. Bluemke, “CT calcium scoring . History , current status and outlook,” Diagn. Interv. Imaging, vol. 98, no. 1, pp. 3–10, 2017.

import sys, os
import numpy as np
from collections import defaultdict, OrderedDict
from SimpleITK import ConnectedComponentImageFilter
import SimpleITK as sitk
import time
import csv

# Agatston score
class LesionVolume():
    
    name = 'LESIONVOLUME_SCORE'
    
    def __init__(self):
        #CalciumScoreBase.__init__(self) 
        self.lesvolume = None
        #self.arteries = ['LAD', 'LCX', 'RCA']

    def compute(self, inputVolume, inputVolumeLabel, arteries_dict={}, arteries_sum={}):
        """ Compute agatston score from image and image label

        :param image: Image
        :type image: np.ndarray
        :param imageLabel: Image label
        :type imageLabel: np.ndarray
        :param pixelVolume: Volume of apixel
        :type pixelVolume: float
        """
        
        if arteries_dict is not None:
            self.arteries_dict = arteries_dict

        image = sitk.GetArrayFromImage(inputVolume)
        imageLabel = sitk.GetArrayFromImage(inputVolumeLabel)
        spacing = inputVolume.GetSpacing()
        pixelVolume = spacing[0]*spacing[1]*spacing[2]
        arteries_sum_keys = list(arteries_sum.keys())

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
        lesvolume = OrderedDict([('NAME', self.name)])
        for key in self.arteries_dict.keys():
            if key not in arteries_sum_keys:
                # Extract binary mask of lesions from one artery
                imageLabelA = imageLabel==self.arteries_dict[key]
                if imageLabelA.sum()>0:
                    image_sitk = sitk.GetImageFromArray(imageLabelA.astype(np.uint8))
                    # Extract connected components
                    compFilter = ConnectedComponentImageFilter()
                    labeled_sitk = compFilter.Execute(image_sitk)
                    labeled = sitk.GetArrayFromImage(labeled_sitk)
                    ncomponents = labeled.max()

                    # Iterate over lesions from an artery
                    volumeList=[]
                    for c in range(1,ncomponents+1):
                        labeledc = labeled==c
                        image_mask = image * labeledc
                        NumPixels = image_mask.sum()
                        volume = NumPixels * pixelVolume
                        volumeList.append({'LesionID': c, 'LesionVolume': volume})
                    lesvolume[key] = volumeList
                else:
                    lesvolume[key] = []

        # Sum agatston score over arteries_sum
#        for key in arteries_sum_keys:
#            value = 0
#            for key_sum in arteries_sum[key]:
#                value += agatston[key_sum]
#            agatston[key] = value
        
        # Sum agatston score over arteries
        #agatstonScore=0.0
        #for key in self.arteries:
        #    agatstonScore = agatstonScore + agatston[key]
        
#        if 'CC' in list(lesvolume.keys()):
#            agatstonScore = agatston['CC']
#        else:
#            agatstonScore=0.0
#            for key in self.arteries:
#                agatstonScore = agatstonScore + agatston[key]
        
        #agatston['AgatstonScore'] = agatstonScore
        #agatston['Grading'] = self.CACSGrading(agatstonScore)
        self.lesvolume = lesvolume
        return lesvolume
    
    def show(self):
        if self.arteries_dict is not None:
            # Print calcium scoring
            print('---------------------------')
            print('----- Lesion volumes -----')
#            for key in self.arteries_dict.keys():
#                for les in self.lesvolume[key]:
#                    print('LesionID: ' + str(les['LesionID']) + ' LesionVolume: ' + str(les['LesionVolume']))
#            print('---------------------------')
        else:
            print('Lesion volume not defined')


    def export_csv(self, settings, calciumScoresResult):
        # Write calcium scores into csv
        if settings['MODE'] == 'CACS':
            columns = settings['columns_CACS']
        elif settings['MODE'] == 'CACSTREE_CUMULATIVE':
            columns = settings['columns_CACSTREE_CUMULATIVE']
        else:
            raise ValueError('Mode ' + settings['MODE'] + ' does not exist.')
            
        folderpath_export_csv = settings['folderpath_export']
        filepath_csv = os.path.join(folderpath_export_csv, self.name + '.csv')
        if not os.path.isdir(folderpath_export_csv):
            os.mkdir(folderpath_export_csv)
        with open(filepath_csv, 'w') as file:
            writer = csv.writer(file, delimiter=';', lineterminator="\n")
            writer.writerow(columns)
            for s,sample in enumerate(calciumScoresResult):
                scores = sample['Scores']
                for score in scores:
                    if score['NAME'] == self.name:
                        # Create row
                        name_list = sample['ImageName'].split('_')
                        if len(name_list)==2:
                            PatientID = sample['ImageName'].split('_')[0]
                            SeriesInstanceUID = sample['ImageName'].split('_')[1]
                        else:
                            PatientID = ''
                            SeriesInstanceUID = ''
                        row = [PatientID, SeriesInstanceUID]
#                        for c in columns[2:]:
#                            lesions = score[c]
#                            for les in lesions:
#                                row = row + [les['LesionID'].replace('.', ',')]
                        writer.writerow(row)

                        
                        
                        