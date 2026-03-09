"""Tests for region-aware box style normalization (NBX-* → BX1-*)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from processor.box_normalizer import (
    is_in_box_region,
    normalize_box_styles,
    stamp_in_box_region,
)


# ---------------------------------------------------------------------------
# Allowed-style set used across tests.  Contains the BX1 targets we expect
# the normalizer to remap into, plus a few non-BX1 styles.
# ---------------------------------------------------------------------------
BX1_STYLES = {
    "BX1-TTL", "BX1-TYPE",
    "BX1-TXT", "BX1-TXT-DC", "BX1-TXT-FIRST", "BX1-TXT-FLUSH",
    "BX1-H1", "BX1-H2", "BX1-H3", "BX1-L1",
    "BX1-BL-FIRST", "BX1-BL-MID", "BX1-BL-LAST", "BX1-BL2-MID",
    "BX1-NL-FIRST", "BX1-NL-MID", "BX1-NL-LAST",
    "BX1-UL-FIRST", "BX1-UL-MID", "BX1-UL-LAST",
    "BX1-MCUL-FIRST", "BX1-MCUL-MID", "BX1-MCUL-LAST",
    "BX1-OUT1-FIRST", "BX1-OUT1-MID", "BX1-OUT2", "BX1-OUT2-LAST", "BX1-OUT3",
    "BX1-EQ-FIRST", "BX1-EQ-MID", "BX1-EQ-LAST", "BX1-EQ-ONLY",
    "BX1-EXT-ONLY", "BX1-FN", "BX1-QUO", "BX1-QUO-AU", "BX1-SRC",
    # Non-box styles (should never appear as a remapping target)
    "TXT", "TXT-FLUSH", "H1", "PMI",
}


def _block(pid, text="Box content", zone="BOX_NBX", **extra_meta):
    meta = {"context_zone": zone}
    meta.update(extra_meta)
    return {"id": pid, "text": text, "metadata": meta}


def _clf(pid, tag, conf=0.85):
    return {"id": pid, "tag": tag, "confidence": conf}


# ===================================================================
# is_in_box_region
# ===================================================================

class TestIsInBoxRegion:
    def test_box_nbx(self):
        assert is_in_box_region({"context_zone": "BOX_NBX"}) is True

    def test_box_bx1(self):
        assert is_in_box_region({"context_zone": "BOX_BX1"}) is True

    def test_box_bx2(self):
        assert is_in_box_region({"context_zone": "BOX_BX2"}) is True

    def test_box_bx4(self):
        assert is_in_box_region({"context_zone": "BOX_BX4"}) is True

    def test_body(self):
        assert is_in_box_region({"context_zone": "BODY"}) is False

    def test_front_matter(self):
        assert is_in_box_region({"context_zone": "FRONT_MATTER"}) is False

    def test_table(self):
        assert is_in_box_region({"context_zone": "TABLE"}) is False

    def test_empty_meta(self):
        assert is_in_box_region({}) is False


# ===================================================================
# stamp_in_box_region
# ===================================================================

class TestStampInBoxRegion:
    def test_stamps_true(self):
        blocks = [_block(1, zone="BOX_NBX")]
        stamp_in_box_region(blocks)
        assert blocks[0]["metadata"]["in_box_region"] is True

    def test_stamps_false(self):
        blocks = [_block(1, zone="BODY")]
        stamp_in_box_region(blocks)
        assert blocks[0]["metadata"]["in_box_region"] is False

    def test_mixed(self):
        blocks = [_block(1, zone="BODY"), _block(2, zone="BOX_BX1")]
        stamp_in_box_region(blocks)
        assert blocks[0]["metadata"]["in_box_region"] is False
        assert blocks[1]["metadata"]["in_box_region"] is True


# ===================================================================
# Explicit mapping rules
# ===================================================================

class TestExplicitMappings:
    """Verify the three explicit rules from the requirements."""

    def test_nbx_h1_to_bx1_h1(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-H1")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-H1"

    def test_nbx_txt_to_bx1_txt_flush(self):
        """NBX-TXT has a special override → BX1-TXT-FLUSH (not BX1-TXT)."""
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-TXT")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-TXT-FLUSH"

    def test_nbx1_eq_first_to_bx1_eq_first(self):
        """NBX1-EQ-FIRST → BX1-EQ-FIRST (NBX1 prefix variant)."""
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX1-EQ-FIRST")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-EQ-FIRST"


# ===================================================================
# List variant remapping (generic prefix swap)
# ===================================================================

class TestListVariants:
    """Any NBX* list variant → BX1* equivalent."""

    def test_nbx_bl_first(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-BL-FIRST")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-BL-FIRST"

    def test_nbx_bl_mid(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-BL-MID")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-BL-MID"

    def test_nbx_bl_last(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-BL-LAST")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-BL-LAST"

    def test_nbx_nl_first(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-NL-FIRST")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-NL-FIRST"

    def test_nbx_nl_mid(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-NL-MID")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-NL-MID"

    def test_nbx_nl_last(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-NL-LAST")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-NL-LAST"

    def test_nbx_ul_first(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-UL-FIRST")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-UL-FIRST"

    def test_nbx_ul_mid(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-UL-MID")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-UL-MID"

    def test_nbx_ul_last(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-UL-LAST")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-UL-LAST"

    def test_nbx_bl2_mid(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-BL2-MID")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-BL2-MID"

    def test_nbx1_bl_mid(self):
        """NBX1 list variant also remaps."""
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX1-BL-MID")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-BL-MID"

    def test_nbx1_nl_first(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX1-NL-FIRST")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-NL-FIRST"


# ===================================================================
# Other NBX styles
# ===================================================================

class TestOtherNBXStyles:
    def test_nbx_ttl(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-TTL")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-TTL"

    def test_nbx_type(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-TYPE")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-TYPE"

    def test_nbx_txt_first(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-TXT-FIRST")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-TXT-FIRST"

    def test_nbx_txt_dc(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-TXT-DC")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-TXT-DC"

    def test_nbx_h2(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-H2")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-H2"

    def test_nbx_h3(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-H3")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-H3"

    def test_nbx_eq_only(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-EQ-ONLY")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-EQ-ONLY"

    def test_nbx_src(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-SRC")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-SRC"

    def test_nbx_fn(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-FN")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-FN"

    def test_nbx_h4_clamps_to_bx1_h3(self):
        """NBX-H4 has explicit override → BX1-H3 (no BX1-H4 exists)."""
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-H4")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-H3"


# ===================================================================
# in_box_region=True invariant: NBX-* never survives
# ===================================================================

class TestNBXNeverSurvivesInBoxRegion:
    """When in_box_region=True and a BX1 equivalent exists, NBX-* is remapped."""

    NBX_TAGS_WITH_BX1_EQUIVALENT = [
        "NBX-TTL", "NBX-TYPE", "NBX-TXT", "NBX-TXT-DC", "NBX-TXT-FIRST",
        "NBX-H1", "NBX-H2", "NBX-H3", "NBX-H4", "NBX-L1",
        "NBX-BL-FIRST", "NBX-BL-MID", "NBX-BL-LAST", "NBX-BL2-MID",
        "NBX-NL-FIRST", "NBX-NL-MID", "NBX-NL-LAST",
        "NBX-UL-FIRST", "NBX-UL-MID", "NBX-UL-LAST",
        "NBX-MCUL-FIRST", "NBX-MCUL-MID", "NBX-MCUL-LAST",
        "NBX-OUT1-FIRST", "NBX-OUT1-MID", "NBX-OUT2", "NBX-OUT2-LAST", "NBX-OUT3",
        "NBX-EQ-FIRST", "NBX-EQ-MID", "NBX-EQ-LAST", "NBX-EQ-ONLY",
        "NBX-EXT-ONLY", "NBX-FN", "NBX-QUO", "NBX-QUO-AU", "NBX-SRC",
    ]

    def test_no_nbx_survives(self):
        """Every NBX-* tag with a BX1 equivalent must be remapped."""
        for nbx_tag in self.NBX_TAGS_WITH_BX1_EQUIVALENT:
            blocks = [_block(1, zone="BOX_NBX")]
            clfs = [_clf(1, nbx_tag)]
            result = normalize_box_styles(blocks, clfs, BX1_STYLES)
            assert result[0]["tag"].startswith("BX1-"), (
                f"{nbx_tag} was not remapped: got {result[0]['tag']}"
            )

    def test_nbx1_variants_also_remapped(self):
        nbx1_tags = [
            "NBX1-BL-FIRST", "NBX1-BL-MID", "NBX1-BL-LAST",
            "NBX1-NL-FIRST", "NBX1-NL-MID", "NBX1-NL-LAST",
        ]
        for tag in nbx1_tags:
            blocks = [_block(1, zone="BOX_BX1")]
            clfs = [_clf(1, tag)]
            result = normalize_box_styles(blocks, clfs, BX1_STYLES)
            assert result[0]["tag"].startswith("BX1-"), (
                f"{tag} was not remapped: got {result[0]['tag']}"
            )


# ===================================================================
# Non-box paragraphs are NOT affected
# ===================================================================

class TestNonBoxUnchanged:
    def test_body_nbx_unchanged(self):
        """NBX-TXT in BODY zone must NOT be remapped."""
        blocks = [_block(1, zone="BODY")]
        clfs = [_clf(1, "NBX-TXT")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "NBX-TXT"

    def test_front_matter_unchanged(self):
        blocks = [_block(1, zone="FRONT_MATTER")]
        clfs = [_clf(1, "NBX-H1")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "NBX-H1"

    def test_table_zone_unchanged(self):
        blocks = [_block(1, zone="TABLE")]
        clfs = [_clf(1, "NBX-BL-MID")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "NBX-BL-MID"


# ===================================================================
# Non-NBX styles in box regions are NOT affected
# ===================================================================

class TestNonNBXInBoxUnchanged:
    def test_bx2_preserved(self):
        blocks = [_block(1, zone="BOX_BX2")]
        clfs = [_clf(1, "BX2-TXT")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX2-TXT"

    def test_pmi_preserved(self):
        blocks = [_block(1, zone="BOX_NBX")]
        clfs = [_clf(1, "PMI")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "PMI"

    def test_txt_preserved(self):
        blocks = [_block(1, zone="BOX_NBX")]
        clfs = [_clf(1, "TXT")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "TXT"


# ===================================================================
# Target missing from allowed set → no remapping
# ===================================================================

class TestMissingTarget:
    def test_no_bx1_styles_available(self):
        """If allowed_styles has no BX1 entries, nothing changes."""
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-H1")]
        result = normalize_box_styles(blocks, clfs, {"TXT", "H1", "PMI"})
        assert result[0]["tag"] == "NBX-H1"

    def test_nbx_dia_no_bx1_equivalent(self):
        """NBX-DIA has no BX1-DIA in BX1_STYLES → stays as-is."""
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-DIA")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "NBX-DIA"


# ===================================================================
# Repair metadata
# ===================================================================

class TestRepairMetadata:
    def test_repair_reason_set(self):
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-H1")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["repaired"] is True
        assert "box-region-normalize" in result[0]["repair_reason"]

    def test_existing_repair_reason_preserved(self):
        blocks = [_block(1)]
        clfs = [{"id": 1, "tag": "NBX-H1", "confidence": 0.85, "repair_reason": "heading-hierarchy"}]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert "heading-hierarchy" in result[0]["repair_reason"]
        assert "box-region-normalize" in result[0]["repair_reason"]

    def test_unchanged_entry_not_marked_repaired(self):
        blocks = [_block(1, zone="BODY")]
        clfs = [_clf(1, "TXT")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0].get("repaired") is not True


# ===================================================================
# Multi-block integration
# ===================================================================

# ===================================================================
# NBX-BL2/BL3 invalid-variant handling — no FN-* drift
# ===================================================================

class TestNBXBL2BL3InvalidVariants:
    """NBX-BL2-FIRST/LAST and NBX-BL3-* have no BX1 equivalents.
    box_normalizer must leave them unchanged (not map to FN-* or other
    unrelated families).  The classifier's alias layer converts them to
    NBX-BL2-MID before they reach this function; these tests verify the
    box_normalizer itself is safe if the raw invalid tag arrives directly."""

    def test_nbx_bl2_first_no_bx1_target_unchanged(self):
        """NBX-BL2-FIRST has no BX1-BL2-FIRST → stays NBX-BL2-FIRST (not FN-*)."""
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-BL2-FIRST")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "NBX-BL2-FIRST"
        assert not result[0]["tag"].startswith("FN-")

    def test_nbx_bl2_last_no_bx1_target_unchanged(self):
        """NBX-BL2-LAST has no BX1-BL2-LAST → stays NBX-BL2-LAST (not FN-*)."""
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-BL2-LAST")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "NBX-BL2-LAST"
        assert not result[0]["tag"].startswith("FN-")

    def test_nbx_bl3_first_no_bx1_target_unchanged(self):
        """NBX-BL3-FIRST has no BX1-BL3-FIRST → unchanged (not FN-BL-FIRST)."""
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-BL3-FIRST")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "NBX-BL3-FIRST"
        assert result[0]["tag"] != "FN-BL-FIRST"

    def test_nbx_bl3_mid_no_bx1_target_unchanged(self):
        """NBX-BL3-MID has no BX1-BL3-MID → unchanged (not FN-BL-MID)."""
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-BL3-MID")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "NBX-BL3-MID"
        assert result[0]["tag"] != "FN-BL-MID"

    def test_nbx_bl3_last_no_bx1_target_unchanged(self):
        """NBX-BL3-LAST has no BX1-BL3-LAST → unchanged (not FN-BL-LAST)."""
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-BL3-LAST")]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "NBX-BL3-LAST"
        assert result[0]["tag"] != "FN-BL-LAST"

    def test_nbx_bl2_mid_after_alias_maps_to_bx1_bl2_mid(self):
        """After classifier alias maps NBX-BL2-FIRST → NBX-BL2-MID, box_normalizer
        correctly remaps NBX-BL2-MID → BX1-BL2-MID."""
        blocks = [_block(1)]
        clfs = [_clf(1, "NBX-BL2-MID")]   # alias already applied by classifier
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-BL2-MID"


class TestMultiBlock:
    def test_mixed_pipeline(self):
        blocks = [
            _block(1, zone="BOX_NBX"),      # box region
            _block(2, zone="BOX_NBX"),      # box region
            _block(3, zone="BODY"),          # not box
            _block(4, zone="BOX_BX1"),      # box region
            _block(5, zone="BOX_NBX"),      # box region, PMI
        ]
        clfs = [
            _clf(1, "NBX-TTL"),
            _clf(2, "NBX-BL-MID"),
            _clf(3, "NBX-H1"),              # in BODY → no change
            _clf(4, "NBX-NL-FIRST"),        # in BOX_BX1 → remap
            _clf(5, "PMI"),                  # PMI stays
        ]
        result = normalize_box_styles(blocks, clfs, BX1_STYLES)
        assert result[0]["tag"] == "BX1-TTL"
        assert result[1]["tag"] == "BX1-BL-MID"
        assert result[2]["tag"] == "NBX-H1"       # BODY → unchanged
        assert result[3]["tag"] == "BX1-NL-FIRST"
        assert result[4]["tag"] == "PMI"            # not NBX prefix
