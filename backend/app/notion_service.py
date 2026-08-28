import json
import os
import re
import time
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
        with request.urlopen(req, timeout=10) as response:
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


def get_page(page_id: str) -> dict:
    return _request("GET", f"/pages/{page_id}")


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
    property_address: str | None = None,
    tenant_phone: str | int | None = None,
) -> dict:
    valid_statuses = {"In Progress", "Pending Review", "Completed"}
    chosen_status = status if status in valid_statuses else "In Progress"

    id_digits = "".join(re.findall(r"\d+", str(onboarding_id)))
    num_id = int(id_digits) if id_digits else int(time.time()) % 100000

    props: dict[str, Any] = {
        "Tenant Name ": {
            "title": [
                {
                    "text": {
                        "content": tenant_name or "Tenant"
                    }
                }
            ]
        },
        "Onboarding ID": {
            "number": num_id
        },
        "Onboarding Status": {
            "select": {
                "name": chosen_status
            }
        },
    }

    if property_name:
        props["Property Name"] = {
            "select": {
                "name": property_name
            }
        }

    if property_address:
        props["Property Address"] = {
            "select": {
                "name": property_address
            }
        }

    if tenant_phone:
        digits = "".join(re.findall(r"\d+", str(tenant_phone)))
        if digits:
            try:
                props["Tenant Phone"] = {
                    "number": int(digits[-10:])
                }
            except Exception:
                pass

    return create_page(database_id, props)


def get_onboarding_by_id(database_id: str, onboarding_id: int | str) -> dict | None:
    id_digits = "".join(re.findall(r"\d+", str(onboarding_id)))
    target_num = int(id_digits) if id_digits else None
    target_title = f"ONB-{onboarding_id}" if not str(onboarding_id).startswith("ONB-") else str(onboarding_id)

    # 1. Try querying by number
    if target_num is not None:
        try:
            res = query_database(
                database_id,
                filter_body={
                    "property": "Onboarding ID",
                    "number": {
                        "equals": target_num
                    }
                }
            )
            results = res.get("results", [])
            if results:
                return results[0]
        except Exception:
            pass

    # 2. Try querying by title
    try:
        res = query_database(
            database_id,
            filter_body={
                "property": "Onboarding ID",
                "title": {
                    "equals": target_title
                }
            }
        )
        results = res.get("results", [])
        if results:
            return results[0]
    except Exception:
        pass

    # 3. Fallback scan all
    try:
        all_res = query_database(database_id).get("results", [])
        for p in all_res:
            p_props = p.get("properties", {})
            for key, val in p_props.items():
                if "onboarding" in key.lower():
                    if val.get("number") == target_num:
                        return p
                    if val.get("title") and val["title"] and target_title in val["title"][0].get("plain_text", ""):
                        return p
    except Exception:
        pass

    return None


def update_onboarding_status(page_id: str, status: str) -> dict:
    valid_statuses = {"In Progress", "Pending Review", "Completed"}
    chosen_status = status if status in valid_statuses else "In Progress"

    return update_page(
        page_id,
        {
            "Onboarding Status": {
                "select": {
                    "name": chosen_status
                }
            }
        }
    )


def get_all_onboardings(database_id: str) -> list:
    try:
        res = query_database(database_id)
        return res.get("results", [])
    except Exception:
        return []


def update_onboarding_id(page_id: str, onboarding_id: int | str) -> dict:
    id_digits = "".join(re.findall(r"\d+", str(onboarding_id)))
    num_id = int(id_digits) if id_digits else int(time.time()) % 100000
    try:
        return update_page(
            page_id,
            {
                "Onboarding ID": {
                    "number": num_id
                }
            },
        )
    except Exception:
        target_id = f"ONB-{onboarding_id}" if not str(onboarding_id).startswith("ONB-") else str(onboarding_id)
        return update_page(
            page_id,
            {
                "Onboarding ID": {
                    "title": [
                        {
                            "text": {
                                "content": target_id
                            }
                        }
                    ]
                }
            },
        )


def reset_send_message_checkbox(page_id: str) -> dict:
    try:
        return update_page(
            page_id,
            {
                "Send Message": {
                    "checkbox": False
                }
            }
        )
    except Exception:
        return {}


# =========================================================
# DOCUMENTS
# =========================================================

def create_document_item(
    database_id: str,
    document_id: int | str,
    doc_type: str,
    name: str | None = None,
    number: str | None = None,
    validation_status: str = "Manual Review",
    onboarding_page_id: str | None = None,
    file_url: str | None = None,
) -> dict:
    type_map = {
        "AADHAAR": "AADHAR",
        "AADHAR": "AADHAR",
        "PAN": "PAN",
        "RENT_AGREEMENT": "RENT_AGREEMENT",
        "PASSPORT_PHOTO": "PASSPORT_PHOTO",
        "PASSPORT": "PASSPORT_PHOTO",
    }
    doc_type_val = type_map.get(doc_type.upper(), "AADHAR")

    status_map = {
        "APPROVED": "Approved",
        "VALID": "Approved",
        "MANUAL_REVIEW": "Manual Review",
        "REVIEW": "Manual Review",
        "PROCESSING_ERROR": "Processing Error",
        "QUALITY_FAILED": "Processing Error",
        "REJECTED": "Processing Error",
    }
    chosen_status = status_map.get(validation_status.upper(), "Manual Review")
    doc_title = f"DOC-{document_id}" if not str(document_id).startswith("DOC-") else str(document_id)

    props: dict[str, Any] = {
        "Tenant Name": {
            "title": [
                {
                    "text": {
                        "content": name or doc_title
                    }
                }
            ]
        },
        "Document Type": {
            "select": {
                "name": doc_type_val
            }
        },
        "Extracted Name": {
            "rich_text": [
                {
                    "text": {
                        "content": name or ""
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

    if number:
        digits = "".join(re.findall(r"\d+", number))
        if digits:
            try:
                props["Extracted Number"] = {
                    "number": int(digits[-12:])
                }
            except Exception:
                pass

    if onboarding_page_id:
        props["Related Onboarding"] = {
            "relation": [
                {
                    "id": onboarding_page_id
                }
            ]
        }

    if file_url:
        props["File link/View"] = {
            "url": file_url
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
        "VALID": "Approved",
        "MANUAL_REVIEW": "Manual Review",
        "REVIEW": "Manual Review",
        "PROCESSING_ERROR": "Processing Error",
        "QUALITY_FAILED": "Processing Error",
        "REJECTED": "Processing Error",
    }
    chosen_status = status_map.get(status.upper(), "Manual Review")

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
    valid_decisions = {"Pending", "Approve", "Reject"}
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
        "Reason": {
            "rich_text": [
                {
                    "text": {
                        "content": stop_reason or review_notes or ""
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
        props["Document to review"] = {
            "relation": [
                {
                    "id": document_page_id
                }
            ]
        }

    return create_page(database_id, props)


def get_pending_review_queue_items(database_id: str) -> list:
    """
    Finds review tasks where broker has selected 'Approve' or 'Reject'.
    """
    try:
        res = query_database(
            database_id,
            filter_body={
                "or": [
                    {
                        "property": "Reviewer Decision",
                        "status": {
                            "equals": "Approve"
                        }
                    },
                    {
                        "property": "Reviewer Decision",
                        "status": {
                            "equals": "Reject"
                        }
                    },
                ]
            }
        )
        return res.get("results", [])
    except Exception:
        try:
            res = query_database(database_id)
            items = []
            for p in res.get("results", []):
                dec = p.get("properties", {}).get("Reviewer Decision", {}).get("status", {}).get("name", "")
                if dec in {"Approve", "Reject"}:
                    items.append(p)
            return items
        except Exception:
            return []


def update_review_task_decision(page_id: str, decision: str) -> dict:
    try:
        return update_page(
            page_id,
            {
                "Reviewer Decision": {
                    "status": {
                        "name": decision
                    }
                }
            }
        )
    except Exception:
        return {}


# =========================================================
# RENT AGREEMENTS DATABASE POLLING
# =========================================================

def get_pending_agreement_requests(database_id: str) -> list:
    try:
        res = query_database(
            database_id,
            filter_body={
                "property": "[ ] Generate Now",
                "checkbox": {
                    "equals": True
                }
            }
        )
        return res.get("results", [])
    except Exception:
        return []


def mark_agreement_as_generated(page_id: str) -> dict:
    return update_page(
        page_id,
        {
            "[ ] Generate Now": {
                "checkbox": False
            }
        }
    )


# =========================================================
# RUN LOG (Graceful fallback if database unlinked)
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

    try:
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
    except Exception as e:
        print(f"[RUN_LOG] {event_type}: {action_text} ({e})")
        return {}