from pathlib import Path
import csv
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LEADS_FILE = DATA_DIR / "leads.csv"

HEADERS = [
    "name",
    "platform",
    "profile_url",
    "channel_url",
    "creator_or_business",
    "niche",
    "country",
    "city",
    "subscribers",
    "avg_views",
    "business_email",
    "instagram",
    "linkedin",
    "twitter_x",
    "website",
    "recent_upload",
    "contact_type",
    "lead_source",
    "status",
    "notes",
]


def ensure_csv():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not LEADS_FILE.exists() or LEADS_FILE.stat().st_size == 0:
        with LEADS_FILE.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(HEADERS)


def add_lead(lead):
    ensure_csv()

    with LEADS_FILE.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=HEADERS)
        writer.writerow({key: lead.get(key, "") for key in HEADERS})


def main():
    ensure_csv()

    print("Lead Collector started.")
    print(f"Database: {LEADS_FILE}")

    # Safe test record
    # This is only for testing CSV writing.
    test_lead = {
        "name": "TEST_LEAD",
        "platform": "test",
        "profile_url": "",
        "channel_url": "",
        "creator_or_business": "test",
        "niche": "testing",
        "country": "India",
        "city": "",
        "subscribers": "",
        "avg_views": "",
        "business_email": "",
        "instagram": "",
        "linkedin": "",
        "twitter_x": "",
        "website": "",
        "recent_upload": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "contact_type": "test",
        "lead_source": "local_test",
        "status": "test",
        "notes": "Automation test record",
    }

    # Write the test lead into leads.csv
    add_lead(test_lead)

    print("Test lead added successfully.")
    print("Lead Collector is ready.")


if __name__ == "__main__":
    main()
