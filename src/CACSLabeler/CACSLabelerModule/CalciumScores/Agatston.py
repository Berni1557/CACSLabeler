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
class Agatston():
    
    name = 'AGATSTON_SCORE'
    
    def __init__(self):
        #CalciumScoreBase.__init__(self) 
        self.agatston = None
        self.arteries = ['LAD', 'LCX', 'RCA']

    def densityFactor(self, value):
        """ Compute density weigt factor for agatston score based on maximum HU value of a lesion

        :param value: Maximum HU value of a lesion
        :type value: int
        """
        if value<130:
            densfactor=0
        elif value>=130 and value<=199:
            densfactor=1
        elif value>199 and value<=299:
            densfactor=2
        elif value>299 and value<=399:
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
        pixelArea = spacing[0]*spacing[1]
        arteries_sum_keys = list(arteries_sum.keys())
        #print('arteries_sum_keys123', arteries_sum_keys)

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
        agatston = OrderedDict([('NAME', self.name), ('AgatstonScore', 0), ('Grading', None)])
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
                    agatstonArtery = 0

                    # Iterate over lesions from an artery
                    for c in range(1,ncomponents+1):
                        labeledc = labeled==c
                        image_mask = image * labeledc
                        # Iterate over slices
                        for s in range(0,labeled.shape[0]):
                            image_mask_slice = image_mask[s,:,:]
                            labeledc_slice = labeledc[s,:,:]
                            # Extract maximum HU of a lesion
                            attenuation = image_mask_slice.max()
                            area = labeledc_slice.sum() * pixelArea
                            # Calculate density weigt factor
                            densfactor = self.densityFactor(attenuation)
                            # Calculate agatston score for a lesion
                            agatstonLesionSlice = area * densfactor
                            agatstonArtery = agatstonArtery + agatstonLesionSlice
                            
                    agatston[key] = agatstonArtery
                else:
                    agatston[key] = 0.0

        # Sum agatston score over arteries_sum
        for key in arteries_sum_keys:
            value = 0
            for key_sum in arteries_sum[key]:
                #print('key_sum0', key_sum)
                value += agatston[key_sum]
            agatston[key] = value

        if 'CC' in list(agatston.keys()):
            agatstonScore = agatston['CC']
        else:
            agatstonScore=0.0
            for key in self.arteries:
                agatstonScore = agatstonScore + agatston[key]
        
        agatston['AgatstonScore'] = agatstonScore
        agatston['Grading'] = self.CACSGrading(agatstonScore)
        self.agatston = agatston
        
        return agatston
    
    def show(self):
        if self.arteries_dict is not None:
            # Print calcium scoring
            print('---------------------------')
            print('----- Agatston score per Artery-----')
            for key in self.arteries_dict.keys():
                print(key, self.agatston[key])
            print('----- Agatston score-----')
            print(self.agatston['AgatstonScore'])
            print('----- Agatston grading-----')
            print(self.agatston['Grading'])
            print('---------------------------')
        else:
            print('Agatston not defined')


    def export_csv(self, settings, calciumScoresResult):
        # Write calcium scores into csv
        if settings['MODE'] == 'CACS':
            columns = settings['columns_CACS']
        elif settings['MODE'] == 'CACSTREE_CUMULATIVE':
            columns = settings['columns_CACSTREE_CUMULATIVE']
        else:
            raise ValueError('Mode ' + settings['MODE'] + ' does not exist.')
             
        folderpath_export_csv = settings['folderpath_export']
        if not os.path.isdir(folderpath_export_csv):
            os.mkdir(folderpath_export_csv)
        filepath_csv = os.path.join(folderpath_export_csv, self.name + '.csv')
        with open(filepath_csv, 'w') as file:
            writer = csv.writer(file, delimiter=';', lineterminator="\n")
            writer.writerow(columns)
            for s,sample in enumerate(calciumScoresResult):
                scores = sample['Scores']
                for score in scores:
                    if score['NAME'] == self.name:
                        PatientID = sample['ImageName'].split('_')[0]
                        SeriesInstanceUID = sample['ImageName'].split('_')[1]
                        row = [PatientID, SeriesInstanceUID]
                        for c in columns[2:]:
                            row = row + [str(score[c]).replace('.', ',')]
                        writer.writerow(row)


                        
                        
                        
                        
                        
                        