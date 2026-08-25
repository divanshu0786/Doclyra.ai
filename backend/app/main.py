import asyncio
from contextlib import asynccontextmanager
import os
import re
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
    validate_passport_photo,
)
from .whatsapp_service import (
    send_tenant_greeting,
    send_approval_notification,
    send_rejection_notification,
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
    get_all_onboardings,
    update_onboarding_id,
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
    property_address: str | None = None
    name: str
    phone: str
    unit_number: str


class OnboardingCreate(BaseModel):
    tenant_name: str
    tenant_phone: str = "+919996570779"
    property_name: str | None = None
    property_address: str | None = None
    onboarding_id: str | int | None = None


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

        # Generate PDF
        pdf_buffer = generate_rent_agreement(agreement_data)
        os.makedirs("uploads/agreements", exist_ok=True)
        pdf_filename = f"agreement_{row_id}.pdf"
        pdf_path = os.path.join("uploads", "agreements", pdf_filename)
        with open(pdf_path, "wb") as f:
            f.write(pdf_buffer.getvalue())

        # Reset checkbox in Notion
        try:
            mark_agreement_as_generated(row_id)
        except Exception as e:
            print(f"Error resetting checkbox in Notion: {e}")

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


# In-memory tracking of onboardings that have already received WhatsApp greeting
GREETED_ONBOARDINGS: set[str] = set()


def extract_notion_text(prop: dict | None) -> str:
    if not prop:
        return ""
    if prop.get("title"):
        return prop["title"][0].get("plain_text", "") if prop["title"] else ""
    if prop.get("rich_text"):
        return prop["rich_text"][0].get("plain_text", "") if prop["rich_text"] else ""
    if prop.get("phone_number"):
        return str(prop.get("phone_number"))
    if prop.get("number") is not None:
        return str(prop.get("number"))
    if prop.get("select"):
        return prop["select"].get("name", "") if prop["select"] else ""
    return ""


def poll_and_process_new_onboardings() -> dict:
    """
    Polls Notion ONBOARDINGS database for newly added tenants.
    Automatically sends WhatsApp greeting & 4-document request message.
    """
    notion_onboarding_id = os.getenv("NOTION_ONBOARDING_ID")
    if not notion_onboarding_id:
        return {"processed": 0, "message": "NOTION_ONBOARDING_ID not configured"}

    pages = get_all_onboardings(notion_onboarding_id)
    processed_count = 0

    for page in pages:
        page_id = page.get("id")
        if not page_id:
            continue

        props = page.get("properties", {})
        raw_id = extract_notion_text(props.get("Onboarding ID"))
        tenant_name = extract_notion_text(props.get("Tenant Name"))
        raw_phone = extract_notion_text(props.get("Tenant Phone"))
        property_name = (
            extract_notion_text(props.get("Property Nmae"))
            or extract_notion_text(props.get("Property/PG"))
            or "your assigned property"
        )
        property_address = extract_notion_text(props.get("Property Address"))

        # Skip if page already greeted
        if page_id in GREETED_ONBOARDINGS:
            continue
        if raw_id and raw_id in GREETED_ONBOARDINGS:
            GREETED_ONBOARDINGS.add(page_id)
            continue

        # Need phone number to send WhatsApp greeting
        if not raw_phone:
            continue

        # Format phone number to international standard (E.164)
        digits = "".join(re.findall(r"\d+", raw_phone))
        if not digits:
            continue

        if len(digits) == 10:
            formatted_phone = f"+91{digits}"
        elif digits.startswith("91") and len(digits) == 12:
            formatted_phone = f"+{digits}"
        elif raw_phone.startswith("+"):
            formatted_phone = raw_phone.strip()
        else:
            formatted_phone = f"+{digits}"

        # Assign an Onboarding ID if missing in Notion
        if not raw_id or raw_id.strip() == "":
            gen_num = int(time.time()) % 100000
            try:
                update_onboarding_id(page_id, gen_num)
            except Exception as e:
                print(f"Error updating Onboarding ID in Notion: {e}")
            clean_onb_id = str(gen_num)
        else:
            clean_onb_id = raw_id.replace("ONB-", "")

        # Record in processed set
        GREETED_ONBOARDINGS.add(page_id)
        if raw_id:
            GREETED_ONBOARDINGS.add(raw_id)
        GREETED_ONBOARDINGS.add(f"ONB-{clean_onb_id}")

        # Send automated WhatsApp greeting
        try:
            send_tenant_greeting(
                tenant_name=tenant_name or "Tenant",
                tenant_phone=formatted_phone,
                onboarding_id=clean_onb_id,
                property_name=property_name,
                property_address=property_address,
            )
            create_run_log(
                event_type="WHATSAPP_GREETING_SENT",
                status="SUCCESS",
                message=f"Auto-detected Notion entry: Greeting sent to {formatted_phone}",
                onboarding_id=clean_onb_id,
            )
            print(f"✅ Auto-sent WhatsApp greeting to {tenant_name} ({formatted_phone}) for ONB-{clean_onb_id}")
            processed_count += 1
        except Exception as e:
            print(f"❌ Failed to auto-send WhatsApp greeting for ONB-{clean_onb_id}: {e}")
            create_run_log(
                event_type="WHATSAPP_GREETING_FAILED",
                status="FAILED",
                message=f"Auto-greeting failed: {e}",
                onboarding_id=clean_onb_id,
            )

    return {"processed": processed_count, "status": "ok"}


# =========================================================
# LIFESPAN & BACKGROUND POLLING WORKERS
# =========================================================

async def agreement_polling_loop():
    while True:
        try:
            poll_and_process_rent_agreements()
        except Exception:
            pass
        await asyncio.sleep(10)


async def onboarding_polling_loop():
    while True:
        try:
            poll_and_process_new_onboardings()
        except Exception as e:
            print(f"Error in onboarding poller: {e}")
        await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    agreement_task = asyncio.create_task(agreement_polling_loop())
    onboarding_task = asyncio.create_task(onboarding_polling_loop())
    try:
        yield
    finally:
        agreement_task.cancel()
        onboarding_task.cancel()


app = FastAPI(
    title="Tenant Document Automation (Notion-Powered)",
    version="1.0.0",
    lifespan=lifespan,
)


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
# ONBOARDINGS (Broker registers Property & Tenant)
# =========================================================

@app.post("/onboardings")
def create_onboarding(
    tenant_name: str,
    tenant_phone: str = "+919996570779",
    property_name: str | None = None,
    property_address: str | None = None,
    onboarding_id: int | str | None = None,
):
    notion_onboarding_id = os.getenv("NOTION_ONBOARDING_ID")
    if not notion_onboarding_id:
        raise HTTPException(
            status_code=500,
            detail="NOTION_ONBOARDING_ID is not configured in .env",
        )

    chosen_id = onboarding_id or int(time.time()) % 100000

    # 1. Create Onboarding in Notion
    try:
        page = create_onboarding_item(
            database_id=notion_onboarding_id,
            onboarding_id=chosen_id,
            tenant_name=tenant_name,
            status="In Progress",
            property_name=property_name,
            property_address=property_address,
            tenant_phone=tenant_phone,
        )
        if page and page.get("id"):
            GREETED_ONBOARDINGS.add(page.get("id"))
            GREETED_ONBOARDINGS.add(f"ONB-{chosen_id}")
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create Onboarding in Notion: {e}",
        )

    # 2. Record in Notion RUN LOG
    create_run_log(
        event_type="ONBOARDING_CREATED",
        status="SUCCESS",
        message=f"Onboarding #{chosen_id} created for {tenant_name} ({property_name or 'Unit'})",
        onboarding_id=chosen_id,
    )

    # 3. Send Automated WhatsApp Greeting & Document Request (4 documents)
    wa_result = None
    if tenant_phone:
        try:
            wa_result = send_tenant_greeting(
                tenant_name=tenant_name,
                tenant_phone=tenant_phone,
                onboarding_id=chosen_id,
                property_name=property_name,
                property_address=property_address,
            )
            create_run_log(
                event_type="WHATSAPP_GREETING_SENT",
                status="SUCCESS",
                message=f"Document request message sent to {tenant_phone} on WhatsApp",
                onboarding_id=chosen_id,
            )
        except Exception as e:
            print(f"WhatsApp greeting sending failed: {e}")
            create_run_log(
                event_type="WHATSAPP_GREETING_FAILED",
                status="FAILED",
                message=f"Could not send WhatsApp greeting: {e}",
                onboarding_id=chosen_id,
            )

    return {
        "onboarding_id": chosen_id,
        "tenant_name": tenant_name,
        "tenant_phone": tenant_phone,
        "property_name": property_name,
        "status": "IN_PROGRESS",
        "notion_page_id": page.get("id"),
        "whatsapp": wa_result,
    }


@app.get("/onboardings/{onboarding_id}/checklist")
def onboarding_checklist(onboarding_id: str):
    return get_onboarding_checklist(onboarding_id)


@app.get("/onboardings/{onboarding_id}/status")
def onboarding_status(onboarding_id: str):
    return evaluate_onboarding_status(onboarding_id)


# =========================================================
# DOCUMENT UPLOAD, EXTRACTION & 3-WAY OUTCOME PIPELINE
# =========================================================

@app.post("/documents/upload")
def upload_document(
    onboarding_id: str,
    file: UploadFile = File(...),
    tenant_phone: str = "+919996570779",
):
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

    # 1. Store File Locally
    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)
    filename = os.path.basename(file.filename or "document")
    doc_num_id = int(time.time() * 1000) % 1000000
    storage_path = os.path.join(upload_dir, f"onb_{onboarding_id}_{doc_num_id}_{filename}")

    with open(storage_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    create_run_log(
        event_type="DOCUMENT_RECEIVED",
        status="RECEIVED",
        message=f"File {filename} received for Onboarding #{onboarding_id}",
        onboarding_id=onboarding_id,
        document_id=doc_num_id,
    )

    # 2. Inspect Quality
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

    # Fetch registered tenant details from Notion
    notion_documents_id = os.getenv("NOTION_DOCUMENTS_ID")
    notion_onboarding_id = os.getenv("NOTION_ONBOARDING_ID")
    onb_page = get_onboarding_by_id(notion_onboarding_id, onboarding_id) if notion_onboarding_id else None
    expected_tenant_name = None
    if onb_page:
        tenant_name_prop = onb_page.get("properties", {}).get("Tenant Name", {}).get("rich_text", [{}])
        expected_tenant_name = tenant_name_prop[0].get("plain_text", "") if tenant_name_prop else None

    # OUTCOME: REJECTED (Fully Blurry / Quality Failed)
    if quality_status != "GOOD":
        layman_msg = f"The uploaded photo of {filename} is too blurry or unreadable. Please retake a clear photo in good lighting."
        try:
            send_rejection_notification(
                tenant_phone=tenant_phone,
                doc_type="Document",
                layman_reason=layman_msg,
                tenant_name=expected_tenant_name,
            )
        except Exception as e:
            print(f"WhatsApp rejection send error: {e}")

        # Push to Review Queue as rejected
        notion_review_id = os.getenv("NOTION_REVIEW_QUEUE_ID")
        if notion_review_id:
            try:
                create_review_queue_item(
                    database_id=notion_review_id,
                    task_title=f"Rejected: Quality Failed - Doc #{doc_num_id}",
                    review_notes=f"Tenant: {expected_tenant_name or onboarding_id} | File: {filename}",
                    stop_reason=layman_msg,
                    decision="Reject",
                )
            except Exception as e:
                print(f"Notion REVIEW QUEUE sync failed: {e}")

        return {
            "document_id": doc_num_id,
            "onboarding_id": onboarding_id,
            "filename": filename,
            "document_type": "UNKNOWN",
            "status": "REJECTED",
            "decision": "REJECTED",
            "reason": layman_msg,
            "inspection": inspection,
        }

    # 3. Classify Document with Gemini
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

    # 4. Extract Data (for ID cards & rent agreement)
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

    # 5. Validation with Layman Explanations
    validation = None
    if classified_type == "PAN":
        validation = validate_pan(extracted_data, expected_name=expected_tenant_name)
    elif classified_type == "AADHAAR":
        validation = validate_aadhaar(extracted_data, expected_name=expected_tenant_name)
    elif classified_type == "RENT_AGREEMENT":
        validation = validate_rent_agreement(extracted_data, expected_name=expected_tenant_name)
    elif classified_type == "PASSPORT_PHOTO":
        validation = validate_passport_photo(inspection)
    else:
        validation = {
            "valid": False,
            "status": "MANUAL_REVIEW",
            "error": "Document type could not be recognized as Aadhaar, PAN, Passport Photo, or Rent Agreement.",
        }

    is_valid = validation.get("valid", False) if validation else False
    validation_err = validation.get("error") if validation and isinstance(validation, dict) else "Requires manual review"

    # Determine 3-Way Outcome
    # Total name mismatch or completely unreadable ➔ REJECTED
    # Minor issue ➔ MANUAL_REVIEW
    # Valid ➔ APPROVED
    is_name_mismatch = "Name mismatch" in str(validation_err)

    if is_valid:
        final_status = "APPROVED"
        decision_label = "APPROVED"
    elif is_name_mismatch:
        final_status = "REJECTED"
        decision_label = "REJECTED"
    else:
        final_status = "MANUAL_REVIEW"
        decision_label = "REVIEW"

    create_run_log(
        event_type="DOCUMENT_VALIDATED",
        status="VALID" if is_valid else final_status,
        message="Validation succeeded" if is_valid else f"Validation stopped: {validation_err}",
        onboarding_id=onboarding_id,
        document_id=doc_num_id,
    )

    # 6. Sync Document to Notion DOCUMENTS
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
                validation_status="Approved" if is_valid else ("Manual Review" if final_status == "MANUAL_REVIEW" else "Processing Error"),
                onboarding_page_id=onb_page_id,
            )
        except Exception as e:
            print(f"Notion DOCUMENTS sync failed: {e}")

    # 7. Execute 3-Way Notification Actions
    if final_status == "APPROVED":
        # OUTCOME 1: APPROVED ➔ Send WhatsApp approval message to tenant
        try:
            send_approval_notification(
                tenant_phone=tenant_phone,
                doc_type=classified_type,
                tenant_name=expected_tenant_name,
            )
            create_run_log(
                event_type="WHATSAPP_APPROVAL_SENT",
                status="SUCCESS",
                message=f"Approval message for {classified_type} sent to {tenant_phone}",
                onboarding_id=onboarding_id,
            )
        except Exception as e:
            print(f"WhatsApp approval notification error: {e}")

    elif final_status == "REJECTED":
        # OUTCOME 3: REJECTED ➔ Send WhatsApp rejection message with layman reason
        try:
            send_rejection_notification(
                tenant_phone=tenant_phone,
                doc_type=classified_type,
                layman_reason=str(validation_err),
                tenant_name=expected_tenant_name,
            )
            create_run_log(
                event_type="WHATSAPP_REJECTION_SENT",
                status="SUCCESS",
                message=f"Rejection message for {classified_type} sent to {tenant_phone}",
                onboarding_id=onboarding_id,
            )
        except Exception as e:
            print(f"WhatsApp rejection notification error: {e}")

    else:
        # OUTCOME 2: REVIEW ➔ Broker review in Notion REVIEW QUEUE with layman mismatch notes
        notion_review_id = os.getenv("NOTION_REVIEW_QUEUE_ID")
        if notion_review_id:
            try:
                create_review_queue_item(
                    database_id=notion_review_id,
                    task_title=f"Review {classified_type} - Doc #{doc_num_id}",
                    review_notes=f"Tenant: {expected_tenant_name or onboarding_id} | Details: {extracted_data}",
                    stop_reason=str(validation_err),
                    document_page_id=doc_page.get("id") if doc_page else None,
                )
            except Exception as e:
                print(f"Notion REVIEW QUEUE sync failed: {e}")

    checklist = get_onboarding_checklist(onboarding_id)

    return {
        "document_id": doc_num_id,
        "onboarding_id": onboarding_id,
        "filename": filename,
        "document_type": classified_type,
        "status": final_status,
        "decision": decision_label,
        "extracted_data": extracted_data,
        "validation": validation,
        "inspection": inspection,
        "checklist": checklist,
    }


# =========================================================
# APPROVE / RESEND (Human Broker Decision in Notion)
# =========================================================

@app.post("/documents/{document_id}/approve")
def approve_document(
    document_id: str,
    request_data: ReviewRequest | None = None,
    tenant_phone: str = "+919996570779",
):
    notion_documents_id = os.getenv("NOTION_DOCUMENTS_ID")
    if not notion_documents_id:
        raise HTTPException(status_code=500, detail="NOTION_DOCUMENTS_ID not configured")

    doc_page = get_document_by_id(notion_documents_id, document_id)
    if not doc_page:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found in Notion")

    reason = request_data.reason if request_data and request_data.reason else "Approved by broker"

    update_document_status(doc_page["id"], "Approved")

    create_run_log(
        event_type="HUMAN_APPROVAL",
        status="APPROVED",
        message=f"Document {document_id} manually approved by broker: {reason}",
        document_id=document_id,
    )

    # Notify tenant on WhatsApp
    try:
        send_approval_notification(tenant_phone=tenant_phone, doc_type=f"Document #{document_id}")
    except Exception:
        pass

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
    tenant_phone: str = "+919996570779",
):
    notion_documents_id = os.getenv("NOTION_DOCUMENTS_ID")
    if not notion_documents_id:
        raise HTTPException(status_code=500, detail="NOTION_DOCUMENTS_ID not configured")

    doc_page = get_document_by_id(notion_documents_id, document_id)
    if not doc_page:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found in Notion")

    reason = request_data.reason if request_data and request_data.reason else "Document rejected. Please re-upload."

    update_document_status(doc_page["id"], "Processing Error")

    create_run_log(
        event_type="HUMAN_REJECTION",
        status="RESEND_REQUIRED",
        message=f"Document {document_id} rejected by broker: {reason}",
        document_id=document_id,
    )

    # Notify tenant on WhatsApp with layman reason
    try:
        send_rejection_notification(
            tenant_phone=tenant_phone,
            doc_type=f"Document #{document_id}",
            layman_reason=reason,
        )
    except Exception:
        pass

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
    return poll_and_process_rent_agreements()


@app.post("/notion/poll-onboardings")
def poll_onboardings_now():
    return poll_and_process_new_onboardings()


@app.get("/onboardings/{onboarding_id}/rent-agreement")
def download_rent_agreement(onboarding_id: str):
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