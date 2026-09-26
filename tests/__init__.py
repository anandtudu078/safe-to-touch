"""Pytest suite for the backend — no API key, no git required for most tests.

Tests are organised into three groups:
  1. checks.py  – unit tests for the 4 evidence checks using the baked-in demo repo
  2. schemas.py – pydantic model validation (round-trip, field constraints)
  3. main.py    – FastAPI endpoint contract (TestClient, no real Gemini calls)
"""
