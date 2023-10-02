import json
import os
from pathlib import Path

from functools import reduce
from operator import getitem

class SettingsHandler():
    def __init__(self):
        self.settingsFolderpath = os.path.join(Path(__file__).absolute().parent.parent.parent.parent.parent, "data")
        self.settingsFilepath = os.path.join(self.settingsFolderpath, "settings_CACSLabeler5.x.json")

        # Holds read settings json!
        self.settingsJson = None

        # checking if settings json exists otherwise creating new settings file!
        if os.path.isfile(self.settingsFilepath):
            self.settingsJson = self.readFile(self.settingsFilepath)
        else:
            self.createDefaultSettings()

        self.addLabelsToSettingFile()

        #check settings json for errors!
        self.checkSettingsFileForErrors()

        #select default
        self.setDefaultDatasetAndObserver()

    def addLabelsToSettingFile(self):
        labelsJsonPath = os.path.join(Path(__file__).absolute().parent, "labels.json")

        if os.path.isfile(labelsJsonPath):
            json = self.readFile(labelsJsonPath)
            self.settingsJson["labels"] = json["labels"]
            self.settingsJson["exportedLabels"] = json["exportedLabels"]

    def deleteLabelsFromSettingsFile(self, settings):
        if "labels" in settings:
            del settings["labels"]
        if "exportedLabels" in settings:
            del settings["exportedLabels"]

        return settings

    def readFile(self, path):
        with open(path, 'r', encoding='utf-8') as file:
            return (json.load(file))

    def createDefaultSettings(self):
        defaultSettingsPath = os.path.join(Path(__file__).absolute().parent, "defaultSettings.json")

        if os.path.isfile(defaultSettingsPath):
            self.settingsJson = self.readFile(defaultSettingsPath)
            self.saveFile()

    def saveFile(self):
        with open(self.settingsFilepath, 'w', encoding='utf-8') as file:
            settings = self.settingsJson.copy()
            settings = self.deleteLabelsFromSettingsFile(settings)

            json.dump(settings, file, indent=4)

    def getContentByKeys(self, keys):
        data = None

        try:
            for key in keys:
                if data is None:
                    data = self.settingsJson.copy()
                    data = data[key]
                else:
                    data = data[key]

            return data
        except KeyError:
            return None

    def changeContentByKey(self, keys, value):
        reduce(getitem, keys[:-1], self.settingsJson)[keys[-1]] = value
        self.saveFile()

    def setDefaultDatasetAndObserver(self):
        dataset = self.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        observer = self.getContentByKeys(["savedDatasetAndObserverSelection", "observer"])

        if dataset == "" or observer == "":
            datasets = list(self.getContentByKeys(["datasets"]).keys())

            if len(datasets) != 0:
                self.changeContentByKey(["savedDatasetAndObserverSelection", "dataset"], datasets[0])
                observers = list(self.getContentByKeys(["datasets", datasets[0], "observers"]).keys())
                self.changeContentByKey(["savedDatasetAndObserverSelection", "observer"], observers[0])

    def getCurrentDatasetAndObserver(self):
        dataset = self.getContentByKeys(["savedDatasetAndObserverSelection", "dataset"])
        observer = self.getContentByKeys(["savedDatasetAndObserverSelection", "observer"])

        return dataset, observer

    def getAvailableDatasetsAndObservers(self):
        array = {}

        for dataset in self.settingsJson["datasets"]:
            if self.isDatasetSettingCorrect(dataset):
                if dataset not in array:
                    array[dataset] = []

                for observer in self.settingsJson["datasets"][dataset]["observers"]:
                    if self.isObserverSettingCorrent(dataset, observer):
                        array[dataset].append(observer)


            # if self.settingsJson["datasets"][dataset]:
            #     if self.settingsJson["datasets"][dataset]["imagesPath"] and os.path.isdir(self.settingsJson["datasets"][dataset]["imagesPath"]):
            #
            #         if dataset not in array:
            #             array[dataset] = []
            #
            #         for observer in self.settingsJson["datasets"][dataset]["observers"]:
            #             if os.path.isdir(self.settingsJson["datasets"][dataset]["observers"][observer]["labelsPath"]):
            #
            #                 availableSegmentationModes = list(self.settingsJson["labels"].keys())
            #
            #                 if self.settingsJson["datasets"][dataset]["observers"][observer][
            #                     "segmentationMode"] in availableSegmentationModes:
            #                     array[dataset].append(observer)
            #
            #                 else:
            #                     print(f"Observer [{observer}] missing segmentationMode")
            #             else:
            #                 print(f"Label path not existing [{dataset} | {observer}]")
            #     else:
            #         print(f"Dataset [{dataset}] missing images folder path")
            # else:
            #     print(f"Dataset [{dataset}] settings empty")

        return array

    def getAvailableSegmentationTypes(self):
        return list(self.settingsJson["labels"].keys())

    #Settings file checks
    def checkSettingsFileForErrors(self):
        #Checking main json structure
        neededElements = [["datasets"], ["exportType"], ["exportFolder"], ["savedDatasetAndObserverSelection"], ["labels"], ["exportedLabels"], ["tabOpen"]]

        for element in neededElements:
            self.isItemInJson(self.settingsJson, element)

        for dataset in self.settingsJson["datasets"]:
            if self.isDatasetSettingCorrect(dataset):

                for observer in self.settingsJson["datasets"][dataset]["observers"]:
                    self.isObserverSettingCorrent(dataset, observer)

    def isDatasetSettingCorrect(self, dataset):
        if "imagesPath" in self.settingsJson["datasets"][dataset]:
            if os.path.isdir(self.settingsJson["datasets"][dataset]["imagesPath"]):
                pass
            else:
                print(f"[{dataset}] has no valid image path!")
                return False
        else:
            print(f"[{dataset}] is missing image path setting!")
            return False

        if "observers" in self.settingsJson["datasets"][dataset]:
            if len(list(self.settingsJson["datasets"][dataset]["observers"].keys())) > 0:
                pass
            else:
                print(f"[{dataset}] is missing observers!")
                return False
        else:
            print(f"[{dataset}] is missing observers setting!")
            return False

        return True

    def isObserverSettingCorrent(self, dataset, observer):
        if "labelsPath" in self.settingsJson["datasets"][dataset]["observers"][observer]:
            if os.path.isdir(self.settingsJson["datasets"][dataset]["observers"][observer]["labelsPath"]):
                pass
            else:
                print(f"[{dataset} | {observer}] has no valid label path!")
                return False
        else:
            print(f"[{dataset} | {observer}] is missing label path setting!")
            return False

        if "labelsPath" in self.settingsJson["datasets"][dataset]["observers"][observer]:
            if os.path.isdir(self.settingsJson["datasets"][dataset]["observers"][observer]["labelsPath"]):
                pass
            else:
                print(f"[{dataset} | {observer}] has no valid label path!")
                return False
        else:
            print(f"[{dataset} | {observer}] is missing label path setting!")
            return False

        if "segmentationMode" in self.settingsJson["datasets"][dataset]["observers"][observer]:
            if self.settingsJson["datasets"][dataset]["observers"][observer]["segmentationMode"] in self.getAvailableSegmentationTypes():
                pass
            else:
                print(f"[{dataset} | {observer}] has no valid segmentation mode!")
                return False
        else:
            print(f"[{dataset} | {observer}] is missing segmentation mode setting!")
            return False

        return True

    def isItemInJson(self, json, item):
        if self.getContentByKeys(item) is None:
            print(f"Missing json element [{item}]")
