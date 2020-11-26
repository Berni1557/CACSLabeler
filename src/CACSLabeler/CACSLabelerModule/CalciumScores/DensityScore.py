# -*- coding: utf-8 -*-
# Reference: V. Sandfort and D. A. Bluemke, “CT calcium scoring . History , current status and outlook,” Diagn. Interv. Imaging, vol. 98, no. 1, pp. 3–10, 2017.

import numpy as np
from collections import defaultdict, OrderedDict
from SimpleITK import ConnectedComponentImageFilter
import SimpleITK as sitk
from Agatston import Agatston
from VolumeScore import VolumeScore


# DensityScore
class DensityScore():
    
    name = 'DensityScore'
    
    def __init__(self):
        #CalciumScoreBase.__init__(self) 
        self.DensityScore = None
        self.arteries = ['LAD', 'LCX', 'RCA']

        
    def compute(self, inputVolume, inputVolumeLabel,  arteries_dict=None):
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
        
        #DensityScore = defaultdict(lambda: None, {'NAME': 'DensityScore', 'LAD': 0, 'LCX': 0, 'RCA': 0, 'DensityScore': 0})
        DensityScore = OrderedDict([('NAME', 'DensityScore'), ('DensityScore', 0)])
         
        # Iterate over arteries
        #for k, key in enumerate(self.arteries):
        for key in self.arteries_dict.keys():
            if score_volumeScore[key]>0:
                DensityScore[key] = score_agatston[key] / (score_volumeScore[key] * (1 / sliceThickness))
            else:
                DensityScore[key] = 0.0
                    
        # Sum DensityScore score over arteries
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