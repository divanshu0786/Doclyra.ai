import re
from datetime import datetime


# =========================================================
# PATTERNS
# =========================================================

PAN_PATTERN = re.compile(
    r"^[A-Z]{5}[0-9]{4}[A-Z]$"
)

AADHAAR_PATTERN = re.compile(
    r"^[0-9]{12}$"
)


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
            datetime.strptime(
                date_value,
                date_format,
            )

            return True

        except ValueError:
            pass

    return False


# =========================================================
# PAN VALIDATION
# =========================================================

def validate_pan(data: dict):

    errors = []

    # -----------------------------
    # PAN NUMBER
    # -----------------------------

    pan_number = str(
        data.get("pan_number", "")
    ).strip().upper()

    if not pan_number:

        errors.append(
            "PAN number is missing."
        )

    elif not PAN_PATTERN.fullmatch(
        pan_number
    ):

        errors.append(
            "PAN number does not match the expected format."
        )

    # -----------------------------
    # NAME
    # -----------------------------

    name = str(
        data.get("name", "")
    ).strip()

    if not name:

        errors.append(
            "Name is missing."
        )

    # -----------------------------
    # DATE OF BIRTH
    # -----------------------------

    date_of_birth = str(
        data.get("date_of_birth", "")
    ).strip()

    if not date_of_birth:

        errors.append(
            "Date of birth is missing."
        )

    elif not is_valid_date(
        date_of_birth
    ):

        errors.append(
            "Date of birth is not in a valid format."
        )

    # -----------------------------
    # RESULT
    # -----------------------------

    if errors:

        return {
            "valid": False,
            "status": "MANUAL_REVIEW",
            "errors": errors,
        }

    return {
        "valid": True,
        "status": "VALID",
        "errors": [],
    }


# =========================================================
# AADHAAR VALIDATION
# =========================================================

def validate_aadhaar(data: dict):

    errors = []

    # -----------------------------
    # AADHAAR NUMBER
    # -----------------------------

    aadhaar_number = str(
        data.get("aadhaar_number") or ""
    ).strip()

    # Remove spaces/hyphens just in case
    aadhaar_number = (
        aadhaar_number
        .replace(" ", "")
        .replace("-", "")
    )

    if not aadhaar_number:

        errors.append(
            "Aadhaar number is missing."
        )

    elif not AADHAAR_PATTERN.fullmatch(
        aadhaar_number
    ):

        errors.append(
            "Aadhaar number must contain exactly 12 digits."
        )

    # -----------------------------
    # NAME
    # -----------------------------

    name = str(
        data.get("name") or ""
    ).strip()

    if not name:

        errors.append(
            "Name is missing."
        )

    # -----------------------------
    # DATE OF BIRTH
    # -----------------------------

    date_of_birth = str(
        data.get("date_of_birth") or ""
    ).strip()

    if date_of_birth.lower() in {
        "null",
        "none",
    }:

        date_of_birth = ""

    if date_of_birth:

        if not is_valid_date(
            date_of_birth
        ):

            errors.append(
                "Date of birth is not in a valid format."
            )

    # -----------------------------
    # YEAR OF BIRTH
    # -----------------------------

    year_of_birth = str(
        data.get("year_of_birth") or ""
    ).strip()

    if year_of_birth.lower() in {
        "null",
        "none",
    }:

        year_of_birth = ""

    if year_of_birth:

        if not re.fullmatch(
            r"^(19|20)[0-9]{2}$",
            year_of_birth,
        ):

            errors.append(
                "Year of birth is not valid."
            )

    # -----------------------------
    # DOB OR YEAR REQUIRED
    # -----------------------------

    if not date_of_birth and not year_of_birth:

        errors.append(
            "Date of birth or year of birth is missing."
        )

    # -----------------------------
    # GENDER
    # -----------------------------

    gender = str(
        data.get("gender") or ""
    ).strip().upper()

    if gender.lower() in {
        "null",
        "none",
    }:

        gender = ""

    if not gender:

        errors.append(
            "Gender is missing."
        )

    elif gender not in {
        "MALE",
        "FEMALE",
        "TRANSGENDER",
        "OTHER",
    }:

        errors.append(
            "Gender is not valid."
        )

    # -----------------------------
    # RESULT
    # -----------------------------

    if errors:

        return {
            "valid": False,
            "status": "MANUAL_REVIEW",
            "errors": errors,
        }

    return {
        "valid": True,
        "status": "VALID",
        "errors": [],
    }
# =========================================================
# RENT AGREEMENT VALIDATION
# =========================================================

def validate_rent_agreement(data: dict):

    errors = []

    # -----------------------------
    # TENANT NAME
    # -----------------------------

    tenant_name = str(
        data.get("tenant_name") or ""
    ).strip()

    if not tenant_name:
        errors.append(
            "Tenant name is missing."
        )

    # -----------------------------
    # LANDLORD NAME
    # -----------------------------

    landlord_name = str(
        data.get("landlord_name") or ""
    ).strip()

    if not landlord_name:
        errors.append(
            "Landlord name is missing."
        )

    # -----------------------------
    # PROPERTY ADDRESS
    # -----------------------------

    property_address = str(
        data.get("property_address") or ""
    ).strip()

    if not property_address:
        errors.append(
            "Property address is missing."
        )

    # -----------------------------
    # RENT AMOUNT
    # -----------------------------

    rent_amount = str(
        data.get("rent_amount") or ""
    ).strip()

    if not rent_amount:
        errors.append(
            "Rent amount is missing."
        )

    # -----------------------------
    # SECURITY DEPOSIT
    # -----------------------------

    security_deposit = str(
        data.get("security_deposit") or ""
    ).strip()

    if not security_deposit:
        errors.append(
            "Security deposit is missing."
        )

    # -----------------------------
    # START DATE
    # -----------------------------

    start_date = str(
        data.get("start_date") or ""
    ).strip()

    if not start_date:

        errors.append(
            "Agreement start date is missing."
        )

    elif not is_valid_date(start_date):

        errors.append(
            "Agreement start date is not in a valid format."
        )

    # -----------------------------
    # END DATE
    # -----------------------------

    end_date = str(
        data.get("end_date") or ""
    ).strip()

    if not end_date:

        errors.append(
            "Agreement end date is missing."
        )

    elif not is_valid_date(end_date):

        errors.append(
            "Agreement end date is not in a valid format."
        )

    # -----------------------------
    # RESULT
    # -----------------------------

    if errors:

        return {
            "valid": False,
            "status": "MANUAL_REVIEW",
            "errors": errors,
        }

    return {
        "valid": True,
        "status": "VALID",
        "errors": [],
    }