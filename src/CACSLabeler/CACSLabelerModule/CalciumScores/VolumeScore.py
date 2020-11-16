# -*- coding: utf-8 -*-
# Reference: V. Sandfort and D. A. Bluemke, “CT calcium scoring . History , current status and outlook,” Diagn. Interv. Imaging, vol. 98, no. 1, pp. 3–10, 2017.

import numpy as np
from collections import defaultdict
from SimpleITK import ConnectedComponentImageFilter
import SimpleITK as sitk

# VolumeScore
class VolumeScore():
    
    name = 'VolumeScore'
    
    def __init__(self):
        self.VolumeScore = None
        self.arteries = ['LAD', 'LCX', 'RCA']
       
    def compute(self, inputVolume, inputVolumeLabel):
        """ Compute agatston score from image and image label

        :param image: Image
        :type image: np.ndarray
        :param imageLabel: Image label
        :type imageLabel: np.ndarray
        :param pixelVolume: Volume of apixel
        :type pixelVolume: float
        """
        
        imageLabel = sitk.GetArrayFromImage(inputVolumeLabel)
        spacing = inputVolume.GetSpacing()
        pixelVolume = spacing[0]*spacing[1]*spacing[2]

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
        VolumeScore = defaultdict(lambda: None, {'NAME': 'VolumeScore', 'LAD': 0, 'LCX': 0, 'RCA': 0, 'VolumeScore': 0})
        for k, key in enumerate(self.arteries):
            # Extract binary mask of lesions from one artery
            imageLabelA = imageLabel==(k+2)
            image_sitk = sitk.GetImageFromArray(imageLabelA.astype(np.uint8))
            # Extract connected components
            compFilter = ConnectedComponentImageFilter()
            labeled_sitk = compFilter.Execute(image_sitk)
            labeled = sitk.GetArrayFromImage(labeled_sitk)
            ncomponents = labeled.max()
            VolumeScoreArtery = 0
            # Iterate over lesions from an artery
            for c in range(1,ncomponents+1):
                labeledc = labeled==c
                volume = labeledc.sum() * pixelVolume
                # Calculate agatston score for a lesion
                VolumeScoreArtery = VolumeScoreArtery + volume
            VolumeScore[key] = VolumeScoreArtery

        # Sum agatston score over arteries
        vScore=0.0
        for key in self.arteries:
            vScore = vScore + VolumeScore[key]
        VolumeScore['VolumeScore'] = vScore

        self.VolumeScore = VolumeScore
        return VolumeScore
    
    def show(self):
        if self.VolumeScore is not None:
            # Print calcium scoring
            print('---------------------------')
            print('----- VolumeScore score per Artery-----')
            for key in self.arteries:
                print(key, self.VolumeScore[key])
            print('----- VolumeScore score-----')
            print(self.VolumeScore['VolumeScore'])
            print('---------------------------')
        else:
            print('VolumeScore not defined')