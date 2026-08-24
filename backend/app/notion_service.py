import json
import os
from typing import Any
from urllib import request, error
from dotenv import load_dotenv

load_dotenv()

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionAPIError(Exception):
    pass


def _get_token() -> str:
    token = os.getenv("NOTION_ACCESS_TOKEN")
    if not token:
        raise NotionAPIError("NOTION_ACCESS_TOKEN is not configured.")
    return token


def _request(
    method: str,
    endpoint: str,
    body: dict | None = None,
) -> dict:
    url = f"{NOTION_API_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {_get_token()}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with request.urlopen(req) as response:
            response_body = response.read().decode("utf-8")
            if not response_body:
                return {}
            return json.loads(response_body)
    except error.HTTPError as e:
        response_body = e.read().decode("utf-8")
        raise NotionAPIError(f"Notion API error {e.code}: {response_body}")
    except error.URLError as e:
        raise NotionAPIError(f"Could not connect to Notion: {e}")


def get_database(database_id: str) -> dict:
    return _request("GET", f"/databases/{database_id}")


def query_database(
    database_id: str,
    filter_body: dict | None = None,
    sorts: list | None = None,
) -> dict:
    body: dict[str, Any] = {}
    if filter_body:
        body["filter"] = filter_body
    if sorts:
        body["sorts"] = sorts

    return _request("POST", f"/databases/{database_id}/query", body)


def create_page(
    database_id: str,
    properties: dict[str, Any],
) -> dict:
    return _request(
        "POST",
        "/pages",
        {
            "parent": {
                "database_id": database_id,
            },
            "properties": properties,
        },
    )


def update_page(
    page_id: str,
    properties: dict[str, Any],
) -> dict:
    return _request(
        "PATCH",
        f"/pages/{page_id}",
        {
            "properties": properties,
        },
    )


# =========================================================
# ONBOARDINGS
# =========================================================

def create_onboarding_item(
    database_id: str,
    onboarding_id: int | str,
    tenant_name: str,
    status: str = "In Progress",
    property_name: str | None = None,
) -> dict:
    valid_statuses = {"In Progress", "Pending Review", "Blocked", "Completed"}
    chosen_status = status if status in valid_statuses else "In Progress"

    props: dict[str, Any] = {
        "Onboarding ID": {
            "title": [
                {
                    "text": {
                        "content": f"ONB-{onboarding_id}"
                    }
                }
            ]
        },
        "Tenant Name": {
            "rich_text": [
                {
                    "text": {
                        "content": tenant_name or ""
                    }
                }
            ]
        },
        "Onboarding Status": {
            "status": {
                "name": chosen_status
            }
        },
    }

    if property_name:
        props["Property/PG"] = {
            "select": {
                "name": property_name
            }
        }

    return create_page(database_id, props)


def get_onboarding_by_id(database_id: str, onboarding_id: int | str) -> dict | None:
    target_id = f"ONB-{onboarding_id}" if not str(onboarding_id).startswith("ONB-") else str(onboarding_id)
    res = query_database(
        database_id,
        filter_body={
            "property": "Onboarding ID",
            "title": {
                "equals": target_id
            }
        }
    )
    results = res.get("results", [])
    return results[0] if results else None


def update_onboarding_status(page_id: str, status: str) -> dict:
    valid_statuses = {"In Progress", "Pending Review", "Blocked", "Completed"}
    chosen_status = status if status in valid_statuses else "In Progress"

    return update_page(
        page_id,
        {
            "Onboarding Status": {
                "status": {
                    "name": chosen_status
                }
            }
        }
    )


# =========================================================
# DOCUMENTS
# =========================================================

def create_document_item(
    database_id: str,
    document_id: int | str,
    doc_type: str,
    name: str | None = None,
    number: str | None = None,
    validation_status: str = "Ready for review",
    onboarding_page_id: str | None = None,
) -> dict:
    type_map = {
        "AADHAAR": "AADHAR",
        "AADHAR": "AADHAR",
        "PAN": "PAN",
        "RENT_AGREEMENT": "RENT_AGREEMENT",
    }
    doc_type_val = type_map.get(doc_type.upper())

    status_map = {
        "APPROVED": "Approved",
        "MANUAL_REVIEW": "Manual Review",
        "PROCESSING_ERROR": "Processing Error",
        "QUALITY_FAILED": "Processing Error",
        "READY": "Ready for review",
        "READY_FOR_REVIEW": "Ready for review",
    }
    chosen_status = status_map.get(validation_status.upper(), "Ready for review")

    doc_title = f"DOC-{document_id}" if not str(document_id).startswith("DOC-") else str(document_id)

    props: dict[str, Any] = {
        "Document ID": {
            "title": [
                {
                    "text": {
                        "content": doc_title
                    }
                }
            ]
        },
        "Extracted Name ": {
            "rich_text": [
                {
                    "text": {
                        "content": name or ""
                    }
                }
            ]
        },
        "Extracted Number": {
            "rich_text": [
                {
                    "text": {
                        "content": number or ""
                    }
                }
            ]
        },
        "Validation Status": {
            "status": {
                "name": chosen_status
            }
        },
    }

    if doc_type_val:
        props["Document Type"] = {
            "select": {
                "name": doc_type_val
            }
        }

    if onboarding_page_id:
        props["Related Onboarding"] = {
            "relation": [
                {
                    "id": onboarding_page_id
                }
            ]
        }

    return create_page(database_id, props)


def get_documents_by_onboarding(database_id: str, onboarding_page_id: str | None = None) -> list:
    filter_body = None
    if onboarding_page_id:
        filter_body = {
            "property": "Related Onboarding",
            "relation": {
                "contains": onboarding_page_id
            }
        }

    res = query_database(database_id, filter_body=filter_body)
    return res.get("results", [])


def get_document_by_id(database_id: str, document_id: int | str) -> dict | None:
    doc_title = f"DOC-{document_id}" if not str(document_id).startswith("DOC-") else str(document_id)
    res = query_database(
        database_id,
        filter_body={
            "property": "Document ID",
            "title": {
                "equals": doc_title
            }
        }
    )
    results = res.get("results", [])
    return results[0] if results else None


def update_document_status(page_id: str, status: str) -> dict:
    status_map = {
        "APPROVED": "Approved",
        "MANUAL_REVIEW": "Manual Review",
        "PROCESSING_ERROR": "Processing Error",
        "QUALITY_FAILED": "Processing Error",
        "READY": "Ready for review",
        "READY_FOR_REVIEW": "Ready for review",
        "RESEND_REQUIRED": "Processing Error",
    }
    chosen_status = status_map.get(status.upper(), "Ready for review")

    return update_page(
        page_id,
        {
            "Validation Status": {
                "status": {
                    "name": chosen_status
                }
            }
        }
    )


# =========================================================
# REVIEW QUEUE
# =========================================================

def create_review_queue_item(
    database_id: str,
    task_title: str,
    review_notes: str,
    stop_reason: str,
    decision: str = "Pending",
    document_page_id: str | None = None,
) -> dict:
    valid_decisions = {"Pending", "Override", "Reject", "Approve"}
    chosen_decision = decision if decision in valid_decisions else "Pending"

    props: dict[str, Any] = {
        "Review Task": {
            "title": [
                {
                    "text": {
                        "content": task_title
                    }
                }
            ]
        },
        "Review Notes": {
            "rich_text": [
                {
                    "text": {
                        "content": review_notes or ""
                    }
                }
            ]
        },
        "Stop Reason": {
            "rich_text": [
                {
                    "text": {
                        "content": stop_reason or ""
                    }
                }
            ]
        },
        "Reviewer Decision": {
            "status": {
                "name": chosen_decision
            }
        },
    }

    if document_page_id:
        props["Document to Review"] = {
            "relation": [
                {
                    "id": document_page_id
                }
            ]
        }

    return create_page(database_id, props)


# =========================================================
# RUN LOG
# =========================================================

def create_run_log_item(
    database_id: str,
    event_type: str,
    status: str,
    message: str,
    onboarding_id: int | str | None = None,
) -> dict:
    is_success = status.upper() in {"SUCCESS", "GOOD", "VALID", "APPROVED", "COMPLETED", "RECEIVED", "CLASSIFIED", "EXTRACTED"}
    outcome_val = "Success" if is_success else "Failed"
    action_text = f"[{status}] {message}" if message else status

    return create_page(
        database_id,
        {
            "Run ID / Event": {
                "title": [
                    {
                        "text": {
                            "content": f"{event_type}_{onboarding_id or 'SYS'}"
                        }
                    }
                ]
            },
            "Outcome": {
                "select": {
                    "name": outcome_val
                }
            },
            "Code Action": {
                "rich_text": [
                    {
                        "text": {
                            "content": action_text[:2000]
                        }
                    }
                ]
            },
        },
    )