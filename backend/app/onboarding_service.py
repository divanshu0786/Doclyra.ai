import os
from .notion_service import (
    get_onboarding_by_id,
    get_documents_by_onboarding,
    update_onboarding_status,
)

REQUIRED_DOCUMENTS = {
    "PAN",
    "AADHAAR",
    "RENT_AGREEMENT",
}


def get_onboarding_checklist(
    onboarding_id: int | str,
    db=None,  # optional param for backward compatibility
):
    notion_onboarding_id = os.getenv("NOTION_ONBOARDING_ID")
    notion_documents_id = os.getenv("NOTION_DOCUMENTS_ID")

    document_statuses = {
        doc_type: "MISSING" for doc_type in REQUIRED_DOCUMENTS
    }
    document_details = {}

    onboarding_page = None
    if notion_onboarding_id:
        try:
            onboarding_page = get_onboarding_by_id(notion_onboarding_id, onboarding_id)
        except Exception as e:
            print(f"Notion get_onboarding failed: {e}")

    # Query documents from Notion
    if notion_documents_id and onboarding_page:
        try:
            doc_pages = get_documents_by_onboarding(
                notion_documents_id,
                onboarding_page_id=onboarding_page.get("id"),
            )
            for page in doc_pages:
                props = page.get("properties", {})
                doc_type_raw = props.get("Document Type", {}).get("select", {}).get("name", "")
                norm_type = "AADHAAR" if doc_type_raw == "AADHAR" else doc_type_raw

                if norm_type in REQUIRED_DOCUMENTS:
                    val_status = props.get("Validation Status", {}).get("status", {}).get("name", "Processing Error")
                    mapped_status = "APPROVED" if val_status == "Approved" else ("MANUAL_REVIEW" if val_status == "Manual Review" else "PROCESSING_ERROR")
                    
                    document_statuses[norm_type] = mapped_status
                    doc_id_title = props.get("Document ID", {}).get("title", [{}])[0].get("plain_text", "")
                    
                    document_details[norm_type] = {
                        "document_id": doc_id_title,
                        "notion_page_id": page.get("id"),
                        "status": mapped_status,
                        "extracted_name": props.get("Extracted Name ", {}).get("rich_text", [{}])[0].get("plain_text", "") if props.get("Extracted Name ", {}).get("rich_text") else None,
                        "extracted_number": props.get("Extracted Number", {}).get("rich_text", [{}])[0].get("plain_text", "") if props.get("Extracted Number", {}).get("rich_text") else None,
                    }
        except Exception as e:
            print(f"Notion get_documents failed: {e}")

    # Determine onboarding status
    statuses = list(document_statuses.values())
    if any(status == "MISSING" for status in statuses):
        calculated_status = "IN_PROGRESS"
    elif all(status == "APPROVED" for status in statuses):
        calculated_status = "APPROVED"
    else:
        calculated_status = "PENDING_REVIEW"

    # Update status in Notion if changed
    if onboarding_page and notion_onboarding_id:
        try:
            notion_status_map = {
                "IN_PROGRESS": "In Progress",
                "PENDING_REVIEW": "Pending Review",
                "APPROVED": "Completed",
                "COMPLETED": "Completed",
            }
            update_onboarding_status(onboarding_page["id"], notion_status_map.get(calculated_status, "In Progress"))
        except Exception as e:
            print(f"Notion update_onboarding_status failed: {e}")

    return {
        "onboarding_id": onboarding_id,
        "onboarding_status": calculated_status,
        "documents": document_statuses,
        "document_details": document_details,
    }