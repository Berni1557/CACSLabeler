import json
import os
from pathlib import Path

from functools import reduce
from operator import getitem

class SettingsHandler():
    def __init__(self):
        self.settingsFolderpath = os.path.join(Path(__file__).absolute().parent.parent.parent.parent.parent, "data")
        self.settingsFilepath = os.path.join(self.settingsFolderpath, "settings_CACSLabelerNew.json")

        # Holds read settings json!
        self.settingsJson = None

        # checking if settings json exists otherwise creating new settings file!
        if os.path.isfile(self.settingsFilepath):
            self.settingsJson = self.readFile(self.settingsFilepath)
        else:
            self.createDefaultSettings()

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
            json.dump(self.settingsJson, file, indent=4)

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
            print("Provided key was not found!")
            return None

    def changeContentByKey(self, keys, value):
        reduce(getitem, keys[:-1], self.settingsJson)[keys[-1]] = value
        self.saveFile()

    def getCurrentDatasetAndObserver(self):
        pass

    def getAvailableDatasetsAndObservers(self):
        array = {}

        for dataset in self.settingsJson["datasets"]:
            if self.settingsJson["datasets"][dataset]:
                if self.settingsJson["datasets"][dataset]["imagesPath"] and os.path.isdir(self.settingsJson["datasets"][dataset]["imagesPath"]):

                    if dataset not in array:
                        array[dataset] = []

                    for observer in self.settingsJson["datasets"][dataset]["observers"]:
                        if os.path.isdir(self.settingsJson["datasets"][dataset]["observers"][observer]["labelsPath"]):

                            # Options: ArteryLevel, SegmentLevel, ArteryLevelWithLM, SegmentLevelDLNExport
                            if self.settingsJson["datasets"][dataset]["observers"][observer][
                                "segmentationMode"] == "ArteryLevel" \
                                    or self.settingsJson["datasets"][dataset]["observers"][observer][
                                "segmentationMode"] == "SegmentLevel" \
                                    or self.settingsJson["datasets"][dataset]["observers"][observer][
                                "segmentationMode"] == "SegmentLevelDLNExport" \
                                    or self.settingsJson["datasets"][dataset]["observers"][observer][
                                "segmentationMode"] == "ArteryLevelWithLM":
                                array[dataset].append(observer)

                            else:
                                print(f"Observer [{observer}] missing segmentationMode")
                        else:
                            print(f"Observer [{observer}] missing labels folder path")
                else:
                    print(f"Dataset [{dataset}] missing images folder path")
            else:
                print(f"Dataset [{dataset}] settings empty")

        return array