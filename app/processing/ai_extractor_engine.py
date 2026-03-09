import os
from app.processing.legacy.extractor_ai import extract_from_file_ai
from app.processing.legacy.extractor import write_permission_log

class AIExtractorEngine:
    def process_document(self, file_path: str) -> list[str]:
        """
        Extracts permission/credit lines using Gemini AI and writes them to an Excel log.
        Returns list of generated file paths.
        """
        results = extract_from_file_ai(file_path)
        
        if not results:
            raise ValueError("No permissions/credits found in document via AI")
            
        folder = os.path.dirname(file_path)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        excel_filename = f"{base_name}_AIPermissionsLog.xlsx"
        excel_path = os.path.join(folder, excel_filename)
        
        write_permission_log(results, excel_path)
        
        return [excel_path]
