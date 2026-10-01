from pathlib import Path
import csv
import json
import os
import re
import time
from typing import Any, Dict, List

import requests


# ============================================================
# PROJECT
# ============================================================

def get_project_root() -> Path:
    current_file = Path(__file__).resolve()

    for parent in [current_file.parent, *current_file.parents]:
        if (parent / "requirements.txt").exists():
            return parent

    return current_file.parent.parent


PROJECT_ROOT = get_project_root()
DATA_FILE = PROJECT_ROOT / "data" / "leads.csv"


# ============================================================
# CSV COLUMNS
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
# SETTINGS
# ============================================================

MIN_SUBSCRIBERS = 10_000
MAX_SUBSCRIBERS = 50_000

REQUEST_TIMEOUT = 30
SLEEP_BETWEEN_REQUESTS = 0.2

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


# ============================================================
# SECRETS
# ============================================================

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()

GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON", ""
).strip()

GOOGLE_SHEET_ID = os.getenv(
    "GOOGLE_SHEET_ID", ""
).strip()

INSTAGRAM_ACCESS_TOKEN = os.getenv(
    "INSTAGRAM_ACCESS_TOKEN", ""
).strip()

FACEBOOK_ACCESS_TOKEN = os.getenv(
    "FACEBOOK_ACCESS_TOKEN", ""
).strip()

FACEBOOK_PAGE_ID = os.getenv(
    "FACEBOOK_PAGE_ID", ""
).strip()

X_BEARER_TOKEN = os.getenv(
    "X_BEARER_TOKEN", ""
).strip()


# ============================================================
# HELPERS
# ============================================================

def clean(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def normalize_url(value: Any) -> str:
    url = clean(value)

    if not url:
        return ""

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    return url.rstrip("/")


def safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def extract_email(text: Any) -> str:
    text = clean(text)

    if not text:
        return ""

    pattern = (
        r"[A-Za-z0-9._%+-]+"
        r"@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    )

    matches = re.findall(pattern, text)

    for email in matches:
        lower = email.lower()

        if any(
            blocked in lower
            for blocked in [
                "example.com",
                "example.org",
                "example.net",
                "test.com",
            ]
        ):
            continue

        return email

    return ""


def detect_niche(text: Any) -> str:
    text = clean(text).lower()

    niches = {
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
            "smartphones",
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
            "mobile",
            "phone",
            "android",
            "iphone",
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
            "clothing",
        ],
        "Travel": [
            "travel",
            "travelling",
            "tour",
            "trip",
        ],
        "Finance": [
            "finance",
            "stock market",
            "stocks",
            "investing",
            "investment",
            "trading",
            "money",
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

    for niche, keywords in niches.items():
        for keyword in keywords:
            if keyword in text:
                return niche

    return "Other"


def request_json(
    url: str,
    params: Dict[str, Any] = None,
    headers: Dict[str, str] = None,
) -> Dict[str, Any]:

    try:
        response = requests.get(
            url,
            params=params or {},
            headers=headers or {},
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        return response.json()

    except requests.RequestException as exc:
        print(f"Request failed: {exc}")
        return {}

    except ValueError as exc:
        print(f"Invalid JSON response: {exc}")
        return {}


# ============================================================
# CSV
# ============================================================

def create_csv_if_missing() -> None:
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


def normalize_lead(
    row: Dict[str, Any]
) -> Dict[str, str]:

    return {
        header: clean(row.get(header, ""))
        for header in CSV_HEADERS
    }


def read_csv() -> List[Dict[str, str]]:
    create_csv_if_missing()

    try:
        with DATA_FILE.open(
            "r",
            newline="",
            encoding="utf-8",
        ) as file:

            reader = csv.DictReader(file)

            return [
                normalize_lead(row)
                for row in reader
                if row
            ]

    except Exception as exc:
        print(f"CSV read error: {exc}")
        return []


def get_lead_key(
    lead: Dict[str, Any]
) -> str:

    lead = normalize_lead(lead)

    platform = lead["platform"].lower()

    profile_url = normalize_url(
        lead["profile_url"]
    ).lower()

    channel_url = normalize_url(
        lead["channel_url"]
    ).lower()

    if profile_url:
        return f"{platform}|{profile_url}"

    if channel_url:
        return f"{platform}|{channel_url}"

    name = lead["name"].lower()
    email = lead["business_email"].lower()

    return f"{platform}|{name}|{email}"


def save_csv(
    leads: List[Dict[str, Any]]
) -> None:

    create_csv_if_missing()

    existing = read_csv()

    combined = {}

    for lead in existing:
        normalized = normalize_lead(lead)
        key = get_lead_key(normalized)

        if key:
            combined[key] = normalized

    for lead in leads:
        normalized = normalize_lead(lead)
        key = get_lead_key(normalized)

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
        writer.writerows(combined.values())

    print(
        f"Saved {len(combined)} total leads "
        f"to {DATA_FILE}"
    )


def deduplicate_leads(
    leads: List[Dict[str, Any]]
) -> List[Dict[str, str]]:

    unique = {}

    for lead in leads:
        normalized = normalize_lead(lead)
        key = get_lead_key(normalized)

        if key and key not in unique:
            unique[key] = normalized

    return list(unique.values())


# ============================================================
# YOUTUBE SEARCHES
# ============================================================

YOUTUBE_SEARCH_QUERIES = [
    "Indian gaming creator",
    "Indian tech creator",
    "Indian gadget creator",
    "Indian PC creator",
    "Indian computer creator",
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
    "Indian vlogging creator",
    "India gaming YouTuber",
    "India tech YouTuber",
    "India gadgets YouTuber",
    "India PC YouTuber",
    "India mobile YouTuber",
    "India lifestyle YouTuber",
    "India education YouTuber",
    "India entertainment YouTuber",
    "India fitness YouTuber",
    "India fashion YouTuber",
    "India travel YouTuber",
    "India finance YouTuber",
    "India automotive YouTuber",
    "India comedy YouTuber",
    "India vlogging YouTuber",
]


# ============================================================
# YOUTUBE API
# ============================================================

def youtube_search(
    query: str,
    page_token: str = "",
) -> Dict[str, Any]:

    params = {
        "part": "snippet",
        "q": query,
        "type": "channel",
        "maxResults": 50,
        "key": YOUTUBE_API_KEY,
    }

    if page_token:
        params["pageToken"] = page_token

    return request_json(
        f"{YOUTUBE_API_BASE}/search",
        params=params,
    )


def youtube_get_channels(
    channel_ids: List[str]
) -> List[Dict[str, Any]]:

    all_channels = []

    for start in range(
        0,
        len(channel_ids),
        50,
    ):

        batch = channel_ids[
            start:start + 50
        ]

        params = {
            "part": (
                "snippet,"
                "statistics,"
                "contentDetails"
            ),
            "id": ",".join(batch),
            "key": YOUTUBE_API_KEY,
        }

        data = request_json(
            f"{YOUTUBE_API_BASE}/channels",
            params=params,
        )

        all_channels.extend(
            data.get("items", [])
        )

        time.sleep(
            SLEEP_BETWEEN_REQUESTS
        )

    return all_channels


def youtube_latest_upload(
    uploads_playlist_id: str
) -> str:

    if not uploads_playlist_id:
        return ""

    params = {
        "part": "snippet",
        "playlistId": uploads_playlist_id,
        "maxResults": 1,
        "key": YOUTUBE_API_KEY,
    }

    data = request_json(
        f"{YOUTUBE_API_BASE}/playlistItems",
        params=params,
    )

    items = data.get("items", [])

    if not items:
        return ""

    snippet = items[0].get(
        "snippet",
        {},
    )

    return clean(
        snippet.get("publishedAt", "")
    )


def collect_youtube_leads() -> List[Dict[str, Any]]:

    if not YOUTUBE_API_KEY:
        print(
            "YOUTUBE_API_KEY is missing. "
            "Skipping YouTube."
        )
        return []

    print(
        "Starting YouTube lead collection..."
    )

    channel_ids = set()

    for query in YOUTUBE_SEARCH_QUERIES:

        print(
            f"YouTube search: {query}"
        )

        page_token = ""

        for _ in range(2):

            data = youtube_search(
                query,
                page_token,
            )

            for item in data.get(
                "items",
                [],
            ):

                channel_id = clean(
                    item.get(
                        "snippet",
                        {},
                    ).get(
                        "channelId",
                        "",
                    )
                )

                if channel_id:
                    channel_ids.add(
                        channel_id
                    )

            page_token = clean(
                data.get(
                    "nextPageToken",
                    "",
                )
            )

            if not page_token:
                break

            time.sleep(
                SLEEP_BETWEEN_REQUESTS
            )

    print(
        f"Found {len(channel_ids)} "
        "unique YouTube channels."
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

        if not (
            MIN_SUBSCRIBERS
            <= subscribers
            <= MAX_SUBSCRIBERS
        ):
            continue

        channel_id = clean(
            channel.get("id", "")
        )

        if not channel_id:
            continue

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

        email = extract_email(
            description
        )

        country = clean(
            snippet.get(
                "country",
                "",
            )
        )

        niche = detect_niche(
            f"{name} {description}"
        )

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

        leads.append(
            {
                "name": name,
                "platform": "YouTube",
                "profile_url": profile_url,
                "channel_url": channel_url,
                "creator_or_business": "Creator",
                "niche": niche,
                "country": country or "India",
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
                    "Subscriber range: 10K-50K."
                ),
            }
        )

    print(
        f"YouTube leads after filtering: "
        f"{len(leads)}"
    )

    return leads


# ============================================================
# INSTAGRAM
# ============================================================

def collect_instagram_leads() -> List[Dict[str, Any]]:

    if not INSTAGRAM_ACCESS_TOKEN:
        print(
            "INSTAGRAM_ACCESS_TOKEN not configured. "
            "Skipping Instagram."
        )
        return []

    print(
        "Checking authorized Instagram account..."
    )

    params = {
        "fields": (
            "id,username,name,biography,"
            "website,followers_count"
        ),
        "access_token": (
            INSTAGRAM_ACCESS_TOKEN
        ),
    }

    data = request_json(
        "https://graph.instagram.com/me",
        params=params,
    )

    if not data:
        print(
            "Instagram account could not be read."
        )
        return []

    username = clean(
        data.get(
            "username",
            "",
        )
    )

    name = clean(
        data.get(
            "name",
            "",
        )
    )

    if not username:
        return []

    profile_url = (
        "https://www.instagram.com/"
        + username
        + "/"
    )

    followers = safe_int(
        data.get(
            "followers_count",
            0,
        )
    )

    biography = clean(
        data.get(
            "biography",
            "",
        )
    )

    return [
        {
            "name": name or username,
            "platform": "Instagram",
            "profile_url": profile_url,
            "channel_url": "",
            "creator_or_business": (
                "Creator/Business"
            ),
            "niche": detect_niche(
                biography
            ),
            "country": "",
            "city": "",
            "subscribers": str(
                followers
            ),
            "avg_views": "",
            "business_email": extract_email(
                biography
            ),
            "instagram": profile_url,
            "linkedin": "",
            "twitter_x": "",
            "website": normalize_url(
                data.get(
                    "website",
                    "",
                )
            ),
            "recent_upload": "",
            "contact_type": "Public Profile",
            "lead_source": (
                "Instagram Graph API"
            ),
            "status": "New",
            "notes": (
                "Authorized Instagram account "
                "data only."
            ),
        }
    ]


# ============================================================
# FACEBOOK
# ============================================================

def collect_facebook_leads() -> List[Dict[str, Any]]:

    if not FACEBOOK_ACCESS_TOKEN:
        print(
            "FACEBOOK_ACCESS_TOKEN not configured. "
            "Skipping Facebook."
        )
        return []

    if not FACEBOOK_PAGE_ID:
        print(
 
