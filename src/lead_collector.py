
import csv
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    gspread = None
    Credentials = None


# ==================================================
# CONFIGURATION
# ==================================================

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CSV_FILE = DATA_DIR / "leads.csv"

MIN_AUDIENCE = 10_000
MAX_AUDIENCE = 50_000
REQUEST_TIMEOUT = 30

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
YOUTUBE_SEARCH_QUERY = os.getenv(
    "YOUTUBE_SEARCH_QUERY",
    "India gaming tech vlogging creator"
).strip()

X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "").strip()

GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON", ""
).strip()
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
GOOGLE_SHEET_WORKSHEET = os.getenv(
    "GOOGLE_SHEET_WORKSHEET", "Sheet1"
).strip()

FIELDS = [
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

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

NICHES = {
    "Gaming": ["gaming", "gamer", "gameplay", "esports"],
    "Tech": ["technology", "tech", "software", "artificial intelligence"],
    "Gadgets": ["gadgets", "smartphone", "smartphones", "gadget review"],
    "PC/Computer": ["pc build", "computer", "laptop", "hardware"],
    "Mobile": ["mobile review", "android", "iphone", "mobile tips"],
    "Lifestyle": ["lifestyle", "daily life", "routine"],
    "Education": ["education", "tutorial", "learning", "explained"],
    "Entertainment": ["entertainment", "reaction", "movie review"],
    "Fitness": ["fitness", "workout", "gym"],
    "Fashion": ["fashion", "style", "outfit", "beauty"],
    "Travel": ["travel", "travel vlog", "tourism"],
    "Finance": ["finance", "investing", "personal finance"],
    "Automotive": ["automotive", "car review", "cars", "bikes"],
    "Comedy": ["comedy", "funny", "stand up", "skit"],
    "Vlogging": ["vlog", "vlogging", "daily vlog"],
    "Video Editing": [
        "video editing", "video editor", "premiere pro",
        "after effects", "davinci resolve"
    ],
}


# ==================================================
# HELPERS
# ==================================================

def log(message):
    print(message, flush=True)


def normalize_url(value):
    value = (value or "").strip()
    if not value:
        return ""

    if not value.startswith(("https://", "http://")):
        value = "https://" + value

    try:
        parsed = urlparse(value)
        host = (parsed.netloc or "").lower()
        path = (parsed.path or "").rstrip("/")
        return f"{host}{path}".lower()
    except Exception:
        return value.lower().rstrip("/")


def classify_niche(text):
    text = (text or "").lower()

    for niche, keywords in NICHES.items():
        if any(keyword in text for keyword in keywords):
            return niche

    return "Other/Unclassified"


def extract_public_email(text):
    if not text:
        return ""

    matches = re.findall(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        text,
    )

    for email in matches:
        if not email.lower().endswith(
            (".png", ".jpg", ".jpeg", ".webp")
        ):
            return email

    return ""


def in_target_range(audience):
    try:
        count = int(audience)
        return MIN_AUDIENCE <= count <= MAX_AUDIENCE
    except (TypeError, ValueError):
        return False


def read_csv_leads():
    if not CSV_FILE.exists():
        return []

    try:
        with CSV_FILE.open(
            "r", newline="", encoding="utf-8-sig"
        ) as file:
            return list(csv.DictReader(file))
    except (OSError, csv.Error) as exc:
        log(f"CSV read warning: {exc}")
        return []


def save_csv(new_leads):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    combined = read_csv_leads() + new_leads
    unique = {}

    for lead in combined:
        url = lead.get("profile_url") or lead.get("channel_url")
        key = normalize_url(url)

        if not key:
            continue

        row = {field: lead.get(field, "") for field in FIELDS}
        unique[key] = row

    with CSV_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(unique.values())

    log(f"CSV total unique leads: {len(unique)}")
    return list(unique.values())


# ==================================================
# YOUTUBE COLLECTION
# ==================================================

def collect_youtube():
    leads = []

    if not YOUTUBE_API_KEY:
        log("YouTube skipped: YOUTUBE_API_KEY is missing.")
        return leads

    base_url = "https://www.googleapis.com/youtube/v3"
    session = requests.Session()

    # One search.list call per run to conserve quota.
    try:
        response = session.get(
            f"{base_url}/search",
            params={
                "key": YOUTUBE_API_KEY,
                "part": "snippet",
                "type": "channel",
                "q": YOUTUBE_SEARCH_QUERY,
                "maxResults": 50,
                "order": "relevance",
            },
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code == 403:
            log("YouTube HTTP 403: check quota and API key permissions.")
            log(response.text[:400])
            return leads

        response.raise_for_status()
        items = response.json().get("items", [])

    except requests.RequestException as exc:
        log(f"YouTube search error: {exc}")
        return leads

    channel_ids = list(dict.fromkeys(
        item.get("id", {}).get("channelId", "")
        for item in items
        if item.get("id", {}).get("channelId")
    ))

    if not channel_ids:
        log("YouTube returned no channels.")
        return leads

    try:
        response = session.get(
            f"{base_url}/channels",
            params={
                "key": YOUTUBE_API_KEY,
                "part": "snippet,statistics",
                "id": ",".join(channel_ids),
                "maxResults": 50,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        channels = response.json().get("items", [])

    except requests.RequestException as exc:
        log(f"YouTube channel details error: {exc}")
        return leads

    country_codes = {
        "IN": "India",
        "US": "United States",
        "GB": "United Kingdom",
        "CA": "Canada",
        "AU": "Australia",
    }

    for channel in channels:
        snippet = channel.get("snippet", {})
        stats = channel.get("statistics", {})

        if stats.get("hiddenSubscriberCount"):
            continue

        try:
            subscribers = int(stats.get("subscriberCount", 0))
        except (TypeError, ValueError):
            continue

        if not in_target_range(subscribers):
            continue

        name = snippet.get("title", "").strip()
        description = snippet.get("description", "")
        text = f"{name} {description}"

        channel_id = channel.get("id", "")
        channel_url = f"https://www.youtube.com/channel/{channel_id}"
        email = extract_public_email(description)
        country_code = snippet.get("country", "")

        leads.append({
            "name": name,
            "platform": "YouTube",
            "profile_url": channel_url,
            "channel_url": channel_url,
            "creator_or_business": "Creator",
            "niche": classify_niche(text),
            "country": country_codes.get(
                country_code, country_code or "Unknown"
            ),
            "city": "",
            "subscribers": subscribers,
            "avg_views": "",
            "business_email": email,
            "instagram": "",
            "linkedin": "",
            "twitter_x": "",
            "website": "",
            "recent_upload": "",
            "contact_type": (
                "Public business email" if email else "Public profile"
            ),
            "lead_source": "YouTube Data API",
            "status": "New",
            "notes": (
                "Subscriber count is within 10K–50K. "
                "Unknown country means channel country was not provided."
            ),
        })

    log(f"YouTube channels examined: {len(channels)}")
    log(f"YouTube leads within 10K–50K: {len(leads)}")
    return leads


# ==================================================
# X / TWITTER COLLECTION
# ==================================================

def collect_x():
    leads = []

    if not X_BEARER_TOKEN:
        log("X skipped: X_BEARER_TOKEN is not configured.")
        return leads

    endpoint = "https://api.x.com/2/tweets/search/recent"

    params = {
        "query": (
            '("video editor" OR "looking for an editor" OR '
            '"content creator") -is:retweet lang:en'
        ),
        "max_results": 100,
        "expansions": "author_id",
        "user.fields": "description,public_metrics,location",
    }

    try:
        response = requests.get(
            endpoint,
            headers={"Authorization": f"Bearer {X_BEARER_TOKEN}"},
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code in (401, 403):
            log(
                f"X authentication/API access error: "
                f"HTTP {response.status_code}"
            )
            log(response.text[:400])
            return leads

        response.raise_for_status()
        payload = response.json()

    except requests.RequestException as exc:
        log(f"X collection error: {exc}")
        return leads

    users = payload.get("includes", {}).get("users", [])
    seen = set()

    for user in users:
        username = user.get("username", "").strip()
        if not username or username.lower() in seen:
            continue

        seen.add(username.lower())

        metrics = user.get("public_metrics", {})
        followers = metrics.get("followers_count", 0)

        if not in_target_range(followers):
            continue

        description = user.get("description", "")
        profile_url = f"https://x.com/{username}"
        email = extract_public_email(description)

        leads.append({
            "name": user.get("name", username),
            "platform": "X",
            "profile_url": profile_url,
            "channel_url": profile_url,
            "creator_or_business": "Creator/Business",
            "niche": classify_niche(description),
            "country": user.get("location", "") or "Unknown",
            "city": "",
            "subscribers": followers,
            "avg_views": "",
            "business_email": email,
            "instagram": "",
            "linkedin": "",
            "twitter_x": profile_url,
            "website": "",
            "recent_upload": "",
            "contact_type": (
                "Public business email" if email else "Public profile"
            ),
            "lead_source": "X API",
            "status": "New",
            "notes": (
                "Filtered by public follower count of 10K–50K. "
                "Profile location is user-entered and may be imprecise."
            ),
        })

    log(f"X leads within 10K–50K followers: {len(leads)}")
    return leads


# ==================================================
# GOOGLE SHEETS
# ==================================================

def header_value(header, lead):
    key = (header or "").strip().lower()

    aliases = {
        "profile_url": [
            "profile_url", "channel_url", "url", "profile"
        ],
        "channel_url": [
            "channel_url", "profile_url", "url", "profile"
        ],
        "subscribers": [
            "subscribers", "subscriber_count", "followers"
        ],
        "business_email": [
            "business_email", "contact_email", "email"
        ],
        "twitter_x": [
            "twitter_x", "twitter", "x", "x_url"
        ],
        "name": ["name", "creator_name", "channel_name"],
    }

    if key in lead:
        return lead.get(key, "")

    for canonical, names in aliases.items():
        if key in names:
            return lead.get(canonical, "")

    return ""


def upload_to_google_sheets(new_leads):
    if not GOOGLE_SERVICE_ACCOUNT_JSON or not GOOGLE_SHEET_ID:
        log("Google Sheets error: required secret is missing.")
        return False

    if gspread is None or Credentials is None:
        log("Google Sheets error: install gspread and google-auth.")
        return False

    try:
        service_account = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)

        credentials = Credentials.from_service_account_info(
            service_account,
            scopes=SCOPES,
        )

        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

        try:
            worksheet = spreadsheet.worksheet(
                GOOGLE_SHEET_WORKSHEET or "Sheet1"
            )
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.sheet1

        values = worksheet.get_all_values()

        if not values or not any(values[0]):
            worksheet.update(range_name="A1", values=[FIELDS])
            values = [FIELDS]

        headers = values[0]

        url_indices = [
            i for i, header in enumerate(headers)
            if (header or "").strip().lower() in (
                "profile_url", "channel_url", "url", "profile"
            )
        ]

        existing_urls = set()

        for row in values[1:]:
            for index in url_indices:
                if index < len(row):
                    key = normalize_url(row[index])
                    if key:
                        existing_urls.add(key)

        pending = []
        run_seen = set()

        for lead in new_leads:
            url = lead.get("profile_url") or lead.get("channel_url")
            key = normalize_url(url)

            if not key or key in existing_urls or key in run_seen:
                continue

            run_seen.add(key)
            pending.append(lead)

        log(f"New rows ready for Google Sheets: {len(pending)}")

        if not pending:
            log("No new leads to append; duplicates were skipped.")
            log(f"Sheet data rows now: {max(0, len(values) - 1)}")
            return True

        rows = [
            [str(header_value(header, lead)) for header in headers]
            for lead in pending
        ]

        worksheet.append_rows(
            rows,
            value_input_option="USER_ENTERED",
            insert_data_option="INSERT_ROWS",
        )

        # Read back the worksheet and verify inserted profile URLs.
        updated_values = worksheet.get_all_values()
        verified_urls = set()

        for row in updated_values[1:]:
            for index in url_indices:
                if index < len(row):
                    key = normalize_url(row[index])
                    if key:
                        verified_urls.add(key)

        verified = sum(
            1
            for lead in pending
            if normalize_url(
                lead.get("profile_url") or lead.get("channel_url")
            ) in verified_urls
        )

        log(f"New leads uploaded: {len(rows)}")
        log(f"Uploaded rows verified: {verified}/{len(pending)}")
        log(f"Sheet data rows now: {max(0, len(updated_values) - 1)}")

        if verified != len(pending):
            log("ERROR: Google Sheets verification failed.")
            return False

        log("GOOGLE SHEETS UPLOAD VERIFIED.")
        return True

    except Exception as exc:
        log(f"GOOGLE SHEETS ERROR: {type(exc).__name__}: {exc}")
        return False


# ==================================================
# MAIN
# ==================================================

def main():
    log("=" * 55)
    log("LEAD AUTOMATION STARTED")
    log(f"Target audience: {MIN_AUDIENCE:,}–{MAX_AUDIENCE:,}")
    log("=" * 55)

    collected = []

    log("\n=== YOUTUBE ===")
    collected.extend(collect_youtube())

    log("\n=== X / TWITTER ===")
    collected.extend(collect_x())

    # These platforms are reported honestly until their collectors
    # are implemented. A token alone does not perform collection.
    for platform, env_name in [
        ("Instagram", "INSTAGRAM_ACCESS_TOKEN"),
        ("Facebook", "FACEBOOK_ACCESS_TOKEN"),
        ("LinkedIn", "LINKEDIN_ACCESS_TOKEN"),
    ]:
        if not os.getenv(env_name, "").strip():
            log(f"{platform} skipped: {env_name} is missing.")
        else:
            log(
                f"{platform}: token detected, but this code does not "
                "yet implement its collection endpoint."
            )

    # Save all existing CSV data plus this run's newly collected leads.
    all_csv_leads = save_csv(collected)

    log("\n=== GOOGLE SHEETS ===")

    # IMPORTANT: upload only this run's leads, not every historical CSV row.
    sheets_ok = upload_to_google_sheets(collected)

    log("\n" + "=" * 55)
    log(f"Leads collected this run: {len(collected)}")
    log(f"CSV total unique leads: {len(all_csv_leads)}")
    log(f"Google Sheets success: {sheets_ok}")
    log("LEAD AUTOMATION FINISHED")
    log("=" * 55)

    if not sheets_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
