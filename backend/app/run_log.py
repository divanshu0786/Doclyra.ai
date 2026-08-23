import os

from sqlalchemy.orm import Session

from .models import RunLog
from .notion_service import create_run_log_item


def create_run_log(
    db: Session,
    event_type: str,
    status: str,
    message: str | None = None,
    onboarding_id: int | None = None,
    document_id: int | None = None,
):
    """
    Create a Run Log entry in the application database
    and synchronize it to Notion.
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

    # ---------------------------------------------
    # Sync Run Log to Notion
    # ---------------------------------------------

    notion_run_log_id = os.getenv(
        "NOTION_RUN_LOG_ID"
    )

    if notion_run_log_id:

        try:

            create_run_log_item(
                database_id=notion_run_log_id,
                event_type=event_type,
                status=status,
                message=message or "",
                onboarding_id=onboarding_id,
            )

        except Exception as e:

            print(
                f"Notion RUN LOG sync failed: {e}"
            )

    return log