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
    "UNKNOWN",
}


def classify_document(
    file_path: str,
    mime_type: str,
):
    """
    Classify a tenant document using Gemini.

    Returns:
        A document type string on successful classification.

    Raises:
        RuntimeError when Gemini is unavailable,
        quota is exceeded, or classification fails.
    """

    with open(file_path, "rb") as file:
        file_data = file.read()

    prompt = """
You are a document classification system for a tenant onboarding service.

Classify the provided document into exactly ONE of these categories:

AADHAAR
PAN
RENT_AGREEMENT
UNKNOWN

Rules:

- AADHAAR means an Indian Aadhaar identity document.
- PAN means an Indian Permanent Account Number card/document.
- RENT_AGREEMENT means a rental or lease agreement.
- UNKNOWN means the document cannot be confidently identified.

Return ONLY one of these exact values:

AADHAAR
PAN
RENT_AGREEMENT
UNKNOWN

Do not explain your answer.
Do not add punctuation.
"""

    max_attempts = 3

    for attempt in range(
        1,
        max_attempts + 1,
    ):

        print(
            f"Gemini classification attempt "
            f"{attempt}/{max_attempts}"
        )

        try:

            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=[
                    types.Part.from_text(
                        text=prompt
                    ),
                    types.Part.from_bytes(
                        data=file_data,
                        mime_type=mime_type,
                    ),
                ],
            )

            raw_result = (
                response.text or ""
            ).strip()

            print(
                "Gemini raw response:",
                repr(raw_result),
            )

            result = raw_result.upper()

            if result not in ALLOWED_TYPES:
                print(
                    "Gemini returned an "
                    "invalid classification."
                )

                return "UNKNOWN"

            return result

        except Exception as e:

            error_text = str(e)

            print(
                "Gemini classification error:",
                error_text,
            )

            # -----------------------------------------
            # Quota / rate limit
            # -----------------------------------------

            if (
                "429" in error_text
                or "RESOURCE_EXHAUSTED"
                in error_text
                or "quota" in error_text.lower()
            ):

                raise RuntimeError(
                    "Gemini API quota exceeded. "
                    "Please try again later or "
                    "check your Gemini API quota."
                ) from e

            # -----------------------------------------
            # Temporary server failure
            # -----------------------------------------

            if (
                "503" in error_text
                or "UNAVAILABLE"
                in error_text
            ):

                if attempt < max_attempts:
                    time.sleep(2)
                    continue

                raise RuntimeError(
                    "Gemini API is temporarily "
                    "unavailable. Please try again."
                ) from e

            # -----------------------------------------
            # Other API errors
            # -----------------------------------------

            raise RuntimeError(
                "Gemini document classification failed."
            ) from e

    raise RuntimeError(
        "Gemini document classification failed "
        "after multiple attempts."
    )