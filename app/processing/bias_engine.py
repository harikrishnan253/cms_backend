import os
from app.processing.legacy import bias_scanner

class BiasEngine:
    def process_document(self, file_path: str) -> list[str]:
        """
        Runs the bias scanning logic on a document.
        Returns the generated files (DOCX, Excel, and a ZIP bundle).
        """
        generated_files = []
        folder = os.path.dirname(file_path)
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        # Paths
        legacy_dir = os.path.join(os.path.dirname(__file__), 'legacy')
        csv_path = os.path.join(legacy_dir, 'bias_terms.csv')
        
        # Load terms
        term_map, categories = bias_scanner.load_bias_terms(csv_path)
        if not term_map:
            raise ValueError(f"Bias terms could not be loaded from {csv_path}")
            
        # Scan DOCX
        output_dir = os.path.join(folder, "bias_output")
        os.makedirs(output_dir, exist_ok=True)
        
        highlighted_docx, report_rows = bias_scanner.scan_docx(file_path, term_map, output_dir)
        if highlighted_docx and os.path.exists(highlighted_docx):
            generated_files.append(highlighted_docx)
        
        # Generate Excel
        excel_path = os.path.join(output_dir, f"{base_name}_BiasReport.xlsx")
        bias_scanner.write_excel(report_rows, excel_path)
        if os.path.exists(excel_path):
            generated_files.append(excel_path)
        
        # Generate ZIP bundle
        zip_path = os.path.join(folder, f"{base_name}_BiasScan.zip")
        bias_scanner.create_zip(output_dir, excel_path, zip_path)
        if os.path.exists(zip_path):
            generated_files.append(zip_path)
        
        # Cleanup temporary PDF if LibreOffice was used
        bias_scanner.cleanup_pdf_files()
        
        return generated_files
