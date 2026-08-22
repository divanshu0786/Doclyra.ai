from sqlalchemy.orm import Session

from .models import RunLog


def create_run_log(
    db: Session,
    event_type: str,
    status: str,
    message: str | None = None,
    onboarding_id: int | None = None,
    document_id: int | None = None,
):
    """
    Create a Run Log entry for an important backend event.
    """

    log = RunLog(
        onboarding_id=onboarding_id,
        document_id=document_id,
        event_type=event_type,
        status=status,
        message=message,
    )

    db.add(log)
    db.commit()
    db.refresh(log)

    return log