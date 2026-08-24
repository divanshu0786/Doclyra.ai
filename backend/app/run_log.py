import os
from .notion_service import create_run_log_item


def create_run_log(
    event_type: str,
    status: str,
    message: str | None = None,
    onboarding_id: int | str | None = None,
    document_id: int | str | None = None,
    db=None,  # optional param for backward compatibility
):
    """
    Synchronize Run Log entry directly to Notion RUN LOG database.
    """
    notion_run_log_id = os.getenv("NOTION_RUN_LOG_ID")
    log_result = None

    if notion_run_log_id:
        try:
            log_result = create_run_log_item(
                database_id=notion_run_log_id,
                event_type=event_type,
                status=status,
                message=message or "",
                onboarding_id=int(onboarding_id) if isinstance(onboarding_id, (int, str)) and str(onboarding_id).isdigit() else None,
            )
        except Exception as e:
            print(f"Notion RUN LOG sync failed: {e}")

    return {
        "event_type": event_type,
        "status": status,
        "message": message,
        "onboarding_id": onboarding_id,
        "document_id": document_id,
        "notion_log_id": log_result.get("id") if log_result else None,
    }