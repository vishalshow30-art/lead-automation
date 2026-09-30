from pathlib import Path
import csv
import os
import re
import time
from typing import Dict, List

try:
    from googleapiclient.discovery import build
except ImportError:
    build = None


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
# CSV STRUCTURE
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
# TARGET NICHES
# ============================================================

NICHES = [
    "Gaming",
    "Tech",
    "Gadgets",
    "PC Computer",
    "Mobile",
    "Lifestyle",
    "Education",
    "Entertainment",
    "Fitness",
    "Fashion",
    "Travel",
    "Finance",
    "Automotive",
    "Comedy",
    "Vlogging",
]


# ============================================================
# YOUTUBE SEARCH TERMS
# ============================================================

SEARCH_TERMS = [
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
    "Indian video creator",
    "Indian content creator",
    "Indian influencer",
]


# ============================================================
# FILE HELPERS
# ============================================================

def ensure_leads_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

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

        print(f"Created: {DATA_FILE}")


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
                leads.append({
                    header: (row.get(header) or "").strip()
                    for header in CSV_HEADERS
                })

    except Exception as exc:
        print(f"Could not read existing leads: {exc}")

    return leads


def save_leads(leads: List[Dict[str, str]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

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
            writer.writerow({
                header: lead.get(header, "")
                for header in CSV_HEADERS
            })


# ============================================================
# TEXT / URL CLEANING
# ============================================================

def clean_text(value: str) -> str:
    if not value:
        return ""

    value = value.replace("\n", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_url(url: str) -> str:
    return url.strip().lower().rstrip("/")


# ============================================================
# DUPLICATE PROTECTION
# ============================================================

def lead_exists(
    existing_leads: List[Dict[str, str]],
    channel_url: str,
    name: str,
) -> bool:

    normalized_url = normalize_url(channel_url)
    normalized_name = name.strip().lower()

    for lead in existing_leads:
        old_url = normalize_url(
            lead.get("channel_url", "")
        )

        old_name = (
            lead.get("name", "")
            .strip()
            .lower()
        )

        if normalized_url and old_url == normalized_url:
            return True

        if normalized_name and old_name == normalized_name:
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

    niche_keywords = {
        "Gaming": [
            "gaming",
            "gamer",
            "gameplay",
            "esports",
        ],
        "Tech": [
            "technology",
            "tech",
            "smartphone",
            "computer",
        ],
        "Gadgets": [
            "gadgets",
            "gadget",
            "devices",
            "accessories",
        ],
        "PC Computer": [
            "pc",
            "computer",
            "laptop",
            "desktop",
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
            "life style",
        ],
        "Education": [
            "education",
            "educational",
            "study",
            "learning",
        ],
        "Entertainment": [
            "entertainment",
            "celebrity",
            "movies",
            "music",
        ],
        "Fitness": [
            "fitness",
            "workout",
            "gym",
            "health",
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
            "vlog",
        ],
        "Finance": [
            "finance",
            "investment",
            "investing",
            "stock market",
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
            "daily vlog",
        ],
    }

    for niche, keywords in niche_keywords.items():
        for keyword in keywords:
            if keyword in text:
                return niche

    return ""


# ============================================================
# COUNTRY DETECTION
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
        "ghaziabad",
        "uttar pradesh",
    ]

    if any(
        term in text
        for term in india_terms
    ):
        return "India"

    return ""


# ============================================================
# YOUTUBE API
# ============================================================

def get_youtube_service():
    api_key = os.getenv(
        "YOUTUBE_API_KEY"
    )

    if not api_key:
        print(
            "YOUTUBE_API_KEY not found. "
            "Skipping YouTube collection."
        )
        return None

    if build is None:
        print(
            "google-api-python-client is not installed. "
            "Skipping YouTube collection."
        )
        return None

    try:
        return build(
            "youtube",
            "v3",
            developerKey=api_key,
        )

    except Exception as exc:
        print(
            f"Could not create YouTube client: {exc}"
        )
        return None


# ============================================================
# YOUTUBE SEARCH
# ============================================================

def search_youtube_channels(
    youtube,
    search_term: str,
    max_results: int = 25,
) -> List[Dict[str, str]]:

    results = []

    try:
        response = youtube.search().list(
            part="snippet",
            q=search_term,
            type="channel",
            maxResults=max_results,
        ).execute()

    except Exception as exc:
        print(
            f"YouTube search failed for "
            f"'{search_term}': {exc}"
        )
        return results

    for item in response.get(
        "items",
        [],
    ):

        channel_id = (
            item.get("id", {})
            .get("channelId", "")
        )

        snippet = item.get(
            "snippet",
            {},
        )

        title = clean_text(
            snippet.get("title", "")
        )

        description = clean_text(
            snippet.get("description", "")
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


# ============================================================
# YOUTUBE CHANNEL DETAILS
# ============================================================

def get_youtube_channel_details(
    youtube,
    channel_ids: List[str],
) -> List[Dict[str, str]]:

    if not channel_ids:
        return []

    details = []

    for start in range(
        0,
        len(channel_ids),
        50,
    ):

        batch = channel_ids[
            start:start + 50
        ]

        try:
            response = youtube.channels().list(
                part="snippet,statistics",
                id=",".join(batch),
            ).execute()

        except Exception as exc:
            print(
                f"YouTube channel details failed: {exc}"
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

            title = clean_text(
                snippet.get("title", "")
            )

            description = clean_text(
                snippet.get("description", "")
            )

            channel_id = item.get(
                "id",
                "",
            )

            subscribers = statistics.get(
                "subscriberCount",
                "",
            )

            hidden_subscribers = statistics.get(
                "hiddenSubscriberCount",
                False,
            )

            if hidden_subscribers:
                subscribers = ""

            details.append({
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
                "country": (
                    clean_text(
                        snippet.get(
                            "country",
                            "",
                        )
                    )
                    or detect_country(
                        title,
                        description,
                    )
                ),
                "contact_email": "",
                "business_email": "",
                "website": "",
                "instagram_url": "",
                "notes": (
                    "Public YouTube channel "
                    "information. Business contact "
                    "details are not inferred."
                ),
            })

    return details


# ============================================================
# CREATOR FILTER
# ============================================================

def subscriber_in_target_range(
    subscriber_count: str,
) -> bool:

    if not subscriber_count:
        return False

    try:
        count = int(
            subscriber_count
        )

    except ValueError:
        return False

    return 10_000 <= count <= 50_000


def is_relevant_lead(
    lead: Dict[str, str],
) -> bool:

    platform = lead.get(
        "platform",
        "",
    )

    if platform == "YouTube":
        return subscriber_in_target_range(
            lead.get(
                "subscriber_count",
                "",
            )
        )

    return True


# ============================================================
# PUBLIC BUSINESS CONTACT VALIDATION
# ============================================================

def looks_like_public_business_email(
    email: str,
) -> bool:

    if not email:
        return False

    email = email.strip()

    pattern = (
        r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )

    return bool(
        re.match(
            pattern,
            email,
        )
    )


def add_public_contact(
    lead: Dict[str, str],
    email: str = "",
    website: str = "",
) -> Dict[str, str]:

    """
    Store only contact information that has been
    supplied by an authorized/public source.
    """

    if email and looks_like_public_business_email(email):
        lead["business_email"] = email.strip()

    if website:
        lead["website"] = website.strip()

    return lead


# ============================================================
# INSTAGRAM
# ============================================================

def collect_instagram_leads():
    """
    No unauthorized Instagram scraping.

    Future implementation can use an authorized
    Meta/Instagram API or another permitted data source.
    """

    print(
        "Instagram: authorized API not configured. "
        "Skipping."
    )

    return []


# ============================================================
# FACEBOOK
# ============================================================

def collect_facebook_leads():
    """
    No unauthorized Facebook scraping.

    Future implementation can use an authorized
    Meta API.
    """

    print(
        "Facebook: authorized API not configured. "
        "Skipping."
    )

    return []


# ============================================================
# X / TWITTER
# ============================================================

def collect_x_leads():
    """
    No unauthorized X/Twitter scraping.

    Future implementation can use an authorized API.
    """

    print(
        "X/Twitter: authorized API not configured. "
        "Skipping."
    )

    return []


# ============================================================
# LINKEDIN
# ============================================================

def collect_linkedin_leads():
    """
    No unauthorized LinkedIn scraping.

    Future implementation can use an authorized API
    or approved data source.
    """

    print(
        "LinkedIn: authorized API not configured. "
        "Skipping."
    )

    return []


# ============================================================
# WEBSITES / PUBLIC WEB
# ============================================================

def collect_website_leads():
    """
    Website discovery requires an authorized search/API
    source. No unauthorized scraping is performed here.
    """

    print(
        "Websites: authorized search source "
        "not configured. Skipping."
    )

    return []


# ============================================================
# YOUTUBE COLLECTION
# ============================================================

def collect_youtube_leads(
    existing_leads: List[Dict[str, str]],
) -> List[Dict[str, str]]:

    youtube = get_youtube_service()

    if youtube is None:
        return []

    discovered = []

    print(
        "Starting YouTube discovery..."
    )

    for search_term in SEARCH_TERMS:

        print(
            f"Searching YouTube: {search_term}"
        )

        channels = search_youtube_channels(
            youtube,
            search_term,
            max_results=25,
        )

        channel_ids = [
            channel["channel_id"]
            for channel in channels
            if channel.get("channel_id")
        ]

        channel_details = (
            get_youtube_channel_details(
                youtube,
                channel_ids,
            )
        )

        for lead in channel_details:

            if not is_relevant_lead(
                lead
            ):
                continue

            if lead_exists(
                existing_leads,
                lead["channel_url"],
                lead["name"],
            ):
                continue

            duplicate_in_new = any(
                normalize_url(
                    existing.get(
                        "channel_url",
                        "",
                    )
                )
                == normalize_url(
                    lead["channel_url"]
                )
                for existing in discovered
            )

            if duplicate_in_new:
                continue

            discovered.append(
                lead
            )

        time.sleep(1)

    print(
        f"New YouTube leads found: "
        f"{len(discovered)}"
    )

    return discovered


# ============================================================
# ALL PLATFORMS
# ============================================================

def collect_all_leads(
    existing_leads: List[Dict[str, str]],
) -> List[Dict[str, str]]:

    all_new_leads = []

    # YouTube
    all_new_leads.extend(
        collect_youtube_leads(
            existing_leads
        )
    )

    # Instagram
    all_new_leads.extend(
        collect_instagram_leads()
    )

    # Facebook
    all_new_leads.extend(
        collect_facebook_leads()
    )

    # X/Twitter
    all_new_leads.extend(
        collect_x_leads()
    )

    # LinkedIn
    all_new_leads.extend(
        collect_linkedin_leads()
    )

    # Websites
    all_new_leads.extend(
        collect_website_leads()
    )

    return all_new_leads


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

def main() -> None:

    print("=" * 60)
    print("LEAD AUTOMATION STARTED")
    print("=" * 60)

    print(
        f"Project root: {PROJECT_ROOT}"
    )

    print(
        f"Lead file: {DATA_FILE}"
    )

    ensure_leads_file()

    existing_leads = (
        load_existing_leads()
    )

    print(
        f"Existing leads: "
        f"{len(existing_leads)}"
    )

    new_leads = collect_all_leads(
        existing_leads
    )

    if new_leads:

        existing_leads.extend(
            new_leads
        )

        save_leads(
            existing_leads
        )

        print(
            f"Added {len(new_leads)} "
            f"new leads."
        )

    else:

        print(
            "No new leads collected
