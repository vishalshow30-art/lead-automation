from pathlib import Path
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

DATA_FILE = PROJECT_ROOT / "data" / "leads.csv"

MIN_SUBSCRIBERS = 10_000
MAX_SUBSCRIBERS = 50_000

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON", ""
).strip()
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()

REQUEST_TIMEOUT = 30


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
# HELPERS
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

    if match:
        return match.group(0)

    return ""


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
            "smartphone",
            "android",
            "iphone",
            "software",
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
    DATA_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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
    channel_url = clean(
        lead.get("channel_url", "")
    ).lower()

    profile_url = clean(
        lead.get("profile_url", "")
    ).lower()

    email = clean(
        lead.get("business_email", "")
    ).lower()

    if channel_url:
        return "channel:" + channel_url

    if profile_url:
        return "profile:" + profile_url

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

    result["profile_url"] = normalize_url(
        result["profile_url"]
    )

    result["channel_url"] = normalize_url(
        result["channel_url"]
    )

    result["instagram"] = normalize_url(
        result["instagram"]
    )

    result["linkedin"] = normalize_url(
        result["linkedin"]
    )

    result["twitter_x"] = normalize_url(
        result["twitter_x"]
    )

    result["website"] = normalize_url(
        result["website"]
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
                f"HTTP error {response.status_code}: "
                f"{response.text[:500]}"
            )
            return {}

        return response.json()

    except Exception as error:
        print(
            f"Request error: {error}"
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
        print(
            "ERROR: YOUTUBE_API_KEY is missing."
        )
        return []

    url = (
        "https://www.googleapis.com/youtube/v3/search"
    )

    params = {
        "part": "snippet",
        "q": query,
        "type": "channel",
        "regionCode": "IN",
        "maxResults": 50,
        "key": YOUTUBE_API_KEY,
    }

    data = get_json(
        url,
        params,
    )

    if "error" in data:
        print(
            "YouTube API error:",
            json.dumps(
                data["error"],
                indent=2,
            ),
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

    data = get_json(
        url,
        params,
    )

    if "error" in data:
        print(
            "YouTube channel API error:",
            json.dumps(
                data["error"],
                indent=2,
            ),
        )
        return []

    return data.get("items", [])


def youtube_latest_upload(channel):
    try:
        uploads_playlist = (
            channel
            .get("contentDetails", {})
            .get("relatedPlaylists", {})
            .get("uploads", "")
        )

        if not uploads_playlist:
            return ""

        url = (
            "https://www.googleapis.com/"
            "youtube/v3/playlistItems"
        )

        params = {
            "part": "snippet",
            "playlistId": uploads_playlist,
            "maxResults": 1,
            "key": YOUTUBE_API_KEY,
        }

        data = get_json(
            url,
            params,
        )

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
            f"Latest upload error: {error}"
        )
        return ""


def collect_youtube():
    print(
        "Starting YouTube lead collection..."
    )

    if not YOUTUBE_API_KEY:
        print(
            "ERROR: YOUTUBE_API_KEY is missing."
        )
        return []

    found_channels = {}

    for query in YOUTUBE_SEARCH_QUERIES:
        print(
            f"Searching YouTube: {query}"
        )

        items = youtube_search(query)

        print(
            f"Found {len(items)} search results."
        )

        for item in items:
            channel_id = (
                item.get("snippet", {})
                .get("channelId", "")
            )

            if channel_id:
                found_channels[channel_id] = item

        time.sleep(0.2)

    print(
        f"Unique YouTube channels found: "
        f"{len(found_channels)}"
    )

    if not found_channels:
        print(
            "WARNING: YouTube returned "
            "zero channels."
        )
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
            snippet.get("title", "")
        )

        description = clean(
            snippet.get("description", "")
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

        combined_text = (
            title
            + " "
            + description
        )

        niche = detect_niche(
            combined_text
        )

        if not niche:
            continue

        custom_url = clean(
            snippet.get("customUrl", "")
        )

        channel_id = clean(
            channel.get("id", "")
        )

        if custom_url:
            profile_url = (
                "https://www.youtube.com/"
                + custom_url.lstrip("@/")
            )
        else:
            profile_url = (
                "https://www.youtube.com/"
                "channel/"
                + channel_id
            )

        channel_url = (
            "https://www.youtube.com/"
            "channel/"
            + channel_id
        )

        email = extract_email(
            description
        )

        latest_upload = (
            youtube_latest_upload(channel)
        )

        contact_type = (
            "Business Email"
            if email
            else "Public Profile"
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
            "contact_type": contact_type,
            "lead_source": "YouTube Data API",
            "status": "New",
            "notes": (
                "Public YouTube channel. "
                "Subscriber range matched."
            ),
        }

        leads.append(lead)

    print(
        f"YouTube leads after filtering: "
        f"{len(leads)}"
    )

    return leads


# =========================================================
# GOOGLE SHEETS
# =========================================================

def upload_to_google_sheets(leads):
    print(
        "Starting Google Sheets upload..."
    )

    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        print(
            "ERROR: GOOGLE_SERVICE_ACCOUNT_JSON "
            "is missing."
        )
        return

    if not GOOGLE_SHEET_ID:
        print(
            "ERROR: GOOGLE_SHEET_ID "
            "is missing."
        )
        return

    if not leads:
        print(
            "No leads available for Google Sheets."
        )
        return

    try:
        import gspread
        from google.oauth2.service_account import (
            Credentials,
        )

        print(
            "Google Sheets libraries loaded."
        )

        service_account_info = json.loads(
            GOOGLE_SERVICE_ACCOUNT_JSON
        )

        scopes = [
            "https://www.googleapis.com/auth/"
            "spreadsheets",
            "https://www.googleapis.com/auth/"
            "drive",
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

        print(
            "Connected to Google account."
        )

        spreadsheet = client.open_by_key(
            GOOGLE_SHEET_ID
        )

        print(
            f"Google Sheet opened: "
            f"{spreadsheet.title}"
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
                    row[header] = (
                        row_values[index]
                    )
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
                "Google Sheet already contains "
                "these leads."
            )
            return

        worksheet.append_rows(
            rows_to_add,
            value_input_option="USER_ENTERED",
        )

        print(
            f"SUCCESS: Uploaded "
            f"{len(rows_to_add)} new leads "
            f"to Google Sheets."
        )

    except ImportError as error:
        print(
            "ERROR: Google Sheets package "
            f"is missing: {error}"
        )

    except json.JSONDecodeError as error:
        print(
            "ERROR: GOOGLE_SERVICE_ACCOUNT_JSON "
            f"is not valid JSON: {error}"
        )

    except Exception as error:
        print(
            "ERROR: Google Sheets upload failed:"
        )
        print(
            repr(error)
        )


# =========================================================
# MAIN
# =========================================================

def main():
    print("=" * 60)
    print("LEAD AUTOMATION STARTED")
    print("=" * 60)

    ensure_csv()

    youtube_leads = collect_youtube()

    all_leads = youtube_leads

    print(
        f"Total collected leads: "
        f"{len(all_leads)}"
    )

    existing_leads = read_csv()

    existing_keys = {
        lead_key(lead)
        for lead in existing_leads
    }

    final_leads = list(existing_leads)

    new_count = 0

    for lead in all_leads:
        normalized = normalize_lead(
            lead
        )

        key = lead_key(
            normalized
        )

        if key not in existing_keys:
            final_leads.append(
                normalized
            )
            existing_keys.add(key)
            new_count += 1

    print(
        f"New leads found: {new_count}"
    )

    save_leads(final_leads)

    # Upload ONLY the newly collected leads.
    upload_to_google_sheets(
        all_leads
    )

    print("=" * 60)
    print("LEAD AUTOMATION FINISHED")
    print("=" * 60)


if __name__ == "__main__":
    main()
