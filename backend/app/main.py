import os
import shutil

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import (
    Document,
    Onboarding,
    Property,
    Tenant,
    RunLog,
    ReviewDecision,
)
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
from pydantic import BaseModel
from .notion_service import (
    get_database,
    get_data_source,
)

class ReviewRequest(BaseModel):
    decision: str
    reason: str | None = None


app = FastAPI(
    title="Tenant Document Automation",
    version="0.1.0",
)


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health(
    db: Session = Depends(get_db),
):
    try:
        db.execute(text("SELECT 1"))

        return {
            "status": "ok",
            "database": "connected",
        }

    except Exception as e:
        return {
            "status": "error",
            "database": "unavailable",
            "detail": str(e),
        }
# =========================================================
# NOTION CONNECTION TEST
# =========================================================

@app.get("/notion/test")
def notion_test():

    databases = {
        "review_queue": os.getenv(
            "NOTION_REVIEW_QUEUE_ID"
        ),
        "onboarding": os.getenv(
            "NOTION_ONBOARDING_ID"
        ),
        "run_log": os.getenv(
            "NOTION_RUN_LOG_ID"
        ),
    }

    results = {}

    for name, database_id in databases.items():

        if not database_id:

            results[name] = {
                "status": "ERROR",
                "message": "Database ID is missing.",
            }

            continue

        try:

            database = get_database(
                database_id
            )

            data_source = get_data_source(
                database_id
            )

            results[name] = {
                "status": "CONNECTED",
                "database_id": database_id,
                "database_name": database.get(
                    "title",
                    [{}],
                )[0].get(
                    "plain_text",
                    "",
                ) if database.get("title") else "",
                "data_source_id": data_source.get(
                    "id"
                ),
                "properties": list(
                    data_source.get(
                        "properties",
                        {}
                    ).keys()
                ),
            }

        except Exception as e:

            results[name] = {
                "status": "ERROR",
                "message": str(e),
            }

    return results
# =========================================================
# DATABASE SETUP
# =========================================================

@app.post("/setup")
def setup_database():
    Base.metadata.create_all(
        bind=engine
    )

    return {
        "status": "ok",
        "message": "Database tables created",
    }


# =========================================================
# PROPERTIES
# =========================================================

@app.post("/properties")
def create_property(
    name: str,
    address: str,
    db: Session = Depends(get_db),
):
    property_item = Property(
        name=name,
        address=address,
    )

    db.add(property_item)
    db.commit()
    db.refresh(property_item)

    return {
        "id": property_item.id,
        "name": property_item.name,
        "address": property_item.address,
    }


# =========================================================
# TENANTS
# =========================================================

@app.post("/tenants")
def create_tenant(
    property_id: int,
    name: str,
    phone: str,
    unit_number: str,
    db: Session = Depends(get_db),
):
    property_item = db.get(
        Property,
        property_id,
    )

    if not property_item:
        raise HTTPException(
            status_code=404,
            detail="Property not found",
        )

    tenant = Tenant(
        property_id=property_id,
        name=name,
        phone=phone,
        unit_number=unit_number,
    )

    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    return {
        "id": tenant.id,
        "property_id": tenant.property_id,
        "name": tenant.name,
        "phone": tenant.phone,
        "unit_number": tenant.unit_number,
    }


# =========================================================
# ONBOARDING
# =========================================================

@app.post("/onboardings")
def create_onboarding(
    tenant_id: int,
    db: Session = Depends(get_db),
):
    tenant = db.get(
        Tenant,
        tenant_id,
    )

    if not tenant:
        raise HTTPException(
            status_code=404,
            detail="Tenant not found",
        )

    onboarding = Onboarding(
        tenant_id=tenant_id,
    )

    db.add(onboarding)
    db.commit()
    db.refresh(onboarding)

    return {
        "id": onboarding.id,
        "tenant_id": onboarding.tenant_id,
        "status": onboarding.status,
        "created_at": onboarding.created_at,
    }


# =========================================================
# ONBOARDING CHECKLIST
# =========================================================

@app.get("/onboardings/{onboarding_id}/checklist")
def onboarding_checklist(
    onboarding_id: int,
    db: Session = Depends(get_db),
):
    onboarding = db.get(
        Onboarding,
        onboarding_id,
    )

    if not onboarding:
        raise HTTPException(
            status_code=404,
            detail="Onboarding not found",
        )

    return get_onboarding_checklist(
        db,
        onboarding_id,
    )


# =========================================================
# ONBOARDING STATUS
# =========================================================

@app.get("/onboardings/{onboarding_id}/status")
def onboarding_status(
    onboarding_id: int,
    db: Session = Depends(get_db),
):
    onboarding = db.get(
        Onboarding,
        onboarding_id,
    )

    if not onboarding:
        raise HTTPException(
            status_code=404,
            detail="Onboarding not found",
        )

    return evaluate_onboarding_status(
        db,
        onboarding_id,
    )


# =========================================================
# DOCUMENT UPLOAD
# =========================================================

@app.post("/documents/upload")
def upload_document(
    onboarding_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # =====================================================
    # 1. CHECK ONBOARDING
    # =====================================================

    onboarding = db.get(
        Onboarding,
        onboarding_id,
    )

    if not onboarding:
        raise HTTPException(
            status_code=404,
            detail="Onboarding not found",
        )

    # =====================================================
    # 2. CHECK FILE TYPE
    # =====================================================

    allowed_types = {
        "application/pdf",
        "image/jpeg",
        "image/png",
    }

    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, JPG, and PNG files are allowed",
        )

    # =====================================================
    # 3. CREATE UPLOAD DIRECTORY
    # =====================================================

    upload_dir = "uploads"

    os.makedirs(
        upload_dir,
        exist_ok=True,
    )

    # =====================================================
    # 4. MAKE FILENAME SAFE
    # =====================================================

    filename = os.path.basename(
        file.filename or "document"
    )

    # =====================================================
    # 5. SAVE FILE
    # =====================================================

    storage_path = os.path.join(
        upload_dir,
        f"onboarding_{onboarding_id}_{filename}",
    )

    with open(
        storage_path,
        "wb",
    ) as buffer:
        shutil.copyfileobj(
            file.file,
            buffer,
        )

    # =====================================================
    # 6. CREATE DOCUMENT DATABASE RECORD
    # =====================================================

    document = Document(
        onboarding_id=onboarding_id,
        filename=filename,
        mime_type=file.content_type,
        source="WEB_UPLOAD",
        storage_path=storage_path,
        document_type="UNKNOWN",
        status="RECEIVED",
        extracted_data={},
    )

    db.add(document)
    db.flush()

    # =====================================================
    # RUN LOG: DOCUMENT RECEIVED
    # =====================================================

    create_run_log(
        db=db,
        event_type="DOCUMENT_RECEIVED",
        status="RECEIVED",
        message=f"Document {filename} received for processing.",
        onboarding_id=onboarding_id,
        document_id=document.id,
    )

    # =====================================================
    # 7. INSPECT DOCUMENT QUALITY
    # =====================================================

    inspection = inspect_document(
        storage_path,
        file.content_type,
    )

    document.quality_score = inspection[
        "quality_score"
    ]

    document.quality_reason = inspection[
        "quality_reason"
    ]

    # =====================================================
    # RUN LOG: QUALITY CHECK
    # =====================================================

    if inspection["quality"] == "GOOD":

        create_run_log(
            db=db,
            event_type="QUALITY_CHECK",
            status="GOOD",
            message=inspection["quality_reason"],
            onboarding_id=onboarding_id,
            document_id=document.id,
        )

    else:

        create_run_log(
            db=db,
            event_type="QUALITY_CHECK",
            status="QUALITY_FAILED",
            message=inspection["quality_reason"],
            onboarding_id=onboarding_id,
            document_id=document.id,
        )

    # =====================================================
    # 8. STOP IF QUALITY IS BAD
    # =====================================================

    if inspection["quality"] != "GOOD":

        document.document_type = "UNKNOWN"
        document.status = "QUALITY_FAILED"
        document.extracted_data = {}

        db.commit()
        db.refresh(document)

        checklist = get_onboarding_checklist(
            db,
            onboarding_id,
        )

        return {
            "id": document.id,
            "onboarding_id": document.onboarding_id,
            "filename": document.filename,
            "mime_type": document.mime_type,
            "document_type": document.document_type,
            "status": document.status,
            "extracted_data": {},
            "validation": None,
            "inspection": inspection,
            "checklist": checklist,
        }

    # =====================================================
    # 9. CLASSIFY DOCUMENT WITH GEMINI
    # =====================================================

    try:

        document_type = classify_document(
            storage_path,
            file.content_type,
        )

    except RuntimeError as e:

        document.status = "PROCESSING_ERROR"
        document.document_type = "UNKNOWN"
        document.extracted_data = {}

        create_run_log(
            db=db,
            event_type="CLASSIFICATION_FAILED",
            status="PROCESSING_ERROR",
            message=str(e),
            onboarding_id=onboarding_id,
            document_id=document.id,
        )

        db.commit()
        db.refresh(document)

        return {
            "id": document.id,
            "onboarding_id": document.onboarding_id,
            "filename": document.filename,
            "mime_type": document.mime_type,
            "document_type": "UNKNOWN",
            "status": "PROCESSING_ERROR",
            "extracted_data": {},
            "validation": None,
            "inspection": inspection,
            "error": str(e),
        }

    document.document_type = document_type

    # =====================================================
    # RUN LOG: DOCUMENT CLASSIFIED
    # =====================================================

    create_run_log(
        db=db,
        event_type="DOCUMENT_CLASSIFIED",
        status="CLASSIFIED",
        message=f"Document classified as {document_type}.",
        onboarding_id=onboarding_id,
        document_id=document.id,
    )

    # =====================================================
    # 10. EXTRACT DOCUMENT DATA
    # =====================================================

    extracted_data = {}

    if document_type in {
        "PAN",
        "AADHAAR",
        "RENT_AGREEMENT",
    }:

        try:

            extracted_data = extract_document_data(
                storage_path,
                file.content_type,
                document_type,
            )

        except RuntimeError as e:

            document.status = "PROCESSING_ERROR"
            document.extracted_data = {}

            create_run_log(
                db=db,
                event_type="EXTRACTION_FAILED",
                status="PROCESSING_ERROR",
                message=str(e),
                onboarding_id=onboarding_id,
                document_id=document.id,
            )

            db.commit()
            db.refresh(document)

            return {
                "id": document.id,
                "onboarding_id": document.onboarding_id,
                "filename": document.filename,
                "mime_type": document.mime_type,
                "document_type": document.document_type,
                "status": "PROCESSING_ERROR",
                "extracted_data": {},
                "validation": None,
                "inspection": inspection,
                "error": str(e),
            }

    document.extracted_data = extracted_data

    # =====================================================
    # RUN LOG: DATA EXTRACTED
    # =====================================================

    create_run_log(
        db=db,
        event_type="DATA_EXTRACTED",
        status="EXTRACTED",
        message=f"Data extracted from {document_type} document.",
        onboarding_id=onboarding_id,
        document_id=document.id,
    )

    # =====================================================
    # 11. VALIDATE DOCUMENT
    # =====================================================

    validation = None

    # -----------------------------------------------------
    # PAN
    # -----------------------------------------------------

    if document_type == "PAN":

        validation = validate_pan(
            extracted_data
        )

        if validation["valid"]:
            document.status = "APPROVED"
        else:
            document.status = "MANUAL_REVIEW"

    # -----------------------------------------------------
    # AADHAAR
    # -----------------------------------------------------

    elif document_type == "AADHAAR":

        validation = validate_aadhaar(
            extracted_data
        )

        if validation["valid"]:
            document.status = "APPROVED"
        else:
            document.status = "MANUAL_REVIEW"

    # -----------------------------------------------------
    # RENT AGREEMENT
    # -----------------------------------------------------

    elif document_type == "RENT_AGREEMENT":

        validation = validate_rent_agreement(
            extracted_data
        )

        if validation["valid"]:
            document.status = "APPROVED"
        else:
            document.status = "MANUAL_REVIEW"

    # -----------------------------------------------------
    # UNKNOWN
    # -----------------------------------------------------

    else:

        document.status = "MANUAL_REVIEW"

    # =====================================================
    # RUN LOG: DOCUMENT VALIDATED
    # =====================================================

    if validation:

        create_run_log(
            db=db,
            event_type="DOCUMENT_VALIDATED",
            status=validation["status"],
            message=(
                "Document validation passed."
                if validation["valid"]
                else "Document requires manual review."
            ),
            onboarding_id=onboarding_id,
            document_id=document.id,
        )

    # =====================================================
    # 12. SAVE DATABASE CHANGES
    # =====================================================

    db.commit()
    db.refresh(document)

    # =====================================================
    # 13. GET ONBOARDING CHECKLIST
    # =====================================================

    checklist = get_onboarding_checklist(
        db,
        onboarding_id,
    )

    # =====================================================
    # 14. RETURN COMPLETE RESULT
    # =====================================================

    return {
        "id": document.id,
        "onboarding_id": document.onboarding_id,
        "filename": document.filename,
        "mime_type": document.mime_type,
        "document_type": document.document_type,
        "status": document.status,
        "extracted_data": document.extracted_data,
        "validation": validation,
        "inspection": inspection,
        "checklist": checklist,
    }


# =========================================================
# APPROVE DOCUMENT
# =========================================================

@app.post("/documents/{document_id}/approve")
def approve_document(
    document_id: int,
    db: Session = Depends(get_db),
):
    document = db.get(
        Document,
        document_id,
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    if document.status not in {
        "MANUAL_REVIEW",
        "READY_FOR_REVIEW",
    }:
        raise HTTPException(
            status_code=400,
            detail=(
                "Document cannot be approved "
                f"from status {document.status}"
            ),
        )

    # ---------------------------------------------
    # Approve document
    # ---------------------------------------------

    document.status = "APPROVED"

    # ---------------------------------------------
    # Run Log: document approved
    # ---------------------------------------------

    create_run_log(
        db=db,
        event_type="DOCUMENT_APPROVED",
        status="APPROVED",
        message=(
            f"Document {document.id} manually approved."
        ),
        onboarding_id=document.onboarding_id,
        document_id=document.id,
    )

    db.commit()
    db.refresh(document)

    # ---------------------------------------------
    # Recalculate onboarding status
    # ---------------------------------------------

    checklist = get_onboarding_checklist(
        db,
        document.onboarding_id,
    )

    return {
        "document_id": document.id,
        "document_type": document.document_type,
        "status": document.status,
        "onboarding": checklist,
    }

    # =====================================================
    # SAVE HUMAN REVIEW DECISION
    # =====================================================

    review = ReviewDecision(
        document_id=document.id,
        decision="APPROVED",
        reason="Approved by human reviewer.",
    )

    db.add(review)

    # =====================================================
    # UPDATE DOCUMENT
    # =====================================================

    document.status = "APPROVED"

    # =====================================================
    # RUN LOG: HUMAN APPROVAL
    # =====================================================

    create_run_log(
        db=db,
        event_type="HUMAN_APPROVAL",
        status="APPROVED",
        message="Document approved by human reviewer.",
        onboarding_id=document.onboarding_id,
        document_id=document.id,
    )

    db.commit()
    db.refresh(document)
    db.refresh(review)

    # =====================================================
    # GET UPDATED CHECKLIST
    # =====================================================

    checklist = get_onboarding_checklist(
        db,
        document.onboarding_id,
    )

    return {
        "document_id": document.id,
        "document_type": document.document_type,
        "status": document.status,
        "review": {
            "decision": review.decision,
            "reason": review.reason,
        },
        "onboarding": checklist,
    }


# =========================================================
# REQUEST DOCUMENT RESEND
# =========================================================

@app.post("/documents/{document_id}/resend")
def resend_document(
    document_id: int,
    db: Session = Depends(get_db),
):
    document = db.get(
        Document,
        document_id,
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    # ---------------------------------------------
    # Mark document for resend
    # ---------------------------------------------

    document.status = "RESEND_REQUIRED"

    # ---------------------------------------------
    # Run Log: resend requested
    # ---------------------------------------------

    create_run_log(
        db=db,
        event_type="DOCUMENT_RESEND_REQUESTED",
        status="RESEND_REQUIRED",
        message=(
            f"Document {document.id} requires a new upload."
        ),
        onboarding_id=document.onboarding_id,
        document_id=document.id,
    )

    db.commit()
    db.refresh(document)

    # ---------------------------------------------
    # Recalculate onboarding status
    # ---------------------------------------------

    checklist = get_onboarding_checklist(
        db,
        document.onboarding_id,
    )

    return {
        "document_id": document.id,
        "document_type": document.document_type,
        "status": document.status,
        "onboarding": checklist,
    }
    # =====================================================
    # SAVE HUMAN REVIEW DECISION
    # =====================================================

    review = ReviewDecision(
        document_id=document.id,
        decision="REJECTED",
        reason="Document rejected. Resubmission required.",
    )

    db.add(review)

    # =====================================================
    # UPDATE DOCUMENT
    # =====================================================

    document.status = "RESEND_REQUIRED"

    # =====================================================
    # RUN LOG: HUMAN REJECTION
    # =====================================================

    create_run_log(
        db=db,
        event_type="HUMAN_REJECTION",
        status="REJECTED",
        message="Document rejected. Resubmission required.",
        onboarding_id=document.onboarding_id,
        document_id=document.id,
    )

    db.commit()
    db.refresh(document)
    db.refresh(review)

    # =====================================================
    # GET UPDATED CHECKLIST
    # =====================================================

    checklist = get_onboarding_checklist(
        db,
        document.onboarding_id,
    )

    return {
        "document_id": document.id,
        "document_type": document.document_type,
        "status": document.status,
        "review": {
            "decision": review.decision,
            "reason": review.reason,
        },
        "onboarding": checklist,
    }


# =========================================================
# GENERATE RENT AGREEMENT
# =========================================================

@app.post("/rent-agreements")
def create_rent_agreement(
    data: dict,
):
    try:

        pdf_file = generate_rent_agreement(
            data
        )

        return StreamingResponse(
            pdf_file,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    'attachment; filename="rent_agreement.pdf"'
                )
            },
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to generate rent agreement: "
                f"{str(e)}"
            ),
        )


# =========================================================
# RUN LOGS
# =========================================================

@app.get("/run-logs")
def get_run_logs(
    onboarding_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(
        RunLog
    )

    if onboarding_id is not None:

        query = query.filter(
            RunLog.onboarding_id == onboarding_id
        )

    logs = (
        query
        .order_by(
            RunLog.created_at.desc()
        )
        .all()
    )

    return [
        {
            "id": log.id,
            "onboarding_id": log.onboarding_id,
            "document_id": log.document_id,
            "event_type": log.event_type,
            "status": log.status,
            "message": log.message,
            "created_at": log.created_at,
        }
        for log in logs
    ]