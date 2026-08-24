import asyncio
import os
import shutil
import time
from typing import Any
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

load_dotenv()

from .document_inspector import inspect_document
from .document_classifier import classify_document
from .document_extractor import extract_document_data
from .document_validator import (
    validate_pan,
    validate_aadhaar,
    validate_rent_agreement,
)
from .onboarding_service import get_onboarding_checklist
from .onboarding_status import evaluate_onboarding_status
from .run_log import create_run_log
from .rent_agreement_generator import generate_rent_agreement
from .notion_service import (
    get_database,
    get_page,
    create_onboarding_item,
    get_onboarding_by_id,
    create_document_item,
    get_document_by_id,
    get_documents_by_onboarding,
    update_document_status,
    create_review_queue_item,
    query_database,
    get_pending_agreement_requests,
    mark_agreement_as_generated,
)
from .models import (
    DocumentType,
    DocumentStatus,
    OnboardingStatus,
    ReviewDecision,
)


class ReviewRequest(BaseModel):
    decision: str
    reason: str | None = None


class PropertyCreate(BaseModel):
    name: str
    address: str


class TenantCreate(BaseModel):
    property_name: str | None = None
    name: str
    phone: str
    unit_number: str


class OnboardingCreate(BaseModel):
    tenant_name: str
    onboarding_id: str | int | None = None
    property_name: str | None = None


app = FastAPI(
    title="Tenant Document Automation (Notion-Powered)",
    version="1.0.0",
)


# =========================================================
# HELPER: CONSTRUCT RENT AGREEMENT DATA
# =========================================================

def build_agreement_data_for_onboarding(onboarding_page: dict) -> dict:
    props = onboarding_page.get("properties", {})
    tenant_name_list = props.get("Tenant Name", {}).get("rich_text", [{}])
    tenant_name = tenant_name_list[0].get("plain_text", "Tenant") if tenant_name_list else "Tenant"

    prop_select = props.get("Property/PG", {}).get("select", {})
    property_name = prop_select.get("name", "Flat - 101") if prop_select else "Flat - 101"

    onb_id_list = props.get("Onboarding ID", {}).get("title", [{}])
    onb_title = onb_id_list[0].get("plain_text", "ONB-1") if onb_id_list else "ONB-1"

    # Fetch linked documents to get Aadhaar & PAN details if available
    notion_documents_id = os.getenv("NOTION_DOCUMENTS_ID")
    aadhaar_num = "____________"
    pan_num = "____________"

    if notion_documents_id and onboarding_page.get("id"):
        try:
            doc_pages = get_documents_by_onboarding(notion_documents_id, onboarding_page.get("id"))
            for doc in doc_pages:
                d_props = doc.get("properties", {})
                d_type = d_props.get("Document Type", {}).get("select", {}).get("name", "")
                d_num_list = d_props.get("Extracted Number", {}).get("rich_text", [{}])
                d_num = d_num_list[0].get("plain_text", "") if d_num_list else ""
                if d_type in ["AADHAR", "AADHAAR"] and d_num:
                    aadhaar_num = d_num
                elif d_type == "PAN" and d_num:
                    pan_num = d_num
        except Exception as e:
            print(f"Error fetching documents for agreement: {e}")

    return {
        "landlord_name": "Property Owner / Landlord",
        "landlord_address": f"{property_name}, Sunrise Residency, Chandigarh",
        "landlord_contact": "+91 9876543210",
        "tenant_name": f"{tenant_name} (Aadhaar: {aadhaar_num}, PAN: {pan_num})",
        "tenant_address": f"Resident at {property_name}",
        "tenant_contact": "+91 9996570779",
        "property_address": f"{property_name}, Sunrise Residency, Sector 22, Chandigarh",
        "property_type": "Apartment",
        "property_floor_unit": property_name,
        "start_date": "01-09-2026",
        "end_date": "31-07-2027",
        "lease_duration": "11 months",
        "rent_amount": "15,000",
        "rent_in_words": "Fifteen Thousand Rupees Only",
        "rent_due_day": "5th",
        "payment_method": "BANK_TRANSFER",
        "late_fee": "100",
        "security_deposit": "30,000",
        "deposit_refund_days": "30",
        "signature_date": "24-08-2026",
    }


# =========================================================
# NOTION CHECKBOX POLLER FUNCTION
# =========================================================

def poll_and_process_rent_agreements() -> dict:
    notion_agreements_id = os.getenv("NOTION_RENT_AGREEMENTS_ID")
    notion_onboarding_id = os.getenv("NOTION_ONBOARDING_ID")

    if not notion_agreements_id:
        return {"processed": 0, "message": "NOTION_RENT_AGREEMENTS_ID not configured"}

    pending_requests = get_pending_agreement_requests(notion_agreements_id)
    processed_count = 0

    for row in pending_requests:
        row_id = row.get("id")
        props = row.get("properties", {})
        target_relations = props.get("Target Onboarding", {}).get("relation", [])

        onb_page = None
        if target_relations:
            onb_page_id = target_relations[0].get("id")
            try:
                onb_page = get_page(onb_page_id)
            except Exception as e:
                print(f"Error fetching target onboarding {onb_page_id}: {e}")

        # Fallback if no target relation linked: fetch most recent onboarding
        if not onb_page and notion_onboarding_id:
            try:
                all_onb = query_database(notion_onboarding_id).get("results", [])
                if all_onb:
                    onb_page = all_onb[0]
            except Exception:
                pass

        if onb_page:
            agreement_data = build_agreement_data_for_onboarding(onb_page)
        else:
            agreement_data = {
                "tenant_name": "Tenant",
                "property_address": "Assigned Unit",
                "rent_amount": "15,000",
                "security_deposit": "30,000",
                "start_date": "01-09-2026",
                "end_date": "31-07-2027",
            }

        # 1. Generate PDF
        pdf_buffer = generate_rent_agreement(agreement_data)
        os.makedirs("uploads/agreements", exist_ok=True)
        pdf_filename = f"agreement_{row_id}.pdf"
        pdf_path = os.path.join("uploads", "agreements", pdf_filename)
        with open(pdf_path, "wb") as f:
            f.write(pdf_buffer.getvalue())

        # 2. Reset '[ ] Generate Now' checkbox back to False in Notion
        try:
            mark_agreement_as_generated(row_id)
        except Exception as e:
            print(f"Error resetting checkbox in Notion: {e}")

        # 3. Log to Notion RUN LOG
        onb_title = onb_page.get("properties", {}).get("Onboarding ID", {}).get("title", [{}])[0].get("plain_text", "1") if onb_page else "1"
        clean_num = onb_title.replace("ONB-", "")

        create_run_log(
            event_type="RENT_AGREEMENT_GENERATED",
            status="SUCCESS",
            message=f"Rent Agreement generated for {agreement_data.get('tenant_name')}",
            onboarding_id=clean_num,
        )

        processed_count += 1

    return {"processed": processed_count, "status": "ok"}


# =========================================================
# STARTUP BACKGROUND POLLING LOOP
# =========================================================

@app.on_event("startup")
async def start_background_workers():
    async def agreement_polling_loop():
        # Polling loop: checks every 10 seconds for checked boxes in Notion
        while True:
            try:
                poll_and_process_rent_agreements()
            except Exception as e:
                pass
            await asyncio.sleep(10)

    asyncio.create_task(agreement_polling_loop())


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health():
    token = os.getenv("NOTION_ACCESS_TOKEN")
    return {
        "status": "ok",
        "storage": "notion",
        "notion_configured": bool(token),
    }


# =========================================================
# NOTION CONNECTION TEST
# =========================================================

@app.get("/notion/test")
def notion_test():
    databases = {
        "review_queue": os.getenv("NOTION_REVIEW_QUEUE_ID"),
        "onboarding": os.getenv("NOTION_ONBOARDING_ID"),
        "run_log": os.getenv("NOTION_RUN_LOG_ID"),
        "documents": os.getenv("NOTION_DOCUMENTS_ID"),
        "rent_agreements": os.getenv("NOTION_RENT_AGREEMENTS_ID"),
    }

    results = {}
    for name, database_id in databases.items():
        if not database_id:
            results[name] = {
                "status": "ERROR",
                "message": "Database ID is missing in .env.",
            }
            continue

        try:
            database = get_database(database_id)
            title_prop = database.get("title", [{}])
            db_title = title_prop[0].get("plain_text", "") if title_prop else ""
            results[name] = {
                "status": "CONNECTED",
                "database_id": database_id,
                "database_name": db_title,
                "properties": list(database.get("properties", {}).keys()),
            }
        except Exception as e:
            results[name] = {
                "status": "ERROR",
                "message": str(e),
            }

    return results


# =========================================================
# PROPERTIES & TENANTS (Helper Endpoints)
# =========================================================

@app.post("/properties")
def create_property(name: str, address: str):
    return {
        "name": name,
        "address": address,
        "status": "active",
    }


@app.post("/tenants")
def create_tenant(
    name: str,
    phone: str,
    unit_number: str,
    property_name: str | None = None,
):
    return {
        "name": name,
        "phone": phone,
        "unit_number": unit_number,
        "property_name": property_name or "Flat - 101",
    }


# =========================================================
# ONBOARDINGS
# =========================================================

@app.post("/onboardings")
def create_onboarding(
    tenant_name: str,
    property_name: str | None = None,
    onboarding_id: int | str | None = None,
):
    notion_onboarding_id = os.getenv("NOTION_ONBOARDING_ID")
    if not notion_onboarding_id:
        raise HTTPException(
            status_code=500,
            detail="NOTION_ONBOARDING_ID is not configured in .env",
        )

    # Generate sequential or timestamped ID if not provided
    chosen_id = onboarding_id or int(time.time()) % 100000

    try:
        page = create_onboarding_item(
            database_id=notion_onboarding_id,
            onboarding_id=chosen_id,
            tenant_name=tenant_name,
            status="In Progress",
            property_name=property_name,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create Onboarding in Notion: {e}",
        )

    # Record in Notion RUN LOG
    create_run_log(
        event_type="ONBOARDING_CREATED",
        status="SUCCESS",
        message=f"Onboarding #{chosen_id} created for {tenant_name}",
        onboarding_id=chosen_id,
    )

    return {
        "onboarding_id": chosen_id,
        "tenant_name": tenant_name,
        "status": "IN_PROGRESS",
        "notion_page_id": page.get("id"),
    }


@app.get("/onboardings/{onboarding_id}/checklist")
def onboarding_checklist(onboarding_id: str):
    return get_onboarding_checklist(onboarding_id)


@app.get("/onboardings/{onboarding_id}/status")
def onboarding_status(onboarding_id: str):
    return evaluate_onboarding_status(onboarding_id)


# =========================================================
# DOCUMENT UPLOAD & EXTRACTION PIPELINE
# =========================================================

@app.post("/documents/upload")
def upload_document(
    onboarding_id: str,
    file: UploadFile = File(...),
):
    # 1. Verify Allowed Types
    allowed_types = {
        "application/pdf",
        "image/jpeg",
        "image/png",
    }
    content_type_str = file.content_type or "application/octet-stream"
    if content_type_str not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, JPG, and PNG files are allowed",
        )

    # 2. Store Local Temp File
    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)
    filename = os.path.basename(file.filename or "document")
    doc_num_id = int(time.time() * 1000) % 1000000
    storage_path = os.path.join(upload_dir, f"onb_{onboarding_id}_{doc_num_id}_{filename}")

    with open(storage_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 3. Log Document Received in Notion RUN LOG
    create_run_log(
        event_type="DOCUMENT_RECEIVED",
        status="RECEIVED",
        message=f"File {filename} received for Onboarding #{onboarding_id}",
        onboarding_id=onboarding_id,
        document_id=doc_num_id,
    )

    # 4. Inspect Document Quality
    inspection = inspect_document(storage_path, content_type_str)
    quality_status = inspection.get("quality", "GOOD")
    quality_reason = str(inspection.get("quality_reason", ""))

    create_run_log(
        event_type="QUALITY_CHECK",
        status="GOOD" if quality_status == "GOOD" else "QUALITY_FAILED",
        message=quality_reason,
        onboarding_id=onboarding_id,
        document_id=doc_num_id,
    )

    if quality_status != "GOOD":
        # Create Error / Manual Review in Notion REVIEW QUEUE
        notion_review_id = os.getenv("NOTION_REVIEW_QUEUE_ID")
        if notion_review_id:
            try:
                create_review_queue_item(
                    database_id=notion_review_id,
                    task_title=f"Quality Failed - Doc #{doc_num_id}",
                    review_notes=f"File: {filename}",
                    stop_reason=quality_reason or "Image quality rejected",
                )
            except Exception as e:
                print(f"Notion REVIEW QUEUE sync failed: {e}")

        return {
            "document_id": doc_num_id,
            "onboarding_id": onboarding_id,
            "filename": filename,
            "document_type": "UNKNOWN",
            "status": "QUALITY_FAILED",
            "extracted_data": {},
            "inspection": inspection,
            "validation": None,
        }

    # 5. Classify Document with Gemini
    try:
        classified_type = classify_document(storage_path, content_type_str)
    except RuntimeError as e:
        create_run_log(
            event_type="CLASSIFICATION_FAILED",
            status="PROCESSING_ERROR",
            message=str(e),
            onboarding_id=onboarding_id,
            document_id=doc_num_id,
        )
        return {
            "document_id": doc_num_id,
            "onboarding_id": onboarding_id,
            "filename": filename,
            "document_type": "UNKNOWN",
            "status": "PROCESSING_ERROR",
            "error": str(e),
        }

    create_run_log(
        event_type="DOCUMENT_CLASSIFIED",
        status="CLASSIFIED",
        message=f"Document classified as {classified_type}.",
        onboarding_id=onboarding_id,
        document_id=doc_num_id,
    )

    # 6. Extract Document Data
    extracted_data = {}
    if classified_type in {"PAN", "AADHAAR", "RENT_AGREEMENT"}:
        try:
            extracted_data = extract_document_data(
                storage_path,
                content_type_str,
                classified_type,
            )
        except RuntimeError as e:
            create_run_log(
                event_type="EXTRACTION_FAILED",
                status="PROCESSING_ERROR",
                message=str(e),
                onboarding_id=onboarding_id,
                document_id=doc_num_id,
            )

    create_run_log(
        event_type="DATA_EXTRACTED",
        status="EXTRACTED",
        message=f"Data extracted for {classified_type}.",
        onboarding_id=onboarding_id,
        document_id=doc_num_id,
    )

    # 7. Fetch tenant registered name for mismatch checking
    notion_documents_id = os.getenv("NOTION_DOCUMENTS_ID")
    notion_onboarding_id = os.getenv("NOTION_ONBOARDING_ID")
    onb_page = get_onboarding_by_id(notion_onboarding_id, onboarding_id) if notion_onboarding_id else None
    expected_tenant_name = None
    if onb_page:
        tenant_name_prop = onb_page.get("properties", {}).get("Tenant Name", {}).get("rich_text", [{}])
        expected_tenant_name = tenant_name_prop[0].get("plain_text", "") if tenant_name_prop else None

    # Validate Document
    validation = None
    if classified_type == "PAN":
        validation = validate_pan(extracted_data, expected_name=expected_tenant_name)
    elif classified_type == "AADHAAR":
        validation = validate_aadhaar(extracted_data, expected_name=expected_tenant_name)
    elif classified_type == "RENT_AGREEMENT":
        validation = validate_rent_agreement(extracted_data, expected_name=expected_tenant_name)

    is_valid = validation.get("valid", False) if validation else False
    final_status = "APPROVED" if is_valid else "MANUAL_REVIEW"
    validation_err = validation.get("error") if validation and isinstance(validation, dict) else "Requires manual review"

    create_run_log(
        event_type="DOCUMENT_VALIDATED",
        status="VALID" if is_valid else "MANUAL_REVIEW",
        message="Validation succeeded" if is_valid else f"Validation stopped: {validation_err}",
        onboarding_id=onboarding_id,
        document_id=doc_num_id,
    )

    # 8. Sync Document directly to Notion DOCUMENTS database
    doc_page = None

    if notion_documents_id:
        try:
            extracted_name = None
            extracted_num = None
            if extracted_data:
                extracted_name = extracted_data.get("name") or extracted_data.get("tenant_name")
                extracted_num = extracted_data.get("pan_number") or extracted_data.get("aadhaar_number")

            onb_page_id = onb_page.get("id") if onb_page else None

            doc_page = create_document_item(
                database_id=notion_documents_id,
                document_id=doc_num_id,
                doc_type=classified_type,
                name=str(extracted_name) if extracted_name else None,
                number=str(extracted_num) if extracted_num else None,
                validation_status=final_status,
                onboarding_page_id=onb_page_id,
            )
        except Exception as e:
            print(f"Notion DOCUMENTS sync failed: {e}")

    # 9. If Manual Review Required, push to Notion REVIEW QUEUE
    if final_status == "MANUAL_REVIEW":
        notion_review_id = os.getenv("NOTION_REVIEW_QUEUE_ID")
        if notion_review_id:
            try:
                err_msg = validation.get("error") if validation and isinstance(validation, dict) else "Manual check required"
                create_review_queue_item(
                    database_id=notion_review_id,
                    task_title=f"Review {classified_type} - Doc #{doc_num_id}",
                    review_notes=f"Onboarding #{onboarding_id} | Extracted: {extracted_data}",
                    stop_reason=str(err_msg),
                    document_page_id=doc_page.get("id") if doc_page else None,
                )
            except Exception as e:
                print(f"Notion REVIEW QUEUE sync failed: {e}")

    # 10. Return Checklist & Results
    checklist = get_onboarding_checklist(onboarding_id)

    return {
        "document_id": doc_num_id,
        "onboarding_id": onboarding_id,
        "filename": filename,
        "document_type": classified_type,
        "status": final_status,
        "extracted_data": extracted_data,
        "validation": validation,
        "inspection": inspection,
        "checklist": checklist,
    }


# =========================================================
# APPROVE / RESEND (Human Decision in Notion)
# =========================================================

@app.post("/documents/{document_id}/approve")
def approve_document(
    document_id: str,
    request_data: ReviewRequest | None = None,
):
    notion_documents_id = os.getenv("NOTION_DOCUMENTS_ID")
    if not notion_documents_id:
        raise HTTPException(status_code=500, detail="NOTION_DOCUMENTS_ID not configured")

    doc_page = get_document_by_id(notion_documents_id, document_id)
    if not doc_page:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found in Notion")

    reason = request_data.reason if request_data and request_data.reason else "Approved by human reviewer"

    # Update in Notion DOCUMENTS
    update_document_status(doc_page["id"], "Approved")

    # Log to Notion RUN LOG
    create_run_log(
        event_type="HUMAN_APPROVAL",
        status="APPROVED",
        message=f"Document {document_id} manually approved: {reason}",
        document_id=document_id,
    )

    return {
        "document_id": document_id,
        "status": "APPROVED",
        "decision": "APPROVED",
        "reason": reason,
    }


@app.post("/documents/{document_id}/resend")
def resend_document(
    document_id: str,
    request_data: ReviewRequest | None = None,
):
    notion_documents_id = os.getenv("NOTION_DOCUMENTS_ID")
    if not notion_documents_id:
        raise HTTPException(status_code=500, detail="NOTION_DOCUMENTS_ID not configured")

    doc_page = get_document_by_id(notion_documents_id, document_id)
    if not doc_page:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found in Notion")

    reason = request_data.reason if request_data and request_data.reason else "Document rejected. Resubmission required."

    # Update in Notion DOCUMENTS
    update_document_status(doc_page["id"], "Processing Error")

    # Log to Notion RUN LOG
    create_run_log(
        event_type="HUMAN_REJECTION",
        status="RESEND_REQUIRED",
        message=f"Document {document_id} rejected: {reason}",
        document_id=document_id,
    )

    return {
        "document_id": document_id,
        "status": "RESEND_REQUIRED",
        "decision": "REJECTED",
        "reason": reason,
    }


# =========================================================
# RENT AGREEMENT GENERATION & POLLING ENDPOINTS
# =========================================================

@app.post("/notion/poll-agreements")
def poll_agreements_now():
    """
    Manually triggers a scan of the RENT AGREEMENTS database for checked rows.
    """
    result = poll_and_process_rent_agreements()
    return result


@app.get("/onboardings/{onboarding_id}/rent-agreement")
def download_rent_agreement(onboarding_id: str):
    """
    Dynamically generates and downloads the Rent Agreement PDF for a given onboarding.
    """
    notion_onboarding_id = os.getenv("NOTION_ONBOARDING_ID")
    onb_page = get_onboarding_by_id(notion_onboarding_id, onboarding_id) if notion_onboarding_id else None

    if onb_page:
        agreement_data = build_agreement_data_for_onboarding(onb_page)
    else:
        agreement_data = {
            "tenant_name": f"Tenant #{onboarding_id}",
            "property_address": "Assigned Unit",
            "rent_amount": "15,000",
            "security_deposit": "30,000",
            "start_date": "01-09-2026",
            "end_date": "31-07-2027",
        }

    pdf_buffer = generate_rent_agreement(agreement_data)
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="rent_agreement_onb_{onboarding_id}.pdf"'
        },
    )


@app.post("/rent-agreements")
def create_rent_agreement_custom(data: dict):
    try:
        pdf_file = generate_rent_agreement(data)
        return StreamingResponse(
            pdf_file,
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="rent_agreement.pdf"'
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate rent agreement: {str(e)}",
        )


# =========================================================
# RUN LOGS (Fetch from Notion)
# =========================================================

@app.get("/run-logs")
def get_run_logs():
    notion_run_log_id = os.getenv("NOTION_RUN_LOG_ID")
    if not notion_run_log_id:
        return []

    res = query_database(notion_run_log_id)
    pages = res.get("results", [])
    logs = []

    for p in pages:
        props = p.get("properties", {})
        title_prop = props.get("Run ID / Event", {}).get("title", [{}])
        event_title = title_prop[0].get("plain_text", "") if title_prop else ""
        outcome_val = props.get("Outcome", {}).get("select", {}).get("name", "")
        action_prop = props.get("Code Action", {}).get("rich_text", [{}])
        action_text = action_prop[0].get("plain_text", "") if action_prop else ""

        logs.append({
            "id": p.get("id"),
            "event_type": event_title,
            "outcome": outcome_val,
            "message": action_text,
            "created_time": p.get("created_time"),
        })

    return logs