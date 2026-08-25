import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

ALLOWED_TYPES = {
    "AADHAAR",
    "PAN",
    "RENT_AGREEMENT",
    "PASSPORT_PHOTO",
    "UNKNOWN",
}


def classify_document(
    file_path: str,
    mime_type: str,
) -> str:
    """
    Classify a tenant document using Gemini.
    """
    with open(file_path, "rb") as file:
        file_data = file.read()

    prompt = """
You are a document classification system for a tenant onboarding service.

Classify the provided document into exactly ONE of these categories:

AADHAAR
PAN
RENT_AGREEMENT
PASSPORT_PHOTO
UNKNOWN

Rules:

- AADHAAR means an Indian Aadhaar identity document (card or letter).
- PAN means an Indian Permanent Account Number card/document.
- RENT_AGREEMENT means a rental or lease agreement document.
- PASSPORT_PHOTO means a passport-size portrait photo of a person (headshot/selfie).
- UNKNOWN means the document cannot be confidently identified.

Return ONLY one of these exact values:

AADHAAR
PAN
RENT_AGREEMENT
PASSPORT_PHOTO
UNKNOWN

Do not explain your answer.
Do not add punctuation.
"""

    models = ["gemini-3.7-flash", "gemini-3.1-flash-lite-preview", "gemini-3.5-flash"]

    for model_name in models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=types.Content(
                    parts=[
                        types.Part.from_text(text=prompt),
                        types.Part.from_bytes(
                            data=file_data,
                            mime_type=mime_type,
                        ),
                    ]
                ),
            )

            raw_result = (response.text or "").strip().upper()
            print(f"Gemini ({model_name}) response: '{raw_result}'")

            for doc_type in ALLOWED_TYPES:
                if doc_type in raw_result:
                    return doc_type

            return "UNKNOWN"

        except Exception as e:
            print(f"Gemini {model_name} failed: {e}")
            continue

    raise RuntimeError("All Gemini models temporarily unavailable. Please try again.")