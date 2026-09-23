from pathlib import Path
import csv
from datetime import datetime, timezone


BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
LEADS_FILE = DATA_DIR / "leads.csv"
INPUT_FILE = DATA_DIR / "public_leads.csv"


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
        with LEADS_FILE.open(
            "w",
            newline="",
            encoding="utf-8"
        ) as file:
            writer = csv.writer(file)
            writer.writerow(HEADERS)


def add_lead(lead):
    ensure_csv()

    with LEADS_FILE.open(
        "a",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=HEADERS
        )

        writer.writerow({
            key: str(lead.get(key, "")).strip()
            for key in HEADERS
        })


def load_public_leads():
    if not INPUT_FILE.exists():
        return []

    with INPUT_FILE.open(
        "r",
        newline="",
        encoding="utf-8-sig"
    ) as file:
        reader = csv.DictReader(file)

        leads = []

        for row in reader:
            lead = {
                key: row.get(key, "")
                for key in HEADERS
            }

            # Only accept rows that have a name.
            if lead["name"].strip():
                leads.append(lead)

        return leads


def main():
    ensure_csv()

    print("Lead Collector started.")
    print(f"Database: {LEADS_FILE}")
    print(f"Input file: {INPUT_FILE}")

    public_leads = load_public_leads()

    if not public_leads:
        print("No public/authorized leads found.")
        print("Lead Collector is ready.")
        return

    added = 0

    for lead in public_leads:
        lead["lead_source"] = (
            lead["lead_source"].strip()
            or "public_authorized_source"
        )

        lead["status"] = (
            lead["status"].strip()
            or "new"
        )

        if not lead["recent_upload"].strip():
            lead["recent_upload"] = (
                datetime.now(timezone.utc)
                .strftime("%Y-%m-%d")
            )

        add_lead(lead)
        added += 1

    print(f"Added {added} public/authorized lead(s).")
    print("Lead Collector is ready.")


if __name__ == "__main__":
    main()
