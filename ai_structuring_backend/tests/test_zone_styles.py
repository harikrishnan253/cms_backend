"""
Tests for zone_styles.py - zone-to-styles mapping and lookups.
"""

import pytest
from backend.processor.zone_styles import get_allowed_styles_for_zone, ZONE_VALID_STYLES


class TestGetAllowedStylesForZone:
    def test_body_zone_unrestricted(self):
        """BODY zone returns full allowed_styles set (unrestricted)."""
        allowed = {"TXT", "H1", "H2", "REF-N", "T1", "BL-MID"}
        result = get_allowed_styles_for_zone("BODY", allowed)
        assert result == allowed

    def test_body_zone_empty_allowed(self):
        """BODY zone with empty allowed_styles returns empty set."""
        result = get_allowed_styles_for_zone("BODY", set())
        assert result == set()

    def test_table_zone_restricted(self):
        """TABLE zone returns only table-valid styles."""
        allowed = {"T", "T1", "TH1", "TFN", "TSN", "TXT", "H1", "REF-N", "BL-MID"}
        result = get_allowed_styles_for_zone("TABLE", allowed)
        # Should only include table-valid styles
        assert "T" in result
        assert "T1" in result
        assert "TH1" in result
        assert "TFN" in result
        assert "TSN" in result
        # Should NOT include non-table styles
        assert "TXT" not in result  # TXT not valid in TABLE
        assert "H1" not in result   # H1 not valid in TABLE
        assert "REF-N" not in result  # REF-N not valid in TABLE
        assert "BL-MID" not in result  # BL-MID not valid in TABLE

    def test_metadata_zone_restricted(self):
        """METADATA zone returns minimal set (PMI, ChapterAuthor, etc.)."""
        allowed = {"PMI", "ChapterAuthor", "ChapterNumber", "TXT", "H1", "REF-N"}
        result = get_allowed_styles_for_zone("METADATA", allowed)
        # Should only include metadata-valid styles
        assert "PMI" in result
        assert "ChapterAuthor" in result
        assert "ChapterNumber" in result
        # Should NOT include non-metadata styles
        assert "TXT" not in result
        assert "H1" not in result  # H1 not in METADATA zone list
        assert "REF-N" not in result

    def test_box_zone_variants(self):
        """BOX_NBX, BOX_BX1, etc. return box-specific styles."""
        allowed = {"NBX-TTL", "NBX-TXT", "BX1-TTL", "BX1-TXT", "TXT", "H1", "PMI"}

        # BOX_NBX
        nbx_result = get_allowed_styles_for_zone("BOX_NBX", allowed)
        assert "NBX-TTL" in nbx_result
        assert "NBX-TXT" in nbx_result
        assert "PMI" in nbx_result  # PMI valid in all box zones
        assert "BX1-TTL" not in nbx_result  # BX1 styles not in NBX zone
        assert "TXT" not in nbx_result  # TXT not valid in BOX_NBX

        # BOX_BX1
        bx1_result = get_allowed_styles_for_zone("BOX_BX1", allowed)
        assert "BX1-TTL" in bx1_result
        assert "BX1-TXT" in bx1_result
        assert "PMI" in bx1_result
        assert "NBX-TTL" not in bx1_result  # NBX styles not in BX1 zone

    def test_back_matter_zone(self):
        """BACK_MATTER returns reference/EOC/appendix styles."""
        allowed = {
            "REF-N", "REF-U", "REFH1", "EOC-H1", "EOC-NL-MID",
            "APX-TXT", "FIG-LEG", "TSN", "TXT", "H1", "BL-MID"
        }
        result = get_allowed_styles_for_zone("BACK_MATTER", allowed)
        # Should include back matter styles
        assert "REF-N" in result
        assert "REF-U" in result
        assert "REFH1" in result
        assert "EOC-H1" in result
        assert "EOC-NL-MID" in result
        assert "APX-TXT" in result
        assert "FIG-LEG" in result
        assert "TSN" in result
        # Should NOT include body-only styles
        assert "TXT" not in result  # TXT not in BACK_MATTER zone list
        assert "BL-MID" not in result

    def test_unknown_zone_returns_allowed_styles(self):
        """Unknown zone falls back to global allowed set."""
        allowed = {"TXT", "H1", "PMI"}
        result = get_allowed_styles_for_zone("UNKNOWN_ZONE", allowed)
        assert result == allowed

    def test_none_allowed_styles_returns_zone_set(self):
        """If allowed_styles=None, return raw zone set."""
        result = get_allowed_styles_for_zone("TABLE", None)
        # Should return the raw TABLE zone set
        assert "T" in result
        assert "T1" in result
        assert "TH1" in result
        assert "TFN" in result
        assert isinstance(result, set)

    def test_intersection_with_allowed_styles(self):
        """Zone styles filtered by global allowed_styles."""
        # Only a subset of TABLE styles are allowed globally
        allowed = {"T", "T1", "FAKE-TAG", "TXT"}  # T and T1 valid for TABLE, others not
        result = get_allowed_styles_for_zone("TABLE", allowed)
        # Should only return T and T1 (intersection of zone + allowed)
        assert result == {"T", "T1"}

    def test_front_matter_zone(self):
        """FRONT_MATTER returns chapter opener and objectives styles."""
        allowed = {
            "CN", "CT", "OBJ-BL-MID", "OBJ-NL-FIRST", "KT-TXT",
            "TXT", "H2", "REF-N", "PMI"
        }
        result = get_allowed_styles_for_zone("FRONT_MATTER", allowed)
        # Should include front matter styles
        assert "CN" in result
        assert "CT" in result
        assert "OBJ-BL-MID" in result
        assert "OBJ-NL-FIRST" in result
        assert "KT-TXT" in result
        assert "PMI" in result
        assert "TXT" in result
        assert "H2" in result
        # Should NOT include reference-only styles
        assert "REF-N" not in result

    def test_exercise_zone(self):
        """EXERCISE returns exercise/workbook styles."""
        allowed = {
            "EXER-H1", "EXER-TTL", "EXER-MC-NL-MID", "EXER-SA-NL-FIRST",
            "TXT", "H1", "PMI"
        }
        result = get_allowed_styles_for_zone("EXERCISE", allowed)
        # Should include exercise styles
        assert "EXER-H1" in result
        assert "EXER-TTL" in result
        assert "EXER-MC-NL-MID" in result
        assert "EXER-SA-NL-FIRST" in result
        assert "PMI" in result  # PMI in EXERCISE zone
        # Should NOT include non-exercise styles
        assert "TXT" not in result
        assert "H1" not in result

    def test_allowed_styles_as_list(self):
        """get_allowed_styles_for_zone() accepts list and converts to set."""
        allowed_list = ["T", "T1", "TH1", "TFN"]
        result = get_allowed_styles_for_zone("TABLE", allowed_list)
        assert isinstance(result, set)
        assert "T" in result
        assert "T1" in result

    def test_zone_valid_styles_dict_structure(self):
        """ZONE_VALID_STYLES dict has expected structure."""
        # Check that all zones are present
        assert "METADATA" in ZONE_VALID_STYLES
        assert "FRONT_MATTER" in ZONE_VALID_STYLES
        assert "TABLE" in ZONE_VALID_STYLES
        assert "BODY" in ZONE_VALID_STYLES
        assert "BACK_MATTER" in ZONE_VALID_STYLES
        assert "EXERCISE" in ZONE_VALID_STYLES
        # BOX zones
        assert "BOX_NBX" in ZONE_VALID_STYLES
        assert "BOX_BX1" in ZONE_VALID_STYLES
        assert "BOX_BX2" in ZONE_VALID_STYLES

        # BODY should be None (unrestricted)
        assert ZONE_VALID_STYLES["BODY"] is None

        # All other zones should be sets
        for zone, styles in ZONE_VALID_STYLES.items():
            if zone != "BODY":
                assert isinstance(styles, set), f"{zone} should be a set"

    def test_pmi_in_most_zones(self):
        """PMI should be valid in most zones (not in TABLE though)."""
        zones_with_pmi = ["METADATA", "FRONT_MATTER", "BOX_NBX", "BOX_BX1", "BOX_BX2",
                          "BOX_BX3", "BOX_BX4", "BACK_MATTER", "EXERCISE"]
        for zone in zones_with_pmi:
            zone_styles = ZONE_VALID_STYLES[zone]
            assert "PMI" in zone_styles, f"PMI should be in {zone}"

        # TABLE zone does NOT have PMI
        assert "PMI" not in ZONE_VALID_STYLES["TABLE"]


class TestZoneStyleSingleSource:
    """Verify ingestion reuses zone_styles as its canonical source."""

    def test_ingestion_imports_canonical_zone_styles(self):
        """ingestion.py should import the canonical zone map from zone_styles.py."""
        import inspect
        import backend.processor.ingestion as ingestion_mod

        source = inspect.getsource(ingestion_mod)
        assert "from .zone_styles import ZONE_VALID_STYLES as ZONE_VALID_STYLES_SET" in source
        assert "for zone, styles in ZONE_VALID_STYLES_SET.items()" in source

    def test_same_zone_keys(self):
        """ingestion and zone_styles must expose the same zone keys."""
        from backend.processor.ingestion import ZONE_VALID_STYLES as ingestion_zvs
        from backend.processor.zone_styles import ZONE_VALID_STYLES as zs_zvs

        ingestion_keys = set(ingestion_zvs.keys())
        zs_keys = set(zs_zvs.keys())

        only_in_ingestion = ingestion_keys - zs_keys
        only_in_zone_styles = zs_keys - ingestion_keys

        assert only_in_ingestion == set(), (
            f"Zones in ingestion.py but missing from zone_styles.py: {only_in_ingestion}"
        )
        assert only_in_zone_styles == set(), (
            f"Zones in zone_styles.py but missing from ingestion.py: {only_in_zone_styles}"
        )

    def test_body_zone_both_none(self):
        """BODY zone must stay unrestricted in both files."""
        from backend.processor.ingestion import ZONE_VALID_STYLES as ingestion_zvs
        from backend.processor.zone_styles import ZONE_VALID_STYLES as zs_zvs

        assert ingestion_zvs["BODY"] is None, "ingestion.py BODY must be None"
        assert zs_zvs["BODY"] is None, "zone_styles.py BODY must be None"

    def test_zone_style_contents_match(self):
        """For every non-BODY zone, style values must stay equivalent."""
        from backend.processor.ingestion import ZONE_VALID_STYLES as ingestion_zvs
        from backend.processor.zone_styles import ZONE_VALID_STYLES as zs_zvs

        for zone in ingestion_zvs:
            if zone == "BODY":
                continue

            ingestion_set = set(ingestion_zvs[zone]) if ingestion_zvs[zone] else set()
            zs_set = set(zs_zvs[zone]) if zs_zvs[zone] else set()

            only_in_ingestion = ingestion_set - zs_set
            only_in_zone_styles = zs_set - ingestion_set

            assert only_in_ingestion == set(), (
                f"Zone '{zone}': styles in ingestion.py but missing from zone_styles.py: "
                f"{sorted(only_in_ingestion)}"
            )
            assert only_in_zone_styles == set(), (
                f"Zone '{zone}': styles in zone_styles.py but missing from ingestion.py: "
                f"{sorted(only_in_zone_styles)}"
            )
