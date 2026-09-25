from pathlib import Path
import csv
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
import gspread
from google.oauth2.service_account import Credentials


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

LEADS_FILE = DATA_DIR / "leads.csv"
INPUT_FILE = DATA_DIR / "public_leads.csv"

GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Lead Automation")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()

GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON", ""
).strip()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()


# Minimum subscriber count.
# There is NO maximum subscriber limit.
MIN_SUBSCRIBERS = int(os.getenv("MIN_SUBSCRIBERS", "10000"))

# Number of channels returned by each YouTube search query.
SEARCH_RESULTS_PER_QUERY = int(
    os.getenv("SEARCH_RESULTS_PER_QUERY", "50")
)

# Maximum channels to process in one run.
MAX_CHANNELS_PER_RUN = int(
    os.getenv("MAX_CHANNELS_PER_RUN", "200")
)


# ============================================================
# NICHES
# ============================================================

SEARCH_QUERIES = [
    "tech",
    "technology",
    "gadgets",
    "smartphone",
    "mobile",
    "android",
    "iPhone",
    "PC",
    "computer",
    "laptop",
    "gaming",
    "gaming PC",
    "PC build",
    "graphics card",
    "GPU",
    "video editing",
    "Premiere Pro",
    "CapCut",
    "creator",
    "YouTuber",
    "content creator",
    "camera",
    "photography",
    "videography",
    "VFX",
    "3D",
]


# ============================================================
# CSV HEADERS
# ============================================================

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


# ============================================================
# BASIC HELPERS
# ============================================================

def now_utc_date():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def normalize_url(url):
    if not url:
        return ""

    url = url.strip()

    if not url:
        return ""

    return url.rstrip("/").lower()


def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def ensure_csv():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not LEADS_FILE.exists():
        with LEADS_FILE.open(
            "w",
            newline="",
            encoding="utf-8"
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=HEADERS
            )
            writer.writeheader()


# ============================================================
# CSV DATABASE
# ============================================================

def load_existing_csv_leads():
    ensure_csv()

    leads = []

    with LEADS_FILE.open(
        "r",
        newline="",
        encoding="utf-8"
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:
            leads.append(dict(row))

    return leads


def csv_duplicate(lead, existing_leads):
    profile_url = normalize_url(
        lead.get("profile_url", "")
    )

    channel_url = normalize_url(
        lead.get("channel_url", "")
    )

    name = clean_text(
        lead.get("name", "")
    ).lower()

    for existing in existing_leads:

        existing_profile = normalize_url(
            existing.get("profile_url", "")
        )

        existing_channel = normalize_url(
            existing.get("channel_url", "")
        )

        existing_name = clean_text(
            existing.get("name", "")
        ).lower()

        if (
            channel_url
            and channel_url == existing_channel
        ):
            return True

        if (
            profile_url
            and profile_url == existing_profile
        ):
            return True

        if (
            name
            and name == existing_name
            and existing.get("platform", "").lower()
            == lead.get("platform", "").lower()
        ):
            return True

    return False


def add_lead_to_csv(lead, existing_leads):
    if csv_duplicate(lead, existing_leads):
        return False

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
            header: lead.get(header, "")
            for header in HEADERS
        })

    existing_leads.append(lead)

    return True


# ============================================================
# OLD INPUT FILE
# ============================================================

def load_public_leads():
    leads = []

    if not INPUT_FILE.exists():
        print("public_leads.csv not found.")
        return leads

    print(f"Reading input file: {INPUT_FILE}")

    with INPUT_FILE.open(
        "r",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:

            if not row.get("name"):
                continue

            lead = {
                header: clean_text(row.get(header, ""))
                for header in HEADERS
            }

            lead["lead_source"] = (
                lead.get("lead_source")
                or "public_csv"
            )

            lead["status"] = (
                lead.get("status")
                or "new"
            )

            leads.append(lead)

    print(
        f"Rows loaded from public_leads.csv: {len(leads)}"
    )

    return leads


# ============================================================
# GOOGLE SHEETS
# ============================================================

def connect_google_sheet():
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        print(
            "Google Sheets disabled: "
            "GOOGLE_SERVICE_ACCOUNT_JSON is missing."
        )
        return None

    try:
        credentials_info = json.loads(
            GOOGLE_SERVICE_ACCOUNT_JSON
        )

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        credentials = Credentials.from_service_account_info(
            credentials_info,
            scopes=scopes
        )

        client = gspread.authorize(credentials)

        # Prefer Spreadsheet ID.
        if GOOGLE_SHEET_ID:
            print("Opening Google Sheet using Sheet ID...")
            spreadsheet = client.open_by_key(
                GOOGLE_SHEET_ID
            )
        else:
            print(
                f"Opening Google Sheet by name: "
                f"{GOOGLE_SHEET_NAME}"
            )

            spreadsheet = client.open(
                GOOGLE_SHEET_NAME
            )

        try:
            worksheet = spreadsheet.worksheet("Leads")
        except gspread.WorksheetNotFound:
            print("Leads worksheet not found. Creating it...")

            worksheet = spreadsheet.add_worksheet(
                title="Leads",
                rows=1000,
                cols=len(HEADERS)
            )

        # Make sure header exists.
        existing_values = worksheet.get_all_values()

        if not existing_values:
            worksheet.append_row(
                HEADERS,
                value_input_option="USER_ENTERED"
            )

        print("Google Sheets connected successfully.")

        return worksheet

    except Exception as error:
        print(
            f"Google Sheets connection failed: {error}"
        )
        return None


def load_sheet_records(worksheet):
    if worksheet is None:
        return []

    try:
        return worksheet.get_all_records()
    except Exception as error:
        print(
            f"Could not read Google Sheet records: {error}"
        )
        return []


def sheet_duplicate(lead, records):
    channel_url = normalize_url(
        lead.get("channel_url", "")
    )

    profile_url = normalize_url(
        lead.get("profile_url", "")
    )

    for row in records:

        existing_channel = normalize_url(
            row.get("channel_url", "")
        )

        existing_profile = normalize_url(
            row.get("profile_url", "")
        )

        if (
            channel_url
            and channel_url == existing_channel
        ):
            return True

        if (
            profile_url
            and profile_url == existing_profile
        ):
            return True

    return False


def add_lead_to_sheet(
    worksheet,
    lead,
    existing_records
):
    if worksheet is None:
        return False

    if sheet_duplicate(
        lead,
        existing_records
    ):
        return False

    row = [
        lead.get(header, "")
        for header in HEADERS
    ]

    worksheet.append_row(
        row,
        value_input_option="USER_ENTERED"
    )

    existing_records.append(lead)

    return True


# ============================================================
# YOUTUBE API
# ============================================================

YOUTUBE_BASE_URL = (
    "https://www.googleapis.com/youtube/v3"
)


def youtube_request(endpoint, params):
    params = dict(params)
    params["key"] = YOUTUBE_API_KEY

    response = requests.get(
        f"{YOUTUBE_BASE_URL}/{endpoint}",
        params=params,
        timeout=30
    )

    response.raise_for_status()

    return response.json()


def search_youtube_channels(query):
    data = youtube_request(
        "search",
        {
            "part": "snippet",
            "q": query,
            "type": "channel",
            "regionCode": "IN",
            "maxResults": SEARCH_RESULTS_PER_QUERY,
        }
    )

    return data.get("items", [])


def get_channel_details(channel_ids):
    if not channel_ids:
        return []

    # YouTube accepts up to 50 channel IDs.
    channel_ids = channel_ids[:50]

    data = youtube_request(
        "channels",
        {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(channel_ids),
            "maxResults": 50,
        }
    )

    return data.get("items", [])


def parse_niche(text):
    text = clean_text(text).lower()

    niche_map = [
        ("gaming", "gaming"),
        ("gamer", "gaming"),
        ("technology", "technology"),
        ("tech", "technology"),
        ("gadget", "tech/gadgets"),
        ("smartphone", "mobile/smartphone"),
        ("mobile", "mobile/smartphone"),
        ("android", "mobile/smartphone"),
        ("iphone", "mobile/smartphone"),
        ("laptop", "computers/laptops"),
        ("computer", "computers/laptops"),
        ("pc", "pc"),
        ("editing", "video editing"),
        ("premiere", "video editing"),
        ("capcut", "video editing"),
        ("camera", "photography/videography"),
        ("photography", "photography"),
        ("videography", "videography"),
        ("vfx", "VFX"),
        ("3d", "3D"),
        ("creator", "content creator"),
    ]

    found = []

    for keyword, niche in niche_map:
        if keyword in text and niche not in found:
            found.append(niche)

    if not found:
        return "creator/technology"

    return ", ".join(found[:3])


def extract_country(channel):
    snippet = channel.get("snippet", {})

    country = clean_text(
        snippet.get("country", "")
    )

    if country:
        return country.upper()

    return "IN"


def build_channel_url(channel_id, custom_url=""):
    custom_url = clean_text(custom_url)

    if custom_url.startswith("http"):
        return custom_url

    if custom_url.startswith("@"):
        return f"https://www.youtube.com/{custom_url}"

    return (
        "https://www.youtube.com/channel/"
        f"{channel_id}"
    )


def build_youtube_lead(channel):
    snippet = channel.get("snippet", {})
    statistics = channel.get("statistics", {})

    channel_id = clean_text(
        channel.get("id", "")
    )

    title = clean_text(
        snippet.get("title", "")
    )

    description = clean_text(
        snippet.get("description", "")
    )

    custom_url = clean_text(
        snippet.get("customUrl", "")
    )

    subscribers = safe_int(
        statistics.get("subscriberCount", 0)
    )

    if subscribers < MIN_SUBSCRIBERS:
        return None

    channel_url = build_channel_url(
        channel_id,
        custom_url
    )

    text_for_niche = (
        f"{title} {description}"
    )

    niche = parse_niche(text_for_niche)

    country = extract_country(channel)

    published_at = clean_text(
        snippet.get("publishedAt", "")
    )

    recent_upload = (
        published_at[:10]
        if published_at
        else now_utc_date()
    )

    return {
        "name": title,
        "platform": "YouTube",
        "profile_url": channel_url,
        "channel_url": channel_url,
        "creator_or_business": "creator",
        "niche": niche,
        "country": country,
        "city": "",
        "subscribers": subscribers,
        "avg_views": "",
        "business_email": "",
        "instagram": "",
        "linkedin": "",
        "twitter_x": "",
        "website": "",
        "recent_upload": recent_upload,
        "contact_type": "public",
        "lead_source": "youtube_api",
        "status": "new",
        "notes": "Discovered through official YouTube Data API",
    }


def discover_youtube_leads(existing_csv):
    if not YOUTUBE_API_KEY:
        print(
            "YOUTUBE_API_KEY is missing. "
            "Skipping automatic YouTube discovery."
        )
        return []

    print("Starting automatic YouTube discovery...")

    found_channel_ids = set()
    channels_to_fetch = []

    for query in SEARCH_QUERIES:

        if len(channels_to_fetch) >= MAX_CHANNELS_PER_RUN:
            break

        try:
            print(
                f"YouTube search: {query}"
            )

            search_results = search_youtube_channels(
                query
            )

            for item in search_results:

                channel_id = (
                    item.get("snippet", {})
                    .get("channelId", "")
                )

                if not channel_id:
                    continue

                if channel_id in found_channel_ids:
                    continue

                found_channel_ids.add(channel_id)
                channels_to_fetch.append(channel_id)

                if (
                    len(channels_to_fetch)
                    >= MAX_CHANNELS_PER_RUN
                ):
                    break

        except requests.HTTPError as error:
            print(
                f"YouTube API error for "
                f"'{query}': {error}"
            )

        except Exception as error:
            print(
                f"YouTube search failed for "
                f"'{query}': {error}"
            )

    print(
        f"Unique YouTube channels discovered: "
        f"{len(channels_to_fetch)}"
    )

    all_channels = []

    for start in range(
        0,
        len(channels_to_fetch),
        50
    ):

        batch = channels_to_fetch[
            start:start + 50
        ]

        try:
            details = get_channel_details(
                batch
            )

            all_channels.extend(details)

        except Exception as error:
            print(
                f"Channel details request failed: "
                f"{error}"
            )

    leads = []

    for channel in all_channels:

        lead = build_youtube_lead(
            channel
        )

        if lead is None:
            continue

        if csv_duplicate(
            lead,
            existing_csv
        ):
            continue

        leads.append(lead)

    print(
        f"New YouTube leads after filtering "
        f"and duplicate check: {len(leads)}"
    )

    return leads


# ============================================================
# MAIN
# ============================================================

def main():

    print("========================================")
    print("Lead Collector started.")
    print("========================================")

    ensure_csv()

    existing_csv = load_existing_csv_leads()

    print(
        f"Existing CSV leads: "
        f"{len(existing_csv)}"
    )

    # --------------------------------------------------------
    # 1. Process old public_leads.csv
    # --------------------------------------------------------

    old_input_leads = load_public_leads()

    csv_added = 0

    for lead in old_input_leads:

        if add_lead_to_csv(
            lead,
            existing_csv
        ):
            csv_added += 1

    print(
        f"Added {csv_added} old/public lead(s) "
        f"to CSV."
    )

    # --------------------------------------------------------
    # 2. Connect Google Sheets
    # --------------------------------------------------------

    worksheet = connect_google_sheet()

    sheet_records = load_sheet_records(
        worksheet
    )

    print(
        f"Existing Google Sheet records: "
        f"{len(sheet_records)}"
    )

    # --------------------------------------------------------
    # 3. Automatic YouTube discovery
    # --------------------------------------------------------

    youtube_leads = discover_youtube_leads(
        existing_csv
    )

    # --------------------------------------------------------
    # 4. Add YouTube leads to CSV
    # --------------------------------------------------------

    youtube_csv_added = 0

    for lead in youtube_leads:

        if add_lead_to_csv(
            lead,
            existing_csv
        ):
            youtube_csv_added += 1

    print(
        f"New YouTube leads added to CSV: "
        f"{youtube_csv_added}"
    )

    # --------------------------------------------------------
    # 5. Add all new leads to Google Sheets
    # --------------------------------------------------------

    sheet_added = 0

    all_new_leads = (
        old_input_leads
        + youtube_leads
    )

    for lead in all_new_leads:

        if add_lead_to_sheet(
            worksheet,
            lead,
            sheet_records
        ):
            sheet_added += 1

    print(
        f"Added {sheet_added} new lead(s) "
        f"to Google Sheets."
    )

    # --------------------------------------------------------
    # 6. Final summary
    # --------------------------------------------------------

    print("----------------------------------------")
    print("Lead Collector completed.")
    print(
        f"Total CSV leads: {len(existing_csv)}"
    )
    print(
        f"New YouTube leads: {youtube_csv_added}"
    )
    print(
        f"New Google Sheet rows: {sheet_added}"
    )
    print("----------------------------------------")


if __name__ == "__main__":
    main()
