import os
from dotenv import load_dotenv
from app.notion_service import query_database

load_dotenv()

DATABASES = {
    "ONBOARDINGS": os.getenv("NOTION_ONBOARDING_ID"),
    "DOCUMENTS": os.getenv("NOTION_DOCUMENTS_ID"),
    "REVIEW_QUEUE": os.getenv("NOTION_REVIEW_QUEUE_ID"),
    "RENT_AGREEMENTS": os.getenv("NOTION_RENT_AGREEMENTS_ID"),
    "RUN_LOG": os.getenv("NOTION_RUN_LOG_ID"),
}

def print_table(title, rows):
    print(f"\n{'='*70}")
    print(f" 📂 NOTION: {title} ({len(rows)} entries)")
    print(f"{'='*70}")
    if not rows:
        print(" (No entries found)")
        return
    for r in rows:
        print(" • " + " | ".join(f"{k}: {v}" for k, v in r.items()))

def main():
    print("\n" + "="*50)
    print(" ☁️  NOTION WORKSPACE LIVE OVERVIEW")
    print("="*50)

    # 1. Onboardings
    if DATABASES["ONBOARDINGS"]:
        res = query_database(DATABASES["ONBOARDINGS"])
        rows = []
        for p in res.get("results", []):
            props = p.get("properties", {})
            title = props.get("Onboarding ID", {}).get("title", [{}])[0].get("plain_text", "")
            tenant = props.get("Tenant Name", {}).get("rich_text", [{}])[0].get("plain_text", "") if props.get("Tenant Name", {}).get("rich_text") else ""
            status = props.get("Onboarding Status", {}).get("status", {}).get("name", "")
            rows.append({"ID": title, "Tenant": tenant, "Status": status})
        print_table("ONBOARDINGS", rows)

    # 2. Documents
    if DATABASES["DOCUMENTS"]:
        res = query_database(DATABASES["DOCUMENTS"])
        rows = []
        for p in res.get("results", []):
            props = p.get("properties", {})
            doc_id = props.get("Document ID", {}).get("title", [{}])[0].get("plain_text", "")
            doc_type = props.get("Document Type", {}).get("select", {}).get("name", "")
            val_status = props.get("Validation Status", {}).get("status", {}).get("name", "")
            num = props.get("Extracted Number", {}).get("rich_text", [{}])[0].get("plain_text", "") if props.get("Extracted Number", {}).get("rich_text") else ""
            rows.append({"Doc ID": doc_id, "Type": doc_type, "Status": val_status, "Number": num})
        print_table("DOCUMENTS", rows)

    # 3. Review Queue
    if DATABASES["REVIEW_QUEUE"]:
        res = query_database(DATABASES["REVIEW_QUEUE"])
        rows = []
        for p in res.get("results", []):
            props = p.get("properties", {})
            task = props.get("Review Task", {}).get("title", [{}])[0].get("plain_text", "")
            decision = props.get("Reviewer Decision", {}).get("status", {}).get("name", "")
            reason = props.get("Stop Reason", {}).get("rich_text", [{}])[0].get("plain_text", "") if props.get("Stop Reason", {}).get("rich_text") else ""
            rows.append({"Task": task, "Decision": decision, "Stop Reason": reason[:40]})
        print_table("REVIEW QUEUE", rows)

    # 4. Rent Agreements
    if DATABASES["RENT_AGREEMENTS"]:
        res = query_database(DATABASES["RENT_AGREEMENTS"])
        rows = []
        for p in res.get("results", []):
            props = p.get("properties", {})
            name = props.get("Name", {}).get("title", [{}])[0].get("plain_text", "") if props.get("Name", {}).get("title") else "Agreement"
            generate_now = props.get("[ ] Generate Now", {}).get("checkbox", False)
            rows.append({"Name": name, "Generate Now Checkbox": generate_now})
        print_table("RENT AGREEMENTS", rows)

    # 5. Run Log
    if DATABASES["RUN_LOG"]:
        res = query_database(DATABASES["RUN_LOG"])
        rows = []
        for p in res.get("results", [])[:5]:
            props = p.get("properties", {})
            event = props.get("Run ID / Event", {}).get("title", [{}])[0].get("plain_text", "")
            outcome = props.get("Outcome", {}).get("select", {}).get("name", "")
            action = props.get("Code Action", {}).get("rich_text", [{}])[0].get("plain_text", "") if props.get("Code Action", {}).get("rich_text") else ""
            rows.append({"Event": event, "Outcome": outcome, "Action": action[:45]})
        print_table("RUN LOG (Latest 5)", rows)

if __name__ == "__main__":
    main()
