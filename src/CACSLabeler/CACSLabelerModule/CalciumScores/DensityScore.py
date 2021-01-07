# -*- coding: utf-8 -*-
# Reference: V. Sandfort and D. A. Bluemke, “CT calcium scoring . History , current status and outlook,” Diagn. Interv. Imaging, vol. 98, no. 1, pp. 3–10, 2017.
import sys, os
import numpy as np
from collections import defaultdict, OrderedDict
from SimpleITK import ConnectedComponentImageFilter
import SimpleITK as sitk
from Agatston import Agatston
from VolumeScore import VolumeScore
import csv

# DensityScore
class DensityScore():
    
    name = 'DENSITY_SCORE'
    
    def __init__(self):
        #CalciumScoreBase.__init__(self) 
        self.DensityScore = None
        self.arteries = ['LAD', 'LCX', 'RCA']

        
    def compute(self, inputVolume, inputVolumeLabel,  arteries_dict={}, arteries_sum={}):
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
            
        agatston = Agatston()
        volumeScore = VolumeScore()
        score_agatston = agatston.compute(inputVolume, inputVolumeLabel, arteries_dict)
        score_volumeScore = volumeScore.compute(inputVolume, inputVolumeLabel, arteries_dict)
        spacing = inputVolume.GetSpacing()
        sliceThickness = spacing[2]
        arteries_sum_keys = list(arteries_sum.keys())
        
        #DensityScore = defaultdict(lambda: None, {'NAME': 'DensityScore', 'LAD': 0, 'LCX': 0, 'RCA': 0, 'DensityScore': 0})
        DensityScore = OrderedDict([('NAME', self.name), ('DensityScore', 0)])
         
        # Iterate over arteries
        #for k, key in enumerate(self.arteries):
        for key in self.arteries_dict.keys():
            if key not in arteries_sum_keys:
                if score_volumeScore[key]>0:
                    DensityScore[key] = score_agatston[key] / (score_volumeScore[key] * (1 / sliceThickness))
                else:
                    DensityScore[key] = 0.0
                    
        # Sum DensityScore score over arteries
#        denseScore=0.0
#        for key in self.arteries:
#            denseScore = denseScore + DensityScore[key] 
#        DensityScore['DensityScore'] = denseScore

        # Sum agatston score over arteries_sum
        for key in arteries_sum_keys:
            value = 0
            for key_sum in arteries_sum[key]:
                value += DensityScore[key_sum]
            DensityScore[key] = value

        if 'CC' in list(DensityScore.keys()):
           denseScore = DensityScore['CC']
        else:
            denseScore=0.0
            for key in self.arteries:
                denseScore = denseScore + DensityScore[key] 
        DensityScore['DensityScore'] = denseScore

        self.DensityScore = DensityScore
        return DensityScore
    
    def show(self):
        if self.DensityScore is not None:
            # Print calcium scoring
            print('---------------------------')
            print('----- Density score per Artery-----')
            for key in self.arteries_dict.keys():
                print(key, self.DensityScore[key])
            print('----- DensityScore score-----')
            print(self.DensityScore['DensityScore'])
            print('---------------------------')
        else:
            print('Density score not defined')
            
            
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
                        for c in columns[2:]:
                            row = row + [str(score[c]).replace('.', ',')]
                        writer.writerow(row)