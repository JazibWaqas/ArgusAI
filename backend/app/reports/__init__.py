"""Isolated report export helpers (PDF, etc.). Does not import pipeline or detectors."""

from .pdf_official import build_official_forensic_pdf

__all__ = ["build_official_forensic_pdf"]
