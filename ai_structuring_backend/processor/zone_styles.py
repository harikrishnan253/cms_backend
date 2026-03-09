"""
Centralized zone-to-styles mapping for style validation and enforcement.

This module provides a single source of truth for which paragraph styles are
valid in each document zone (METADATA, FRONT_MATTER, BODY, TABLE, BOX_*, BACK_MATTER, EXERCISE).
"""

from typing import Iterable

# Zone-to-styles mapping extracted from ingestion.py ZONE_VALID_STYLES
# Converted to sets for efficient membership checking
ZONE_VALID_STYLES = {
    # METADATA: Pure pre-press info before chapter opener
    'METADATA': {
        'PMI',
        # Author/title info that appears before chapter
        'ChapterAuthor', 'ChapterNumber', 'ChapterTitle', 'ChapterTitleFootnote',
        # Special headings for abstract, keywords
        'SP-Heading2', 'SpeacialHeading2', 'SpecialHeading2',
        # Paragraph styles
        'Para-FL', 'ParaFirstLine-Ind',
        # Markers
        'H2', 'Normal',
    },

    # FRONT_MATTER: Chapter opener through objectives (before first H1)
    'FRONT_MATTER': {
        # Chapter opener (Official WK Template)
        'CN', 'CT', 'CST', 'CAU', 'CW', 'CHAP', 'COQ', 'COQA',
        'ChapterNumber', 'ChapterTitle', 'ChapterAuthor',
        'Chapter-Epigraph', 'Chapter-EpigraphSource', 'EPIGRAPH',
        # Part openers (Official WK Template)
        'PART', 'PN', 'PT', 'PST', 'PAU', 'PTXT', 'PTXT-DC',
        'POC', 'POC-FIRST', 'POUT-1', 'POUT-2', 'POUTH1', 'PQUOTE', 'POS',
        # Unit openers (Official WK Template)
        'UNIT', 'UN', 'UT', 'UST', 'UAU', 'UTXT',
        'UOC', 'UOC-FIRST', 'UOUT-1', 'UOUT-2', 'UOUTH1', 'UQUOTE', 'UOS',
        # Section openers (Official WK Template)
        'SECTION', 'SN', 'ST', 'SST', 'SAU', 'STXT', 'STXT-DC',
        'SOC', 'SOC-FIRST', 'SOUT-1', 'SOUT-2', 'SOUTH1', 'SQUOTE', 'SOS',
        'SOUT-NL-FIRST', 'SOUT-NL-MID',
        # Objectives - Bulleted (Official WK Template)
        'OBJ1', 'OBJ-TXT', 'OBJ-TXT-FLUSH',
        'OBJ-BL-FIRST', 'OBJ-BL-MID', 'OBJ-BL-LAST',
        # Objectives - Numbered (Official WK Template)
        'OBJ-NL-FIRST', 'OBJ-NL-MID', 'OBJ-NL-LAST', 'OBJ_NL',
        # Objectives - Unnumbered (Official WK Template)
        'OBJ-UL-FIRST', 'OBJ-UL-MID', 'OBJ-UL-LAST',
        # Chapter outline (Official WK Template)
        'COUT-1', 'COUT-2', 'COUT-3', 'COUT1', 'COUT2',
        'COUT-1-TXT', 'COUT-1-H1', 'COUTH1',
        'COUT-BL', 'COUT-NL-FIRST', 'COUT-NL-MID',
        # Key Terms (Official WK Template)
        'KT1', 'KT-TXT',
        'KT-BL-FIRST', 'KT-BL-MID', 'KT-BL-LAST',
        'KT-NL-FIRST', 'KT-NL-MID', 'KT-NL-LAST',
        'KT-UL-FIRST', 'KT-UL-MID', 'KT-UL-LAST',
        # Compact objectives (Training data)
        'COBJ', 'COBJ_T', 'COBJ_TXL',
        # Learning objectives alternatives (Training data)
        'LearningObj-BulletList1', 'LearningObj-BulletList1_first',
        'LearningObj-BulletList1_last', 'LearningObj-BulletList1-last',
        'LearningObj-Para-FL', 'LearnObjHeading',
        # Objectives alternatives (Training data)
        'ObjectiveHead', 'ObjectivesHeading', 'Objectives-Para-FL',
        'ObjectiveNumberList', 'ObjectiveNumberList-First', 'ObjectiveNumberList-Last',
        'ObjectivesNumberlist1', 'ObjectivesNumberlist1_first', 'ObjectivesNumberlist1_last',
        # Special intro elements
        'H1A', 'SP-H1', 'TXT-DC', 'TXT-FLUSH', 'TXT', 'KEYNOTE', 'INTRO',
        'H2', 'H3',
        # Case study in intro
        'CS-TTL', 'CS-TXT-FLUSH', 'CS-TXT', 'CS-H1',
        'CS-QUES-TXT', 'CS-ANS-TXT',
        # Domain title (Training data)
        'DOM-TTL',
        # Markers
        'PMI', 'Normal',
    },

    # TABLE: Word table content
    'TABLE': {
        # Basic table cells (Official WK Template)
        'T', 'T-DIR', 'TD',
        'T1', 'T11', 'T12',
        'T2', 'T2-C', 'T21', 'T22', 'T23',
        'T3', 'T4', 'T5', 'T6',
        # Table headings (normalized)
        'TH1', 'TH2', 'TH3', 'TH4', 'TH5', 'TH6',
        # Table bullets (Official WK Template + Training)
        'TBL', 'TBL-FIRST', 'TBL-MID', 'TBL-MID0', 'TBL-LAST', 'TBL-LAST1',
        'TBL2-MID', 'TBL3-MID', 'TBL4-MID',
        # Table numbered lists (Official WK Template)
        'TNL-FIRST', 'TNL-MID',
        # Table unnumbered lists (Official WK Template + Training)
        'TUL', 'TUL-FIRST', 'TUL-MID', 'TUL-LAST',
        # Table footnotes and sources (Official WK Template)
        'TFN', 'TFN1', 'TFN-FIRST', 'TFN-MID', 'TFN-LAST',
        'TFN-BL-FIRST', 'TFN-BL-MID', 'TFN-BL-LAST',
        'TSN',
        # Table math (Official WK Template)
        'TMATH',
        # Unnumbered tables (Official WK Template)
        'UNT', 'UNT-TTL', 'UNT-T1', 'UNT-T2', 'UNT-T3',
        'UNT-BL', 'UNT-BL-MID',
        'UNT-NL-FIRST', 'UNT-NL-MID',
        'UNT-UL', 'UNT-FN',
        # Unnumbered table in box (Official WK Template)
        'UNBX-TT', 'UNBX-T', 'UNBX-T2', 'UNBX-BL', 'UNBX-NL', 'UNBX-UL',
        # Alternative table styles (Training data)
        'TB', 'TB-BulletList1', 'TB-NumberList1', 'TB-AlphaList1',
        'TT',           # Table title alternate (publisher-specific, e.g. ENA)
        'TCH1', 'TCH',  # Table column-header alternates (publisher-specific)
        'TableBody', 'TableCaption', 'TableCaptions', 'TableColumnHead1',
        'TableFootnote', 'TableList', 'TableNote', 'TableSource',
        'Exhibit-TableBody', 'Exhibit-TableColumnHead1', 'Exhibit-TB-BulletList1',
        'Exhibit-TableFootnote', 'ExhibitTitle',
        # Clinical judgment in tables (Training data)
        'CJC-UL-FIRST', 'CJC-UL-LAST', 'CJC-UL-MID',
        'CJC-NN-BL-LAST',
        'CJC-UNT', 'CJC-UNBX-T', 'CJC-UNBX-T2',
        # Box content in tables
        'NBX1-UNT', 'NBX1-UNT-T2',
    },

    # BOX_NBX: Informational boxes (NOTE, TIP, etc.)
    'BOX_NBX': {
        # Structure (Official WK Template)
        'NBX-TTL', 'NBX-TYPE', 'NBX-TXT', 'NBX-TXT-DC', 'NBX-TXT-FIRST', 'NBX-TXT-FLUSH',
        'NBX-FN', 'NBX-QUO',
        # Headings (Official WK Template)
        'NBX-H1', 'NBX-H2', 'NBX-H3', 'NBX-L1',
        # Bulleted lists (Official WK Template)
        'NBX-BL-FIRST', 'NBX-BL-MID', 'NBX-BL-LAST', 'NBX-BL2-MID',
        # Numbered lists (Official WK Template)
        'NBX-NL-FIRST', 'NBX-NL-MID', 'NBX-NL-LAST',
        # Unnumbered lists (Official WK Template)
        'NBX-UL-FIRST', 'NBX-UL-MID', 'NBX-UL-LAST',
        # Multi-column lists (Official WK Template)
        'NBX-MCUL-FIRST', 'NBX-MCUL-MID', 'NBX-MCUL-LAST',
        # Outline lists (Official WK Template)
        'NBX-OUT1-FIRST', 'NBX-OUT1-MID', 'NBX-OUT2', 'NBX-OUT2-LAST', 'NBX-OUT3',
        # Equations (Official WK Template)
        'NBX-EQ-FIRST', 'NBX-EQ-MID', 'NBX-EQ-LAST', 'NBX-EQ-ONLY',
        # Extracts (Official WK Template)
        'NBX-EXT-ONLY',
        # Dialogue (Training data)
        'NBX-DIA', 'NBX-DIA-FIRST', 'NBX-DIA-MID', 'NBX-DIA-LAST',
        # Table/source in box
        'NBX-UNT', 'NBX-UNT-T2', 'NBX-SRC',
        # NBX1 variants - Edwards template (Training data)
        'NBX1-TTL', 'NBX1-TXT', 'NBX1-TXT-FIRST', 'NBX1-TXT-FLUSH',
        'NBX1-BL-FIRST', 'NBX1-BL-MID', 'NBX1-BL-LAST', 'NBX1-BL2-MID',
        'NBX1-NL-FIRST', 'NBX1-NL-MID', 'NBX1-NL-LAST',
        'NBX1-DIA-FIRST', 'NBX1-DIA-MID', 'NBX1-DIA-LAST',
        'NBX1-UNT', 'NBX1-UNT-T2', 'NBX1-SRC',
        # Box-01 variants - Wheeler template (Training data)
        'Box-01-BoxTitle', 'Box-01-BulletList1', 'Box-01-BulletList1_first', 'Box-01-BulletList1_last',
        'Box-01-NumberList1', 'Box-01-ParaFirstLine-Ind', 'Box-01-Para-FL',
        'Box-01-Head1',
        'Box-01-UN-TableBody', 'Box-01-UN-TableCaption', 'Box-01-UN-TableColumnHead1', 'Box-01-UN-TableFootnote',
        # Markers
        'PMI',
    },

    # BOX_BX1: Clinical/practical boxes (CLINICAL PEARL, EXAMPLE, TIP)
    'BOX_BX1': {
        # Structure (Official WK Template)
        'BX1-TTL', 'BX1-TYPE', 'BX1-TXT', 'BX1-TXT-DC', 'BX1-TXT-FIRST', 'BX1-TXT-FLUSH',
        'BX1-FN', 'BX1-QUO',
        # Headings (Official WK Template)
        'BX1-H1', 'BX1-H2', 'BX1-H3', 'BX1-L1',
        # Bulleted lists (Official WK Template)
        'BX1-BL-FIRST', 'BX1-BL-MID', 'BX1-BL-LAST', 'BX1-BL2-MID',
        # Numbered lists (Official WK Template)
        'BX1-NL-FIRST', 'BX1-NL-MID', 'BX1-NL-LAST',
        # Unnumbered lists (Official WK Template)
        'BX1-UL-FIRST', 'BX1-UL-MID', 'BX1-UL-LAST',
        # Multi-column lists (Official WK Template)
        'BX1-MCUL-FIRST', 'BX1-MCUL-MID', 'BX1-MCUL-LAST',
        # Outline lists (Official WK Template)
        'BX1-OUT1-FIRST', 'BX1-OUT1-MID', 'BX1-OUT2', 'BX1-OUT2-LAST', 'BX1-OUT3',
        # Equations (Official WK Template)
        'BX1-EQ-FIRST', 'BX1-EQ-MID', 'BX1-EQ-LAST', 'BX1-EQ-ONLY',
        # Extracts (Official WK Template)
        'BX1-EXT-ONLY',
        # Questions in box (Training data)
        'BX1-QUES-TXT',
        # Markers
        'PMI',
    },

    # BOX_BX2: Warning boxes (RED FLAG, WARNING, ALERT)
    'BOX_BX2': {
        'BX2-TTL', 'BX2-TYPE', 'BX2-TXT', 'BX2-TXT-FIRST', 'BX2-TXT-FLUSH', 'BX2-TXT-LAST',
        'BX2-H1',
        'BX2-BL-FIRST', 'BX2-BL-MID', 'BX2-BL-LAST',
        'BX2-NL-FIRST', 'BX2-NL-MID', 'BX2-NL-LAST',
        'PMI',
    },

    # BOX_BX3: Reflection/discussion boxes
    'BOX_BX3': {
        'BX3-TTL', 'BX3-TYPE', 'BX3-TXT', 'BX3-TXT-FIRST', 'BX3-TXT-FLUSH',
        'BX3-BL-FIRST', 'BX3-BL-MID', 'BX3-BL-LAST',
        'BX3-NL-FIRST', 'BX3-NL-MID', 'BX3-NL-LAST',
        'BX3_BL', 'BX3_BLF', 'BX3_BLL',
        'PMI',
    },

    # BOX_BX4: Procedure/Case study boxes
    'BOX_BX4': {
        'BX4-TTL', 'BX4-TYPE', 'BX4-TXT', 'BX4-TXT-FIRST', 'BX4-TXT-FLUSH',
        'BX4-H1', 'BX4-H2',
        'BX4-BL-MID', 'BX4-BL2-MID',
        'BX4-NL-MID', 'BX4-LL2-MID',
        # Case study styles
        'CS-H1', 'CS-TTL', 'CS-TXT', 'CS-TXT-FLUSH',
        'CS-QUES-TXT', 'CS-ANS-TXT',
        'CaseStudy-UL-FL1', 'CaseStudy-Dialogue', 'CaseStudy-Heading1',
        'CaseStudy-ParaFirstLine-Ind', 'CaseStudy-BulletList1',
        'PMI',
    },

    # BOX_BX6: Resource boxes
    'BOX_BX6': {
        'BX6-TTL', 'BX6-TYPE', 'BX6-TXT', 'BX6-TXT-FIRST',
        'BX6-BL-MID',
        'PMI',
    },

    # BOX_BX7: Case study boxes
    'BOX_BX7': {
        'BX7-TTL', 'BX7-TYPE', 'BX7-TXT', 'BX7-TXT-FIRST',
        'BX7-BL-FIRST', 'BX7-BL-LAST',
        'BX7-NL-MID',
        'PMI',
    },

    # BOX_BX15: Special boxes
    'BOX_BX15': {
        'BX15-TTL', 'BX15-TYPE', 'BX15-TXT', 'BX15-TXT-FIRST',
        'BX15-H1',
        'PMI',
    },

    # BOX_BX16: Special boxes with unnumbered tables
    'BOX_BX16': {
        'BX16-TTL', 'BX16-TYPE',
        'BX16-UNT', 'BX16-UNT2', 'BX16-UNT-BL-MID',
        'PMI',
    },

    # BACK_MATTER: References, figures, end-of-chapter, appendix, glossary, index
    'BACK_MATTER': {
        # Reference headings (Official WK Template + Training)
        'REF-H1', 'REF-H2', 'REFH1', 'REFH2', 'REFH2a',
        'H1-REF', 'ReferencesHeading1',
        # Reference entries (Official WK Template + Training)
        'REF-N', 'REF-N-FIRST', 'REF-N0', 'REF', 'REF-U',
        'Reference-Alphabetical', 'ReferenceAlphabetical', 'Reference-Numbered',
        # Suggested readings (Official WK Template)
        'SR', 'SRH1', 'SRH2',
        # Bibliography (Official WK Template)
        'BIB', 'BIBH1', 'BIBH2',
        # Acknowledgments (Official WK Template)
        'ACK1', 'ACKTXT',
        # Web links (Official WK Template)
        'WEBTXT', 'WL1',
        # Figure elements
        'FIG-LEG', 'FIG-CRED', 'FIG-SRC', 'UNFIG', 'UNFIG-LEG', 'UNFIG-SRC',
        'FigureLegend', 'FigureCaption', 'FigureSource', 'FG-CAP',
        'FGC', 'FGS',  # Figure caption/source alternates (publisher-specific, e.g. ENA)
        # Table elements in back matter
        'T1', 'TFN', 'TSN',
        # Exhibit elements
        'ExhibitTitle', 'Exhibit-TableFootnote',
        # End of chapter headings (Training data)
        'EOC-H1', 'EOC-H2',
        # EOC numbered lists (Official WK Template + Training)
        'EOC-NL-FIRST', 'EOC-NL-MID', 'EOC-NL-LAST',
        'EOC_NL', 'EOC_NLF', 'EOC_NLLL',
        'EOC-NumberList1', 'EOC-NumberList1_first', 'EOC-NumberLis1t_first', 'EOC-NumberList1_last',
        # EOC bulleted lists (Training data)
        'EOC-BL-FIRST', 'EOC-BL-MID', 'EOC-BL-LAST',
        'EOC-BulletList1', 'EOC-BulletList1_first', 'EOC-BulletList1_last', 'EOC-BulletList2',
        # EOC lettered lists (Training data)
        'EOC-Lc-AlphaList2', 'EOC-LL2-MID',
        # EOC dialogue (Training data)
        'EOC-Dialogue', 'EOC-UL-FL1',
        # EOC text/other (Training data)
        'EOC-Para-FL', 'EOC-ParaFirstLine-Ind', 'EOC-EQ-ONLY',
        'EOC_REF',
        # Glossary (Official WK Template)
        'GLOS-UL-FIRST', 'GLOS-UL-MID',
        'GLOS-NL-FIRST', 'GLOS-NL-MID',
        'GLOS-BL-FIRST', 'GLOS-BL-MID',
        # Index (Official WK Template)
        'IDX-TXT', 'IDX-ALPHA', 'IDX-1', 'IDX-2', 'IDX-3',
        # Appendix (Official WK Template + Training)
        'APX', 'APXN', 'APXT', 'APXST', 'APXAU',
        'APXH1', 'APXH2', 'APXH3',
        'APX-TXT', 'APX-TXT-FLUSH', 'APX-REF-N',
        # TOC elements (Official WK Template)
        'TOC-FM', 'TOC-UN', 'TOC-UT', 'TOC-SN', 'TOC-ST',
        'TOC-CN', 'TOC-CT', 'TOC-CAU',
        'TOC-H1', 'TOC-H2', 'TOC-BM-FIRST', 'TOC-BM',
        # Backmatter (Official WK Template)
        'BM-TTL',
        # Markers
        'PMI', 'ParaFirstLine-Ind',
    },

    # EXERCISE: Exercise/workbook content (Official WK Template)
    'EXERCISE': {
        # Headers
        'EXER-H1', 'EXER-TTL', 'EXER-DIR',
        # True/False
        'EXER-TF-NL-FIRST', 'EXER-TF-NL-MID',
        # Multiple Choice
        'EXER-MC-NL-FIRST', 'EXER-MC-NL-MID', 'EXER-MC-NL2-FIRST', 'EXER-MC-NL2-MID',
        # Matching
        'EXER-M-NL-FIRST', 'EXER-M-NL-MID',
        # Fill Blank
        'EXER-FB-NL-FIRST', 'EXER-FB-NL-MID',
        # Short Answer
        'EXER-SA-NL-FIRST', 'EXER-SA-NL-MID',
        # Abbreviations
        'EXER-AB-NL-FIRST', 'EXER-AB-NL-MID',
        # Word Parts
        'EXER-WP-NL-FIRST', 'EXER-WP-NL-MID', 'EXER-WP-L',
        # Word Build
        'EXER-WB-NL-FIRST', 'EXER-WB-NL-MID',
        # Spelling
        'EXER-SP-NL-FIRST', 'EXER-SP-NL-MID', 'EXER-SP-NL2-FIRST', 'EXER-SP-NL2-MID',
        # Define Term
        'EXER-DT-NL-FIRST', 'EXER-DT-NL-MID',
        # Analyze
        'EXER-AT-NL-FIRST', 'EXER-AT-NL-MID', 'EXER-AT-T2',
        # Case Study
        'EXER-CS-AU', 'EXER-CS-T', 'EXER-CS-T2', 'EXER-CS-NL-FIRST', 'EXER-CS-NL-MID',
        # Other
        'EXER-L-UL',
        'PMI',
    },

    # BODY has access to all styles (no restriction)
    'BODY': None,  # None means all styles allowed
}


def get_allowed_styles_for_zone(
    zone: str,
    allowed_styles: set[str] | Iterable[str] | None = None
) -> set[str]:
    """
    Returns the set of styles valid for a given zone.

    Args:
        zone: Zone identifier (BODY, TABLE, FRONT_MATTER, BACK_MATTER, BOX_NBX, etc.)
        allowed_styles: Global allowed styles set (optional filter). If provided,
                       returns the intersection of zone styles and global allowed styles.

    Returns:
        Set of style tags valid for the zone. BODY zone returns all allowed_styles (unrestricted).
        Unknown zones fall back to the global allowed_styles set (or empty set if None).

    Examples:
        >>> get_allowed_styles_for_zone('TABLE')
        {'T', 'T1', 'TH1', 'TFN', 'TSN', ...}

        >>> get_allowed_styles_for_zone('BODY', {'TXT', 'H1', 'REF-N'})
        {'TXT', 'H1', 'REF-N'}  # BODY is unrestricted

        >>> get_allowed_styles_for_zone('TABLE', {'T', 'T1', 'REF-N'})
        {'T', 'T1'}  # REF-N not valid in TABLE zone
    """
    # Convert allowed_styles to set if provided as iterable
    if allowed_styles is not None and not isinstance(allowed_styles, set):
        allowed_styles = set(allowed_styles)

    # Get zone-specific valid styles
    zone_styles = ZONE_VALID_STYLES.get(zone)

    # BODY zone: unrestricted (all styles allowed)
    if zone == 'BODY':
        return allowed_styles if allowed_styles is not None else set()

    # Unknown zone: fall back to global allowed_styles
    if zone_styles is None:
        return allowed_styles if allowed_styles is not None else set()

    # Zone has specific style restrictions
    if allowed_styles is None:
        # Return raw zone styles if no global filter
        return zone_styles

    # Return intersection: styles that are both zone-valid AND globally allowed
    return zone_styles & allowed_styles
