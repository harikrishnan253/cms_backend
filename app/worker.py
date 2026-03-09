from app.core.celery_app import celery_app
from docx import Document
import lxml.etree as ET
import os

@celery_app.task(acks_late=True)
def process_document(file_path: str, project_id: int):
    """
    Background task to process uploaded docx files.
    Demonstrates python-docx and lxml usage.
    """
    try:
        if not os.path.exists(file_path):
            return {"status": "failed", "error": "File not found"}

        # 1. Read DOCX
        doc = Document(file_path)
        
        # 2. Extract Metadata (Mocking complex logic)
        word_count = sum(len(p.text.split()) for p in doc.paragraphs)
        
        # 3. XML Processing (Mocking JATS/BITS generation)
        # In a real scenario, this would convert docx content to XML
        root = ET.Element("article")
        meta = ET.SubElement(root, "front")
        ET.SubElement(meta, "word-count").text = str(word_count)
        
        xml_content = ET.tostring(root, pretty_print=True).decode()
        
        # Return result (in production, save this to DB)
        return {
            "status": "completed", 
            "project_id": project_id, 
            "word_count": word_count,
            "preview_xml": xml_content
        }
    except Exception as e:
        return {"status": "failed", "error": str(e)}
