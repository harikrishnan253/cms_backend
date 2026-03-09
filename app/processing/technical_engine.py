import os
import shutil
# Check if module exists, assuming yes based on previous listing
from app.processing.legacy.highlighter.core_highlighter_docx import process_docx

class TechnicalEngine:
    def process_document(self, file_path: str) -> list[str]:
        """
        Runs Technical Editing (Highlighting) on the document.
        Generates a new file with technical highlights.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        folder = os.path.dirname(file_path)
        base = os.path.splitext(os.path.basename(file_path))[0]
        output_filename = f"{base}_TechnicallyEdited.docx"
        output_path = os.path.join(folder, output_filename)
        
        try:
            # Run the legacy highlighter logic
            process_docx(file_path, output_path, skip_validation=True)
            
            if os.path.exists(output_path):
                return [output_path]
            else:
                raise RuntimeError("Technical processing failed to generate output file.")
                
        except Exception as e:
            print(f"Technical Engine Error: {e}")
            raise e
