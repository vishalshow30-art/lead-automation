from pathlib import Path

code = r'''from pathlib import Path
import csv
import json
import os
import re
import time

import requests


# =========================================================
# PROJECT SETTINGS
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DATA_FILE = DATA_DIR / "leads.csv"

MIN_SUBSCRIBERS = 10_000
MAX_SUBSCRIBERS = 50_000

REQUEST_TIMEOUT = 30

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON", ""
).strip()
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()

CSV_HEADERS = [
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


# =========================================================
# BASIC HELPERS
# =========================================================

def clean(value):
    if value is None:
        return ""
    return str(value).strip()


def safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize_url(url):
    url = clean(url)

    if not url:
        return ""

    if not url.startswith(("http://", "https://")):
        return "https://" + url

    return url


def extract_email(text):
    text = clean(text)

    if not text:
        return ""

    match = re.search(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        text,
    )

    return match.group(0) if match else ""


def detect_niche(text):
    text = clean(text).lower()

    niches = {
        "Gaming": [
            "gaming",
            "gamer",
            "gameplay",
            "bgmi",
            "pubg",
            "minecraft",
            "free fire",
            "valorant",
        ],
        "Tech": [
            "technology",
            "tech",
            "android",
            "iphone",
            "software",
            "smartphone",
        ],
        "Gadgets": [
            "gadget",
            "gadgets",
            "unboxing",
            "review",
            "earbuds",
            "smartwatch",
        ],
        "PC/Computer": [
            "pc",
            "computer",
            "laptop",
            "hardware",
            "processor",
            "gpu",
        ],
        "Mobile": [
            "mobile",
            "phone",
            "smartphone",
        ],
        "Lifestyle": [
            "lifestyle",
            "daily life",
            "routine",
        ],
        "Education": [
            "education",
            "educational",
            "study",
            "learning",
        ],
        "Entertainment": [
            "entertainment",
            "movies",
            "film",
            "films",
            "celebrity",
        ],
        "Fitness": [
            "fitness",
            "gym",
            "workout",
            "bodybuilding",
        ],
        "Fashion": [
            "fashion",
            "style",
            "makeup",
        ],
        "Travel": [
            "travel",
            "travelling",
            "tour",
            "trip",
        ],
        "Finance": [
            "finance",
            "stock",
            "investing",
            "investment",
            "trading",
        ],
        "Automotive": [
            "automotive",
            "car",
            "cars",
            "bike",
            "bikes",
            "automobile",
        ],
        "Comedy": [
            "comedy",
            "funny",
            "standup",
        ],
        "Vlogging": [
            "vlog",
            "vlogging",
            "vlogger",
        ],
    }

    for niche, keywords in niches.items():
        for keyword in keywords:
            if keyword in text:
                return niche

    return ""


# =========================================================
# CSV
# =========================================================

def ensure_csv():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not DATA_FILE.exists():
        with open(
            DATA_FILE,
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=CSV_HEADERS,
            )
            writer.writeheader()


def read_csv():
    ensure_csv()

    with open(
        DATA_FILE,
        "r",
        newline="",
        encoding="utf-8",
    ) as file:
        return list(csv.DictReader(file))


def lead_key(lead):
    channel = clean(
        lead.get("channel_url", "")
    ).lower()

    profile = clean(
        lead.get("profile_url", "")
    ).lower()

    email = clean(
        lead.get("business_email", "")
    ).lower()

    if channel:
        return "channel:" + channel

    if profile:
        return "profile:" + profile

    if email:
        return "email:" + email

    return (
        clean(lead.get("name", "")).lower()
        + "|"
        + clean(lead.get("platform", "")).lower()
    )


def normalize_lead(lead):
    result = {}

    for header in CSV_HEADERS:
        result[header] = clean(
            lead.get(header, "")
        )

    for field in [
        "profile_url",
        "channel_url",
        "instagram",
        "linkedin",
        "twitter_x",
        "website",
    ]:
        result[field] = normalize_url(
            result[field]
        )

    return result


def save_leads(leads):
    ensure_csv()

    with open(
        DATA_FILE,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=CSV_HEADERS,
        )

        writer.writeheader()

        for lead in leads:
            writer.writerow(
                normalize_lead(lead)
            )

    print(
        f"Saved {len(leads)} leads to {DATA_FILE}"
    )


# =========================================================
# HTTP
# =========================================================

def get_json(url, params):
    try:
        response = requests.get(
            url,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code != 200:
            print(
                f"HTTP ERROR {response.status_code}"
            )
            print(response.text[:1000])
            return {}

        return response.json()

    except Exception as error:
        print(
            f"REQUEST ERROR: {type(error).__name__}: {error}"
        )
        return {}


# =========================================================
# YOUTUBE
# =========================================================

YOUTUBE_SEARCH_QUERIES = [
    "Indian gaming YouTuber",
    "Indian tech YouTuber",
    "Indian gadgets YouTuber",
    "Indian PC computer YouTuber",
    "Indian mobile YouTuber",
    "Indian lifestyle YouTuber",
    "Indian education YouTuber",
    "Indian entertainment YouTuber",
    "Indian fitness YouTuber",
    "Indian fashion YouTuber",
    "Indian travel YouTuber",
    "Indian finance YouTuber",
    "Indian automotive YouTuber",
    "Indian comedy YouTuber",
    "Indian vlogging YouTuber",
]


def youtube_search(query):
    if not YOUTUBE_API_KEY:
        print("ERROR: YOUTUBE_API_KEY is missing.")
        return []

    url = (
        "https://www.googleapis.com/"
        "youtube/v3/search"
    )

    params = {
        "part": "snippet",
        "q": query,
        "type": "channel",
        "regionCode": "IN",
        "maxResults": 50,
        "key": YOUTUBE_API_KEY,
    }

    data = get_json(url, params)

    if "error" in data:
        print("YOUTUBE API ERROR:")
        print(
            json.dumps(
                data["error"],
                indent=2,
            )
        )
        return []

    return data.get("items", [])


def youtube_get_channels(channel_ids):
    if not channel_ids:
        return []

    url = (
        "https://www.googleapis.com/"
        "youtube/v3/channels"
    )

    params = {
        "part": "snippet,statistics,contentDetails",
        "id": ",".join(channel_ids),
        "maxResults": 50,
        "key": YOUTUBE_API_KEY,
    }

    data = get_json(url, params)

    if "error" in data:
        print("YOUTUBE CHANNEL API ERROR:")
        print(
            json.dumps(
                data["error"],
                indent=2,
            )
        )
        return []

    return data.get("items", [])


def youtube_latest_upload(channel):
    try:
        playlist_id = (
            channel
            .get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("uploads", "")
        )

        if not playlist_id:
            return ""

        url = (
            "https://www.googleapis.com/"
            "youtube/v3/playlistItems"
        )

        params = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 1,
            "key": YOUTUBE_API_KEY,
        }

        data = get_json(url, params)
        items = data.get("items", [])

        if not items:
            return ""

        return clean(
            items[0]
            .get("snippet", {})
            .get("publishedAt", "")
        )

    except Exception as error:
        print(
            f"LATEST UPLOAD ERROR: {error}"
        )
        return ""


def collect_youtube():
    print("=" * 60)
    print("STARTING YOUTUBE COLLECTION")
    print("=" * 60)

    if not YOUTUBE_API_KEY:
        print("ERROR: YOUTUBE_API_KEY is missing.")
        return []

    found_channels = {}

    for query in YOUTUBE_SEARCH_QUERIES:
        print(f"Searching YouTube: {query}")

        items = youtube_search(query)

        print(
            f"Results received: {len(items)}"
        )

        for item in items:
            channel_id = (
                item
                .get("snippet", {})
                .get("channelId", "")
            )

            if channel_id:
                found_channels[channel_id] = item

        time.sleep(0.2)

    print(
        f"Unique channels found: "
        f"{len(found_channels)}"
    )

    if not found_channels:
        print("WARNING: No YouTube channels found.")
        return []

    channel_ids = list(
        found_channels.keys()
    )

    channels = []

    for start in range(
        0,
        len(channel_ids),
        50,
    ):
        batch = channel_ids[
            start:start + 50
        ]

        channels.extend(
            youtube_get_channels(batch)
        )

    print(
        f"Channel details received: "
        f"{len(channels)}"
    )

    leads = []

    for channel in channels:
        snippet = channel.get(
            "snippet",
            {},
        )

        statistics = channel.get(
            "statistics",
            {},
        )

        title = clean(
            snippet.get(
                "title",
                "",
            )
        )

        description = clean(
            snippet.get(
                "description",
                "",
            )
        )

        subscribers = safe_int(
            statistics.get(
                "subscriberCount",
                0,
            )
        )

        if not (
            MIN_SUBSCRIBERS
            <= subscribers
            <= MAX_SUBSCRIBERS
        ):
            continue

        niche = detect_niche(
            title
            + " "
            + description
        )

        if not niche:
            continue

        channel_id = clean(
            channel.get(
                "id",
                "",
            )
        )

        if not channel_id:
            continue

        custom_url = clean(
            snippet.get(
                "customUrl",
                "",
            )
        )

        if custom_url:
            profile_url = (
                "https://www.youtube.com/"
                + custom_url.lstrip("@/")
            )
        else:
            profile_url = (
                "https://www.youtube.com/channel/"
                + channel_id
            )

        channel_url = (
            "https://www.youtube.com/channel/"
            + channel_id
        )

        email = extract_email(
            description
        )

        latest_upload = (
            youtube_latest_upload(
                channel
            )
        )

        lead = {
            "name": title,
            "platform": "YouTube",
            "profile_url": profile_url,
            "channel_url": channel_url,
            "creator_or_business": "Creator",
            "niche": niche,
            "country": "IN",
            "city": "",
            "subscribers": subscribers,
            "avg_views": "",
            "business_email": email,
            "instagram": "",
            "linkedin": "",
            "twitter_x": "",
            "website": "",
            "recent_upload": latest_upload,
            "contact_type": (
                "Business Email"
                if email
                else "Public Profile"
            ),
            "lead_source": "YouTube Data API",
            "status": "New",
            "notes": (
                "Public YouTube channel. "
                "Subscriber range matched."
            ),
        }

        leads.append(lead)

    print(
        "YOUTUBE LEADS AFTER FILTERING: "
        f"{len(leads)}"
    )

    return leads


# =========================================================
# GOOGLE SHEETS
# =========================================================

def upload_to_google_sheets(leads):
    print("=" * 60)
    print("STARTING GOOGLE SHEETS UPLOAD")
    print("=" * 60)

    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        print(
            "ERROR: GOOGLE_SERVICE_ACCOUNT_JSON "
            "IS EMPTY OR MISSING."
        )
        return False

    if not GOOGLE_SHEET_ID:
        print(
            "ERROR: GOOGLE_SHEET_ID "
            "IS EMPTY OR MISSING."
        )
        return False

    if not leads:
        print(
            "WARNING: No new leads available "
            "for Google Sheets."
        )
        return True

    try:
        print(
            "Loading Google Sheets libraries..."
        )

        import gspread
        from google.oauth2.service_account import (
            Credentials
        )

        print(
            "Google Sheets libraries loaded."
        )

        # -------------------------------------------------
        # Parse Service Account JSON
        # -------------------------------------------------

        try:
            service_account_info = json.loads(
                GOOGLE_SERVICE_ACCOUNT_JSON
            )
        except json.JSONDecodeError as error:
            print(
                "ERROR: GOOGLE_SERVICE_ACCOUNT_JSON "
                "IS NOT VALID JSON."
            )
            print(
                f"JSON ERROR: {error}"
            )
            return False

        if not isinstance(
            service_account_info,
            dict,
        ):
            print(
                "ERROR: GOOGLE_SERVICE_ACCOUNT_JSON "
                "must contain a JSON object."
            )
            return False

        # -------------------------------------------------
        # Show SAFE account information
        # -------------------------------------------------

        service_account_email = clean(
            service_account_info.get(
                "client_email",
                "",
            )
        )

        project_id = clean(
            service_account_info.get(
                "project_id",
                "",
            )
        )

        if not service_account_email:
            print(
                "ERROR: client_email missing "
                "inside service account JSON."
            )
            return False

        print(
            "Service Account:"
            f" {service_account_email}"
        )

        print(
            "Google Cloud Project:"
            f" {project_id}"
        )

        # -------------------------------------------------
        # Google API Scopes
        # -------------------------------------------------

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        credentials = (
            Credentials.from_service_account_info(
                service_account_info,
                scopes=scopes,
            )
        )

        print(
            "Credentials created successfully."
        )

        # -------------------------------------------------
        # Authorize using the SAME service account
        # from GOOGLE_SERVICE_ACCOUNT_JSON secret
        # -------------------------------------------------

        client = gspread.authorize(
            credentials
        )

        print(
            "Google account authorization "
            "successful."
        )

        # -------------------------------------------------
        # Open EXACT Sheet from GOOGLE_SHEET_ID
        # -------------------------------------------------

        print(
            "Opening Google Sheet using "
            "GOOGLE_SHEET_ID..."
        )

        spreadsheet = client.open_by_key(
            GOOGLE_SHEET_ID
        )

        print(
            "Google Sheet opened successfully:"
            f" {spreadsheet.title}"
        )

        # -------------------------------------------------
        # Use first worksheet
        # -------------------------------------------------

        worksheet = spreadsheet.sheet1

        print(
            "Using worksheet:"
            f" {worksheet.title}"
        )

        # -------------------------------------------------
        # Header
        # -------------------------------------------------

        existing_values = (
            worksheet.get_all_values()
        )

        if not existing_values:
            worksheet.append_row(
                CSV_HEADERS,
                value_input_option="RAW",
            )

            existing_values = [
                CSV_HEADERS
            ]

            print(
                "Google Sheet was empty."
            )

            print(
                "Header row created."
            )

        else:
            existing_header = (
                existing_values[0]
                if existing_values
                else []
            )

            if existing_header != CSV_HEADERS:
                worksheet.update(
                    "A1:T1",
                    [CSV_HEADERS],
                )

                print(
                    "Google Sheet header "
                    "updated."
                )

        # -------------------------------------------------
        # Existing rows / duplicate protection
        # -------------------------------------------------

        existing_values = (
            worksheet.get_all_values()
        )

        print(
            "Existing Google Sheet rows:"
            f" {len(existing_values)}"
        )

        existing_keys = set()

        for row_values in (
            existing_values[1:]
        ):
            row = {}

            for index, header in enumerate(
                CSV_HEADERS
            ):
                row[header] = (
                    row_values[index]
                    if index < len(row_values)
                    else ""
                )

            existing_keys.add(
                lead_key(row)
            )

        # -------------------------------------------------
        # Prepare only NEW rows
        # -------------------------------------------------

        rows_to_add = []

        for lead in leads:
            normalized = normalize_lead(
                lead
            )

            key = lead_key(normalized)

            if key in existing_keys:
                continue

            rows_to_add.append(
                [
                    normalized[header]
                    for header in CSV_HEADERS
                ]
            )

            existing_keys.add(key)

        print(
            "New rows ready for upload:"
            f" {len(rows_to_add)}"
        )

        if not rows_to_add:
            print(
                "No new rows to upload."
            )
            print(
                "Google Sheet already contains "
                "all these leads."
            )
            return True

        # -------------------------------------------------
        # Upload
        # -------------------------------------------------

        print(
            "Uploading rows to Google Sheets..."
        )

        worksheet.append_rows(
            rows_to_add,
            value_input_option="USER_ENTERED",
        )

        print(
            "SUCCESS:"
            f" {len(rows_to_add)} NEW LEADS "
            "UPLOADED TO GOOGLE SHEETS."
        )

        # -------------------------------------------------
        # Verify upload
        # -------------------------------------------------

        print(
            "Verifying Google Sheets upload..."
        )

        updated_values = (
            worksheet.get_all_values()
        )

        print(
            "Google Sheet rows after upload:"
            f" {len(updated_values)}"
        )

        expected_min_rows = (
            len(existing_values)
            + len(rows_to_add)
        )

        if len(updated_values) >= expected_min_rows:
            print(
                "GOOGLE SHEETS UPLOAD VERIFIED."
            )
            return True

        print(
            "WARNING: Upload request completed, "
            "but row count verification did "
            "not match."
        )
        return False

    except Exception as error:
        print("=" * 60)
        print("GOOGLE SHEETS UPLOAD FAILED")
        print("=" * 60)
        print(
            f"ERROR TYPE: {type(error).__name__}"
        )
        print(
            f"ERROR: {error}"
        )
        print()
        print(
            "CHECKLIST:"
        )
        print(
            "1. GOOGLE_SERVICE_ACCOUNT_JSON "
            "contains the complete JSON."
        )
        print(
            "2. GOOGLE_SHEET_ID is correct."
        )
        print(
            "3. The service-account email "
            "has Editor access to the Sheet."
        )
        print(
            "4. Google Sheets API and Google "
            "Drive API are enabled."
        )
        return False


# =========================================================
# MAIN
# =========================================================

def main():
    print("=" * 60)
    print("LEAD AUTOMATION STARTED")
    print("=" * 60)

    print(
        "Google Sheet ID configured:"
        f" {'YES' if GOOGLE_SHEET_ID else 'NO'}"
    )

    print(
        "Google Service Account configured:"
        f" {'YES' if GOOGLE_SERVICE_ACCOUNT_JSON else 'NO'}"
    )

    print(
        "YouTube API configured:"
        f" {'YES' if YOUTUBE_API_KEY else 'NO'}"
    )

    ensure_csv()

    youtube_leads = collect_youtube()

    print(
        "Total YouTube leads collected:"
        f" {len(youtube_leads)}"
    )

    # -----------------------------------------------------
    # Save only new leads to local CSV
    # -----------------------------------------------------

    existing_leads = read_csv()

    existing_keys = {
        lead_key(lead)
        for lead in existing_leads
    }

    final_leads = list(existing_leads)
    new_count = 0

    for lead in youtube_leads:
        normalized = normalize_lead(lead)
        key = lead_key(normalized)

        if key not in existing_keys:
            final_leads.append(normalized)
            existing_keys.add(key)
            new_count += 1

    print(
        "New leads added to CSV:"
        f" {new_count}"
    )

    save_leads(final_leads)

    # -----------------------------------------------------
    # Google Sheets
    # -----------------------------------------------------

    sheets_success = upload_to_google_sheets(
        youtube_leads
    )

    if sheets_success:
        print(
            "FINAL STATUS: GOOGLE SHEETS SUCCESS"
        )
    else:
        print(
            "FINAL STATUS: GOOGLE SHEETS FAILED"
        )

    print("=" * 60)
    print("LEAD AUTOMATION FINISHED")
    print("=" * 60)


if __name__ == "__main__":
    main()
'''

output_path = "/mnt/data/lead_collector_updated.py"
Path(output_path).write_text(code, encoding="utf-8")

# Final syntax check before giving the file to the user.
compile(code, output_path, "exec")

print(f"Updated file created: {output_path}")
print(f"Lines: {len(code.splitlines())}")
print("Syntax check: PASSED")
