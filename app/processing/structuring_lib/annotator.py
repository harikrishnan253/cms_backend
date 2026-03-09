# annotator.py
"""
Document annotation module.
Identifies and tags document elements (headings, sections, lists, etc).
"""

import re
import logging
from typing import List, Dict, Any, Optional
from docx.document import Document
from docx.text.paragraph import Paragraph
from .rules_loader import get_rules_loader
from .logger_config import get_logger

logger = get_logger(__name__)
rules_loader = get_rules_loader()


# =========================
# Helpers
# =========================

def is_list_paragraph(paragraph: Paragraph) -> bool:
    """
    Detect if paragraph is a list item (has numbering or bullets).
    
    Args:
        paragraph: python-docx Paragraph object
    
    Returns:
        True if paragraph has list formatting
    """
    try:
        p = paragraph._p
        return p.pPr is not None and p.pPr.numPr is not None
    except Exception as e:
        logger.debug(f"Error checking list formatting: {e}")
        return False


def is_references_end(text: str) -> bool:
    """
    Detect end of references section.
    
    Args:
        text: Paragraph text to check
    
    Returns:
        True if text indicates end of references
    """
    if not text:
        return False
    
    text = text.strip()
    patterns = [
        r"^FIGURE\s+\d+",
        r"^Table\s+\d+",
        r"^Box\s+\d+",
        r"^[A-Z][A-Z\s]{3,}$",
    ]
    
    return any(re.match(pattern, text) for pattern in patterns)


# =========================
# Core annotator
# =========================

def annotate_document(doc: Document) -> List[Dict[str, Any]]:
    """
    Annotate all paragraphs in a document with tags and styles.
    
    Args:
        doc: python-docx Document object
    
    Returns:
        List of annotation dictionaries with keys:
        - para: Paragraph object
        - tag: String tag (e.g., "CHAPTER_TITLE", "BODY_TEXT")
        - style: Word style name (e.g., "Heading 1", "Normal")
    
    Raises:
        ValueError: If document is invalid
    """
    if not doc or not hasattr(doc, 'paragraphs'):
        raise ValueError("Invalid Document object")
    
    annotations: List[Dict[str, Any]] = []
    current_block: Optional[str] = None
    in_chapter_preamble: bool = False
    previous_tag: Optional[str] = None
    
    logger.info(f"Annotating document with {len(doc.paragraphs)} paragraphs")
    
    for para_idx, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        tag = "TXT"
        style = "TXT"
        
        try:
            if not text:
                annotations.append({"para": para, "tag": "EMPTY", "style": style})
                continue
            
            # ===== PRIORITY 0: EXPLICIT TAGS <TAG> =====
            explicit_match = re.match(r"^<([A-Z0-9-]+)>(.*)", text, re.DOTALL)
            explicit_tag_found = False
            
            if explicit_match:
                tag_name = explicit_match.group(1)
                content = explicit_match.group(2) # content after tag
                
                # Assign tag and style
                tag = tag_name
                style = tag_name
                
                # Remove tag from text (Clean up document)
                # Note: This removes run formatting on the line. 
                # If explicit tags are used, we assume style is driven by the tag, not manual runs.
                # User request: "don't removed <CN>,<CT>"
                # para.text = content
                text = content.strip() # Update text for block checks if needed
                
                explicit_tag_found = True
                logger.debug(f"Para {para_idx}: Found explicit tag <{tag}>")

            # ===== BLOCK START (Based on text match) =====
            block_markers = rules_loader.get_block_start_markers()
            # This logic below is for exact text matches from 'blocks: start_markers'
            if not explicit_tag_found and text in block_markers:
                current_block = block_markers[text]
                # Default behavior for block marker headings, can be overridden by regex rules below
                tag = current_block + "_HEADING"
                style = "H2" 
                logger.debug(f"Para {para_idx}: Detected block start: {current_block}")
            
            # ===== BLOCK END =====
            elif current_block == "REFERENCES_BLOCK" and is_references_end(text):
                current_block = None
                logger.debug(f"Para {para_idx}: References block ended")
            
            # ===== WORD LISTS =====
            if not explicit_tag_found and is_list_paragraph(para):
                if current_block == "LEARNING_OBJECTIVES_BLOCK":
                    tag = "OBJ-BL-MID"
                    style = "OBJ-BL-MID"
                elif current_block == "REFERENCES_BLOCK":
                    if re.match(r"(?:^\[\d+\]|^\d+\.)", text):
                        tag = "REF"
                        style = "REF"
                    else:
                        tag = "BODY_TEXT"
                        style = "TXT"
                else:
                    # Generic list detection
                    # Default assumption: NL-MID (commonly 'List Paragraph' is numbered)
                    tag = "NL-MID"
                    style = "NL-MID"
                    
                    style_name = para.style.name if para.style else ""
                    
                    # Check for indicators
                    if re.match(r"^\s*\d+[\.\)]", text):
                        # Manual numbering
                        tag = "NL-MID"
                    elif "Bullet" in style_name:
                        # Explicit Bullet style
                        tag = "BL-MID"
                        style = "BL-MID"
                    elif re.match(r"^[•\-\–]", text):
                        # Manual bullet char
                        tag = "BL-MID"
                        style = "BL-MID"
                    elif "Number" in style_name:
                        # Explicit Number style
                        tag = "NL-MID"
                    
                    # If matches nothing above, stays NL-MID (default)
            
            # ===== PARAGRAPH RULES =====
            else:
                rule_matched = explicit_tag_found # If we found explicit tag, we skip regex search
                
                # Priority 1: Force CT after CN
                # Only if not explicit (Explicit tags override strict sequencing if present)
                if not explicit_tag_found and previous_tag == "CN":
                    tag = "CT"
                    style = "CT"
                    rule_matched = True
                    logger.debug(f"Para {para_idx}: Forced CT due to previous CN")
                
                # Priority 2: Regex Rules
                if not rule_matched:
                    paragraph_rules = rules_loader.get_paragraphs()
                    for rule in paragraph_rules:
                        try:
                            if re.match(rule["pattern"], text):
                                tag = rule["tag"]
                                style = rule["style"]
                                rule_matched = True
                                
                                # Special Logic: Check if this matched rule is actually starting a block
                                if text in block_markers:
                                     current_block = block_markers[text]
                                     logger.debug(f"Para {para_idx}: Matched block start rule '{tag}', set block to {current_block}")

                                logger.debug(f"Para {para_idx}: Matched rule '{tag}'")
                                break
                        except re.error as e:
                            logger.error(f"Invalid regex in rule '{rule.get('tag', 'unknown')}': {e}")
                
                # ===== BLOCK RESET LOGIC (Moved out to run for ALL tags) =====
                # If we hit a new section heading, exit the current block
                # This now applies to Explicit Tags, Regex matches, or Forced tags
                if tag in ("H1", "H2", "H3", "H4", "CT", "CN", "OBJ1", "REFH1"):
                    is_current_block_starter = False
                    if current_block:
                        if text in block_markers and block_markers[text] == current_block:
                            is_current_block_starter = True
                    
                    if not is_current_block_starter:
                        current_block = None
                        logger.debug(f"Para {para_idx}: Block reset due to heading '{tag}'")

                # Priority 3: Block Context Text
                if not rule_matched and current_block:
                    # Map block names to shorter text tags if needed
                    if current_block == "LEARNING_OBJECTIVES_BLOCK":
                        tag = "OBJ-TXT"
                        style = "OBJ-TXT"
                    elif current_block == "REFERENCES_BLOCK":
                        tag = "REF-TXT"
                        style = "REF-TXT"
                    else:
                        tag = current_block + "_TXT"
                        style = tag
            
            # Priority 3.5: Epigraph Context Logic
            if tag in ("CN", "CT", "CAU"):
                in_chapter_preamble = True
            elif tag in ("H1", "H2", "H3", "OBJ1", "ABS"):
                in_chapter_preamble = False
            
            if in_chapter_preamble and tag in ("TXT", "EPI-ATT"): 
                # If we matched EPI-ATT via regex, keep it. 
                # If TXT, check heuristics.
                if tag == "TXT":
                    if text.startswith("“") or text.startswith('"'):
                        tag = "EPI"
                        style = "EPI"
                    elif re.match(r"^[—–-]", text):
                         tag = "EPI-ATT"
                         style = "EPI-ATT"
                    else:
                         # Default text in preamble (after Title/Author, before H1) is likely Epigraph
                         tag = "EPI"
                         style = "EPI"
            
            # Priority 4: TXT-FLUSH Logic
            if tag == "TXT" and previous_tag in ("H1", "H2", "H3"):
                tag = "TXT-FLUSH"
                style = "TXT-FLUSH"
                logger.debug(f"Para {para_idx}: Changed TXT to TXT-FLUSH (previous: {previous_tag})")

            # Update history
            if tag != "EMPTY":
                previous_tag = tag

            annotations.append({"para": para, "tag": tag, "style": style})
        
        except Exception as e:
            logger.error(f"Error annotating paragraph {para_idx}: {e}", exc_info=True)
            annotations.append({"para": para, "tag": "TXT", "style": "TXT"})
    
    logger.info(f"Document annotation complete: {len(annotations)} paragraphs annotated")
    return annotations

