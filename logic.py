import os
import time
import shutil
import requests
import openpyxl
import pandas as pd
import numpy as np
from copy import copy
from openpyxl.comments import Comment
from pydrive2.drive import GoogleDrive

class TransferGrades:
    def __init__(self, drive: GoogleDrive, credentials):
        self.drive = drive
        self.credentials = credentials

    def cleanup_local_files(self, target_path='output'):
        """
        Clears the output directory and deletes local .xlsx files.
        """
        print(f"Cleaning up local files... Target path: {target_path}")
        if os.path.exists(target_path):
            shutil.rmtree(target_path)
        os.makedirs(target_path)

        for f in os.listdir('.'):
            if f.endswith('.xlsx') and os.path.isfile(f):
                try:
                    os.remove(f)
                    print(f"Deleted: {f}")
                except Exception as e:
                    print(f"Error deleting {f}: {e}")

    def position_from_column(self, l):
        num_array = [ord(x.upper()) - 64 for x in l]
        result = 0
        for i, v in enumerate(num_array):
            result = i * 26 + v
        return result

    def search_file(self, filename, is_sheet=True):
        # Remove extension for searching if it's a Google Sheet
        search_name = filename
        if is_sheet and filename.lower().endswith('.xlsx'):
            search_name = filename[:-5]
        elif not is_sheet and not filename.lower().endswith('.xlsx'):
            search_name = f"{filename}.xlsx"
        else:
            search_name = filename

        if not is_sheet:
            query = f"title = '{search_name}'"
        else:
            query = f"mimeType ='application/vnd.google-apps.spreadsheet' and title = '{search_name}'"
        
        print(f"Searching for file with query: {query}")
        listed = self.drive.ListFile({'q': query}).GetList()
        
        if len(listed):
            file = listed[0]
            print(f"File found: {file['title']} ({file['id']})")
            spreadsheet_id = file['id']
            # Local filename should have .xlsx for processing
            local_filename = filename if filename.lower().endswith('.xlsx') else f"{filename}.xlsx"
            
            if not is_sheet:
                downloaded = self.drive.CreateFile({'id': spreadsheet_id})
                downloaded.GetContentFile(local_filename)
            else:
                url = f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=xlsx&id={spreadsheet_id}'
                headers = {'Authorization': 'Bearer ' + self.credentials.token}
                res = requests.get(url, headers=headers)
                with open(local_filename, 'wb') as f:
                    f.write(res.content)
            return local_filename, spreadsheet_id
        return None, None

    def copy_grades(self, config):
        """
        Processes grades locally and creates student workbooks.
        """
        filename = config['nombre_excel_notas']
        sheet_name = config.get('nombre_hoja')
        header_count = config['numero_cabecera']
        col_name_idx = self.position_from_column(config['letra_columna_nombre']) - 1
        col_email_idx = self.position_from_column(config['letra_columna_correo']) - 1
        template_name = config.get('plantilla_cabecera')
        target_path = config.get('path_target', 'output')

        if filename.lower().endswith('.xlsx'):
            local_file = filename
        else:
            local_file = f"{filename}.xlsx"
        
        if not os.path.exists(local_file):
            if os.path.exists(filename):
                local_file = filename
            else:
                raise FileNotFoundError(f"Archivo local no encontrado: {local_file}")

        wb_original = openpyxl.load_workbook(local_file, data_only=False)
        available_sheets = wb_original.sheetnames

        if sheet_name:
            sheet_name = sheet_name.strip()
            if sheet_name not in available_sheets:
                matches = [s for s in available_sheets if s.lower() == sheet_name.lower()]
                if matches:
                    sheet_name = matches[0]
                else:
                    raise KeyError(f"La hoja '{sheet_name}' no existe.")
            ws_original = wb_original[sheet_name]
        else:
            ws_original = wb_original.worksheets[0]
            sheet_name = None

        if not os.path.exists(target_path):
            os.makedirs(target_path)

        # Load data with Pandas to get evaluated values (resolved formulas)
        # Note: we use ws_original.title to ensure we use the same sheet identified by Openpyxl
        df = pd.read_excel(local_file, header=None, sheet_name=ws_original.title)
        
        results = []
        for index, row_pd in df.iloc[header_count:].iterrows():
            name_val = row_pd.values[col_name_idx]
            email_val = row_pd.values[col_email_idx]
            
            name = str(name_val) if name_val is not None and str(name_val).lower() != 'nan' else ""
            email = str(email_val).strip() if email_val is not None and str(email_val).lower() != 'nan' else ""
            
            if not name or not email:
                continue

            print(f"Processing student: {name}")
            
            if sheet_name:
                folder_name = f"{name}__{filename}"
                student_file_name = f"{sheet_name}.xlsx"
            else:
                folder_name = name
                student_file_name = f"{name}__{filename}.xlsx"

            student_folder_path = os.path.join(target_path, folder_name)
            if not os.path.exists(student_folder_path):
                os.makedirs(student_folder_path)

            full_student_file_path = os.path.join(student_folder_path, student_file_name)

            # Create Student Workbook
            if template_name:
                template_file, _ = self.search_file(template_name, config['extension_cabecera'] == 'Google Sheet')
                if template_file:
                    wb_student = openpyxl.load_workbook(template_file)
                    if sheet_name:
                        if sheet_name not in wb_student.sheetnames:
                            wb_student.active.title = sheet_name
                        for s_name in list(wb_student.sheetnames):
                            if s_name != sheet_name and s_name not in config.get('nombre_otras_hoja', []):
                                wb_student.remove(wb_student[s_name])
                    ws_student = wb_student[sheet_name] if sheet_name else wb_student.active
                else:
                    wb_student = openpyxl.Workbook()
                    ws_student = wb_student.active
                    if sheet_name: ws_student.title = sheet_name
            else:
                wb_student = openpyxl.Workbook()
                ws_student = wb_student.active
                if sheet_name: ws_student.title = sheet_name
                
                # Copy Header using Pandas values and Openpyxl comments/styles
                for r_idx, row_header in df.iloc[:header_count].iterrows():
                    row_list_header = row_header.values.tolist()
                    for c_idx, val_header in enumerate(row_list_header):
                        cell_orig = ws_original.cell(row=r_idx + 1, column=c_idx + 1)
                        cell_new = ws_student.cell(row=r_idx + 1, column=c_idx + 1, value=val_header)
                        cell_new.comment = cell_orig.comment
                        if cell_orig.has_style:
                            cell_new.font = copy(cell_orig.font)
                            cell_new.border = copy(cell_orig.border)
                            cell_new.fill = copy(cell_orig.fill)
                            cell_new.number_format = copy(cell_orig.number_format)
                            cell_new.protection = copy(cell_orig.protection)
                            cell_new.alignment = copy(cell_orig.alignment)

            # Add Student Values
            # We use row_pd values (from Pandas) and ws_original cells (from Openpyxl)
            row_list = row_pd.values.tolist()
            for c_idx, val in enumerate(row_list):
                cell_orig = ws_original.cell(row=index + 1, column=c_idx + 1)
                cell_new = ws_student.cell(row=header_count + 1, column=c_idx + 1, value=val)
                cell_new.comment = cell_orig.comment
                if cell_orig.has_style:
                    cell_new.font = copy(cell_orig.font)
                    cell_new.border = copy(cell_orig.border)
                    cell_new.fill = copy(cell_orig.fill)
                    cell_new.number_format = copy(cell_orig.number_format)
                    cell_new.protection = copy(cell_orig.protection)
                    cell_new.alignment = copy(cell_orig.alignment)
                if cell_orig.hyperlink:
                    cell_new.hyperlink = copy(cell_orig.hyperlink)
            
            wb_student.save(full_student_file_path)
            wb_student.close()
            results.append({'name': name, 'email': email, 'folder': folder_name, 'file': student_file_name})

        return results

    def get_or_create_folder_path(self, path):
        if not path or path.lower() == 'root':
            return 'root'
        parts = [p for p in path.replace('\\', '/').split('/') if p]
        parent_id = 'root'
        for part in parts:
            query = f"title = '{part}' and mimeType = 'application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed = false"
            listed = self.drive.ListFile({'q': query}).GetList()
            if listed:
                parent_id = listed[0]['id']
            else:
                folder = self.drive.CreateFile({'title': part, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [{'id': parent_id}]})
                folder.Upload()
                parent_id = folder['id']
        return parent_id

    def upload_folders(self, results, target_folder_path, convert=False):
        target_drive_folder_id = self.get_or_create_folder_path(target_folder_path)
        uploaded_items = []
        for item in results:
            print(f"Uploading folder/file for {item['name']}")
            
            # 1. Get or Create Student Folder
            query_folder = f"title = '{item['folder']}' and mimeType = 'application/vnd.google-apps.folder' and '{target_drive_folder_id}' in parents and trashed = false"
            listed_folders = self.drive.ListFile({'q': query_folder}).GetList()
            
            if listed_folders:
                folder = listed_folders[0]
            else:
                folder = self.drive.CreateFile({'title': item['folder'], 'mimeType': 'application/vnd.google-apps.folder', 'parents': [{'id': target_drive_folder_id}]})
                folder.Upload()
            
            # 2. Overwrite or Create Student File
            query_file = f"title = '{item['file']}' and '{folder['id']}' in parents and trashed = false"
            if convert:
                title_search = item['file'].replace('.xlsx', '')
                query_file = f"title = '{title_search}' and '{folder['id']}' in parents and trashed = false"
            else:
                title_search = item['file']

            listed_files = self.drive.ListFile({'q': query_file}).GetList()
            local_file_path = os.path.join('output', item['folder'], item['file'])
            
            if listed_files:
                f = listed_files[0]
            else:
                f = self.drive.CreateFile({'title': title_search, 'parents': [{'id': folder['id']}]})
            
            f.SetContentFile(local_file_path)
            # convert=True converts .xlsx to Google Sheets, which also converts Excel comments to GSheet comments
            f.Upload(param={'convert': convert})
            
            item['folder_id'] = folder['id']
            uploaded_items.append(item)
        
        return uploaded_items

    def share_with_students(self, items):
        results = []
        for item in items:
            print(f"Sharing folder {item['folder_id']} with {item['email']}")
            try:
                folder = self.drive.CreateFile({'id': item['folder_id']})
                perms = folder.GetPermissions()
                already_shared = any(p.get('emailAddress') == item['email'] for p in perms)
                if not already_shared:
                    folder.InsertPermission({'type': 'user', 'value': item['email'], 'role': 'writer'})
                results.append({'email': item['email'], 'status': 'success'})
            except Exception as e:
                print(f"Error sharing with {item['email']}: {e}")
                results.append({'email': item['email'], 'status': 'error', 'error': str(e)})
        return results
