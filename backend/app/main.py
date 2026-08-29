import asyncio
from contextlib import asynccontextmanager
import json
import os
import re
import shutil
import time
from typing import Any
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, File, UploadFile, Request, Response, Form
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from pydantic import BaseModel
import requests

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
    send_whatsapp_message,
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
    get_pending_review_queue_items,
    update_review_task_decision,
    query_database,
    get_pending_agreement_requests,
    mark_agreement_as_generated,
    get_all_onboardings,
    update_onboarding_id,
    update_onboarding_status,
    reset_send_message_checkbox,
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


# Persistent tracking of onboardings that have already received WhatsApp greeting
UPLOAD_DIR = os.path.abspath("uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
GREETED_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "uploads",
    ".greeted_onboardings.json",
)


def load_greeted_cache() -> set[str]:
    try:
        if os.path.exists(GREETED_CACHE_FILE):
            with open(GREETED_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Keep only valid Notion page UUIDs (never keep generic integers like '1' or '2')
                return {x for x in data if len(x) >= 30 and "-" in x}
    except Exception as e:
        print(f"Warning loading greeted cache: {e}")
    return set()


def save_greeted_cache(greeted_set: set[str]):
    try:
        os.makedirs(os.path.dirname(GREETED_CACHE_FILE), exist_ok=True)
        with open(GREETED_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(list(greeted_set), f, indent=2)
    except Exception as e:
        print(f"Warning saving greeted cache: {e}")


GREETED_ONBOARDINGS: set[str] = load_greeted_cache()

REMINDER_CACHE_FILE = os.path.join(UPLOAD_DIR, ".reminder_tracking.json")
REMINDER_INTERVAL_SECONDS = int(os.getenv("REMINDER_INTERVAL_HOURS", "6")) * 3600  # Default 6 hours


def load_reminder_cache() -> dict[str, float]:
    try:
        if os.path.exists(REMINDER_CACHE_FILE):
            with open(REMINDER_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning loading reminder cache: {e}")
    return {}


def save_reminder_cache(cache: dict[str, float]):
    try:
        os.makedirs(os.path.dirname(REMINDER_CACHE_FILE), exist_ok=True)
        with open(REMINDER_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"Warning saving reminder cache: {e}")


REMINDER_TRACKING: dict[str, float] = load_reminder_cache()

DOC_DISPLAY_NAMES = {
    "AADHAR": "Aadhaar Card",
    "AADHAAR": "Aadhaar Card",
    "PAN": "PAN Card",
    "PASSPORT_PHOTO": "Passport Size Photo",
    "PASSPORT_SIZE_PHOTO": "Passport Size Photo",
    "RENT_AGREEMENT": "Rent Agreement",
}


def get_onboarding_progress(tenant_docs: list, current_approved_type: str | None = None) -> tuple[int, str, bool]:
    """
    Evaluates completion across the 4 required documents:
    1. Aadhaar Card
    2. PAN Card
    3. Passport Size Photo
    4. Rent Agreement
    """
    approved_types = set()
    for td in tenant_docs:
        td_props = td.get("properties", {})
        td_status = td_props.get("Validation Status", {}).get("status", {}).get("name", "")
        td_type = td_props.get("Document Type", {}).get("select", {}).get("name", "")
        if td_status == "Approved" and td_type:
            norm = "PASSPORT_PHOTO" if "PASSPORT" in td_type.upper() else td_type.upper()
            if norm == "AADHAAR":
                norm = "AADHAR"
            approved_types.add(norm)

    if current_approved_type:
        norm_curr = "PASSPORT_PHOTO" if "PASSPORT" in current_approved_type.upper() else current_approved_type.upper()
        if norm_curr == "AADHAAR":
            norm_curr = "AADHAR"
        approved_types.add(norm_curr)

    req_keys = ["AADHAR", "PAN", "PASSPORT_PHOTO", "RENT_AGREEMENT"]
    completed_count = sum(1 for k in req_keys if k in approved_types)
    all_completed = (completed_count == 4)

    items = []
    for k in req_keys:
        name = DOC_DISPLAY_NAMES.get(k, k)
        status_icon = "✅" if k in approved_types else "⏳"
        items.append(f"{name} {status_icon}")

    progress_summary = f"({completed_count}/4 completed: " + ", ".join(items) + ")"
    return completed_count, progress_summary, all_completed


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
    if prop.get("unique_id"):
        uid = prop.get("unique_id", {})
        prefix = uid.get("prefix", "ONB")
        num = uid.get("number", "")
        return f"{prefix}-{num}" if prefix else str(num)
    return ""


def get_prop_value(props: dict, key_name: str) -> str:
    """
    Finds a property value flexibly by checking exact key, stripped key,
    and case-insensitive matching. Handles title, rich_text, select, number, unique_id.
    """
    if not props:
        return ""

    target_clean = key_name.strip().lower()

    # 1. Exact / stripped matching
    for k, v in props.items():
        if k.strip().lower() == target_clean:
            return extract_notion_text(v)

    # 2. Substring matching
    for k, v in props.items():
        if target_clean in k.strip().lower():
            return extract_notion_text(v)

    # 3. If looking for tenant name, check if any property is the title column
    if "tenant" in target_clean or "name" in target_clean:
        for k, v in props.items():
            if v.get("type") == "title" or "title" in v:
                return extract_notion_text(v)

    return ""


def poll_and_process_new_onboardings() -> dict:
    """
    Polls Notion ONBOARDINGS database for newly added tenants or checked [ ] Send Message boxes.
    Automatically assigns next sequential Onboarding ID (1, 2, 3...), sets initial status,
    and sends WhatsApp greeting & 4-document request message.
    """
    notion_onboarding_id = os.getenv("NOTION_ONBOARDING_ID")
    if not notion_onboarding_id:
        return {"processed": 0, "message": "NOTION_ONBOARDING_ID not configured"}

    pages = get_all_onboardings(notion_onboarding_id)
    processed_count = 0

    # 1. Collect all existing numeric IDs across the entire database to compute the next auto-ID
    existing_ids = []
    for p in pages:
        p_props = p.get("properties", {})
        id_str = get_prop_value(p_props, "Onboarding ID") or get_prop_value(p_props, "Onboarding id")
        digits = "".join(re.findall(r"\d+", id_str))
        if digits:
            try:
                existing_ids.append(int(digits))
            except Exception:
                pass

    next_auto_id = max(existing_ids, default=0) + 1

    for page in pages:
        page_id = page.get("id")
        if not page_id:
            continue

        props = page.get("properties", {})
        raw_id = get_prop_value(props, "Onboarding ID") or get_prop_value(props, "Onboarding id")
        tenant_name = get_prop_value(props, "Tenant Name") or get_prop_value(props, "Tenant Name ")
        raw_phone = get_prop_value(props, "Tenant Phone")
        property_name = (
            get_prop_value(props, "Property Name")
            or get_prop_value(props, "Property Nmae")
            or get_prop_value(props, "Property/PG")
            or "your assigned property"
        )
        property_address = get_prop_value(props, "Property Address")

        # Auto-set initial status to 'In Progress' if empty
        curr_status = get_prop_value(props, "Onboarding Status")
        if not curr_status and tenant_name:
            try:
                update_onboarding_status(page_id, "In Progress")
            except Exception as e:
                print(f"Error setting default status for {tenant_name}: {e}")

        # Check Send Message checkbox
        send_msg_prop = props.get("Send Message", {})
        send_message_checked = bool(send_msg_prop.get("checkbox", False)) if send_msg_prop else False

        # Assign next sequential Onboarding ID if missing in Notion
        if not raw_id or raw_id.strip() == "":
            if tenant_name:
                clean_onb_id = str(next_auto_id)
                next_auto_id += 1
                try:
                    update_onboarding_id(page_id, int(clean_onb_id))
                    print(f"🔢 Auto-assigned Onboarding ID #{clean_onb_id} to tenant '{tenant_name}' in Notion")
                except Exception as e:
                    print(f"Error updating Onboarding ID in Notion: {e}")
            else:
                clean_onb_id = ""
        else:
            id_digits = "".join(re.findall(r"\d+", raw_id))
            clean_onb_id = id_digits if id_digits else raw_id.replace("ONB-", "").strip()

        # ONLY send WhatsApp greeting when the broker explicitly checks [ ] Send Message!
        if not send_message_checked:
            continue

        if page_id in GREETED_ONBOARDINGS:
            reset_send_message_checkbox(page_id)
            continue

        # Need phone number to send WhatsApp greeting
        if not raw_phone:
            continue

        # Extract digits
        digits = "".join(re.findall(r"\d+", raw_phone))
        # Must have at least 10 digits to be a valid phone number
        if len(digits) < 10:
            continue

        if len(digits) == 10:
            formatted_phone = f"+91{digits}"
        elif digits.startswith("91") and len(digits) == 12:
            formatted_phone = f"+{digits}"
        elif raw_phone.startswith("+") and len(digits) >= 10:
            formatted_phone = raw_phone.strip().replace(" ", "").replace("-", "")
        else:
            formatted_phone = f"+{digits}"

        # Record page_id in persistent processed cache and reset checkbox
        GREETED_ONBOARDINGS.add(page_id)
        save_greeted_cache(GREETED_ONBOARDINGS)
        reset_send_message_checkbox(page_id)

        # Send automated WhatsApp greeting
        try:
            send_tenant_greeting(
                tenant_name=tenant_name or "Tenant",
                tenant_phone=formatted_phone,
                onboarding_id=clean_onb_id or "1",
                property_name=property_name,
                property_address=property_address,
            )
            create_run_log(
                event_type="WHATSAPP_GREETING_SENT",
                status="SUCCESS",
                message=f"Greeting sent to {formatted_phone}",
                onboarding_id=clean_onb_id or "1",
            )
            print(f"✅ Auto-sent WhatsApp greeting to {tenant_name} ({formatted_phone}) for ONB-{clean_onb_id}")
            processed_count += 1
        except Exception as e:
            print(f"❌ Failed to auto-send WhatsApp greeting for ONB-{clean_onb_id}: {e}")
            create_run_log(
                event_type="WHATSAPP_GREETING_FAILED",
                status="FAILED",
                message=f"Auto-greeting failed: {e}",
                onboarding_id=clean_onb_id or "1",
            )

    return {"processed": processed_count, "status": "ok"}


PROCESSED_REVIEW_TASKS: set[str] = set()

def poll_and_process_review_queue() -> dict:
    """
    Polls Notion REVIEW QUEUE database for tasks where broker has selected 'Approve' or 'Reject'.
    Automatically updates the linked Document in DOCUMENTS, checks for Onboarding completion,
    and notifies the tenant on WhatsApp!
    """
    notion_review_id = os.getenv("NOTION_REVIEW_QUEUE_ID")
    notion_documents_id = os.getenv("NOTION_DOCUMENTS_ID")
    if not notion_review_id:
        return {"processed": 0, "message": "NOTION_REVIEW_QUEUE_ID not configured"}

    review_pages = get_pending_review_queue_items(notion_review_id)
    processed_count = 0

    for page in review_pages:
        page_id = page.get("id")
        if not page_id:
            continue

        props = page.get("properties", {})
        decision = props.get("Reviewer Decision", {}).get("status", {}).get("name", "")
        if decision not in {"Approve", "Reject"}:
            continue

        # Prevent re-processing the same task repeatedly
        task_marker = f"{page_id}_{decision}"
        if task_marker in PROCESSED_REVIEW_TASKS:
            continue

        reason = get_prop_value(props, "Reason") or "Broker Review Decision"
        doc_relations = props.get("Document to review", {}).get("relation", [])
        if not doc_relations:
            continue

        doc_page_id = doc_relations[0].get("id")
        try:
            doc_page = get_page(doc_page_id)
        except Exception as e:
            print(f"Error fetching linked document page {doc_page_id}: {e}")
            continue

        doc_props = doc_page.get("properties", {})
        doc_type = get_prop_value(doc_props, "Document Type") or "Document"
        tenant_name = get_prop_value(doc_props, "Tenant Name") or "Tenant"

        # Find tenant phone and onboarding page from Related Onboarding
        onb_relations = doc_props.get("Related Onboarding", {}).get("relation", [])
        onb_page = None
        onb_page_id = None
        clean_phone = ""
        onb_id_str = "1"

        if onb_relations:
            onb_page_id = onb_relations[0].get("id")
            try:
                onb_page = get_page(onb_page_id)
                o_props = onb_page.get("properties", {})
                raw_phone = get_prop_value(o_props, "Tenant Phone")
                digits = "".join(re.findall(r"\d+", raw_phone))
                if len(digits) >= 10:
                    clean_phone = f"+91{digits[-10:]}"
                tenant_name = get_prop_value(o_props, "Tenant Name") or tenant_name
                onb_id_str = get_prop_value(o_props, "Onboarding ID") or "1"
            except Exception as e:
                print(f"Error fetching onboarding page for review: {e}")

        if decision == "Approve":
            # 1. Update Document status to 'Approved'
            try:
                update_document_status(doc_page_id, "Approved")
                print(f"✅ Broker review: Document {doc_type} for {tenant_name} set to Approved!")
            except Exception as e:
                print(f"Error updating doc status: {e}")

            # 2. Check 4-document progress
            tenant_docs = []
            if onb_page_id and notion_documents_id:
                try:
                    tenant_docs = get_documents_by_onboarding(notion_documents_id, onb_page_id)
                except Exception as e:
                    print(f"Error fetching docs: {e}")

            doc_display = DOC_DISPLAY_NAMES.get(doc_type, doc_type)
            completed_count, progress_summary, all_completed = get_onboarding_progress(tenant_docs, doc_type)

            if all_completed and onb_page_id:
                update_onboarding_status(onb_page_id, "Completed")
                if clean_phone:
                    send_whatsapp_message(
                        to_phone=clean_phone,
                        message_text=(
                            f"🎉 *Congratulations {tenant_name}!* All 4 required documents have been verified and approved!\n\n"
                            f"📋 *Final Status:* 4/4 Verified (Aadhaar ✅, PAN ✅, Passport Size Photo ✅, Rent Agreement ✅)\n"
                            f"Your onboarding is now *Completed*! 🏡✨"
                        ),
                    )
                print(f"🏆 Broker review completed: ONB-{onb_id_str} ({tenant_name}) marked COMPLETED in Notion!")
            else:
                if clean_phone:
                    send_whatsapp_message(
                        to_phone=clean_phone,
                        message_text=(
                            f"✅ *Hi {tenant_name}!* Your *{doc_display}* has been reviewed & *APPROVED* by the broker! 🎉\n\n"
                            f"📊 *Verification Progress:* {progress_summary}\n"
                            f"_Please upload your remaining documents to complete onboarding._"
                        ),
                    )

        elif decision == "Reject":
            try:
                update_document_status(doc_page_id, "Processing Error")
            except Exception as e:
                print(f"Error updating doc status: {e}")

            doc_display = DOC_DISPLAY_NAMES.get(doc_type, doc_type)
            if clean_phone:
                send_whatsapp_message(
                    to_phone=clean_phone,
                    message_text=(
                        f"⚠️ *Hi {tenant_name}!* Your *{doc_display}* was rejected during broker review:\n"
                        f"_{reason}_\n\n"
                        f"Please re-upload a clear, correct document."
                    ),
                )

        PROCESSED_REVIEW_TASKS.add(task_marker)
        processed_count += 1

    return {"processed": processed_count, "status": "ok"}


def poll_and_send_pending_reminders() -> dict:
    """
    Scans Notion ONBOARDINGS database.
    If a tenant is in 'In Progress' or 'Pending Review' status,
    and has not submitted all 4 documents within the last 6 hours,
    sends an automated polite WhatsApp follow-up nudge!
    """
    notion_onboarding_id = os.getenv("NOTION_ONBOARDING_ID")
    notion_documents_id = os.getenv("NOTION_DOCUMENTS_ID")
    if not notion_onboarding_id or not notion_documents_id:
        return {"processed": 0, "message": "Notion IDs not configured"}

    pages = get_all_onboardings(notion_onboarding_id)
    reminders_sent = 0
    now = time.time()

    for page in pages:
        page_id = page.get("id")
        if not page_id:
            continue

        props = page.get("properties", {})
        status = get_prop_value(props, "Onboarding Status")
        tenant_name = get_prop_value(props, "Tenant Name") or get_prop_value(props, "Tenant Name ") or "Tenant"
        raw_phone = get_prop_value(props, "Tenant Phone")
        property_name = (
            get_prop_value(props, "Property Name")
            or get_prop_value(props, "Property Nmae")
            or get_prop_value(props, "Property/PG")
            or "your assigned property"
        )
        id_str = get_prop_value(props, "Onboarding ID") or "1"
        clean_onb_id = "".join(re.findall(r"\d+", id_str)) or id_str.replace("ONB-", "").strip()

        # Only remind tenants who are In Progress or Pending Review
        if status == "Completed":
            if page_id in REMINDER_TRACKING:
                del REMINDER_TRACKING[page_id]
                save_reminder_cache(REMINDER_TRACKING)
            continue

        if not raw_phone:
            continue

        digits = "".join(re.findall(r"\d+", raw_phone))
        if len(digits) < 10:
            continue
        clean_phone = f"+91{digits[-10:]}"

        # Only remind tenants who were already greeted
        if page_id not in GREETED_ONBOARDINGS:
            continue

        # Check time since last reminder (or greeting)
        last_reminded = REMINDER_TRACKING.get(page_id, 0.0)
        if (now - last_reminded) < REMINDER_INTERVAL_SECONDS:
            continue

        # Check tenant document progress
        try:
            tenant_docs = get_documents_by_onboarding(notion_documents_id, page_id)
        except Exception as e:
            print(f"Error checking docs for reminder: {e}")
            continue

        completed_count, progress_summary, all_completed = get_onboarding_progress(tenant_docs)

        if all_completed:
            try:
                update_onboarding_status(page_id, "Completed")
            except Exception:
                pass
            if page_id in REMINDER_TRACKING:
                del REMINDER_TRACKING[page_id]
                save_reminder_cache(REMINDER_TRACKING)
            continue

        # Identify which documents are still missing
        approved_types = set()
        for td in tenant_docs:
            td_props = td.get("properties", {})
            td_status = td_props.get("Validation Status", {}).get("status", {}).get("name", "")
            td_type = td_props.get("Document Type", {}).get("select", {}).get("name", "")
            if td_status == "Approved" and td_type:
                norm = "PASSPORT_PHOTO" if "PASSPORT" in td_type.upper() else td_type.upper()
                if norm == "AADHAAR":
                    norm = "AADHAR"
                approved_types.add(norm)

        missing_list = []
        for req_key in ["AADHAR", "PAN", "PASSPORT_PHOTO", "RENT_AGREEMENT"]:
            if req_key not in approved_types:
                missing_list.append(f"• {DOC_DISPLAY_NAMES.get(req_key, req_key)}")

        missing_docs_str = "\n".join(missing_list)

        reminder_text = (
            f"👋 *Hi {tenant_name}!* 🏡\n\n"
            f"Gentle follow-up regarding your onboarding for *{property_name}* *(ID: ONB-{clean_onb_id})*.\n\n"
            f"📊 *Current Progress:* {completed_count}/4 Documents Verified\n"
            f"⏳ *Still Needed:*\n{missing_docs_str}\n\n"
            f"Please send a clear photo or PDF here on WhatsApp to complete your verification! ✨"
        )

        try:
            send_whatsapp_message(to_phone=clean_phone, message_text=reminder_text)
            REMINDER_TRACKING[page_id] = now
            save_reminder_cache(REMINDER_TRACKING)
            create_run_log(
                event_type="WHATSAPP_FOLLOWUP_SENT",
                status="SUCCESS",
                message=f"6-Hour Follow-up sent to {tenant_name} ({clean_phone}) | Progress: {completed_count}/4",
                onboarding_id=clean_onb_id,
            )
            print(f"⏰ Sent automated 6-hour follow-up to {tenant_name} ({clean_phone}) for ONB-{clean_onb_id}")
            reminders_sent += 1
        except Exception as e:
            print(f"Error sending follow-up reminder to {clean_phone}: {e}")

    return {"reminders_sent": reminders_sent, "status": "ok"}


# =========================================================
# LIFESPAN & BACKGROUND POLLING WORKERS
# =========================================================

async def onboarding_polling_loop():
    while True:
        try:
            await asyncio.to_thread(poll_and_process_new_onboardings)
        except Exception as e:
            print(f"Error in onboarding poller: {e}")
        await asyncio.sleep(5)


async def review_queue_polling_loop():
    while True:
        try:
            await asyncio.to_thread(poll_and_process_review_queue)
        except Exception as e:
            print(f"Error in review queue poller: {e}")
        await asyncio.sleep(5)


async def reminder_polling_loop():
    while True:
        try:
            await asyncio.to_thread(poll_and_send_pending_reminders)
        except Exception as e:
            print(f"Error in reminder poller: {e}")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    onboarding_task = asyncio.create_task(onboarding_polling_loop())
    review_task = asyncio.create_task(review_queue_polling_loop())
    reminder_task = asyncio.create_task(reminder_polling_loop())
    try:
        yield
    finally:
        onboarding_task.cancel()
        review_task.cancel()
        reminder_task.cancel()


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
            save_greeted_cache(GREETED_ONBOARDINGS)
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


# =========================================================
# TWILIO INBOUND WHATSAPP WEBHOOK (AUTOMATIC PROCESSING)
# =========================================================

@app.get("/uploads/{filename:path}")
def get_uploaded_file(filename: str):
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


@app.get("/", response_class=HTMLResponse)
def root_status_page():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Doclyra.ai | Live Backend Service</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0b0f19; color: #f3f4f6; margin: 0; padding: 40px 20px; display: flex; justify-content: center; align-items: center; min-height: 80vh; }
            .card { background: #161e2e; border: 1px solid #374151; border-radius: 16px; padding: 36px; max-width: 600px; width: 100%; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5); }
            .badge { display: inline-flex; align-items: center; gap: 8px; background: rgba(16, 185, 129, 0.1); color: #10b981; padding: 6px 14px; border-radius: 9999px; font-weight: 600; font-size: 14px; border: 1px solid rgba(16, 185, 129, 0.2); }
            .dot { width: 8px; height: 8px; background: #10b981; border-radius: 50%; animation: pulse 2s infinite; }
            h1 { font-size: 28px; margin: 16px 0 8px 0; color: #ffffff; }
            p { color: #9ca3af; line-height: 1.6; font-size: 15px; margin-bottom: 24px; }
            .btn-group { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 20px; }
            .btn { display: inline-block; background: #2563eb; color: #ffffff; text-decoration: none; padding: 10px 20px; border-radius: 8px; font-weight: 500; font-size: 14px; transition: background 0.2s; }
            .btn:hover { background: #1d4ed8; }
            .btn-secondary { background: #374151; }
            .btn-secondary:hover { background: #4b5563; }
            .meta { margin-top: 28px; padding-top: 20px; border-top: 1px solid #374151; font-size: 13px; color: #6b7280; display: flex; justify-content: space-between; }
            @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="badge"><span class="dot"></span> Service Live & Running</div>
            <h1>Doclyra.ai Engine</h1>
            <p>Autonomous Tenant Document Verification & Operations Hub for Notion. Processing Aadhaar, PAN, Passport Size Photos, and Rent Agreements 24/7 via Gemini Vision AI and WhatsApp Webhooks.</p>
            <div class="btn-group">
                <a href="/docs" class="btn">Explore API Swagger Docs</a>
                <a href="https://app.notion.com/p/3c70bd156bc480d9aeece27d1e59e654" target="_blank" class="btn btn-secondary">Open Notion Hub</a>
            </div>
            <div class="meta">
                <span>Infrastructure: ZopDay Cloud (GCP)</span>
                <span>Track: Notion Track</span>
            </div>
        </div>
    </body>
    </html>
    """


@app.post("/whatsapp/webhook")
@app.post("/")
def whatsapp_webhook(
    From: str = Form(""),
    Body: str = Form(""),
    NumMedia: str = Form("0"),
    MediaUrl0: str | None = Form(None),
    MediaContentType0: str | None = Form(None),
    ProfileName: str | None = Form(None),
):
    """
    Twilio Inbound WhatsApp Webhook.
    Receives incoming WhatsApp messages, photos, and PDFs sent by tenants.
    Automatically classifies with Gemini, extracts, validates, updates Notion, and replies on WhatsApp.
    """
    from_phone = From
    clean_phone = from_phone.replace("whatsapp:", "").strip()
    body = Body.strip()
    num_media = int(NumMedia) if NumMedia.isdigit() else 0
    media_url = MediaUrl0
    media_type = MediaContentType0
    profile_name = ProfileName or ""

    print(f"📩 Inbound WhatsApp from {clean_phone} | Media count: {num_media} | Body: {body}")

    # Look up tenant's Onboarding in Notion using phone number
    notion_onboarding_id = os.getenv("NOTION_ONBOARDING_ID")
    notion_documents_id = os.getenv("NOTION_DOCUMENTS_ID")
    target_digits = "".join(re.findall(r"\d+", clean_phone))[-10:]

    onb_page = None
    if notion_onboarding_id and target_digits:
        all_pages = get_all_onboardings(notion_onboarding_id)
        for p in all_pages:
            props = p.get("properties", {})
            p_phone = extract_notion_text(props.get("Tenant Phone"))
            p_digits = "".join(re.findall(r"\d+", p_phone))[-10:]
            if p_digits and p_digits == target_digits:
                onb_page = p
                break
        if not onb_page and all_pages:
            onb_page = all_pages[0]

    onb_id_str = "1"
    tenant_name = profile_name or "Tenant"
    property_name = "your assigned property"
    if onb_page:
        props = onb_page.get("properties", {})
        raw_onb_id = extract_notion_text(props.get("Onboarding ID"))
        onb_id_str = raw_onb_id.replace("ONB-", "").strip() if raw_onb_id else "1"
        t_name = extract_notion_text(props.get("Tenant Name"))
        if t_name:
            tenant_name = t_name
        property_name = (
            get_prop_value(props, "Property Name")
            or get_prop_value(props, "Property Nmae")
            or get_prop_value(props, "Property/PG")
            or "your assigned property"
        )

    # If NO media attached (Text message only)
    if num_media == 0 or not media_url:
        reply_text = (
            f"👋 *Hi {tenant_name}!* 🏡\n\n"
            f"Please send a clear photo or PDF of your document (*Aadhaar Card, PAN Card, Passport Photo, or Rent Agreement*) "
            f"so our AI system can automatically verify it for your onboarding *(ID: ONB-{onb_id_str})*."
        )
        send_whatsapp_message(to_phone=clean_phone, message_text=reply_text)
        return Response(content="<Response></Response>", media_type="application/xml")

    # If media attached: Download from Twilio
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")

    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)
    doc_num_id = int(time.time() * 1000) % 1000000
    ext = "jpg"
    if "pdf" in str(media_type).lower():
        ext = "pdf"
    elif "png" in str(media_type).lower():
        ext = "png"
    storage_filename = f"onb_{onb_id_str}_{doc_num_id}_wa.{ext}"
    storage_path = os.path.join(upload_dir, storage_filename)

    try:
        resp = requests.get(
            media_url,
            auth=(account_sid or "", auth_token or ""),
            timeout=30,
        )
        if resp.status_code != 200:
            send_whatsapp_message(
                to_phone=clean_phone,
                message_text="⚠️ Could not download your document from WhatsApp. Please try sending it again.",
            )
            return Response(content="<Response></Response>", media_type="application/xml")

        with open(storage_path, "wb") as f:
            f.write(resp.content)
    except Exception as e:
        print(f"Error downloading Twilio media: {e}")
        send_whatsapp_message(
            to_phone=clean_phone,
            message_text="⚠️ Error receiving your file. Please try re-uploading.",
        )
        return Response(content="<Response></Response>", media_type="application/xml")

    content_type_str = media_type if media_type else ("application/pdf" if ext == "pdf" else "image/jpeg")

    create_run_log(
        event_type="DOCUMENT_RECEIVED",
        status="RECEIVED",
        message=f"WhatsApp upload: {storage_filename} from {clean_phone}",
        onboarding_id=onb_id_str,
        document_id=doc_num_id,
    )

    # 1. Quality Inspection
    inspection = inspect_document(storage_path, content_type_str)
    quality_status = inspection.get("quality", "GOOD")
    quality_reason = str(inspection.get("quality_reason", ""))

    if quality_status != "GOOD":
        if notion_documents_id:
            create_document_item(
                database_id=notion_documents_id,
                document_id=doc_num_id,
                doc_type="UNKNOWN",
                validation_status="Processing Error",
                onboarding_page_id=onb_page.get("id") if onb_page else None,
            )
        send_rejection_notification(
            tenant_phone=clean_phone,
            doc_type="Document",
            layman_reason=f"Image quality issue: {quality_reason}",
            tenant_name=tenant_name,
        )
        return Response(content="<Response></Response>", media_type="application/xml")

    # 2. AI Classification with Gemini
    try:
        classified_type = classify_document(storage_path, content_type_str)
    except Exception as e:
        classified_type = "UNKNOWN"
        print(f"Classification error: {e}")

    if classified_type == "UNKNOWN":
        if notion_documents_id:
            create_document_item(
                database_id=notion_documents_id,
                document_id=doc_num_id,
                doc_type="UNKNOWN",
                validation_status="Processing Error",
                onboarding_page_id=onb_page.get("id") if onb_page else None,
            )
        send_rejection_notification(
            tenant_phone=clean_phone,
            doc_type="Document",
            layman_reason="Unrecognized document type. Please upload a clear Aadhaar, PAN, Passport Photo, or Rent Agreement.",
            tenant_name=tenant_name,
        )
        return Response(content="<Response></Response>", media_type="application/xml")

    # 3. AI Extraction
    extracted_data = {}
    if classified_type in ["PAN", "AADHAAR", "RENT_AGREEMENT"]:
        try:
            extracted_data = extract_document_data(
                file_path=storage_path,
                mime_type=content_type_str,
                document_type=classified_type,
            )
        except Exception as e:
            print(f"Extraction error: {e}")

    # 4. Validation
    if classified_type == "PAN":
        validation_res = validate_pan(extracted_data, expected_name=tenant_name)
    elif classified_type == "AADHAAR":
        validation_res = validate_aadhaar(extracted_data, expected_name=tenant_name)
    elif classified_type == "RENT_AGREEMENT":
        validation_res = validate_rent_agreement(extracted_data, expected_name=tenant_name)
    elif classified_type == "PASSPORT_PHOTO":
        validation_res = validate_passport_photo(inspection)
    else:
        validation_res = {"valid": False, "status": "REJECTED", "reason": "Unsupported document"}

    if validation_res.get("valid") is True or validation_res.get("status") in {"VALID", "APPROVED"}:
        final_status = "APPROVED"
    elif validation_res.get("status") == "MANUAL_REVIEW":
        final_status = "MANUAL_REVIEW"
    else:
        final_status = "REJECTED"

    extracted_num = validation_res.get("extracted_number") or extracted_data.get("pan_number") or extracted_data.get("aadhaar_number")
    extracted_name_val = validation_res.get("extracted_name") or extracted_data.get("name")

    # 5. Determine File View Link for Broker
    filename = os.path.basename(storage_path)
    file_view_link = f"http://localhost:8000/uploads/{filename}"

    # 6. Sync to Notion DOCUMENTS
    doc_page = None
    if notion_documents_id:
        doc_page = create_document_item(
            database_id=notion_documents_id,
            document_id=doc_num_id,
            doc_type=classified_type,
            name=extracted_name_val,
            number=extracted_num,
            validation_status=final_status,
            onboarding_page_id=onb_page.get("id") if onb_page else None,
            file_url=file_view_link,
        )

    # 7. Outcome handling & Automatic Status Progression
    doc_display = DOC_DISPLAY_NAMES.get(classified_type, classified_type)
    detailed_error = (
        validation_res.get("error")
        or " | ".join(validation_res.get("errors", []))
        or validation_res.get("reason")
        or "Details need broker verification"
    )

    if final_status == "APPROVED":
        create_run_log(
            event_type="DOCUMENT_VALIDATION",
            status="APPROVED",
            message=f"{doc_display} verified and approved for {tenant_name}",
            onboarding_id=onb_id_str,
            document_id=doc_num_id,
        )

        # Check 4-document completion progress
        tenant_docs = []
        if onb_page and notion_documents_id:
            try:
                tenant_docs = get_documents_by_onboarding(notion_documents_id, onb_page.get("id"))
            except Exception as e:
                print(f"Error fetching onboarding documents: {e}")

        completed_count, progress_summary, all_completed = get_onboarding_progress(tenant_docs, classified_type)

        if all_completed and onb_page:
            update_onboarding_status(onb_page.get("id"), "Completed")
            send_whatsapp_message(
                to_phone=clean_phone,
                message_text=(
                    f"🎉 *Congratulations {tenant_name}!* All 4 required documents have been verified and approved!\n\n"
                    f"📋 *Final Status:* 4/4 Verified (Aadhaar ✅, PAN ✅, Passport Size Photo ✅, Rent Agreement ✅)\n"
                    f"Your onboarding for *{property_name}* is now *Completed*! 🏡✨"
                ),
            )
            create_run_log(
                event_type="ONBOARDING_COMPLETED",
                status="SUCCESS",
                message=f"All 4 documents approved for {tenant_name} (ONB-{onb_id_str})",
                onboarding_id=onb_id_str,
            )
            print(f"🏆 Onboarding ONB-{onb_id_str} ({tenant_name}) marked COMPLETED in Notion!")
        else:
            send_whatsapp_message(
                to_phone=clean_phone,
                message_text=(
                    f"✅ *Hi {tenant_name}!* Your *{doc_display}* has been verified & approved! 🎉\n\n"
                    f"📊 *Verification Progress:* {progress_summary}\n"
                    f"_Please send your remaining documents to complete onboarding._"
                ),
            )

    elif final_status == "MANUAL_REVIEW":
        # Automatically flip Onboarding Status to 'Pending Review'
        if onb_page:
            try:
                update_onboarding_status(onb_page.get("id"), "Pending Review")
            except Exception as e:
                print(f"Error setting status to Pending Review: {e}")

        notion_review_id = os.getenv("NOTION_REVIEW_QUEUE_ID")
        if notion_review_id and doc_page:
            try:
                create_review_queue_item(
                    database_id=notion_review_id,
                    task_title=f"REV-{doc_num_id}",
                    review_notes=detailed_error,
                    stop_reason=detailed_error,
                    document_page_id=doc_page.get("id"),
                )
            except Exception as e:
                print(f"Error creating review item: {e}")

        send_whatsapp_message(
            to_phone=clean_phone,
            message_text=(
                f"📋 *Hi {tenant_name}!* Your *{doc_display}* has been received and forwarded for broker review.\n\n"
                f"🔍 *Reason:* _{detailed_error}_\n"
                f"We will update you as soon as the broker reviews it!"
            ),
        )
    else:  # REJECTED
        send_whatsapp_message(
            to_phone=clean_phone,
            message_text=(
                f"⚠️ *Issue with your {doc_display}:*\n"
                f"_{detailed_error}_\n\n"
                f"Please re-upload a clear, valid photo/document."
            ),
        )

    return Response(content="<Response></Response>", media_type="application/xml")