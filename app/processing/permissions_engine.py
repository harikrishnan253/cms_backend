import os
from app.processing.legacy.extractor import extract_from_file, write_permission_log

class PermissionsEngine:
    def process_document(self, file_path: str) -> list[str]:
        """
        Extracts permission/credit lines and writes them to an Excel log.
        Returns list of generated file paths.
        """
        results = extract_from_file(file_path)
        
        if not results:
            # We raise error or just return empty?
            # User snippet raised Exception("No permissions found")
            raise ValueError("No permissions/credits found in document")
            
        folder = os.path.dirname(file_path)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        excel_filename = f"{base_name}_PermissionsLog.xlsx"
        excel_path = os.path.join(folder, excel_filename)
        
        write_permission_log(results, excel_path)
        
        return [excel_path]
