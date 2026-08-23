import json
import os
from urllib import request, error
from dotenv import load_dotenv

load_dotenv()

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2026-03-11"


class NotionAPIError(Exception):
    pass


def _get_token():
    token = os.getenv("NOTION_ACCESS_TOKEN")

    if not token:
        raise NotionAPIError(
            "NOTION_ACCESS_TOKEN is not configured."
        )

    return token


def _request(
    method: str,
    endpoint: str,
    body: dict | None = None,
):
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

            response_body = response.read().decode(
                "utf-8"
            )

            if not response_body:
                return {}

            return json.loads(response_body)

    except error.HTTPError as e:

        response_body = e.read().decode(
            "utf-8"
        )

        raise NotionAPIError(
            f"Notion API error {e.code}: {response_body}"
        )

    except error.URLError as e:

        raise NotionAPIError(
            f"Could not connect to Notion: {e}"
        )


def get_database(
    database_id: str,
):
    return _request(
        "GET",
        f"/databases/{database_id}",
    )


def get_data_source_id(
    database_id: str,
):
    database = get_database(
        database_id
    )

    data_sources = database.get(
        "data_sources",
        [],
    )

    if not data_sources:
        raise NotionAPIError(
            f"No data source found for database {database_id}"
        )

    return data_sources[0]["id"]


def get_data_source(
    database_id: str,
):
    data_source_id = get_data_source_id(
        database_id
    )

    return _request(
        "GET",
        f"/data_sources/{data_source_id}",
    )


def create_page(
    database_id: str,
    properties: dict,
):
    data_source_id = get_data_source_id(
        database_id
    )

    return _request(
        "POST",
        "/pages",
        {
            "parent": {
                "type": "data_source_id",
                "data_source_id": data_source_id,
            },
            "properties": properties,
        },
    )


def update_page(
    page_id: str,
    properties: dict,
):
    return _request(
        "PATCH",
        f"/pages/{page_id}",
        {
            "properties": properties,
        },
    )


def query_data_source(
    database_id: str,
    filter_body: dict | None = None,
):
    data_source_id = get_data_source_id(
        database_id
    )

    body = {}

    if filter_body:
        body["filter"] = filter_body

    return _request(
        "POST",
        f"/data_sources/{data_source_id}/query",
        body,
    )
def create_review_queue_item(
    database_id: str,
    document_name: str,
    review_notes: str,
    stop_reason: str,
):
    return create_page(
        database_id,
        {
            "Document to Review": {
                "title": [
                    {
                        "text": {
                            "content": document_name
                        }
                    }
                ]
            },
            "Review Notes": {
                "rich_text": [
                    {
                        "text": {
                            "content": review_notes
                        }
                    }
                ]
            },
            "Stop Reason": {
                "rich_text": [
                    {
                        "text": {
                            "content": stop_reason
                        }
                    }
                ]
            },
        },
    )


def create_onboarding_item(
    database_id: str,
    onboarding_id: int,
    tenant_name: str,
    status: str,
):
    return create_page(
        database_id,
        {
            "Onboarding ID": {
                "number": onboarding_id
            },
            "Tenant Name": {
                "title": [
                    {
                        "text": {
                            "content": tenant_name
                        }
                    }
                ]
            },
            "Onboarding Status": {
                "select": {
                    "name": status
                }
            },
        },
    )


def create_run_log_item(
    database_id: str,
    event_type: str,
    status: str,
    message: str,
    onboarding_id: int | None = None,
):
    return create_page(
        database_id,
        {
            "Run ID / Event": {
                "title": [
                    {
                        "text": {
                            "content": event_type
                        }
                    }
                ]
            },
            "Outcome": {
                "rich_text": [
                    {
                        "text": {
                            "content": status
                        }
                    }
                ]
            },
            "Code Action": {
                "rich_text": [
                    {
                        "text": {
                            "content": message
                        }
                    }
                ]
            },
        },
    )