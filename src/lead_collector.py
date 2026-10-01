from pathlib import Path
import csv
import json
import os
import re
import time
from typing import Dict, List

import requests

try:
    from googleapiclient.discovery import build
except ImportError:
    build = None

try:
    from google.oauth2.service_account import Credentials
except ImportError:
    Credentials = None


# ============================================================
# PROJECT PATHS
# ============================================================

def get_project_root() -> Path:
    current = Path(__file__).resolve()

    for parent in current.parents:
        if (parent / "requirements.txt").exists():
            return parent

    return current.parent.parent


PROJECT_ROOT = get_project_root()
DATA_DIR = PROJECT_ROOT / "data"
DATA_FILE = DATA_DIR / "leads.csv"


# ============================================================
# CSV HEADERS
# ============================================================

CSV_HEADERS = [
    "name",
    "platform",
    "channel_url",
    "subscriber_count",
    "niche",
    "country",
    "contact_email",
    "business_email",
    "website",
    "instagram_url",
    "notes",
]


# ============================================================
# SEARCH TERMS
# ============================================================

INDIA_SEARCH_TERMS = [
    "Indian gaming creator",
    "Indian tech creator",
    "Indian gadgets creator",
    "Indian PC creator",
    "Indian mobile creator",
    "Indian lifestyle creator",
    "Indian education creator",
    "Indian entertainment creator",
    "Indian fitness creator",
    "Indian fashion creator",
    "Indian travel creator",
    "Indian finance creator",
    "Indian automotive creator",
    "Indian comedy creator",
    "Indian vlogger",
    "Indian content creator",
    "Indian YouTuber",
    "Indian influencer",
]

INTERNATIONAL_SEARCH_TERMS = [
    "gaming creator",
    "tech creator",
    "gadgets creator",
    "PC creator",
    "mobile creator",
    "lifestyle creator",
    "education creator",
    "entertainment creator",
    "fitness creator",
    "fashion creator",
    "travel creator",
    "finance creator",
    "automotive creator",
    "comedy creator",
    "vlogger",
    "content creator",
    "influencer",
]


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(value: str) -> str:
    if not value:
        return ""

    value = str(value)
    value = value.replace("\n", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_url(url: str) -> str:
    return (
        str(url or "")
        .strip()
        .lower()
        .rstrip("/")
    )


# ============================================================
# CSV
# ============================================================

def ensure_leads_file() -> None:
    DATA_DIR.mkdir(
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

        print(
            "Created CSV:",
            DATA_FILE,
        )


def load_existing_leads() -> List[Dict[str, str]]:

    ensure_leads_file()

    leads = []

    try:

        with DATA_FILE.open(
            "r",
            newline="",
            encoding="utf-8",
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:

                lead = {}

                for header in CSV_HEADERS:
                    lead[header] = clean_text(
                        row.get(header, "")
                    )

                leads.append(lead)

    except Exception as exc:

        print(
            "Could not read CSV:",
            exc,
        )

    return leads


def save_leads(
    leads: List[Dict[str, str]]
) -> None:

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

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

        for lead in leads:

            row = {}

            for header in CSV_HEADERS:
                row[header] = lead.get(
                    header,
                    "",
                )

            writer.writerow(row)

    print(
        "CSV saved successfully:",
        DATA_FILE,
    )


# ============================================================
# DUPLICATE CHECK
# ============================================================

def lead_exists(
    existing_leads: List[Dict[str, str]],
    channel_url: str,
    name: str,
) -> bool:

    new_url = normalize_url(
        channel_url
    )

    new_name = clean_text(
        name
    ).lower()

    for lead in existing_leads:

        old_url = normalize_url(
            lead.get(
                "channel_url",
                "",
            )
        )

        old_name = clean_text(
            lead.get(
                "name",
                "",
            )
        ).lower()

        if new_url and new_url == old_url:
            return True

        if new_name and new_name == old_name:
            return True

    return False


# ============================================================
# NICHE DETECTION
# ============================================================

def detect_niche(
    title: str,
    description: str,
) -> str:

    text = (
        f"{title} {description}"
    ).lower()

    keywords = {

        "Gaming": [
            "gaming",
            "gamer",
            "gameplay",
            "esports",
        ],

        "Tech": [
            "tech",
            "technology",
            "smartphone",
            "computer",
        ],

        "Gadgets": [
            "gadget",
            "gadgets",
            "device",
            "accessories",
        ],

        "PC Computer": [
            "pc",
            "laptop",
            "desktop",
            "computer",
        ],

        "Mobile": [
            "mobile",
            "android",
            "iphone",
            "ios",
        ],

        "Lifestyle": [
            "lifestyle",
            "daily life",
        ],

        "Education": [
            "education",
            "study",
            "learning",
        ],

        "Entertainment": [
            "entertainment",
            "movies",
            "music",
        ],

        "Fitness": [
            "fitness",
            "workout",
            "gym",
        ],

        "Fashion": [
            "fashion",
            "style",
            "outfit",
        ],

        "Travel": [
            "travel",
            "tour",
            "trip",
        ],

        "Finance": [
            "finance",
            "investment",
            "investing",
            "stock",
        ],

        "Automotive": [
            "automotive",
            "car",
            "cars",
            "bike",
            "automobile",
        ],

        "Comedy": [
            "comedy",
            "funny",
            "humor",
            "standup",
        ],

        "Vlogging": [
            "vlog",
            "vlogger",
        ],
    }

    for niche, words in keywords.items():

        for word in words:

            if word in text:
                return niche

    return ""


# ============================================================
# COUNTRY
# ============================================================

def detect_country(
    title: str,
    description: str,
) -> str:

    text = (
        f"{title} {description}"
    ).lower()

    india_terms = [
        "india",
        "indian",
        "hindi",
        "bharat",
        "delhi",
        "mumbai",
        "bangalore",
        "bengaluru",
        "hyderabad",
        "pune",
        "noida",
        "gurgaon",
        "uttar pradesh",
    ]

    for term in india_terms:

        if term in text:
            return "India"

    return ""


# ============================================================
# GOOGLE SHEETS
# ============================================================

def get_google_sheets_service():

    if build is None:

        print(
            "ERROR: google-api-python-client "
            "is not installed."
        )

        return None

    if Credentials is None:

        print(
            "ERROR: google-auth "
            "is not installed."
        )

        return None

    service_account_json = os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_JSON"
    )

    if not service_account_json:

        print(
            "ERROR: GOOGLE_SERVICE_ACCOUNT_JSON "
            "is missing."
        )

        return None

    try:

        credentials_info = json.loads(
            service_account_json
        )

        credentials = (
            Credentials.from_service_account_info(
                credentials_info,
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets"
                ],
            )
        )

        service = build(
            "sheets",
            "v4",
            credentials=credentials,
        )

        print(
            "Google Sheets connection successful."
        )

        return service

    except Exception as exc:

        print(
            "Google Sheets connection failed:",
            exc,
        )

        return None


def save_leads_to_google_sheet(
    leads: List[Dict[str, str]]
) -> None:

    if not leads:

        print(
            "Google Sheet: no new leads."
        )

        return

    spreadsheet_id = os.getenv(
        "GOOGLE_SHEET_ID"
    )

    if not spreadsheet_id:

        print(
            "ERROR: GOOGLE_SHEET_ID is missing."
        )

        return

    sheets = get_google_sheets_service()

    if sheets is None:
        return

    try:

        spreadsheet = (
            sheets.spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id
            )
            .execute()
        )

        sheet_list = spreadsheet.get(
            "sheets",
            [],
        )

        if not sheet_list:

            print(
                "ERROR: No Google Sheet tab found."
            )

            return

        sheet_title = (
            sheet_list[0]
            .get("properties", {})
            .get("title", "Sheet1")
        )

        print(
            "Google Sheet tab:",
            sheet_title,
        )

        header_range = (
            f"'{sheet_title}'!A1:K1"
        )

        (
            sheets.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=header_range,
                valueInputOption="RAW",
                body={
                    "values": [
                        CSV_HEADERS
                    ]
                },
            )
            .execute()
        )

        print(
            "Google Sheet header checked."
        )

        values = []

        for lead in leads:

            row = []

            for header in CSV_HEADERS:

                row.append(
                    lead.get(
                        header,
                        "",
                    )
                )

            values.append(row)

        result = (
            sheets.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=f"'{sheet_title}'!A:K",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={
                    "values": values
                },
            )
            .execute()
        )

        updated_range = (
            result
            .get("updates", {})
            .get("updatedRange", "")
        )

        print(
            "Google Sheet updated successfully."
        )

        print(
            "Google Sheet rows added:",
            len(values),
        )

        if updated_range:

            print(
                "Updated range:",
                updated_range,
            )

    except Exception as exc:

        print(
            "Google Sheet upload failed:",
            exc,
        )


# ============================================================
# YOUTUBE
# ============================================================

def get_youtube_service():

    api_key = os.getenv(
        "YOUTUBE_API_KEY"
    )

    if not api_key:

        print(
            "ERROR: YOUTUBE_API_KEY is missing."
        )

        return None

    if build is None:

        print(
            "ERROR: Google API library missing."
        )

        return None

    try:

        service = build(
            "youtube",
            "v3",
            developerKey=api_key,
        )

        print(
            "YouTube API connection successful."
        )

        return service

    except Exception as exc:

        print(
            "YouTube connection failed:",
            exc,
        )

        return None


def search_youtube_channels(
    youtube,
    search_term: str,
    max_results: int = 25,
) -> List[Dict[str, str]]:

    results = []

    try:

        response = (
            youtube.search()
            .list(
                part="snippet",
                q=search_term,
                type="channel",
                maxResults=max_results,
            )
            .execute()
        )

    except Exception as exc:

        print(
            "YouTube search failed:",
            search_term,
        )

        print(exc)

        return results

    for item in response.get(
        "items",
        [],
    ):

        channel_id = (
            item
            .get("id", {})
            .get("channelId", "")
        )

        snippet = item.get(
            "snippet",
            {},
        )

        title = clean_text(
            snippet.get(
                "title",
                "",
            )
        )

        description = clean_text(
            snippet.get(
                "description",
                "",
            )
        )

        if not channel_id or not title:
            continue

        results.append({
            "channel_id": channel_id,
            "name": title,
            "description": description,
            "channel_url": (
                "https://www.youtube.com/channel/"
                + channel_id
            ),
        })

    return results


def get_youtube_channel_details(
    youtube,
    channel_ids: List[str],
) -> List[Dict[str, str]]:

    if not channel_ids:
        return []

    results = []

    for start in range(
        0,
        len(channel_ids),
        50,
    ):

        batch = channel_ids[
            start:start + 50
        ]

        try:

            response = (
                youtube.channels()
                .list(
                    part="snippet,statistics",
                    id=",".join(batch),
                )
                .execute()
            )

        except Exception as exc:

            print(
                "YouTube details error:",
                exc,
            )

            continue

        for item in response.get(
            "items",
            [],
        ):

            snippet = item.get(
                "snippet",
                {},
            )

            statistics = item.get(
                "statistics",
                {},
            )

            channel_id = item.get(
                "id",
                "",
            )

            title = clean_text(
                snippet.get(
                    "title",
                    "",
                )
            )

            description = clean_text(
                snippet.get(
                    "description",
                    "",
                )
            )

            subscribers = statistics.get(
                "subscriberCount",
                "",
            )

            if statistics.get(
                "hiddenSubscriberCount",
                False,
            ):

                subscribers = ""

            country = clean_text(
                snippet.get(
                    "country",
                    "",
                )
            )

            if not country:

                country = detect_country(
                    title,
                    description,
                )

            results.append({
                "name": title,
                "platform": "YouTube",
                "channel_url": (
                    "https://www.youtube.com/channel/"
                    + channel_id
                ),
                "subscriber_count": subscribers,
                "niche": detect_niche(
                    title,
                    description,
                ),
                "country": country,
                "contact_email": "",
                "business_email": "",
                "website": "",
                "instagram_url": "",
                "notes": (
                    "Public YouTube "
                    "channel information."
                ),
            })

    return results


def subscriber_in_target_range(
    subscriber_count: str,
) -> bool:

    try:

        count = int(
            subscriber_count
        )

    except (
        ValueError,
        TypeError,
    ):

        return False

    return (
        10000 <= count <= 50000
    )


def collect_youtube_leads(
    existing_leads: List[Dict[str, str]]
) -> List[Dict[str, str]]:

    youtube = get_youtube_service()

    if youtube is None:
        return []

    new_leads = []

    all_terms = (
        INDIA_SEARCH_TERMS
        + INTERNATIONAL_SEARCH_TERMS
    )

    print(
        "Starting YouTube discovery..."
    )

    seen_ids = set()

    for search_term in all_terms:

        print(
            "YouTube search:",
            search_term,
        )

        channels = search_youtube_channels(
            youtube,
            search_term,
            25,
        )

        channel_ids = []

        for channel in channels:

            channel_id = channel.get(
                "channel_id",
                "",
            )

            if channel_id and channel_id not in seen_ids:

                seen_ids.add(
                    channel_id
                )

                channel_ids.append(
                    channel_id
                )

        details = get_youtube_channel_details(
            youtube,
            channel_ids,
        )

        for lead in details:

            if not subscriber_in_target_range(
                lead.get(
                    "subscriber_count",
                    "",
                )
            ):
                continue

            if lead_exists(
                existing_leads,
                lead.get(
                    "channel_url",
                    "",
                ),
                lead.get(
                    "name",
                    "",
                ),
            ):
                continue

            if lead_exists(
                new_leads,
                lead.get(
                    "channel_url",
                    "",
                ),
                lead.get(
                    "name",
                    "",
                ),
            ):
                continue

            new_leads.append(
                lead
            )

        time.sleep(0.5)

    print(
        "New YouTube leads found:",
        len(new_leads),
    )

    return new_leads


# ============================================================
# GENERIC API HELPERS
# ============================================================

def get_bearer_token(
    env_name: str
) -> str:

    return os.ge
