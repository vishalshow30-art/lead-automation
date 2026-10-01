from pathlib import Path
import csv
import json
import os
import re
import time

import requests


# ============================================================
# PROJECT SETTINGS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = PROJECT_ROOT / "data" / "leads.csv"

MIN_SUBSCRIBERS = 10_000
MAX_SUBSCRIBERS = 50_000

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON", ""
).strip()
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()

REQUEST_TIMEOUT = 30


# ============================================================
# CSV HEADER
# ============================================================

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


# ============================================================
# BASIC HELPERS
# ============================================================

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
        url = "https://" + url

    return url.rstrip("/")


def extract_email(text):
    text = clean(text)

    if not text:
        return ""

    pattern = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    matches = re.findall(pattern, text)

    for email in matches:
        email_lower = email.lower()

        if "example.com" in email_lower:
            continue

        if "example.org" in email_lower:
            continue

        if "example.net" in email_lower:
            continue

        return email

    return ""


def detect_niche(text):
    text = clean(text).lower()

    keywords = {
        "Gaming": [
            "gaming",
            "gamer",
            "gameplay",
            "minecraft",
            "valorant",
            "bgmi",
            "pubg",
            "free fire",
            "esports",
        ],
        "Tech": [
            "technology",
            "tech",
            "smartphone",
            "android",
            "iphone",
            "software",
        ],
        "Gadgets": [
            "gadget",
            "gadgets",
            "unboxing",
            "accessories",
        ],
        "PC/Computer": [
            "pc",
            "computer",
            "laptop",
            "desktop",
            "cpu",
            "gpu",
            "windows",
            "macbook",
        ],
        "Mobile": [
            "mobile phone",
            "mobile",
            "smartphone",
        ],
        "Lifestyle": [
            "lifestyle",
            "daily life",
            "routine",
        ],
        "Education": [
            "education",
            "study",
            "learning",
            "tutorial",
            "career",
        ],
        "Entertainment": [
            "entertainment",
            "movie",
            "movies",
            "film",
            "web series",
        ],
        "Fitness": [
            "fitness",
            "workout",
            "gym",
            "bodybuilding",
        ],
        "Fashion": [
            "fashion",
            "style",
            "makeup",
            "beauty",
        ],
        "Travel": [
            "travel",
            "travelling",
            "trip",
            "tour",
        ],
        "Finance": [
            "finance",
            "stock market",
            "stocks",
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
            "motorcycle",
            "automobile",
        ],
        "Comedy": [
            "comedy",
            "funny",
            "standup",
            "stand-up",
            "humor",
        ],
        "Vlogging": [
            "vlog",
            "vlogging",
            "daily vlog",
        ],
    }

    for niche, words in keywords.items():
        for word in words:
            if word in text:
                return niche

    return "Other"


# ============================================================
# CSV FUNCTIONS
# ============================================================

def ensure_csv():
    DATA_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not DATA_FILE.exists():
        with DATA_FILE.open(
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

    try:
        with DATA_FILE.open(
            "r",
            newline="",
            encoding="utf-8",
        ) as file:
            reader = csv.DictReader(file)

            rows = []

            for row in reader:
                if row:
                    rows.append(row)

            return rows

    except Exception as error:
        print(f"CSV read error: {error}")
        return []


def lead_key(lead):
    platform = clean(
        lead.get("platform", "")
    ).lower()

    profile = normalize_url(
        lead.get("profile_url", "")
    ).lower()

    channel = normalize_url(
        lead.get("channel_url", "")
    ).lower()

    if profile:
        return platform + "|" + profile

    if channel:
        return platform + "|" + channel

    name = clean(
        lead.get("name", "")
    ).lower()

    email = clean(
        lead.get("business_email", "")
    ).lower()

    return platform + "|" + name + "|" + email


def normalize_lead(lead):
    result = {}

    for header in CSV_HEADERS:
        result[header] = clean(
            lead.get(header, "")
        )

    return result


def save_leads(leads):
    ensure_csv()

    existing = read_csv()
    combined = {}

    for lead in existing:
        normalized = normalize_lead(lead)
        key = lead_key(normalized)

        if key:
            combined[key] = normalized

    for lead in leads:
        normalized = normalize_lead(lead)
        key = lead_key(normalized)

        if key:
            combined[key] = normalized

    with DATA_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=CSV_HEADERS,
        )

        writer.writeheader()

        for lead in combined.values():
            writer.writerow(lead)

    print(
        f"CSV saved successfully. "
        f"Total leads: {len(combined)}"
    )


# ============================================================
# HTTP HELPER
# ============================================================

def get_json(url, params=None):
    try:
        response = requests.get(
            url,
            params=params or {},
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        return response.json()

    except requests.RequestException as error:
        print(f"API request error: {error}")
        return {}

    except ValueError as error:
        print(f"JSON error: {error}")
        return {}


# ============================================================
# YOUTUBE API
# ============================================================

YOUTUBE_SEARCHES = [
    "Indian gaming YouTuber",
    "Indian tech YouTuber",
    "Indian gadget YouTuber",
    "Indian PC YouTuber",
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
    url = (
        "https://www.googleapis.com/"
        "youtube/v3/search"
    )

    params = {
        "part": "snippet",
        "q": query,
        "type": "channel",
        "maxResults": 50,
        "key": YOUTUBE_API_KEY,
    }

    return get_json(url, params)


def youtube_get_channels(channel_ids):
    if not channel_ids:
        return []

    channels = []

    for start in range(
        0,
        len(channel_ids),
        50,
    ):
        batch = channel_ids[
            start:start + 50
        ]

        url = (
            "https://www.googleapis.com/"
            "youtube/v3/channels"
        )

        params = {
            "part": (
                "snippet,"
                "statistics,"
                "contentDetails"
            ),
            "id": ",".join(batch),
            "key": YOUTUBE_API_KEY,
        }

        data = get_json(
            url,
            params,
        )

        channels.extend(
            data.get("items", [])
        )

        time.sleep(0.2)

    return channels


def youtube_latest_upload(playlist_id):
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

    data = get_json(
        url,
        params,
    )

    items = data.get(
        "items",
        [],
    )

    if not items:
        return ""

    snippet = items[0].get(
        "snippet",
        {},
    )

    return clean(
        snippet.get(
            "publishedAt",
            "",
        )
    )


def collect_youtube():
    if not YOUTUBE_API_KEY:
        print(
            "YOUTUBE_API_KEY is missing."
        )
        return []

    print(
        "Starting YouTube collection..."
    )

    channel_ids = set()

    for query in YOUTUBE_SEARCHES:
        print(
            f"Searching YouTube: {query}"
        )

        data = youtube_search(
            query
        )

        for item in data.get(
            "items",
            [],
        ):
            snippet = item.get(
                "snippet",
                {},
            )

            channel_id = clean(
                snippet.get(
                    "channelId",
                    "",
                )
            )

            if channel_id:
                channel_ids.add(
                    channel_id
                )

        time.sleep(0.2)

    print(
        f"Found {len(channel_ids)} "
        "YouTube channels."
    )

    channels = youtube_get_channels(
        list(channel_ids)
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

        content_details = channel.get(
            "contentDetails",
            {},
        )

        subscribers = safe_int(
            statistics.get(
                "subscriberCount",
                0,
            )
        )

        if subscribers < MIN_SUBSCRIBERS:
            continue

        if subscribers > MAX_SUBSCRIBERS:
            continue

        channel_id = clean(
            channel.get(
                "id",
                "",
            )
        )

        name = clean(
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

        custom_url = clean(
            snippet.get(
                "customUrl",
                "",
            )
        )

        channel_url = (
            "https://www.youtube.com/channel/"
            + channel_id
        )

        if custom_url:
            if custom_url.startswith("@"):
                profile_url = (
                    "https://www.youtube.com/"
                    + custom_url
                )
            else:
                profile_url = (
                    "https://www.youtube.com/@"
                    + custom_url
                )
        else:
            profile_url = channel_url

        uploads_playlist = (
            content_details
            .get(
                "relatedPlaylists",
                {},
            )
            .get(
                "uploads",
                "",
            )
        )

        recent_upload = youtube_latest_upload(
            uploads_playlist
        )

        email = extract_email(
            description
        )

        niche = detect_niche(
            name + " " + description
        )

        lead = {
            "name": name,
            "platform": "YouTube",
            "profile_url": profile_url,
            "channel_url": channel_url,
            "creator_or_business": "Creator",
            "niche": niche,
            "country": clean(
                snippet.get(
                    "country",
                    "",
                )
            ) or "India",
            "city": "",
            "subscribers": str(
                subscribers
            ),
            "avg_views": "",
            "business_email": email,
            "instagram": "",
            "linkedin": "",
            "twitter_x": "",
            "website": "",
            "recent_upload": recent_upload,
            "contact_type": (
                "Business Email"
                if email
                else "Public Profile"
            ),
            "lead_source": (
                "YouTube Data API"
            ),
            "status": "New",
            "notes": (
                "Public YouTube channel. "
                "Subscriber range matched."
            ),
        }

        leads.append(lead)

    print(
        f"YouTube qualified leads: "
        f"{len(leads)}"
    )

    return leads


# ============================================================
# GOOGLE SHEETS
# ============================================================

def upload_to_google_sheets(leads):
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        print(
            "Google service account secret "
            "not configured. Skipping Sheets."
        )
        return

    if not GOOGLE_SHEET_ID:
        print(
            "Google Sheet ID not configured. "
            "Skipping Sheets."
        )
        return

    if not leads:
        print(
            "No new leads to upload."
        )
        return

    try:
        import gspread
        from google.oauth2.service_account import (
            Credentials,
        )

        service_account_info = json.loads(
            GOOGLE_SERVICE_ACCOUNT_JSON
        )

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

        client = gspread.authorize(
            credentials
        )

        spreadsheet = client.open_by_key(
            GOOGLE_SHEET_ID
        )

        worksheet = spreadsheet.sheet1

        worksheet.update(
            "A1:T1",
            [CSV_HEADERS],
        )

        existing_values = (
            worksheet.get_all_values()
        )

        existing_keys = set()

        for row_values in existing_values[1:]:
            row = {}

            for index, header in enumerate(
                CSV_HEADERS
            ):
                if index < len(row_values):
                    row[header] = row_values[index]
                else:
                    row[header] = ""

            existing_keys.add(
                lead_key(row)
            )

        rows_to_add = []

        for lead in leads:
            normalized = normalize_lead(
                lead
            )

            key = lead_key(
                normalized
            )

            if key in existing_keys:
                continue

            rows_to_add.append(
                [
                    normalized[header]
                    for header in CSV_HEADERS
                ]
            )

            existing_keys.add(key)

        if not rows_to_add:
            print(
                "Google Sheet already "
                "contains these leads."
            )
            return

        worksheet.append_rows(
            rows_to_add,
            value_input_option="USER_ENTERED",
        )

        print(
            f"Uploaded {len(rows_to_add)} "
            "new leads to Google Sheets."
        )

    except Exception as error:
        print(
            f"Google Sheets error: {error}"
        )


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("LEAD AUTOMATION STARTED")
    print("=" * 60)

    print(
        f"CSV file: {DATA_FILE}"
    )

    ensure_csv()

    all_leads = []

    try:
        youtube_leads = collect_youtube()
        all_leads.extend(
            youtube_leads
        )
    except Exception as error:
        print(
            f"YouTube error: {error}"
        )

    unique = {}

    for lead in all_leads:
        normalized = normalize_lead(
            lead
        )

        key = lead_key(
            normalized
        )

        if key:
            unique[key] = normalized

    final_leads = list(
        unique.values()
    )

    print(
        f"Total new leads collected: "
        f"{len(final_leads)}"
    )

    save_leads(
        final_leads
    )

    try:
        upload_to_google_sheets(
            final_leads
        )
    except Exception as error:
        print(
            f"Google Sheets upload error: "
            f"{error}"
        )

    print("=" * 60)
    print("LEAD AUTOMATION FINISHED")
    print("=" * 60)


if __name__ == "__main__":
    main()
