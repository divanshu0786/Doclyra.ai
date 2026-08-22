from sqlalchemy.orm import Session

from .models import Document, Onboarding


REQUIRED_DOCUMENTS = {
    "PAN",
    "AADHAAR",
    "RENT_AGREEMENT",
}


def evaluate_onboarding_status(
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
            "status": "NOT_FOUND",
            "documents": {},
        }

    documents = (
        db.query(Document)
        .filter(
            Document.onboarding_id == onboarding_id
        )
        .all()
    )

    document_statuses = {}

    for document_type in REQUIRED_DOCUMENTS:

        matching_documents = [
            document
            for document in documents
            if document.document_type == document_type
        ]

        if not matching_documents:
            document_statuses[document_type] = "MISSING"
            continue

        latest_document = max(
            matching_documents,
            key=lambda document: document.created_at,
        )

        document_statuses[document_type] = (
            latest_document.status
        )

    # -----------------------------------------
    # Determine onboarding status
    # -----------------------------------------

    all_approved = all(
        document_statuses[document_type] == "APPROVED"
        for document_type in REQUIRED_DOCUMENTS
    )

    has_manual_review = any(
        document_statuses[document_type] == "MANUAL_REVIEW"
        for document_type in REQUIRED_DOCUMENTS
    )

    if all_approved:
        onboarding.status = "APPROVED"

    elif has_manual_review:
        onboarding.status = "PENDING_REVIEW"

    else:
        onboarding.status = "IN_PROGRESS"

    db.commit()
    db.refresh(onboarding)

    return {
        "onboarding_id": onboarding.id,
        "status": onboarding.status,
        "documents": document_statuses,
    }