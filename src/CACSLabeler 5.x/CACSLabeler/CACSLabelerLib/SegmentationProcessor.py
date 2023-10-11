# this class contains all logic needed to convert between different segmentations (e.g. from segmentlevel to artery level)

import numpy
from .SettingsHandler import SettingsHandler

class SegmentationProcessor():
    def __init__(self):
        self.settingsHandler = SettingsHandler()
        
        # segmentation types in order => Definition in settings json!
        self.availableSegmentationTypes = ["ArteryLevel", "ArteryLevelWithLM", "SegmentLevelDLNExport", "SegmentLevelOnlyArteries" ,"SegmentLevel", "17SegmentOnlyArteries", "17Segment"]

    def isSegmentationTypeLowerLevel(self, firstType, secondType):
        return (self.availableSegmentationTypes.index(firstType) < self.availableSegmentationTypes.index(secondType))

    def getEqualAndLowerSegmentationTypes(self, segmentationType):
        return self.availableSegmentationTypes[:self.availableSegmentationTypes.index(segmentationType) + 1]

    def getLabelValueByName(self, segmentationType, name):
        return self.settingsHandler.getContentByKeys(["labels", segmentationType, name, "value"])

    def convert(self, segmentation, oldSegmentationType, newSegmentationType):
        if oldSegmentationType == "SegmentLevelDLNExport":
            segmentation[segmentation == 1] = 0
        else:
            segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "OTHER")] = 0

        if self.isSegmentationTypeLowerLevel(newSegmentationType, oldSegmentationType):
            if oldSegmentationType == "SegmentLevel" and newSegmentationType == "SegmentLevelDLNExport":
                #Remove not needed labels
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "OTHER")] = 0
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "AORTA_ASC")] = 0
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "AORTA_DSC")] = 0
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "AORTA_ARC")] = 0
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "VALVE_AORTIC")] = 0
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "VALVE_PULMONIC")] = 0
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "VALVE_TRICUSPID")] = 0
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "VALVE_MITRAL")] = 0
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "PAPILLAR_MUSCLE")] = 0
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "NFS_CACS")] = 0

                #overwrite old label key!
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "RCA_PROXIMAL")] = self.getLabelValueByName(oldSegmentationType, "RCA_PROXIMAL") + 100
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "RCA_MID")] = self.getLabelValueByName(oldSegmentationType, "RCA_MID") + 100
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "RCA_DISTAL")] = self.getLabelValueByName(oldSegmentationType, "RCA_DISTAL") + 100
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "RCA_SIDE_BRANCH")] = self.getLabelValueByName(oldSegmentationType, "RCA_SIDE_BRANCH") + 100

                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LAD_PROXIMAL")] = self.getLabelValueByName(oldSegmentationType, "LAD_PROXIMAL") + 100
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LAD_MID")] = self.getLabelValueByName(oldSegmentationType, "LAD_MID") + 100
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LAD_DISTAL")] = self.getLabelValueByName(oldSegmentationType, "LAD_DISTAL") + 100
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LAD_SIDE_BRANCH")] = self.getLabelValueByName(oldSegmentationType, "LAD_SIDE_BRANCH") + 100

                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LCX_PROXIMAL")] = self.getLabelValueByName(oldSegmentationType, "LCX_PROXIMAL") + 100
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LCX_MID")] = self.getLabelValueByName(oldSegmentationType, "LCX_MID") + 100
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LCX_DISTAL")] = self.getLabelValueByName(oldSegmentationType, "LCX_DISTAL") + 100
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LCX_SIDE_BRANCH")] = self.getLabelValueByName(oldSegmentationType, "LCX_SIDE_BRANCH") + 100

                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "RIM")] = self.getLabelValueByName(oldSegmentationType, "RIM") + 100

                #convert ids
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LM_BIF_LAD_LCX")] = self.getLabelValueByName(newSegmentationType, "LM")
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LM_BIF_LAD")] = self.getLabelValueByName(newSegmentationType, "LM")
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LM_BIF_LCX")] = self.getLabelValueByName(newSegmentationType, "LM")
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LM_BRANCH")] = self.getLabelValueByName(newSegmentationType, "LM")

                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "RCA_PROXIMAL") + 100] = self.getLabelValueByName(newSegmentationType, "RCA_PROXIMAL")
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "RCA_MID") + 100] = self.getLabelValueByName(newSegmentationType, "RCA_MID")
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "RCA_DISTAL") + 100] = self.getLabelValueByName(newSegmentationType, "RCA_DISTAL")
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "RCA_SIDE_BRANCH") + 100] = self.getLabelValueByName(newSegmentationType, "RCA_SIDE_BRANCH")

                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LAD_PROXIMAL") + 100] = self.getLabelValueByName(newSegmentationType, "LAD_PROXIMAL")
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LAD_MID") + 100] = self.getLabelValueByName(newSegmentationType, "LAD_MID")
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LAD_DISTAL") + 100] = self.getLabelValueByName(newSegmentationType, "LAD_DISTAL")
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LAD_SIDE_BRANCH") + 100] = self.getLabelValueByName(newSegmentationType, "LAD_SIDE_BRANCH")

                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LCX_PROXIMAL") + 100] = self.getLabelValueByName(newSegmentationType, "LCX_PROXIMAL")
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LCX_MID") + 100] = self.getLabelValueByName(newSegmentationType, "LCX_MID")
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LCX_DISTAL") + 100] = self.getLabelValueByName(newSegmentationType, "LCX_DISTAL")
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LCX_SIDE_BRANCH") + 100] = self.getLabelValueByName(newSegmentationType, "LCX_SIDE_BRANCH")

                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "RIM") + 100] = self.getLabelValueByName(newSegmentationType, "RIM")

            elif oldSegmentationType == "SegmentLevel" and newSegmentationType == "ArteryLevel":
                # Combines all lesions in each artery to one group
                # RCA
                segmentation[(segmentation >= 4) & (segmentation <= 7)] = 4

                # LM
                segmentation[(segmentation >= 9) & (segmentation <= 12)] = 2

                # LAD
                segmentation[(segmentation >= 14) & (segmentation <= 17)] = 2

                # LCX
                segmentation[(segmentation >= 19) & (segmentation <= 22)] = 3

                # RIM
                segmentation[(segmentation == 23)] = 2

                segmentation[(segmentation >= 5)] = 0

            elif oldSegmentationType == "SegmentLevel" and newSegmentationType == "ArteryLevelWithLM":
                # Combines all lesions in each artery to one group
                # RCA
                segmentation[(segmentation >= 4) & (segmentation <= 7)] = 4

                # LAD
                segmentation[(segmentation >= 14) & (segmentation <= 17)] = 2

                # LCX
                segmentation[(segmentation >= 19) & (segmentation <= 22)] = 3

                # RIM
                segmentation[(segmentation == 23)] = 2

                # LM
                segmentation[(segmentation >= 9) & (segmentation <= 12)] = 5

                segmentation[(segmentation >= 6)] = 0

            elif oldSegmentationType == "SegmentLevel" and newSegmentationType == "SegmentLevelOnlyArteries":
                segmentation[segmentation >= self.getLabelValueByName(oldSegmentationType, "AORTA_ASC")] = 0
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LM_BIF_LAD_LCX")] = self.getLabelValueByName(oldSegmentationType, "LM_BRANCH")
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LM_BIF_LAD")] = self.getLabelValueByName(oldSegmentationType, "LM_BRANCH")
                segmentation[segmentation == self.getLabelValueByName(oldSegmentationType, "LM_BIF_LCX")] = self.getLabelValueByName(oldSegmentationType, "LM_BRANCH")

            elif oldSegmentationType == "ArteryLevelWithLM" and newSegmentationType == "ArteryLevel":
                # LM
                segmentation[segmentation == 5] = 2
                segmentation[(segmentation > 5)] = 0

            elif oldSegmentationType == "SegmentLevelDLNExport" and newSegmentationType == "ArteryLevelWithLM":
                segmentation[segmentation == 2] = 102  # LM

                segmentation[segmentation == 3] = 103  # LAD PROX
                segmentation[segmentation == 4] = 104  # LAD MID
                segmentation[segmentation == 5] = 105  # LAD DIST
                segmentation[segmentation == 6] = 106  # LAD SIDE

                segmentation[segmentation == 7] = 107  # LCX PROX
                segmentation[segmentation == 8] = 108  # LCX MID
                segmentation[segmentation == 9] = 109  # LCX DIST
                segmentation[segmentation == 10] = 110  # LCX SIDE

                segmentation[segmentation == 11] = 111  # RCA PROX
                segmentation[segmentation == 12] = 112  # RCA MID
                segmentation[segmentation == 13] = 113  # RCA DIST
                segmentation[segmentation == 14] = 114  # RCA SIDE

                segmentation[segmentation == 15] = 115  # RIM

                # Combines all lesions in each artery to one group
                # RCA
                segmentation[(segmentation >= 111) & (segmentation <= 114)] = 4

                # LAD
                segmentation[(segmentation >= 103) & (segmentation <= 106)] = 2

                # LCX
                segmentation[(segmentation >= 107) & (segmentation <= 110)] = 3

                # RIM
                segmentation[(segmentation == 115)] = 2

                # LM
                segmentation[segmentation == 102] = 5

                segmentation[(segmentation >= 6)] = 0

            elif oldSegmentationType == "SegmentLevelDLNExport" and newSegmentationType == "ArteryLevel":
                segmentation[segmentation == 2] = 102  # LM

                segmentation[segmentation == 3] = 103  # LAD PROX
                segmentation[segmentation == 4] = 104  # LAD MID
                segmentation[segmentation == 5] = 105  # LAD DIST
                segmentation[segmentation == 6] = 106  # LAD SIDE

                segmentation[segmentation == 7] = 107  # LCX PROX
                segmentation[segmentation == 8] = 108  # LCX MID
                segmentation[segmentation == 9] = 109  # LCX DIST
                segmentation[segmentation == 10] = 110  # LCX SIDE

                segmentation[segmentation == 11] = 111  # RCA PROX
                segmentation[segmentation == 12] = 112  # RCA MID
                segmentation[segmentation == 13] = 113  # RCA DIST
                segmentation[segmentation == 14] = 114  # RCA SIDE

                segmentation[segmentation == 15] = 115  # RIM

                # Combines all lesions in each artery to one group
                # RCA
                segmentation[(segmentation >= 111) & (segmentation <= 114)] = 4

                # LAD
                segmentation[(segmentation >= 103) & (segmentation <= 106)] = 2

                # LCX
                segmentation[(segmentation >= 107) & (segmentation <= 110)] = 3

                # RIM
                segmentation[(segmentation == 115)] = 2

                # LM
                segmentation[segmentation == 102] = 2

                segmentation[(segmentation >= 5)] = 0

            elif oldSegmentationType == "17Segment" and newSegmentationType == "17SegmentOnlyArteries":
                segmentation[segmentation >= self.getLabelValueByName(oldSegmentationType, "AORTA_ASC")] = 0

            return segmentation

        elif oldSegmentationType == newSegmentationType:
            return segmentation

        else:
            print("Error! Segmentation cannot be converted! Check type!")
            return