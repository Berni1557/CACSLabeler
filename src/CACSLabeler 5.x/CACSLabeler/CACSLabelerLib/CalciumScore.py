import importlib
#import pandas
import os
import json
import numpy
import concurrent.futures
import SimpleITK as sitk
from scipy.ndimage import label
from scipy import ndimage as ndi

class CalciumScore():
    def __init__(self, datasetInformation, settings):
        imagesPath, labelsPath, segmentationMode, sliceStepFile, exportFolder, dataset, observer, fileSuffix = datasetInformation

        self.segmentationMode = segmentationMode
        self.dataset = dataset

        exportTypesOrder = ["ArteryLevel", "ArteryLevelWithLM", "SegmentLevelDLNExport", "SegmentLevel"]

        if exportTypesOrder.index(segmentationMode) >= exportTypesOrder.index(settings["exportType"]):
            self.exportType = settings["exportType"]

        else:
            self.exportType = segmentationMode

        self.filepaths = {
            "imageFolder": imagesPath,
            "referenceFolder": labelsPath,
            "sliceStepFile": sliceStepFile,
            "exportFileCSV": os.path.join(exportFolder, dataset + "_" + observer + "_" + self.exportType + ".csv"),
            "exportFileJSON": os.path.join(exportFolder, dataset + "_" + observer + "_" + self.exportType + ".json")
        }

        self.Items = self.createItems(settings)

        self.arteryId = {}

        for key in self.Items:
            if isinstance(self.Items[key], int):
                self.arteryId[self.Items[key]] = key

        self.exportJson = {}
        self.exportList = []

        self.pandas = importlib.import_module('pandas')

    def createItems(self, settings):
        items = None

        generatedItems = {}

        for item in settings["exportedLabels"][self.exportType]:
            itemContent = None

            labelContent = settings["exportedLabels"][self.exportType][item]

            if isinstance(labelContent, list):
                itemContent = []

                for groupElement in labelContent:
                    itemContent.append(settings["labels"][self.exportType][groupElement]["value"])

            else:
                itemContent = settings["labels"][self.exportType][labelContent]["value"]
                pass

            generatedItems[item] = itemContent

        return generatedItems

    def exportFromJSONFile(self):
        # Opening JSON file

        with open(self.filepaths["exportFileJSON"], 'r', encoding='utf-8') as file:
            # returns JSON object as
            # a dictionary
            self.exportJson = None
            self.exportJson = json.load(file)

            # Iterating through the json
            # list
            for patientId in self.exportJson:
                for seriesInstanceUID in self.exportJson[patientId]:

                    result = self.calculateScore(patientId, seriesInstanceUID)
                    self.exportList.append(result)
                    print("Exported", patientId, seriesInstanceUID)

        self.createExportFilesAndSaveContent(createJson=False)

    def createExportFilesAndSaveContent(self, createJson):
        dataframe = self.pandas.DataFrame.from_records(self.exportList)
        dataframe.to_csv(self.filepaths["exportFileCSV"], index=False, sep=';', float_format='%.3f')

        if createJson:
            with open(self.filepaths["exportFileJSON"], 'w', encoding='utf-8') as file:
                #explicit copy to prevent race condition
                json.dump(dict(self.exportJson), file, ensure_ascii=False, indent=4, cls=NpEncoder)

    def exportFromReferenceFolder(self):
        sliceStepDataframe = self.pandas.read_csv(self.filepaths["sliceStepFile"], dtype={'patient_id': 'string'})

        with concurrent.futures.ThreadPoolExecutor() as executor:
            [executor.submit(self.processImages, filename, sliceStepDataframe)
             for filename in sorted(filter(lambda x: os.path.isfile(os.path.join(self.filepaths["referenceFolder"], x)),
                                           os.listdir(self.filepaths["referenceFolder"])))]

    def processFilename(self, filepath):
        if self.dataset == "DISCHARGE" or self.dataset == "CADMAN":
            fileName = filepath.split("/")[-1]
            PatientID = fileName.split("_")[0]
            fileId = PatientID + "_" + fileName.split("_")[1].split("-")[0]
            SeriesInstanceUID = fileId.split("_")[1]

        elif self.dataset == "OrCaScore":
            fileName = filepath.split("/")[-1]
            fileId = fileName.split("-")[0]
            PatientID = fileId.split("_")[0]
            SeriesInstanceUID = fileId.split("_")[1]

        return fileName, fileId, PatientID, SeriesInstanceUID

    def label(self, referenceTemporaryCopy, uniqueId, structureConnections2d, iterator, connectedElements2d):
        labeled_array, num_features = ndi.label((referenceTemporaryCopy == uniqueId).astype(int),structure=structureConnections2d)
        return numpy.where(labeled_array > 0, labeled_array + iterator, 0).astype(connectedElements2d.dtype)

    def findLesions(self, reference):
        # preprocessing label
        reference[reference == 24] = 35

        # Options: ArteryLevel, SegmentLevel, ArteryLevelWithLM, SegmentLevelDLNExport
        if self.segmentationMode == "SegmentLevel" and self.exportType == "ArteryLevel":
            # Combines all lesions in each artery to one group
            # RCA
            reference[(reference >= 4) & (reference <= 7)] = 4

            # LM
            reference[(reference >= 9) & (reference <= 12)] = 2

            # LAD
            reference[(reference >= 14) & (reference <= 17)] = 2

            # LCX
            reference[(reference >= 19) & (reference <= 22)] = 3

            # RIM
            reference[(reference == 23)] = 2

            reference[(reference >= 5)] = 0
        elif self.segmentationMode == "SegmentLevel" and self.exportType == "ArteryLevelWithLM":
            # Combines all lesions in each artery to one group
            # RCA
            reference[(reference >= 4) & (reference <= 7)] = 4

            # LAD
            reference[(reference >= 14) & (reference <= 17)] = 2

            # LCX
            reference[(reference >= 19) & (reference <= 22)] = 3

            # RIM
            reference[(reference == 23)] = 2

            # LM
            reference[(reference >= 9) & (reference <= 12)] = 5

            reference[(reference >= 6)] = 0
        elif self.segmentationMode == "ArteryLevelWithLM" and self.exportType == "ArteryLevel":
            # LM
            reference[reference == 5] = 2
            reference[(reference > 5)] = 0

        elif self.segmentationMode == "SegmentLevel" and self.exportType == "SegmentLevelDLNExport":
            reference[reference == 4] = 104  # RCA PROX
            reference[reference == 5] = 105  # RCA MID
            reference[reference == 6] = 106  # RCA DIST
            reference[reference == 7] = 107  # RCA SIDE

            reference[reference == 14] = 114  # LAD PROX
            reference[reference == 15] = 115  # LAD MID
            reference[reference == 16] = 116  # LAD DIST
            reference[reference == 17] = 117  # LAD SIDE

            reference[reference == 19] = 119  # LCX PROX
            reference[reference == 20] = 120  # LCX MID
            reference[reference == 21] = 121  # LCX DIST
            reference[reference == 22] = 122  # LCX SIDE

            #convert ids
            reference[(reference >= 9) & (reference <= 12)] = 2 # LM

            reference[reference == 114] = 3  # LAD PROX
            reference[reference == 115] = 4  # LAD MID
            reference[reference == 116] = 5  # LAD DIST
            reference[reference == 117] = 6  # LAD SIDE

            reference[reference == 119] = 7  # LCX PROX
            reference[reference == 120] = 8  # LCX MID
            reference[reference == 121] = 9  # LCX DIST
            reference[reference == 122] = 10  # LCX SIDE

            reference[reference == 104] = 11  # RCA PROX
            reference[reference == 105] = 12  # RCA MID
            reference[reference == 106] = 13  # RCA DIST
            reference[reference == 107] = 14  # RCA SIDE

            reference[reference == 23] = 15  # RIM

            reference[(reference >= 16)] = 0  # LM

        elif self.segmentationMode == "SegmentLevelDLNExport" and self.exportType == "ArteryLevelWithLM":
            reference[reference == 2] = 102  # LM

            reference[reference == 3] = 103  # LAD PROX
            reference[reference == 4] = 104  # LAD MID
            reference[reference == 5] = 105  # LAD DIST
            reference[reference == 6] = 106  # LAD SIDE

            reference[reference == 7] = 107  # LCX PROX
            reference[reference == 8] = 108  # LCX MID
            reference[reference == 9] = 109  # LCX DIST
            reference[reference == 10] = 110  # LCX SIDE

            reference[reference == 11] = 111  # RCA PROX
            reference[reference == 12] = 112  # RCA MID
            reference[reference == 13] = 113  # RCA DIST
            reference[reference == 14] = 114  # RCA SIDE

            reference[reference == 15] = 115  # RIM

            # Combines all lesions in each artery to one group
            # RCA
            reference[(reference >= 111) & (reference <= 114)] = 4

            # LAD
            reference[(reference >= 103) & (reference <= 106)] = 2

            # LCX
            reference[(reference >= 107) & (reference <= 110)] = 3

            # RIM
            reference[(reference == 115)] = 2

            # LM
            reference[reference == 102] = 5

            reference[(reference >= 6)] = 0

        elif self.segmentationMode == "SegmentLevelDLNExport" and self.exportType == "ArteryLevel":
            reference[reference == 2] = 102  # LM

            reference[reference == 3] = 103  # LAD PROX
            reference[reference == 4] = 104  # LAD MID
            reference[reference == 5] = 105  # LAD DIST
            reference[reference == 6] = 106  # LAD SIDE

            reference[reference == 7] = 107  # LCX PROX
            reference[reference == 8] = 108  # LCX MID
            reference[reference == 9] = 109  # LCX DIST
            reference[reference == 10] = 110  # LCX SIDE

            reference[reference == 11] = 111  # RCA PROX
            reference[reference == 12] = 112  # RCA MID
            reference[reference == 13] = 113  # RCA DIST
            reference[reference == 14] = 114  # RCA SIDE

            reference[reference == 15] = 115  # RIM

            # Combines all lesions in each artery to one group
            # RCA
            reference[(reference >= 111) & (reference <= 114)] = 4

            # LAD
            reference[(reference >= 103) & (reference <= 106)] = 2

            # LCX
            reference[(reference >= 107) & (reference <= 110)] = 3

            # RIM
            reference[(reference == 115)] = 2

            # LM
            reference[reference == 102] = 2

            reference[(reference >= 5)] = 0

        referenceTemporaryCopy = reference.copy()
        referenceTemporaryCopy[referenceTemporaryCopy < 2] = 0


        structure = numpy.array([[[0, 0, 0],
                                   [0, 1, 0],
                                   [0, 0, 0]],

                                  [[0, 1, 0],
                                   [1, 1, 1],
                                   [0, 1, 0]],

                                  [[0, 0, 0],
                                   [0, 1, 0],
                                   [0, 0, 0]]])

        uniqueElements = numpy.unique(referenceTemporaryCopy)

        connectedElements = numpy.zeros_like(referenceTemporaryCopy)
        elementIterator = 0

        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = [executor.submit(ndi.label, (referenceTemporaryCopy == uniqueId).astype(int),
                                       structure=structure)
                       for uniqueId in uniqueElements[1:]]

            for future in concurrent.futures.as_completed(results):
                label, elementCount = future.result()
                connectedElements += numpy.where(label > 0, label + elementIterator, 0).astype(
                    connectedElements.dtype)
                elementIterator += elementCount

        return connectedElements, len(numpy.unique(connectedElements)) - 1

    def lesionPositionListEntry(self, connectedElements3d, index, image, reference):
        positions = numpy.array(list(zip(*numpy.where(connectedElements3d[0] == index))))

        newList = []

        for element in positions:
            attenuation = image[element[0], element[1], element[2]]
            originalLabel = reference[element[0], element[1], element[2]]
            element = numpy.concatenate((element, [attenuation, originalLabel]))
            newList.append(element)

        return numpy.array(newList)

    def jsonLesionLoop(self, lesion, it, patientID,seriesInstanceUID):
        self.exportJson[patientID][seriesInstanceUID]["lesions"][it] = {}
        self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["voxelCount3d"] = len(lesion)
        self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"] = {}

        slices = lesion[:, 0:1]
        slice, voxelCount = numpy.unique(slices, return_counts=True)
        slicesDict = dict(zip(slice, voxelCount))

        sliceIterator = 0
        for slice in slicesDict:
            self.jsonSliceLoop(patientID, seriesInstanceUID, it, lesion, slice, sliceIterator, slicesDict)
            sliceIterator += 1

    def jsonSliceLoop(self, patientID, seriesInstanceUID, it, lesion, slice, sliceIterator, slicesDict):
        sliceArray = lesion[numpy.in1d(lesion[:, 0], slice)]

        #needed to check if lesions are seperated in 2d but connected in 3d
        maxCoordinate = 513

        tempComponentAnalysis = numpy.zeros(shape=(maxCoordinate,maxCoordinate))
        tempAttenuation = numpy.zeros(shape=(maxCoordinate, maxCoordinate))
        tempLabel = numpy.zeros(shape=(maxCoordinate, maxCoordinate))

        for element in sliceArray:
            row = element[1]
            column = element[2]
            tempComponentAnalysis[row, column] = 1
            tempAttenuation[row, column] = element[3]
            tempLabel[row, column] = element[4]

        structureConnections2d = numpy.array([[0, 1, 0],
                                               [1, 1, 1],
                                               [0, 1, 0]])

        connections, N = label(tempComponentAnalysis, structureConnections2d)

        self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceIterator] = {}
        self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceIterator]["voxelCount2D"] = slicesDict[slice]
        self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceIterator]["labeledAs"] = {}
        self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceIterator]["sliceNumber"] = slice

        if N > 1:
            labelsSummary = {}

            for lesionId in range(1, N + 1):
                positions = numpy.array(list(zip(*numpy.where(connections == lesionId))))
                lesionSummary = {}

                for position in positions:
                    labelAtPosition = tempLabel[position[0],position[1]]
                    attenuationAtPosition = tempAttenuation[position[0],position[1]]

                    if self.arteryId[labelAtPosition] in lesionSummary:
                        lesionSummary[self.arteryId[labelAtPosition]]["voxelCount"] = lesionSummary[self.arteryId[labelAtPosition]]["voxelCount"] + 1
                        if attenuationAtPosition > lesionSummary[self.arteryId[labelAtPosition]]["maxAttenuation"]:
                            lesionSummary[self.arteryId[labelAtPosition]]["maxAttenuation"] = attenuationAtPosition
                    else:
                        lesionSummary[self.arteryId[labelAtPosition]] = {}
                        lesionSummary[self.arteryId[labelAtPosition]]["voxelCount"] = 1
                        lesionSummary[self.arteryId[labelAtPosition]]["maxAttenuation"] = attenuationAtPosition

                labelsSummary[lesionId] = lesionSummary

            self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceIterator]["labeledAs"] = labelsSummary
            self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceIterator]["maxAttenuation"] = None
        else:
            self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceIterator]["maxAttenuation"] = max(max(sliceArray[:, 3:4]))

            arteryId = sliceArray[:, 4:5]
            arteries, arteryCount = numpy.unique(arteryId, return_counts=True)
            arteryDict = dict(zip(arteries, arteryCount))

            for artery in arteryDict:
                self.exportJson[patientID][seriesInstanceUID]["lesions"][it]["slices"][sliceIterator]["labeledAs"][self.arteryId[artery]] = arteryDict[artery]

    def calculateLesions(self, image, reference, connectedElements3d, patientID, seriesInstanceUID):
        lesionPositionList = []

        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = [executor.submit(self.lesionPositionListEntry, connectedElements3d, index, image, reference) for index in range(1, connectedElements3d[1] + 1)]

            for future in concurrent.futures.as_completed(results):
                lesionPositionList.append(future.result())

        it = 0
        for lesion in lesionPositionList:
            self.jsonLesionLoop(lesion, it, patientID, seriesInstanceUID)

            it += 1

    def agatstonScore(self, voxelLength, voxelCount, attenuation, ratio):
        score = 0.0

        if (voxelLength is not None) and (voxelCount is not None) and (attenuation is not None) and (ratio is not None):
            voxelArea = voxelLength * voxelLength
            lesionArea = voxelArea * voxelCount

            if attenuation >= 130 and lesionArea > 1:
                score = lesionArea * self.densityFactor(attenuation) * ratio

        return score

    def calculateScore(self, patientID, seriesInstanceUID):
        total = {"PatientID": patientID, "SeriesInstanceUID": seriesInstanceUID}

        for key in self.Items:
            total[key] = 0.0

        for lesionsJson in self.exportJson[patientID][seriesInstanceUID]["lesions"]:
            for sliceJson in self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"]:

                sliceNumber = self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["sliceNumber"]
                if sliceNumber in self.exportJson[patientID][seriesInstanceUID]["countingSlices"]:
                    attenuation = self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["maxAttenuation"]

                    if attenuation is not None:
                        for arteryJson in self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["labeledAs"]:
                            voxelCount = self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["labeledAs"][arteryJson]
                            voxelLength = self.exportJson[patientID][seriesInstanceUID]["voxelLength"]

                            score = self.agatstonScore(voxelLength, voxelCount, attenuation,self.exportJson[patientID][seriesInstanceUID]["sliceRatio"])

                            if arteryJson in total:
                                total[arteryJson] += score
                            else:
                                total[arteryJson] = score
                    else:
                        for subLabelId in self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["labeledAs"]:
                            for sublabelArtery in self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["labeledAs"][subLabelId]:
                                maxAttenuation = self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["labeledAs"][subLabelId][sublabelArtery]["maxAttenuation"]
                                voxelLength = self.exportJson[patientID][seriesInstanceUID]["voxelLength"]
                                voxelCount = self.exportJson[patientID][seriesInstanceUID]["lesions"][lesionsJson]["slices"][sliceJson]["labeledAs"][subLabelId][sublabelArtery]["voxelCount"]

                                score = self.agatstonScore(voxelLength, voxelCount, maxAttenuation, self.exportJson[patientID][seriesInstanceUID]["sliceRatio"])

                                if sublabelArtery in total:
                                    total[sublabelArtery] += score
                                else:
                                    total[sublabelArtery] = score

        for key in self.Items:
            if isinstance(self.Items[key], list):
                sum = 0.0
                for id in self.Items[key]:
                    if id in self.arteryId and self.arteryId[id] in total:
                        sum += total[self.arteryId[id]]

                total[key] = sum

        return total

    def calculateScoreFromImage(self, image, reference, patientID, seriesInstanceUID):
        connectedElements = self.findLesions(reference)

        self.calculateLesions(image, reference, connectedElements, patientID, seriesInstanceUID)
        return self.calculateScore(patientID, seriesInstanceUID)


    def processImages(self, filename, sliceStepDataframe):
        processedFilename = self.processFilename(os.path.join(self.filepaths["referenceFolder"], filename))

        if os.path.isfile(os.path.join(self.filepaths["imageFolder"], processedFilename[1] + ".mhd")):
            image = sitk.ReadImage(os.path.join(self.filepaths["imageFolder"], processedFilename[1] + ".mhd"))
            label = sitk.ReadImage(os.path.join(self.filepaths["referenceFolder"], filename))

            # Convert the image to a numpy array first and then shuffle the dimensions to get axis in the order z,y,x
            imageArray = sitk.GetArrayFromImage(image)
            labelArray = sitk.GetArrayFromImage(label)

            # Read the spacing along each dimension
            spacing = numpy.array(list(reversed(image.GetSpacing())))
            sliceThickness = sliceStepDataframe.loc[(sliceStepDataframe['patient_id'] == processedFilename[2])].slice_thickness.item()
            sliceStep = sliceStepDataframe.loc[(sliceStepDataframe['patient_id'] == processedFilename[2])].slice_step.item()

            exportData = {"PatientID": processedFilename[2], "SeriesInstanceUID": processedFilename[3]}

            self.exportJson[processedFilename[2]] = {}
            self.exportJson[processedFilename[2]][processedFilename[3]] = {}
            self.exportJson[processedFilename[2]][processedFilename[3]]["sliceRatio"] = sliceThickness / 3.0
            self.exportJson[processedFilename[2]][processedFilename[3]]["voxelLength"] = spacing[1]  # voxel length in mm
            self.exportJson[processedFilename[2]][processedFilename[3]]["lesions"] = {}
            self.exportJson[processedFilename[2]][processedFilename[3]]["sliceCount"] = len(imageArray)
            self.exportJson[processedFilename[2]][processedFilename[3]]["sliceStep"] = sliceStep

            countingSlices = []

            for sliceNumber in range(0, len(imageArray), sliceStep):
                countingSlices.append(sliceNumber)

            self.exportJson[processedFilename[2]][processedFilename[3]]["countingSlices"] = countingSlices

            result = self.calculateScoreFromImage(imageArray, labelArray, processedFilename[2], processedFilename[3])

            print("Exported " + processedFilename[1])
            self.exportList.append(result)
            self.createExportFilesAndSaveContent(createJson=True)

    def densityFactor(self, maxDensity):
        if maxDensity >= 130 and maxDensity <= 199:
            return 1
        if maxDensity >= 200 and maxDensity <= 299:
            return 2
        if maxDensity >= 300 and maxDensity <= 399:
            return 3
        if maxDensity >= 400:
            return 4