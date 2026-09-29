import os
import csv
import json
import time
from pathlib import Path
from typing import Dict, List, Set, Optional

import requests
import gspread
from google.oauth2.service_account import Credentials


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

LEADS_FILE = DATA_DIR / "leads.csv"
PUBLIC_LEADS_FILE = DATA_DIR / "public_leads.csv"

# Google
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON", ""
).strip()

GOOGLE_SHEET_ID = os.getenv(
    "GOOGLE_SHEET_ID", ""
).strip()

GOOGLE_SHEET_NAME = os.getenv(
    "GOOGLE_SHEET_NAME", "Lead Automation"
).strip()

# YouTube
YOUTUBE_API_KEY = os.getenv(
    "YOUTUBE_API_KEY", ""
).strip()

# Lead filters
MIN_SUBSCRIBERS = int(
    os.getenv("MIN_SUBSCRIBERS", "10000")
)

MAX_SUBSCRIBERS = int(
    os.getenv("MAX_SUBSCRIBERS", "50000")
)

SEARCH_RESULTS_PER_QUERY = int(
    os.getenv("SEARCH_RESULTS_PER_QUERY", "50")
)

MAX_CHANNELS_PER_RUN = int(
    os.getenv("MAX_CHANNELS_PER_RUN", "200")
)


# ============================================================
# CSV COLUMNS
# ============================================================

CSV_COLUMNS = [
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
# YOUTUBE SEARCH QUERIES
# ============================================================

YOUTUBE_QUERIES = [
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
# GENERAL HELPERS
# ============================================================

def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def clean(value) -> str:
    if value is None:
        return ""

    return str(value).strip()


def normalize_url(url: str) -> str:
    url = clean(url)

    if not url:
        return ""

    return url.rstrip("/")


def channel_url(channel_id: str) -> str:
    return f"https://www.youtube.com/channel/{channel_id}"


def ensure_data_dir():
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


def create_empty_csv_if_needed():
    ensure_data_dir()

    if not LEADS_FILE.exists():
        with LEADS_FILE.open(
            "w",
            newline="",
            encoding="utf-8"
        ) as f:

            writer = csv.DictWriter(
                f,
                fieldnames=CSV_COLUMNS
            )

            writer.writeheader()


# ============================================================
# CSV FUNCTIONS
# ============================================================

def read_csv_file(path: Path) -> List[Dict]:
    if not path.exists():
        return []

    rows = []

    try:
        with path.open(
            "r",
            newline="",
            encoding="utf-8-sig"
        ) as f:

            reader = csv.DictReader(f)

            for row in reader:
                cleaned = {
                    column: clean(
                        row.get(column, "")
                    )
                    for column in CSV_COLUMNS
                }

                rows.append(cleaned)

    except Exception as e:
        print(
            f"CSV read error ({path}): {e}"
        )

    return rows


def append_rows_to_csv(rows: List[Dict]):
    if not rows:
        return

    ensure_data_dir()

    file_exists = LEADS_FILE.exists()
    file_empty = (
        not file_exists
        or LEADS_FILE.stat().st_size == 0
    )

    with LEADS_FILE.open(
        "a",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=CSV_COLUMNS
        )

        if file_empty:
            writer.writeheader()

        for row in rows:
            writer.writerow({
                column: clean(
                    row.get(column, "")
                )
                for column in CSV_COLUMNS
            })


# ============================================================
# DUPLICATE SYSTEM
# ============================================================

def build_duplicate_keys(
    rows: List[Dict]
) -> Set[str]:

    keys = set()

    for row in rows:

        channel = normalize_url(
            row.get("channel_url", "")
        )

        profile = normalize_url(
            row.get("profile_url", "")
        )

        name = clean(
            row.get("name", "")
        ).lower()

        platform = clean(
            row.get("platform", "")
        ).lower()

        if channel:
            keys.add(
                f"channel:{channel.lower()}"
            )

        if profile:
            keys.add(
                f"profile:{profile.lower()}"
            )

        if name and platform:
            keys.add(
                f"name:{platform}:{name}"
            )

    return keys


def is_duplicate(
    row: Dict,
    existing_keys: Set[str]
) -> bool:

    channel = normalize_url(
        row.get("channel_url", "")
    )

    profile = normalize_url(
        row.get("profile_url", "")
    )

    name = clean(
        row.get("name", "")
    ).lower()

    platform = clean(
        row.get("platform", "")
    ).lower()

    possible_keys = []

    if channel:
        possible_keys.append(
            f"channel:{channel.lower()}"
        )

    if profile:
        possible_keys.append(
            f"profile:{profile.lower()}"
        )

    if name and platform:
        possible_keys.append(
            f"name:{platform}:{name}"
        )

    return any(
        key in existing_keys
        for key in possible_keys
    )


def add_row_keys(
    row: Dict,
    existing_keys: Set[str]
):

    channel = normalize_url(
        row.get("channel_url", "")
    )

    profile = normalize_url(
        row.get("profile_url", "")
    )

    name = clean(
        row.get("name", "")
    ).lower()

    platform = clean(
        row.get("platform", "")
    ).lower()

    if channel:
        existing_keys.add(
            f"channel:{channel.lower()}"
        )

    if profile:
        existing_keys.add(
            f"profile:{profile.lower()}"
        )

    if name and platform:
        existing_keys.add(
            f"name:{platform}:{name}"
        )


# ============================================================
# NICHE DETECTION
# ============================================================

def detect_niche(
    title: str,
    description: str
) -> str:

    text = (
        f"{clean(title)} "
        f"{clean(description)}"
    ).lower()

    categories = []

    if any(
        word in text
        for word in [
            "gaming",
            "gamer",
            "gaming pc",
            "game",
        ]
    ):
        categories.append("gaming")

    if any(
        word in text
        for word in [
            "mobile",
            "smartphone",
            "android",
            "iphone",
        ]
    ):
        categories.append(
            "mobile/smartphone"
        )

    if any(
        word in text
        for word in [
            "laptop",
            "computer",
            "pc",
            "cpu",
            "gpu",
            "graphics card",
        ]
    ):
        categories.append(
            "computers/laptops"
        )

    if any(
        word in text
        for word in [
            "camera",
            "photography",
            "videography",
        ]
    ):
        categories.append(
            "photography/videography"
        )

    if any(
        word in text
        for word in [
            "video editing",
            "premiere pro",
            "capcut",
            "editing",
        ]
    ):
        categories.append(
            "video editing"
        )

    if any(
        word in text
        for word in [
            "vfx",
            "3d",
            "visual effects",
        ]
    ):
        categories.append(
            "VFX/3D"
        )

    if not categories:
        categories.append("technology")

    unique = list(
        dict.fromkeys(categories)
    )

    return ", ".join(
        unique[:4]
    )


# ============================================================
# YOUTUBE API
# ============================================================

YOUTUBE_BASE_URL = (
    "https://www.googleapis.com/youtube/v3"
)


def youtube_get(
    endpoint: str,
    params: Dict,
    retries: int = 3
) -> Optional[Dict]:

    if not YOUTUBE_API_KEY:
        print(
            "ERROR: YOUTUBE_API_KEY is missing."
        )
        return None

    url = (
        f"{YOUTUBE_BASE_URL}/{endpoint}"
    )

    params = dict(params)
    params["key"] = YOUTUBE_API_KEY

    for attempt in range(
        1,
        retries + 1
    ):

        try:

            response = requests.get(
                url,
                params=params,
                timeout=30
            )

            if response.status_code == 200:
                return response.json()

            print(
                "YouTube API error "
                f"{response.status_code}: "
                f"{response.text[:500]}"
            )

            if response.status_code in {
                429,
                500,
                502,
                503,
                504,
            }:

                if attempt < retries:
                    time.sleep(
                        attempt * 2
                    )

                    continue

            return None

        except requests.RequestException as e:

            print(
                "YouTube request error "
                f"(attempt {attempt}): {e}"
            )

            if attempt < retries:
                time.sleep(
                    attempt * 2
                )

    return None


# ============================================================
# SEARCH CHANNELS
# ============================================================

def search_youtube_channels(
    query: str
) -> List[str]:

    print(
        f"YouTube search: {query}"
    )

    data = youtube_get(
        "search",
        {
            "part": "snippet",
            "q": query,
            "type": "channel",
            "regionCode": "IN",
            "maxResults": min(
                SEARCH_RESULTS_PER_QUERY,
                50
            ),
        }
    )

    if not data:
        return []

    channel_ids = []

    for item in data.get(
        "items",
        []
    ):

        channel_id = (
            item.get(
                "snippet",
                {}
            ).get(
                "channelId",
                ""
            )
        )

        if channel_id:
            channel_ids.append(
                channel_id
            )

    return channel_ids


# ============================================================
# CHANNEL DETAILS
# ============================================================

def get_channel_details(
    channel_ids: List[str]
) -> List[Dict]:

    if not channel_ids:
        return []

    results = []

    # YouTube allows max 50 IDs/request
    for start in range(
        0,
        len(channel_ids),
        50
    ):

        batch = channel_ids[
            start:start + 50
        ]

        data = youtube_get(
            "channels",
            {
                "part": (
                    "snippet,"
                    "statistics,"
                    "contentDetails"
                ),
                "id": ",".join(batch),
            }
        )

        if not data:
            continue

        results.extend(
            data.get(
                "items",
                []
            )
        )

    return results


# ============================================================
# RECENT VIDEO DATA
# ============================================================

def get_recent_video_stats(
    uploads_playlist_id: str,
    limit: int = 10
):

    if not uploads_playlist_id:
        return "", 0

    playlist_data = youtube_get(
        "playlistItems",
        {
            "part": "snippet",
            "playlistId": uploads_playlist_id,
            "maxResults": min(limit, 50),
        }
    )

    if not playlist_data:
        return "", 0

    video_ids = []

    latest_upload = ""

    for item in playlist_data.get(
        "items",
        []
    ):

        snippet = item.get(
            "snippet",
            {}
        )

        video_id = (
            snippet.get(
                "resourceId",
                {}
            ).get(
                "videoId",
                ""
            )
        )

        published_at = clean(
            snippet.get(
                "publishedAt",
                ""
            )
        )

        if video_id:
            video_ids.append(
                video_id
            )

        if (
            published_at
            and not latest_upload
        ):
            latest_upload = published_at

    if not video_ids:
        return latest_upload, 0

    video_data = youtube_get(
        "videos",
        {
            "part": "statistics",
            "id": ",".join(video_ids),
        }
    )

    if not video_data:
        return latest_upload, 0

    views = []

    for video in video_data.get(
        "items",
        []
    ):

        stats = video.get(
            "statistics",
            {}
        )

        view_count = safe_int(
            stats.get(
                "viewCount",
                0
            )
        )

        if view_count > 0:
            views.append(
                view_count
            )

    if not views:
        return latest_upload, 0

    average_views = int(
        sum(views) / len(views)
    )

    return (
        latest_upload,
        average_views
    )


# ============================================================
# BUILD YOUTUBE LEAD
# ============================================================

def build_youtube_lead(
    channel: Dict
) -> Optional[Dict]:

    snippet = channel.get(
        "snippet",
        {}
    )

    statistics = channel.get(
        "statistics",
        {}
    )

    content_details = channel.get(
        "contentDetails",
        {}
    )

    channel_id = clean(
        channel.get(
            "id",
            ""
        )
    )

    title = clean(
        snippet.get(
            "title",
            ""
        )
    )

    description = clean(
        snippet.get(
            "description",
            ""
        )
    )

    country = clean(
        snippet.get(
            "country",
            ""
        )
    ).upper()

    subscribers = safe_int(
        statistics.get(
            "subscriberCount",
            0
        )
    )

    # --------------------------------------------------------
    # INDIA FILTER
    # --------------------------------------------------------

    if country != "IN":
        return None

    # --------------------------------------------------------
    # SUBSCRIBER FILTER
    # 10K - 50K
    # --------------------------------------------------------

    if subscribers < MIN_SUBSCRIBERS:
        return None

    if subscribers > MAX_SUBSCRIBERS:
        return None

    if not channel_id:
        return None

    if not title:
        return None

    url = channel_url(
        channel_id
    )

    niche = detect_niche(
        title,
        description
    )

    uploads_playlist_id = (
        content_details
        .get(
            "relatedPlaylists",
            {}
        )
        .get(
            "uploads",
            ""
        )
    )

    recent_upload, avg_views = (
        get_recent_video_stats(
            uploads_playlist_id,
            limit=10
        )
    )

    return {
        "name": title,
        "platform": "YouTube",
        "profile_url": url,
        "channel_url": url,
        "creator_or_business": "creator",
        "niche": niche,
        "country": "India",
        "city": "",
        "subscribers": subscribers,
        "avg_views": avg_views,
        "business_email": "",
        "instagram": "",
        "linkedin": "",
        "twitter_x": "",
        "website": "",
        "recent_upload": recent_upload,
        "contact_type": "public",
        "lead_source": "youtube_api",
        "status": "new",
        "notes": (
            "Discovered through official "
            "YouTube Data API"
        ),
    }


# ============================================================
# YOUTUBE DISCOVERY
# ============================================================

def discover_youtube_leads(
    existing_keys: Set[str]
) -> List[Dict]:

    if not YOUTUBE_API_KEY:
        print(
            "ERROR: YOUTUBE_API_KEY is missing."
        )
        return []

    discovered_ids = set()

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    for query in YOUTUBE_QUERIES:

        if (
            len(discovered_ids)
            >= MAX_CHANNELS_PER_RUN
        ):
            break

        ids = search_youtube_channels(
            query
        )

        for channel_id in ids:

            if (
                len(discovered_ids)
                >= MAX_CHANNELS_PER_RUN
            ):
                break

            discovered_ids.add(
                channel_id
            )

    print(
        "Unique YouTube channels "
        f"discovered: {len(discovered_ids)}"
    )

    if not discovered_ids:
        return []

    # --------------------------------------------------------
    # CHANNEL DETAILS
    # --------------------------------------------------------

    channels = get_channel_details(
        list(discovered_ids)
    )

    leads = []

    for channel in channels:

        try:

            lead = build_youtube_lead(
                channel
            )

        except Exception as e:

            print(
                "Error building YouTube "
                f"lead: {e}"
            )

            continue

        if not lead:
            continue

        if is_duplicate(
            lead,
            existing_keys
        ):
            continue

        add_row_keys(
            lead,
            existing_keys
        )

        leads.append(
            lead
        )

    print(
        "New YouTube leads after "
        "India + subscriber filtering "
        f"and duplicate check: {len(leads)}"
    )

    return leads


# ============================================================
# GOOGLE SHEETS
# ============================================================

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def connect_google_sheet():

    if not GOOGLE_SERVICE_ACCOUNT_JSON:

        print(
            "Google service account "
            "secret is missing."
        )

        return None

    try:

        service_account_info = json.loads(
            GOOGLE_SERVICE_ACCOUNT_JSON
        )

        credentials = (
            Credentials
            .from_service_account_info(
                service_account_info,
                scopes=GOOGLE_SCOPES
            )
        )

        client = gspread.authorize(
            credentials
        )

        # ----------------------------------------------------
        # USE SHEET ID FIRST
        # ----------------------------------------------------

        if GOOGLE_SHEET_ID:

            print(
                "Opening Google Sheet by ID."
            )

            spreadsheet = (
                client.open_by_key(
                    GOOGLE_SHEET_ID
                )
            )

        else:

            print(
                "GOOGLE_SHEET_ID is missing."
            )

            print(
                "Trying Google Sheet by name: "
                f"{GOOGLE_SHEET_NAME}"
            )

            spreadsheet = (
                client.open(
                    GOOGLE_SHEET_NAME
                )
            )

        # ----------------------------------------------------
        # GET / CREATE LEADS WORKSHEET
        # ----------------------------------------------------

        try:

            worksheet = (
                spreadsheet.worksheet(
                    "Leads"
                )
            )

        except gspread.WorksheetNotFound:

            print(
                "Leads worksheet not found."
            )

            print(
                "Creating Leads worksheet..."
            )

            worksheet = (
                spreadsheet.add_worksheet(
                    title="Leads",
                    rows=1000,
                    cols=len(CSV_COLUMNS)
                )
            )

            worksheet.append_row(
                CSV_COLUMNS,
                value_input_option="USER_ENTERED"
            )

        # ----------------------------------------------------
        # CHECK EMPTY SHEET
        # ----------------------------------------------------

        values = (
            worksheet.get_all_values()
        )

        if not values:

            worksheet.append_row(
                CSV_COLUMNS,
                value_input_option="USER_ENTERED"
            )

        print(
            "Google Sheets connection successful."
        )

        return worksheet

    except Exception as e:

        print(
            "Google Sheets connection failed:"
        )

        print(
            f"{type(e).__name__}: {e}"
        )

        return None


def get_google_sheet_existing_rows(
    worksheet
) -> List[Dict]:

    if worksheet is None:
        return []

    try:

        values = (
            worksheet.get_all_records()
        )

        return values

    except Exception as e:

        print(
            "Could not read Google Sheet:"
        )

        print(
            f"{type(e).__name__}: {e}"
        )

        return []


def append_to_google_sheet(
    worksheet,
    rows: List[Dict]
) -> int:

    if worksheet is None:
        return 0

    if not rows:
        return 0

    added = 0

    for row in rows:

        try:

            values = [
                row.get(
                    column,
                    ""
                )
                for column in CSV_COLUMNS
            ]

            worksheet.append_row(
                values,
                value_input_option="USER_ENTERED"
            )

            added += 1

        except Exception as e:

            print(
                "Google Sheets row error:"
            )

            print(
                f"{type(e).__name__}: {e}"
            )

    return added


# ============================================================
# IMPORT PUBLIC LEADS
# ============================================================

def import_public_leads(
    existing_keys: Set[str]
) -> List[Dict]:

    if not PUBLIC_LEADS_FILE.exists():

        print(
            "public_leads.csv not found."
        )

        return []

    print(
        "Reading input file: "
        f"{PUBLIC_LEADS_FILE}"
    )

    rows = read_csv_file(
        PUBLIC_LEADS_FILE
    )

    print(
        f"Public leads found: {len(rows)}"
    )

    new_rows = []

    for row in rows:

        if is_duplicate(
            row,
            existing_keys
        ):
            continue

        add_row_keys(
            row,
            existing_keys
        )

        new_rows.append(
            row
        )

    print(
        "New public leads: "
        f"{len(new_rows)}"
    )

    return new_rows


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 50)
    print("Lead Collector started.")
    print("=" * 50)
    print()

    ensure_data_dir()
    create_empty_csv_if_needed()

    # --------------------------------------------------------
    # EXISTING CSV
    # --------------------------------------------------------

    existing_csv_rows = read_csv_file(
        LEADS_FILE
    )

    print(
        "Existing CSV leads: "
        f"{len(existing_csv_rows)}"
    )

    existing_keys = build_duplicate_keys(
        existing_csv_rows
    )

    # --------------------------------------------------------
    # GOOGLE SHEETS
    # --------------------------------------------------------

    worksheet = connect_google_sheet()

    sheet_rows = (
        get_google_sheet_existing_rows(
            worksheet
        )
    )

    if sheet_rows:

        print(
            "Existing Google Sheet leads: "
            f"{len(sheet_rows)}"
        )

        sheet_keys = build_duplicate_keys(
            sheet_rows
        )

        existing_keys.update(
            sheet_keys
        )

    else:

        print(
            "Existing Google Sheet leads: 0"
        )

    # --------------------------------------------------------
    # PUBLIC CSV LEADS
    # --------------------------------------------------------

    public_leads = import_public_leads(
        existing_keys
    )

    # --------------------------------------------------------
    # YOUTUBE LEADS
    # --------------------------------------------------------

    youtube_leads = (
        discover_youtube_leads(
            existing_keys
        )
    )

    # --------------------------------------------------------
    # COMBINE
    # --------------------------------------------------------

    new_leads = (
        public_leads
        + youtube_leads
    )

    print()
    print(
        f"Total new leads: {len(new_leads)}"
    )

    # --------------------------------------------------------
    # SAVE CSV
    # --------------------------------------------------------

    if new_leads:

        append_rows_to_csv(
            new_leads
        )

        print(
            "CSV updated successfully."
        )

    else:

        print(
            "No new leads to add to CSV."
        )

    # --------------------------------------------------------
    # SAVE GOOGLE SHEETS
    # --------------------------------------------------------

    sheets_added = (
        append_to_google_sheet(
            worksheet,
            new_leads
        )
    )

    print(
        "New leads added to Google Sheets: "
        f"{sheets_added}"
    )

    # --------------------------------------------------------
    # FINAL STATS
    # --------------------------------------------------------

    final_csv_rows = read_csv_file(
        LEADS_FILE
    )

    print()
    print("=" * 50)
    print("FINAL RESULT")
    print("=" * 50)
    print(
        f"CSV total leads: "
        f"{len(final_csv_rows)}"
    )
    print(
        f"New leads this run: "
        f"{len(new_leads)}"
    )
    print(
        f"Google Sheets added: "
        f"{sheets_added}"
    )
    print("=" * 50)
    print()
    print(
        "Lead Collector completed successfully."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
