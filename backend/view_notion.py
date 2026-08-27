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

def get_text_from_prop(prop_obj: dict | None) -> str:
    if not prop_obj:
        return ""
    if prop_obj.get("title"):
        return prop_obj["title"][0].get("plain_text", "") if prop_obj["title"] else ""
    if prop_obj.get("rich_text"):
        return prop_obj["rich_text"][0].get("plain_text", "") if prop_obj["rich_text"] else ""
    if prop_obj.get("select"):
        return prop_obj["select"].get("name", "") if prop_obj["select"] else ""
    if prop_obj.get("status"):
        return prop_obj["status"].get("name", "") if prop_obj["status"] else ""
    if prop_obj.get("number") is not None:
        return str(prop_obj.get("number"))
    if prop_obj.get("checkbox") is not None:
        return "☑️" if prop_obj.get("checkbox") else "☐"
    if prop_obj.get("unique_id"):
        uid = prop_obj.get("unique_id", {})
        prefix = uid.get("prefix", "ONB")
        num = uid.get("number", "")
        return f"{prefix}-{num}" if prefix else str(num)
    if prop_obj.get("url"):
        return str(prop_obj.get("url"))
    return ""

def get_prop_by_name(props: dict, target_name: str) -> dict | None:
    target_clean = target_name.strip().lower()
    for k, v in props.items():
        if k.strip().lower() == target_clean or target_clean in k.strip().lower():
            return v
    return None

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
        try:
            res = query_database(DATABASES["ONBOARDINGS"])
            rows = []
            for p in res.get("results", []):
                props = p.get("properties", {})
                onb_id = get_text_from_prop(get_prop_by_name(props, "Onboarding ID")) or get_text_from_prop(get_prop_by_name(props, "Onboarding id"))
                tenant = get_text_from_prop(get_prop_by_name(props, "Tenant Name"))
                phone = get_text_from_prop(get_prop_by_name(props, "Tenant Phone"))
                prop_name = get_text_from_prop(get_prop_by_name(props, "Property Name")) or get_text_from_prop(get_prop_by_name(props, "Property/PG"))
                addr = get_text_from_prop(get_prop_by_name(props, "Property Address"))
                status = get_text_from_prop(get_prop_by_name(props, "Onboarding Status"))
                send_msg = get_text_from_prop(get_prop_by_name(props, "Send Message"))
                rows.append({"ID": onb_id, "Tenant": tenant, "Phone": phone, "Property": prop_name, "Address": addr, "Status": status, "Send Msg": send_msg})
            print_table("ONBOARDINGS", rows)
        except Exception as e:
            print(f"❌ Error fetching ONBOARDINGS: {e}")

    # 2. Documents
    if DATABASES["DOCUMENTS"]:
        try:
            res = query_database(DATABASES["DOCUMENTS"])
            rows = []
            for p in res.get("results", []):
                props = p.get("properties", {})
                doc_id = get_text_from_prop(props.get("Document ID"))
                doc_type = get_text_from_prop(props.get("Document Type"))
                val_status = get_text_from_prop(props.get("Validation Status"))
                num = get_text_from_prop(props.get("Extracted Number"))
                name = get_text_from_prop(props.get("Extracted Name"))
                rows.append({"Doc ID": doc_id, "Type": doc_type, "Name": name, "Status": val_status, "Number": num})
            print_table("DOCUMENTS", rows)
        except Exception as e:
            print(f"❌ Error fetching DOCUMENTS: {e}")

    # 3. Review Queue
    if DATABASES["REVIEW_QUEUE"]:
        try:
            res = query_database(DATABASES["REVIEW_QUEUE"])
            rows = []
            for p in res.get("results", []):
                props = p.get("properties", {})
                task = get_text_from_prop(props.get("Review Task"))
                decision = get_text_from_prop(props.get("Reviewer Decision"))
                reason = get_text_from_prop(props.get("Reason")) or get_text_from_prop(props.get("Stop Reason"))
                rows.append({"Task": task, "Decision": decision, "Reason": reason[:45]})
            print_table("REVIEW QUEUE", rows)
        except Exception as e:
            print(f"❌ Error fetching REVIEW QUEUE: {e}")

    # 4. Run Log
    if DATABASES["RUN_LOG"]:
        try:
            res = query_database(DATABASES["RUN_LOG"])
            rows = []
            for p in res.get("results", []):
                props = p.get("properties", {})
                run_id = get_text_from_prop(props.get("Run ID / Event"))
                outcome = get_text_from_prop(props.get("Outcome"))
                action = get_text_from_prop(props.get("Code Action"))
                rows.append({"Run / Event": run_id, "Outcome": outcome, "Action": action[:60]})
            print_table("RUN LOG", rows)
        except Exception as e:
            print(f"❌ Error fetching RUN LOG: {e}")

if __name__ == "__main__":
    main()
