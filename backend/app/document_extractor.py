import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types


load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


def extract_document_data(
    file_path: str,
    mime_type: str,
    document_type: str,
):
    """
    Extract structured information from a classified
    tenant document.

    Supported document types:

    - PAN
    - AADHAAR
    - RENT_AGREEMENT
    """

    with open(file_path, "rb") as file:
        file_data = file.read()

    # =========================================================
    # PAN
    # =========================================================

    if document_type == "PAN":

        fields = """
Extract exactly these fields:

- is_blurry
- blur_reason
- name
- pan_number
- date_of_birth

Field requirements:

is_blurry:
Set to true if the photo is out of focus, motion-blurred, blurry, has glare, or the text is illegible. Otherwise false.

blur_reason:
If is_blurry is true, provide a brief reason (e.g. "Text is blurry and out of focus"). Otherwise null.

name:
The full name printed on the PAN document.

pan_number:
The PAN number printed on the document.

date_of_birth:
The date of birth printed on the document.

Return null if a field cannot be confidently read.
"""

    # =========================================================
    # AADHAAR
    # =========================================================

    elif document_type == "AADHAAR":

        fields = """
Extract exactly these fields:

- is_blurry
- blur_reason
- name
- aadhaar_number
- date_of_birth
- year_of_birth
- gender

Field requirements:

is_blurry:
Set to true if the photo is out of focus, motion-blurred, blurry, has glare, or the text is illegible. Otherwise false.

blur_reason:
If is_blurry is true, provide a brief reason (e.g. "Text is blurry and out of focus"). Otherwise null.

name:
The person's full name printed on the Aadhaar document.

aadhaar_number:
The 12-digit Aadhaar number.
If spaces or hyphens appear between digits, remove them.

date_of_birth:
The complete date of birth if printed.

year_of_birth:
The year of birth if only the year is printed.

gender:
The gender printed on the document.

Do not invent a date of birth if only the year is visible.

Return null if a field cannot be confidently read.
"""

    # =========================================================
    # RENT AGREEMENT
    # =========================================================

    elif document_type == "RENT_AGREEMENT":

        fields = """
Extract exactly these fields:

- is_blurry
- blur_reason
- tenant_name
- landlord_name
- property_address
- rent_amount
- security_deposit
- start_date
- end_date

Field requirements:

is_blurry:
Set to true if the document page is out of focus, motion-blurred, blurry, or illegible. Otherwise false.

blur_reason:
If is_blurry is true, provide a brief reason (e.g. "Agreement text is blurry"). Otherwise null.

tenant_name:
The full name of the tenant/renter.

landlord_name:
The full name of the landlord/owner.

property_address:
The complete rental property address.

rent_amount:
The agreed monthly rent amount, if present.

security_deposit:
The security deposit amount, if present.

start_date:
The date on which the rental agreement begins.

end_date:
The date on which the rental agreement ends.

Do not guess dates or amounts.

Return null if a field cannot be confidently read.
"""

    else:
        return {}


    # =========================================================
    # PROMPT
    # =========================================================

    prompt = f"""
You are a document data extraction system
for a tenant onboarding service.

The document has already been classified as:

{document_type}

{fields}

IMPORTANT RULES:

1. Extract only information actually visible in the document.
2. Never guess or invent information.
3. Return valid JSON only.
4. Do not return markdown.
5. Do not add explanations.
6. Use null when a value cannot be confidently read.
7. Preserve names as they appear on the document.
8. Do not add fields that were not requested.
9. For numbers, return the value as text if necessary.
10. For dates, preserve the visible date format.
11. If an Aadhaar number contains spaces or hyphens,
    return only the digits.
12. Make sure the JSON is syntactically valid.

Return a JSON object with exactly the requested fields.
"""


    # =========================================================
    # GEMINI EXTRACTION
    # =========================================================

    models = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest", "gemini-3.1-flash-lite"]
    response = None

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
            break
        except Exception as e:
            print(f"Gemini extractor {model_name} failed: {e}")
            continue

    if not response:
        raise RuntimeError("All Gemini extraction models temporarily unavailable. Please try again.")


    # =========================================================
    # READ RESPONSE
    # =========================================================

    raw_result = (
        response.text or ""
    ).strip()

    print(
        "Gemini extraction response:",
        repr(raw_result),
    )


    # =========================================================
    # CLEAN GEMINI RESPONSE
    # =========================================================

    if raw_result.startswith("```"):

        raw_result = raw_result.replace(
            "```json",
            "",
        )

        raw_result = raw_result.replace(
            "```",
            "",
        )

        raw_result = raw_result.strip()


    # =========================================================
    # PARSE JSON
    # =========================================================

    try:

        result = json.loads(
            raw_result
        )

    except json.JSONDecodeError:

        print(
            "Gemini returned invalid JSON."
        )

        raise RuntimeError(
            "Gemini returned invalid JSON "
            "during document extraction."
        )


    # =========================================================
    # MAKE SURE RESULT IS A DICT
    # =========================================================

    if not isinstance(
        result,
        dict,
    ):

        raise RuntimeError(
            "Gemini extraction result was not "
            "a valid JSON object."
        )


    # =========================================================
    # NORMALIZE AADHAAR NUMBER
    # =========================================================

    if document_type == "AADHAAR":

        aadhaar_number = result.get(
            "aadhaar_number"
        )

        if aadhaar_number is not None:

            aadhaar_number = str(
                aadhaar_number
            )

            aadhaar_number = (
                aadhaar_number
                .replace(" ", "")
                .replace("-", "")
            )

            result["aadhaar_number"] = (
                aadhaar_number
            )


    # =========================================================
    # RETURN RESULT
    # =========================================================

    return result