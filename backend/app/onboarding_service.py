from sqlalchemy.orm import Session

from .models import Document, Onboarding


REQUIRED_DOCUMENTS = {
    "PAN",
    "AADHAAR",
    "RENT_AGREEMENT",
}


def get_onboarding_checklist(
    db: Session,
    onboarding_id: int,
):
    onboarding = db.get(
        Onboarding,
        onboarding_id,
    )

    if not onboarding:
        return {
            "onboarding_id": onboarding_id,
            "onboarding_status": "NOT_FOUND",
            "documents": {},
            "document_details": {},
        }

    documents = (
        db.query(Document)
        .filter(
            Document.onboarding_id == onboarding_id
        )
        .all()
    )

    document_statuses = {
        document_type: "MISSING"
        for document_type in REQUIRED_DOCUMENTS
    }

    document_details = {}

    for document in documents:
        document_type = str(
            document.document_type
        )

        # Ignore UNKNOWN documents for the checklist
        if document_type not in REQUIRED_DOCUMENTS:
            continue

        document_statuses[document_type] = str(
            document.status
        )

        document_details[document_type] = {
            "document_id": document.id,
            "filename": document.filename,
            "status": str(document.status),
            "extracted_data": document.extracted_data or {},
        }

    # -----------------------------------------------------
    # Determine onboarding status
    # -----------------------------------------------------

    statuses = list(document_statuses.values())

    # Any required document is still missing
    if any(
        status == "MISSING"
        for status in statuses
    ):
        onboarding.status = "IN_PROGRESS"

    # All required documents are approved
    elif all(
        status == "APPROVED"
        for status in statuses
    ):
        onboarding.status = "APPROVED"

    # Required documents exist, but one or more
    # still need human review
    else:
        onboarding.status = "PENDING_REVIEW"

    db.commit()
    db.refresh(onboarding)

    return {
        "onboarding_id": onboarding.id,
        "onboarding_status": str(
            onboarding.status
        ),
        "documents": document_statuses,
        "document_details": document_details,
    }