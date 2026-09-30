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
# PROJECT
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
# CSV
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
    "Indian content creator",
    "Indian video creator",
    "Indian YouTuber",
    "Indian influencer",
]


# ============================================================
# FILE FUNCTIONS
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
        print(f"Could not read leads.csv: {exc}")

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
# CLEANING
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
# DUPLICATE CHECK
# ============================================================

def lead_exists(
    existing_leads: List[Dict[str, str]],
    channel_url: str,
    name: str,
) -> bool:

    new_url = normalize_url(channel_url)
    new_name = name.strip().lower()

    for lead in existing_leads:

        old_url = normalize_url(
            lead.get("channel_url", "")
        )

        old_name = (
            lead.get("name", "")
            .strip()
            .lower()
        )

        if new_url and new_url == old_url:
            return True

        if new_name and new_name == old_name:
            return True

    return False


# ============================================================
# NICHE
# ============================================================

def detect_niche(
    title: str,
    description: str,
) -> str:

    text = f"{title} {description}".lower()

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

    text = f"{title} {description}".lower()

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
# YOUTUBE API
# ============================================================

def get_youtube_service():

    api_key = os.getenv("YOUTUBE_API_KEY")

    if not api_key:
        print("YOUTUBE_API_KEY is missing.")
        return None

    if build is None:
        print(
            "google-api-python-client is not installed."
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
            f"YouTube client error: {exc}"
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
            f"YouTube search failed: {search_term}"
        )
        print(exc)
        return results

    for item in response.get("items", []):

        channel_id = (
            item.get("id", {})
            .get("channelId", "")
        )

        snippet = item.get("snippet", {})

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
# YOUTUBE DETAILS
# ============================================================

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

        batch = channel_ids[start:start + 50]

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
                f"YouTube details error: {exc}"
            )
            continue

        for item in response.get("items", []):

            snippet = item.get("snippet", {})
            statistics = item.get(
                "statistics",
                {},
            )

            channel_id = item.get(
                "id",
                "",
            )

            title = clean_text(
                snippet.get("title", "")
            )

            description = clean_text(
                snippet.get("description", "")
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
                snippet.get("country", "")
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
                    "Collected from public "
                    "YouTube channel information."
                ),
            })

    return results


# ============================================================
# TARGET FILTER
# ============================================================

def subscriber_in_target_range(
    subscriber_count: str,
) -> bool:

    if not subscriber_count:
        return False

    try:
        count = int(subscriber_count)
    except ValueError:
        return False

    return 10000 <= count <= 50000


def is_relevant_lead(
    lead: Dict[str, str],
) -> bool:

    if lead.get("platform") == "YouTube":
        return subscriber_in_target_range(
            lead.get(
                "subscriber_count",
                "",
            )
        )

    return True


# ============================================================
# YOUTUBE COLLECTOR
# ============================================================

def collect_youtube_leads(
    existing_leads: List[Dict[str, str]],
) -> List[Dict[str, str]]:

    youtube = get_youtube_service()

    if youtube is None:
        return []

    new_leads = []

    print("Starting YouTube discovery...")

    for search_term in SEARCH_TERMS:

        print(
            f"Searching: {search_term}"
        )

        channels = search_youtube_channels(
            youtube,
            search_term,
            25,
        )

        channel_ids = [
            channel["channel_id"]
            for channel in channels
        ]

        details = get_youtube_channel_details(
            youtube,
            channel_ids,
        )

        for lead in details:

            if not is_relevant_lead(lead):
                continue

            if lead_exists(
                existing_leads,
                lead["channel_url"],
                lead["name"],
            ):
                continue

            if lead_exists(
                new_leads,
                lead["channel_url"],
                lead["name"],
            ):
                continue

            new_leads.append(lead)

        time.sleep(1)

    print(
        f"New YouTube leads found: "
        f"{len(new_leads)}"
    )

    return new_leads


# ============================================================
# OTHER PLATFORMS
# ============================================================

def collect_instagram_leads():
    print(
        "Instagram: authorized API not configured."
    )
    return []


def collect_facebook_leads():
    print(
        "Facebook: authorized API not configured."
    )
    return []


def collect_x_leads():
    print(
        "X/Twitter: authorized API not configured."
    )
    return []


def collect_linkedin_leads():
    print(
        "LinkedIn: authorized API not configured."
    )
    return []


def collect_website_leads():
    print(
        "Websites: authorized search source "
        "not configured."
    )
    return []


# ============================================================
# ALL SOURCES
# ============================================================

def collect_all_leads(
    existing_leads: List[Dict[str, str]],
) -> List[Dict[str, str]]:

    all_leads = []

    all_leads.extend(
        collect_youtube_leads(
            existing_leads
        )
    )

    all_leads.extend(
        collect_instagram_leads()
    )

    all_leads.extend(
        collect_facebook_leads()
    )

    all_leads.extend(
        collect_x_leads()
    )

    all_leads.extend(
        collect_linkedin_leads()
    )

    all_leads.extend(
        collect_website_leads()
    )

    return all_leads


# ============================================================
# MAIN
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

    existing_leads = load_existing_leads()

    print(
        f"Existing leads: "
        f"{len(existing_leads)}"
    )

    new_leads = collect_all_leads(
        existing_leads
    )

    if new_leads:

        existing_leads.extend(new_leads)

        save_leads(existing_leads)

        print(
            f"Added {len(new_leads)} "
            f"new leads."
        )

    else:

        print(
            "No new leads collected "
            "in this cycle."
        )

    print(
        f"Total leads in CSV: "
        f"{len(existing_leads)}"
    )

    print("=" * 60)
    print("LEAD AUTOMATION COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()
