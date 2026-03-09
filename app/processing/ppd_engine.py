
import os
import re
import json
import uuid
import datetime
import traceback
from pathlib import Path
from jinja2 import Template
import chardet
from typing import List, Optional

# Import the analysis logic from the legacy module
from app.processing.legacy.word_analyzer_docx import (
    CitationAnalyzer,
    extract_with_docx,
    remove_tags_keep_formatting_docx,
    generate_formatting_html,
    generate_multilingual_html,
    build_comments_html,
    build_export_highlight_html,
    build_detailed_summary_table,
    DASHBOARD_CSS,
    DASHBOARD_JS,
    HTML_WRAPPER,
    extract_with_word, # Kept for failover logic if desired, though legacy defines it as alias
    HAS_WIN32COM
)

def _now_utc():
    return datetime.datetime.now(datetime.timezone.utc)

def html_to_excel_no_images(html_path: str, output_dir: str) -> Optional[str]:
    """
    Converts an HTML file to an .xls file by removing <img> tags and writing
    the resulting HTML to a .xls file so Excel can open it.
    Returns the output file path or None on failure.
    """
    try:
        # read raw bytes and detect encoding
        with open(html_path, "rb") as f:
            raw_data = f.read()

        encoding = None
        try:
            detected = chardet.detect(raw_data)
            encoding = detected.get("encoding") or "utf-8"
        except Exception:
            encoding = "utf-8"

        try:
            html_content = raw_data.decode(encoding, errors="ignore")
        except Exception:
            html_content = raw_data.decode("utf-8", errors="ignore")

        # Remove <img> tags (handles attributes and self-closing)
        html_no_images = re.sub(r"<img\b[^>]*>", "", html_content, flags=re.IGNORECASE)

        # Also remove inline base64 images in style attributes (background-image:url(data:...))
        html_no_images = re.sub(r'url\(\s*data:[^)]+\)', 'url()', html_no_images, flags=re.IGNORECASE)

        # Build a safe output filename
        base = Path(html_path).stem
        # timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S') # The router handles versioning, we can stay simple
        output_file = os.path.join(output_dir, f"{base}.xls")

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html_no_images)

        return output_file
    except Exception as e:
        print(f"HTML to Excel conversion failed for {html_path}: {e}")
        return None

class PPDEngine:
    def __init__(self):
        pass

    def process_document(self, file_path: str, user_name: str = "Analyst") -> List[str]:
        """
        Runs the full PPD pipeline on a single document:
        1. Extract content & Comments
        2. Analyze Citations
        3. Remove Tags
        4. Generate HTML Dashboard
        5. Generate Excel Report
        
        Returns a list of generated file paths (including the modified doc itself if applicable).
        """
        generated_files = []
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            # 1. Extraction
            # We default to docx extraction (linux compatible logic as per user migration)
            paras, comments, imgs, foot, end = extract_with_docx(file_path)

            # 2. Tag Removal (Modifies DOCX in place)
            remove_tags_keep_formatting_docx(file_path)
            
            # 3. Analysis
            analyzer = CitationAnalyzer()
            doc_data = [(t, p, c) for (t, p, c, _) in paras]
            dtypes = analyzer.analyze_document_citations(doc_data)
            
            # Simple count from structure, heavily dependent on accuracy of dtypes
            table_count = len(dtypes.get("Table", {}).get("Caption", {}))

            # 4. Generate HTML Content Blocks
            fmt_html = generate_formatting_html(file_path, used_word=False)
            spec_html = generate_multilingual_html(file_path)
            com_html = build_comments_html(comments)
            summary_html = build_detailed_summary_table(
                dtypes, imgs, table_count, foot, end,
                fmt_html, spec_html, com_html
            )
            msr_html = analyzer.build_citation_tables_html(dtypes, os.path.basename(file_path))
            exp_html = build_export_highlight_html(paras)

            wc = sum(len(t.split()) for (t, _, _, _) in paras)
            
            # 5. Render Full Dashboard HTML
            template = Template(HTML_WRAPPER)
            html = template.render(
                doc_name=os.path.basename(file_path),
                pages=(len(paras) // 40) + 1,
                words=wc,
                ce_pages=(wc // 250) + 1,
                date=_now_utc().strftime("%d-%m-%Y"),
                analyst=user_name,
                detailed_summary=summary_html,
                msr_content=msr_html,
                fmt_content=fmt_html,
                spec_content=spec_html,
                comment_content=com_html,
                export_highlight=exp_html,
                images=imgs,
                footnotes=foot,
                endnotes=end,
                css=DASHBOARD_CSS,
                js=DASHBOARD_JS,
                logo_path="", # Can be added if needed
            )
            
            # Save HTML
            output_dir = os.path.dirname(file_path)
            base_name = Path(file_path).stem
            out_html = os.path.join(output_dir, f"{base_name}_MSS_Anaylsis_Dashboard.html")
            
            with open(out_html, "w", encoding="utf-8") as f:
                f.write(html)
            
            generated_files.append(out_html)
            
            # 6. Convert to Excel
            excel_output = html_to_excel_no_images(out_html, output_dir)
            if excel_output:
                generated_files.append(excel_output)
                
            return generated_files

        except Exception as e:
            print(f"PPD Processing failed for {file_path}: {e}")
            traceback.print_exc()
            raise e
