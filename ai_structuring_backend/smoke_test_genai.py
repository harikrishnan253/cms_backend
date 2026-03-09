"""
Quick smoke test for google.genai SDK integration.

Usage:
    python backend/smoke_test_genai.py
"""

from __future__ import annotations

import os
import sys

from google import genai
from google.genai import types


def main() -> int:
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        print("ERROR: GOOGLE_API_KEY is not set.")
        return 1

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=[
            types.Content(
                role="user",
                parts=[types.Part(text="Reply with exactly: OK")],
            )
        ],
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=16,
        ),
    )

    text = (response.text or "").strip()
    print(text)
    return 0 if text else 2


if __name__ == "__main__":
    raise SystemExit(main())

