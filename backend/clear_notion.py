import os
from dotenv import load_dotenv
from app.notion_service import query_database, update_page

load_dotenv()

DATABASES = {
    "ONBOARDINGS": os.getenv("NOTION_ONBOARDING_ID"),
    "DOCUMENTS": os.getenv("NOTION_DOCUMENTS_ID"),
    "REVIEW_QUEUE": os.getenv("NOTION_REVIEW_QUEUE_ID"),
    "RUN_LOG": os.getenv("NOTION_RUN_LOG_ID"),
}

def clear_database(name: str, db_id: str | None):
    if not db_id:
        print(f"Skipping {name}: ID not configured.")
        return

    print(f"\nClearing Notion database: {name}...")
    try:
        res = query_database(db_id)
        pages = res.get("results", [])
    except Exception as e:
        print(f" ⚠️ Could not query {name} (ID: {db_id}): {e}")
        return

    if not pages:
        print(f" • {name} is already empty (0 pages).")
        return

    for page in pages:
        page_id = page.get("id")
        try:
            update_page(page_id, {"archived": True})
            print(f"   - Archived page {page_id}")
        except Exception as e:
            try:
                from app.notion_service import _request
                _request("PATCH", f"/pages/{page_id}", {"archived": True})
                print(f"   - Archived page {page_id}")
            except Exception as err:
                print(f"   - Failed to archive {page_id}: {err}")

    print(f" ✅ Cleared {len(pages)} pages from {name}.")

if __name__ == "__main__":
    print("=" * 60)
    print(" 🗑️  CLEARING NOTION DATABASES")
    print("=" * 60)
    for name, db_id in DATABASES.items():
        clear_database(name, db_id)
    print("\n ✨ All active Notion databases are now clean and empty!")

