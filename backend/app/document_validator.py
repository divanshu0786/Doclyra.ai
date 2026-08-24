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
        errors.append("PAN number is missing.")
    elif not PAN_PATTERN.fullmatch(pan_number):
        errors.append("PAN number does not match the expected format (e.g. ABCDE1234F).")

    # 2. NAME ON CARD
    name = str(data.get("name") or "").strip()
    if not name:
        errors.append("Name is missing on the PAN document.")
    elif expected_name and not is_name_matching(name, expected_name):
        errors.append(
            f"Name mismatch: Document belongs to '{name}', but onboarding is registered for '{expected_name}'."
        )

    # 3. DATE OF BIRTH
    date_of_birth = str(data.get("date_of_birth") or "").strip()
    if not date_of_birth:
        errors.append("Date of birth is missing.")
    elif not is_valid_date(date_of_birth):
        errors.append("Date of birth is not in a valid format.")

    if errors:
        return {
            "valid": False,
            "status": "MANUAL_REVIEW",
            "errors": errors,
            "error": "; ".join(errors),
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
        errors.append("Aadhaar number is missing.")
    elif not AADHAAR_PATTERN.fullmatch(aadhaar_number):
        errors.append("Aadhaar number must contain exactly 12 digits.")

    # 2. NAME ON CARD
    name = str(data.get("name") or "").strip()
    if not name:
        errors.append("Name is missing on the Aadhaar document.")
    elif expected_name and not is_name_matching(name, expected_name):
        errors.append(
            f"Name mismatch: Document belongs to '{name}', but onboarding is registered for '{expected_name}'."
        )

    # 3. DATE OF BIRTH / YEAR OF BIRTH
    date_of_birth = str(data.get("date_of_birth") or "").strip()
    if date_of_birth.lower() in {"null", "none"}:
        date_of_birth = ""

    if date_of_birth and not is_valid_date(date_of_birth):
        errors.append("Date of birth is not in a valid format.")

    year_of_birth = str(data.get("year_of_birth") or "").strip()
    if year_of_birth.lower() in {"null", "none"}:
        year_of_birth = ""

    if year_of_birth and not re.fullmatch(r"^(19|20)[0-9]{2}$", year_of_birth):
        errors.append("Year of birth is not valid.")

    if not date_of_birth and not year_of_birth:
        errors.append("Date of birth or year of birth is missing.")

    # 4. GENDER
    gender = str(data.get("gender") or "").strip().upper()
    if gender.lower() in {"null", "none"}:
        gender = ""

    if not gender:
        errors.append("Gender is missing.")
    elif gender not in {"MALE", "FEMALE", "TRANSGENDER", "OTHER"}:
        errors.append("Gender is not valid.")

    if errors:
        return {
            "valid": False,
            "status": "MANUAL_REVIEW",
            "errors": errors,
            "error": "; ".join(errors),
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
        errors.append("Tenant name is missing in the agreement.")
    elif expected_name and not is_name_matching(tenant_name, expected_name):
        errors.append(
            f"Name mismatch: Agreement lists '{tenant_name}', but onboarding is registered for '{expected_name}'."
        )

    # 2. LANDLORD NAME
    landlord_name = str(data.get("landlord_name") or "").strip()
    if not landlord_name:
        errors.append("Landlord name is missing in the agreement.")

    # 3. PROPERTY ADDRESS
    property_address = str(data.get("property_address") or "").strip()
    if not property_address:
        errors.append("Property address is missing.")

    # 4. RENT AMOUNT
    rent_amount = str(data.get("rent_amount") or "").strip()
    if not rent_amount:
        errors.append("Rent amount is missing.")

    # 5. SECURITY DEPOSIT
    security_deposit = str(data.get("security_deposit") or "").strip()
    if not security_deposit:
        errors.append("Security deposit is missing.")

    # 6. DATES
    start_date = str(data.get("start_date") or "").strip()
    if not start_date:
        errors.append("Agreement start date is missing.")

    end_date = str(data.get("end_date") or "").strip()
    if not end_date:
        errors.append("Agreement end date is missing.")

    if errors:
        return {
            "valid": False,
            "status": "MANUAL_REVIEW",
            "errors": errors,
            "error": "; ".join(errors),
        }

    return {
        "valid": True,
        "status": "VALID",
        "errors": [],
    }