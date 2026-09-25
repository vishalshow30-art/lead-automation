from pathlib import Path
import csv
import json
import os
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

LEADS_FILE = DATA_DIR / "leads.csv"
INPUT_FILE = DATA_DIR / "public_leads.csv"

GOOGLE_SHEET_NAME = os.getenv(
    "GOOGLE_SHEET_NAME",
    "Lead Automation"
)

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


def add_lead_to_csv(lead):
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
        print(f"Input file not found: {INPUT_FILE}")
        return []

    print(f"Reading input file: {INPUT_FILE}")

    with INPUT_FILE.open(
        "r",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        reader = csv.DictReader(file)

        print(f"CSV columns found: {reader.fieldnames}")

        leads = []

        for row in reader:
            lead = {
                key: row.get(key, "")
                for key in HEADERS
            }

            if lead["name"].strip():
                leads.append(lead)

        return leads


def connect_google_sheet():
    secret = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

    if not secret:
        print(
            "GOOGLE_SERVICE_ACCOUNT_JSON secret not found."
        )
        return None

    try:
        service_account_info = json.loads(secret)

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        credentials = Credentials.from_service_account_info(
            service_account_info,
            scopes=scopes
        )

        client = gspread.authorize(credentials)

        spreadsheet = client.open(GOOGLE_SHEET_NAME)

        try:
            worksheet = spreadsheet.worksheet("Leads")
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(
                title="Leads",
                rows=1000,
                cols=len(HEADERS)
            )

            worksheet.append_row(HEADERS)

        print(
            f"Connected to Google Sheet: {GOOGLE_SHEET_NAME}"
        )

        return worksheet

    except Exception as error:
        print(
            f"Google Sheets connection failed: {error}"
        )
        return None


def lead_exists_in_sheet(worksheet, lead):
    if worksheet is None:
        return False

    try:
        records = worksheet.get_all_records()

        profile_url = lead.get(
            "profile_url",
            ""
        ).strip()

        channel_url = lead.get(
            "channel_url",
            ""
        ).strip()

        for record in records:
            existing_profile = str(
                record.get("profile_url", "")
            ).strip()

            existing_channel = str(
                record.get("channel_url", "")
            ).strip()

            if profile_url and profile_url == existing_profile:
                return True

            if channel_url and channel_url == existing_channel:
                return True

        return False

    except Exception as error:
        print(
            f"Duplicate check failed: {error}"
        )
        return False


def add_lead_to_sheet(worksheet, lead):
    if worksheet is None:
        return False

    try:
        if lead_exists_in_sheet(
            worksheet,
            lead
        ):
            print(
                f"Duplicate skipped: "
                f"{lead.get('name', '')}"
            )
            return False

        row = [
            str(lead.get(key, "")).strip()
            for key in HEADERS
        ]

        worksheet.append_row(
            row,
            value_input_option="USER_ENTERED"
        )

        print(
            f"Added to Google Sheets: "
            f"{lead.get('name', '')}"
        )

        return True

    except Exception as error:
        print(
            f"Failed to add lead to Google Sheets: "
            f"{error}"
        )
        return False


def prepare_lead(lead):
    lead["lead_source"] = (
        lead.get("lead_source", "").strip()
        or "public_authorized_source"
    )

    lead["status"] = (
        lead.get("status", "").strip()
        or "new"
    )

    if not lead.get("recent_upload", "").strip():
        lead["recent_upload"] = (
            datetime.now(timezone.utc)
            .strftime("%Y-%m-%d")
        )

    return lead


def main():
    ensure_csv()

    print("Lead Collector started.")
    print(f"Database: {LEADS_FILE}")
    print(f"Input file: {INPUT_FILE}")

    public_leads = load_public_leads()

    print(
        f"Rows loaded from public_leads.csv: "
        f"{len(public_leads)}"
    )

    if not public_leads:
        print("No public/authorized leads found.")
        print("Lead Collector is ready.")
        return

    worksheet = connect_google_sheet()

    csv_added = 0
    sheet_added = 0

    for lead in public_leads:
        lead = prepare_lead(lead)

        add_lead_to_csv(lead)
        csv_added += 1

        if worksheet is not None:
            if add_lead_to_sheet(
                worksheet,
                lead
            ):
                sheet_added += 1

    print(
        f"Added {csv_added} lead(s) to CSV."
    )

    print(
        f"Added {sheet_added} new lead(s) to Google Sheets."
    )

    print("Lead Collector completed.")


if __name__ == "__main__":
    main()
