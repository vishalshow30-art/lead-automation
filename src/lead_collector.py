
import csv
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

# Optional dependency: Google Sheets
try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    gspread = None
    Credentials = None


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

MIN_AUDIENCE = 10_000
MAX_AUDIENCE = 50_000
REQUEST_TIMEOUT = 30

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CSV_FILE = DATA_DIR / "leads.csv"

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "").strip()

GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON", ""
).strip()
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
GOOGLE_SHEET_WORKSHEET = os.getenv(
    "GOOGLE_SHEET_WORKSHEET", "Sheet1"
).strip()

YOUTUBE_SEARCH_QUERY = os.getenv(
    "YOUTUBE_SEARCH_QUERY",
    "India gaming tech vlogging creator"
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
    "Tech": ["technology", "tech", "software", "ai tools"],
    "Gadgets": ["gadgets", "smartphone", "smartphones", "gadgets review"],
    "PC/Computer": ["pc build", "computer", "laptop", "hardware"],
    "Mobile": ["mobile review", "android", "iphone", "mobile tips"],
    "Lifestyle": ["lifestyle", "daily life", "routine"],
    "Education": ["education", "tutorial", "learning", "explained"],
    "Entertainment": ["entertainment", "reaction", "movie review"],
    "Fitness": ["fitness", "workout", "gym", "health tips"],
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


# --------------------------------------------------
# GENERAL HELPERS
# --------------------------------------------------

def log(message):
    print(message, flush=True)


def normalize_url(value):
    """Normalize URLs for duplicate detection."""
    value = (value or "").strip()
    if not value:
        return ""

    if not value.startswith(("http://", "https://")):
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
    """Extract an email only when it appears in public profile text."""
    if not text:
        return ""

    matches = re.findall(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        text
    )

    for email in matches:
        if not email.lower().endswith(
            (".png", ".jpg", ".jpeg", ".webp")
        ):
            return email

    return ""


def read_csv_leads():
    if not CSV_FILE.exists():
        return []

    try:
        with CSV_FILE.open("r", newline="", encoding="utf-8-sig") as file:
            return list(csv.DictReader(file))
    except (OSError, csv.Error) as exc:
        log(f"CSV read warning: {exc}")
        return []


def save_csv(leads):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Merge with the existing CSV and deduplicate by profile URL.
    combined = read_csv_leads() + leads
    unique = {}
    for lead in combined:
        key = normalize_url(
            lead.get("profile_url") or lead.get("channel_url")
        )
        if key:
            unique[key] = {field: lead.get(field, "") for field in FIELDS}

    with CSV_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(unique.values())

    log(f"Saved {len(unique)} unique leads to {CSV_FILE}")
    return list(unique.values())


def in_target_range(audience):
    try:
        count = int(audience)
        return MIN_AUDIENCE <= count <= MAX_AUDIENCE
    except (TypeError, ValueError):
        return False


# --------------------------------------------------
# YOUTUBE
# --------------------------------------------------

def collect_youtube():
    leads = []

    if not YOUTUBE_API_KEY:
        log("YouTube skipped: YOUTUBE_API_KEY is missing.")
        return leads

    session = requests.Session()
    base_url = "https://www.googleapis.com/youtube/v3"

    # IMPORTANT:
    # search.list can consume 100 quota units per request.
    # This collector deliberately makes just ONE search request.
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
            log(
                "YouTube API returned 403. Check API quota, "
                "API key restrictions and YouTube Data API access."
            )
            log(response.text[:500])
            return leads

        response.raise_for_status()
        items = response.json().get("items", [])

    except requests.RequestException as exc:
        log(f"YouTube search failed: {exc}")
        return leads

    channel_ids = list(dict.fromkeys(
        item.get("id", {}).get("channelId", "")
        for item in items
        if item.get("id", {}).get("channelId")
    ))

    if not channel_ids:
        log("YouTube: no channels returned by the search.")
        return leads

    # channels.list costs far less quota than search.list.
    try:
        response = session.get(
            f"{base_url}/channels",
            params={
                "key": YOUTUBE_API_KEY,
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(channel_ids),
                "maxResults": 50,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        channels = response.json().get("items", [])

    except requests.RequestException as exc:
        log(f"YouTube channel details failed: {exc}")
        return leads

    for channel in channels:
        snippet = channel.get("snippet", {})
        stats = channel.get("statistics", {})
        channel_id = channel.get("id", "")

        if stats.get("hiddenSubscriberCount"):
            continue

        try:
            subscribers = int(stats.get("subscriberCount", 0))
        except (TypeError, ValueError):
            continue

        # Strictly enforce the requested 10K–50K range.
        if not in_target_range(subscribers):
            continue

        name = snippet.get("title", "").strip()
        description = snippet.get("description", "")
        combined_text = f"{name} {description}"

        country_code = snippet.get("country", "")
        country = {
            "IN": "India",
            "US": "United States",
            "GB": "United Kingdom",
            "CA": "Canada",
            "AU": "Australia",
        }.get(country_code, country_code or "Unknown")

        channel_url = f"https://www.youtube.com/channel/{channel_id}"

        leads.append({
            "name": name,
            "platform": "YouTube",
            "profile_url": channel_url,
            "channel_url": channel_url,
            "creator_or_business": "Creator",
            "niche": classify_niche(combined_text),
            "country": country,
            "city": "",
            "subscribers": subscribers,
            "avg_views": "",
            "business_email": extract_public_email(description),
            "instagram": "",
            "linkedin": "",
            "twitter_x": "",
            "website": "",
            "recent_upload": "",
            "contact_type": (
                "Public business email"
                if extract_public_email(description)
                else "Public profile"
            ),
            "lead_source": "YouTube Data API",
            "status": "New",
            "notes": (
                "Audience count is within 10K–50K. "
                "Country is based on channel metadata; "
                "Unknown means country was not provided."
            ),
        })

    log(f"YouTube channels examined: {len(channels)}")
    log(f"YouTube leads within 10K–50K: {len(leads)}")
    return leads


# --------------------------------------------------
# X / TWITTER
# --------------------------------------------------

def collect_x():
    leads = []

    if not X_BEARER_TOKEN:
        log(
            "X skipped: configure the X_BEARER_TOKEN GitHub secret "
            "and pass it through the workflow environment."
        )
        return leads

    url = "https://api.x.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}

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
            url,
            headers=headers,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code in (401, 403):
            log(
                f"X authentication/access error: HTTP "
                f"{response.status_code}. Check token and API access."
            )
            log(response.text[:500])
            return leads

        response.raise_for_status()
        data = response.json()

    except requests.RequestException as exc:
        log(f"X collection failed: {exc}")
        return leads

    users = data.get("includes", {}).get("users", [])
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
            "business_email": extract_public_email(description),
            "instagram": "",
            "linkedin": "",
            "twitter_x": profile_url,
            "website": "",
            "recent_upload": "",
            "contact_type": "Public profile",
            "lead_source": "X API",
            "status": "New",
            "notes": (
                "Filtered by public follower count of 10K–50K. "
                "Location is user-provided and may not be a country."
            ),
        })

    log(f"X leads within 10K–50K followers: {len(leads)}")
    return leads


# --------------------------------------------------
# GOOGLE SHEETS
# --------------------------------------------------

ALIASES = {
    "profile_url": ["profile_url", "channel_url", "url", "profile"],
    "channel_url": ["channel_url", "profile_url", "url", "profile"],
    "twitter_x": ["twitter_x", "twitter", "x", "x_url"],
    "business_email": ["business_email", "contact_email", "email"],
    "subscribers": ["subscribers", "subscriber_count", "followers"],
    "name": ["name", "creator_name", "channel_name"],
}


def get_value_for_sheet_header(header, lead):
    header_key = (header or "").strip().lower()
    if not header_key:
        return ""

    if header_key in lead:
        return lead.get(header_key, "")

    for canonical, alternatives in ALIASES.items():
        if header_key in alternatives:
            value = lead.get(canonical, "")
            if value:
                return value

    return ""


def upload_to_google_sheets(leads):
    if not GOOGLE_SERVICE_ACCOUNT_JSON or not GOOGLE_SHEET_ID:
        log(
            "Google Sheets skipped: GOOGLE_SERVICE_ACCOUNT_JSON "
            "or GOOGLE_SHEET_ID is missing."
        )
        return False

    if gspread is None or Credentials is None:
        log("Google Sheets dependencies are unavailable.")
        return False

    try:
        credentials_data = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        credentials = Credentials.from_service_account_info(
            credentials_data,
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

        existing_values = worksheet.get_all_values()

        if not existing_values or not any(existing_values[0]):
            worksheet.update(
                range_name="A1",
                values=[FIELDS],
            )
            headers = FIELDS[:]
            existing_values = [headers]
        else:
            headers = existing_values[0]

        # Identify already stored profiles using the existing sheet headers.
        url_column_indices = [
            index for index, header in enumerate(headers)
            if (header or "").strip().lower() in (
                "profile_url", "channel_url", "url", "profile"
            )
        ]

        existing_urls = set()
        for row in existing_values[1:]:
            for index in url_column_indices:
                if index < len(row):
                    key = normalize_url(row[index])
                    if key:
                        existing_urls.add(key)

        new_leads = []
        run_seen = set()

        for lead in leads:
            key = normalize_url(
                lead.get("profile_url") or lead.get("channel_url")
            )

            if not key or key in existing_urls or key in run_seen:
                continue

            run_seen.add(key)
            new_leads.append(lead)

        log(f"New rows ready for Google Sheets: {len(new_leads)}")

        if not new_leads:
            log(
                "No new rows to append. Existing sheet URLs matched "
                "the collected leads, or no valid profile URLs were found."
            )
            log(f"Sheet data rows now: {max(0, len(existing_values) - 1)}")
            return True

        rows = [
            [
                str(get_value_for_sheet_header(header, lead))
                for header in headers
            ]
            for lead in new_leads
        ]

        worksheet.append_rows(
            rows,
            value_input_option="USER_ENTERED",
            insert_data_option="INSERT_ROWS",
        )

        # Verify that the appended profiles can be read back.
        updated_values = worksheet.get_all_values()
        verified_urls = set()

        for row in updated_values[1:]:
            for index in url_column_indices:
                if index < len(row):
                    key = normalize_url(row[index])
                    if key:
                        verified_urls.add(key)

        verified_count = sum(
            1 for lead in new_leads
            if normalize_url(
                lead.get("profile_url") or lead.get("channel_url")
            ) in verified_urls
        )

        log(f"New leads uploaded: {len(rows)}")
        log(
            f"Uploaded rows verified: {verified_count}/{len(new_leads)}"
        )
        log(f"Sheet data rows now: {max(0, len(updated_values) - 1)}")

        if verified_count != len(new_leads):
            log("ERROR: Google Sheets verification was incomplete.")
            return False

        log("GOOGLE SHEETS UPLOAD VERIFIED.")
        return True

    except Exception as exc:
        log(f"GOOGLE SHEETS ERROR: {type(exc).__name__}: {exc}")
        return False


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():
    log("=" * 55)
    log("LEAD AUTOMATION STARTED")
    log(f"Target audience range: {MIN_AUDIENCE:,}–{MAX_AUDIENCE:,}")
    log("=" * 55)

    collected = []

    log("\n=== YOUTUBE COLLECTION ===")
    collected.extend(collect_youtube())

    log("\n=== X / TWITTER COLLECTION ===")
    collected.extend(collect_x())

    # These platforms require their own authorized API credentials
    # and platform-specific access. Do not pretend they were collected.
    for platform, secret in [
        ("Instagram", "INSTAGRAM_ACCESS_TOKEN"),
        ("Facebook", "FACEBOOK_ACCESS_TOKEN"),
        ("LinkedIn", "LINKEDIN_ACCESS_TOKEN"),
    ]:
        if not os.getenv(secret, "").strip():
            log(f"{platform} skipped: {secret} is not configured.")
        else:
            log(
                f"{platform} token detected, but this version does not "
                "implement that platform's collection endpoint."
            )

    # Preserve existing CSV rows and merge the current run.
    all_csv_leads = save_csv(collected)

    log("\n=== GOOGLE SHEETS ===")
    sheets_ok = upload_to_google_sheets(all_csv_leads)

    log("\n" + "=" * 55)
    log(f"Leads collected this run: {len(collected)}")
    log(f"CSV total leads: {len(all_csv_leads)}")
    log(f"Google Sheets success: {sheets_ok}")
    log("LEAD AUTOMATION FINISHED")
    log("=" * 55)

    if not sheets_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
