import re
from datetime import datetime


# =========================================================
# PATTERNS
# =========================================================

PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
AADHAAR_PATTERN = re.compile(r"^[0-9]{12}$")


# =========================================================
# DATE VALIDATION
# =========================================================

def is_valid_date(date_value: str) -> bool:
    for date_format in (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
    ):
        try:
            datetime.strptime(date_value, date_format)
            return True
        except ValueError:
            pass
    return False


# =========================================================
# NAME MATCHING HELPER
# =========================================================

def is_name_matching(extracted_name: str, expected_name: str) -> bool:
    if not extracted_name or not expected_name:
        return False

    words_extracted = set(re.findall(r"[a-zA-Z]+", extracted_name.lower()))
    words_expected = set(re.findall(r"[a-zA-Z]+", expected_name.lower()))

    # Ignore generic titles
    titles = {"mr", "mrs", "ms", "dr", "shri", "smt"}
    sig_extracted = words_extracted - titles or words_extracted
    sig_expected = words_expected - titles or words_expected

    # Match if at least one meaningful name part overlaps (e.g. first name or last name)
    return bool(sig_extracted & sig_expected)


# =========================================================
# PAN VALIDATION
# =========================================================

def validate_pan(data: dict, expected_name: str | None = None) -> dict:
    errors = []

    # 1. PAN NUMBER
    pan_number = str(data.get("pan_number") or "").strip().upper()
    if not pan_number:
        errors.append("PAN card number could not be read.")
    elif not PAN_PATTERN.fullmatch(pan_number):
        errors.append("PAN card number is invalid (must be 5 letters, 4 digits, 1 letter like ABCDE1234F).")

    # 2. NAME ON CARD
    name = str(data.get("name") or "").strip()
    if not name:
        errors.append("Name is not clearly visible on the PAN card.")
    elif expected_name and not is_name_matching(name, expected_name):
        errors.append(
            f"Name mismatch: The PAN card belongs to '{name}', but the tenant is registered as '{expected_name}'."
        )

    # 3. DATE OF BIRTH
    date_of_birth = str(data.get("date_of_birth") or "").strip()
    if not date_of_birth:
        errors.append("Date of birth is missing or unreadable on the PAN card.")
    elif not is_valid_date(date_of_birth):
        errors.append("Date of birth on the PAN card is not in a recognized format.")

    if errors:
        return {
            "valid": False,
            "status": "MANUAL_REVIEW",
            "errors": errors,
            "error": " | ".join(errors),
        }

    return {
        "valid": True,
        "status": "VALID",
        "errors": [],
    }


# =========================================================
# AADHAAR VALIDATION
# =========================================================

def validate_aadhaar(data: dict, expected_name: str | None = None) -> dict:
    errors = []

    # 1. AADHAAR NUMBER
    aadhaar_number = str(data.get("aadhaar_number") or "").strip()
    aadhaar_number = aadhaar_number.replace(" ", "").replace("-", "")

    if not aadhaar_number:
        errors.append("Aadhaar number could not be read.")
    elif not AADHAAR_PATTERN.fullmatch(aadhaar_number):
        errors.append("Aadhaar number must contain exactly 12 numeric digits.")

    # 2. NAME ON CARD
    name = str(data.get("name") or "").strip()
    if not name:
        errors.append("Name is not clearly visible on the Aadhaar card.")
    elif expected_name and not is_name_matching(name, expected_name):
        errors.append(
            f"Name mismatch: The Aadhaar card belongs to '{name}', but the tenant is registered as '{expected_name}'."
        )

    # 3. DATE OF BIRTH / YEAR OF BIRTH
    date_of_birth = str(data.get("date_of_birth") or "").strip()
    if date_of_birth.lower() in {"null", "none"}:
        date_of_birth = ""

    if date_of_birth and not is_valid_date(date_of_birth):
        errors.append("Date of birth on Aadhaar is not in a valid format.")

    year_of_birth = str(data.get("year_of_birth") or "").strip()
    if year_of_birth.lower() in {"null", "none"}:
        year_of_birth = ""

    if year_of_birth and not re.fullmatch(r"^(19|20)[0-9]{2}$", year_of_birth):
        errors.append("Year of birth is invalid.")

    if not date_of_birth and not year_of_birth:
        errors.append("Date of birth / Year of birth is missing on Aadhaar card.")

    # 4. GENDER
    gender = str(data.get("gender") or "").strip().upper()
    if gender.lower() in {"null", "none"}:
        gender = ""

    if not gender:
        errors.append("Gender is missing on Aadhaar card.")
    elif gender not in {"MALE", "FEMALE", "TRANSGENDER", "OTHER"}:
        errors.append("Gender is invalid on Aadhaar card.")

    if errors:
        return {
            "valid": False,
            "status": "MANUAL_REVIEW",
            "errors": errors,
            "error": " | ".join(errors),
        }

    return {
        "valid": True,
        "status": "VALID",
        "errors": [],
    }


# =========================================================
# PASSPORT SIZE PHOTO VALIDATION
# =========================================================

def validate_passport_photo(inspection: dict) -> dict:
    errors = []
    quality = inspection.get("quality", "GOOD")
    quality_score = inspection.get("quality_score", 1.0)

    if quality != "GOOD" or quality_score < 0.6:
        errors.append("Passport photo is too blurry or low-resolution. Please send a clear headshot.")

    if errors:
        return {
            "valid": False,
            "status": "MANUAL_REVIEW",
            "errors": errors,
            "error": " | ".join(errors),
        }

    return {
        "valid": True,
        "status": "VALID",
        "errors": [],
    }


# =========================================================
# RENT AGREEMENT VALIDATION
# =========================================================

def validate_rent_agreement(data: dict, expected_name: str | None = None) -> dict:
    errors = []

    # 1. TENANT NAME
    tenant_name = str(data.get("tenant_name") or "").strip()
    if not tenant_name:
        errors.append("Tenant name is missing in the rent agreement.")
    elif expected_name and not is_name_matching(tenant_name, expected_name):
        errors.append(
            f"Name mismatch: Rent agreement lists '{tenant_name}', but onboarding is registered for '{expected_name}'."
        )

    # 2. LANDLORD NAME
    landlord_name = str(data.get("landlord_name") or "").strip()
    if not landlord_name:
        errors.append("Landlord / Owner name is missing in the agreement.")

    # 3. PROPERTY ADDRESS
    property_address = str(data.get("property_address") or "").strip()
    if not property_address:
        errors.append("Property premises address is missing in the agreement.")

    # 4. RENT AMOUNT
    rent_amount = str(data.get("rent_amount") or "").strip()
    if not rent_amount:
        errors.append("Monthly rent amount is missing.")

    # 5. SECURITY DEPOSIT
    security_deposit = str(data.get("security_deposit") or "").strip()
    if not security_deposit:
        errors.append("Security deposit amount is missing.")

    # 6. DATES
    start_date = str(data.get("start_date") or "").strip()
    if not start_date:
        errors.append("Lease start date is missing.")

    end_date = str(data.get("end_date") or "").strip()
    if not end_date:
        errors.append("Lease end date is missing.")

    if errors:
        return {
            "valid": False,
            "status": "MANUAL_REVIEW",
            "errors": errors,
            "error": " | ".join(errors),
        }

    return {
        "valid": True,
        "status": "VALID",
        "errors": [],
    }