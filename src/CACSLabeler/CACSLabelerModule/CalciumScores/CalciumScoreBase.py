# -*- coding: utf-8 -*-
import os
import csv

# scorebase
class CalciumScoreBase:
    def __init__(self):
        pass
    
    @staticmethod
    def export_csv(settings, imagelist, appendCSV, scorename='AGATSTON_SCORE'):
        # Write calcium scores into csv
        if settings['MODE'] == 'CACS':
            columns = settings['columns_CACS']
        elif settings['MODE'] == 'CACSTREE_CUMULATIVE':
            columns = settings['columns_CACSTREE_CUMULATIVE']
        elif settings['MODE'] == 'CACS_ORCASCORE':
            columns = settings['columns_CACS']
        else:
            raise ValueError('Mode ' + settings['MODE'] + ' does not exist.')
             
        folderpath_export_csv = settings['folderpath_export']
        if not os.path.isdir(folderpath_export_csv):
            os.mkdir(folderpath_export_csv)
        filepath_csv = os.path.join(folderpath_export_csv, scorename + '.csv')
        
        if os.path.isfile(filepath_csv):
            writeColumn = False
        else:
            writeColumn = True

        if appendCSV:
            openMode = 'a'
        else:
            openMode = 'w'
        with open(filepath_csv, openMode) as file:
            writer = csv.writer(file, delimiter=';', lineterminator="\n")
            if writeColumn:
                writer.writerow(columns)
            for image in imagelist:
                scores = image.scores
                for score in scores:
                    if score['NAME'] == scorename:
                        PatientID = image.PatientID
                        SeriesInstanceUID = image.SeriesInstanceUID
                        row = [PatientID, SeriesInstanceUID]
                        for c in columns[2:]:
                            row = row + [str(score[c]).replace('.', ',')]
                        writer.writerow(row)
                        
                        
                        