from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class OnboardingStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    COMPLETED = "COMPLETED"


class DocumentStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    QUALITY_FAILED = "QUALITY_FAILED"
    RESEND_REQUIRED = "RESEND_REQUIRED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED = "APPROVED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    PROCESSING_ERROR = "PROCESSING_ERROR"


class DocumentType(str, Enum):
    UNKNOWN = "UNKNOWN"
    AADHAAR = "AADHAAR"
    PAN = "PAN"
    RENT_AGREEMENT = "RENT_AGREEMENT"


class ReviewDecision(BaseModel):
    decision: str
    reason: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentModel(BaseModel):
    id: str | int
    onboarding_id: str | int
    filename: str
    mime_type: str
    source: str = "WEB_UPLOAD"
    storage_path: str
    document_type: DocumentType = DocumentType.UNKNOWN
    status: DocumentStatus = DocumentStatus.RECEIVED
    extracted_data: dict = Field(default_factory=dict)
    quality_score: float | None = None
    quality_reason: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class OnboardingModel(BaseModel):
    id: str | int
    tenant_name: str
    property_name: str | None = None
    status: OnboardingStatus = OnboardingStatus.IN_PROGRESS
    created_at: datetime = Field(default_factory=datetime.utcnow)