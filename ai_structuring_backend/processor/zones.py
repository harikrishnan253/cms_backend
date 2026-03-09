"""Compatibility wrapper for zone detection utilities."""

from app.services.reference_zone import detect_reference_zone  # re-export

__all__ = ["detect_reference_zone"]
