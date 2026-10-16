
import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    gspread = None
    Credentials = None


# =====================================================
# CONFIGURATION
# =====================================================

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CSV_FILE = DATA_DIR / "leads.csv"

TIMEOUT = 30
ACTIVE_DAYS = int(os.getenv("ACTIVE_DAYS", "180"))
MAX_YOUTUBE_CHANNELS = 50

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
YOUTUBE_QUERY = os.getenv(
    "YOUTUBE_SEARCH_QUERY",
    "creator|vlogger|podcast|business|gaming|tech|travel|education|fitness|comedy"
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
    "platform_id",
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

NICHE_KEYWORDS = {
    "Gaming": ["gaming", "gamer", "gameplay", "esports"],
    "Technology": ["tech", "technology", "software", "ai tools"],
    "Gadgets": ["gadgets", "smartphone", "laptop review"],
    "Education": ["education", "tutorial", "learning", "teaching"],
    "Lifestyle": ["lifestyle", "daily life", "routine"],
    "Entertainment": ["entertainment", "reaction", "movie review"],
    "Fitness": ["fitness", "workout", "gym"],
    "Fashion": ["fashion", "style", "beauty", "outfit"],
    "Travel": ["travel", "tourism", "travel vlog"],
    "Finance": ["finance", "investing", "business"],
    "Automotive": ["automotive", "car review", "cars", "bikes"],
    "Comedy": ["comedy", "funny", "skit"],
    "Vlogging": ["vlog", "vlogging", "daily vlog"],
    "Video Editing": [
        "video editing", "video editor", "premiere pro",
        "after effects", "davinci resolve"
    ],
    "Podcast": ["podcast", "interview", "talk show"],
    "Food": ["food", "cooking", "recipe", "restaurant"],
    "Beauty": ["beauty", "makeup", "skincare"],
    "Business": ["business", "entrepreneur", "marketing", "startup"],
}


# =====================================================
# GENERAL HELPERS
# =====================================================

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

    for niche, keywords in NICHE_KEYWORDS.items():
        if any(word in text for word in keywords):
            return niche

    return "Other/Unclassified"


def extract_public_email(text):
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


def extract_public_website(text):
    if not text:
        return ""

    matches = re.findall(
        r"https?://[^\s<>\"']+",
        text
    )

    for url in matches:
        url = url.rstrip(".,);]")
        host = urlparse(url).netloc.lower()

        if host and not any(
            domain in host
            for domain in (
                "youtube.com", "youtu.be", "twitter.com",
                "x.com", "instagram.com", "facebook.com"
            )
        ):
            return url

    return ""


def read_csv():
    if not CSV_FILE.exists():
        return []

    try:
        with CSV_FILE.open(
            "r", newline="", encoding="utf-8-sig"
        ) as file:
            return list(csv.DictReader(file))
    except (OSError, csv.Error) as exc:
        log(f"CSV read error: {exc}")
        return []


def save_csv(new_leads):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    unique = {}

    for lead in read_csv() + new_leads:
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

    log(f"CSV total unique profiles: {len(unique)}")
    return list(unique.values())


def make_lead(
    name,
    platform,
    platform_id,
    profile_url,
    description="",
    audience="",
    country="Unknown",
    recent_upload="",
    source="",
):
    email = extract_public_email(description)
    website = extract_public_website(description)

    return {
        "name": name or "",
        "platform": platform,
        "platform_id": str(platform_id or ""),
        "profile_url": profile_url or "",
        "channel_url": profile_url or "",
        "creator_or_business": "Potential Client",
        "niche": classify_niche(f"{name} {description}"),
        "country": country or "Unknown",
        "city": "",
        "subscribers": audience,
        "avg_views": "",
        "business_email": email,
        "instagram": "",
        "linkedin": "",
        "twitter_x": profile_url if platform == "X" else "",
        "website": website,
        "recent_upload": recent_upload,
        "contact_type": (
            "Public business email"
            if email else "Public profile / direct message"
        ),
        "lead_source": source,
        "status": "New",
        "notes": (
            "Potential outreach lead. Audience size is not restricted. "
            "Monetization and willingness to hire are not verified."
        ),
    }


# =====================================================
# YOUTUBE
# =====================================================

def youtube_get(endpoint, params):
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}"

    response = requests.get(
        url,
        params={"key": YOUTUBE_API_KEY, **params},
        timeout=TIMEOUT,
    )

    if response.status_code == 403:
        log(
            "YouTube API access/quota error: "
            + response.text[:400]
        )
        return None

    response.raise_for_status()
    return response.json()


def collect_youtube():
    leads = []

    if not YOUTUBE_API_KEY:
        log("YouTube skipped: API key missing.")
        return leads

    try:
        # Keep one search request per run to reduce quota usage.
        search = youtube_get(
            "search",
            {
                "part": "snippet",
                "type": "channel",
                "q": YOUTUBE_QUERY,
                "maxResults": MAX_YOUTUBE_CHANNELS,
                "order": "relevance",
            },
        )

        if not search:
            return leads

        channel_ids = list(dict.fromkeys(
            item.get("id", {}).get("channelId", "")
            for item in search.get("items", [])
            if item.get("id", {}).get("channelId")
        ))

        if not channel_ids:
            log("YouTube search returned no channels.")
            return leads

        details = youtube_get(
            "channels",
            {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(channel_ids),
                "maxResults": 50,
            },
        )

        if not details:
            return leads

        cutoff = datetime.now(timezone.utc) - timedelta(
            days=max(1, ACTIVE_DAYS)
        )

        for channel in details.get("items", []):
            snippet = channel.get("snippet", {})
            stats = channel.get("statistics", {})
            content = channel.get("contentDetails", {})

            channel_id = channel.get("id", "")
            title = snippet.get("title", "")
            description = snippet.get("description", "")

            # No subscriber limit: include any visible audience size.
            audience = stats.get("subscriberCount", "")

            # Get the channel's uploads playlist and inspect its latest video.
            uploads_playlist = (
                content.get("relatedPlaylists", {}).get("uploads", "")
            )

            if not uploads_playlist:
                continue

            try:
                playlist = youtube_get(
                    "playlistItems",
                    {
                        "part": "snippet,contentDetails",
                        "playlistId": uploads_playlist,
                        "maxResults": 1,
                    },
                )
            except requests.RequestException as exc:
                log(f"Latest upload check failed for {title}: {exc}")
                continue

            if not playlist:
                continue

            items = playlist.get("items", [])
            if not items:
                continue

            video = items[0]
            video_snippet = video.get("snippet", {})

            published_at = (
                video.get("contentDetails", {}).get("videoPublishedAt")
                or video_snippet.get("publishedAt", "")
            )

            try:
                published = datetime.fromisoformat(
                    published_at.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                continue

            # Active means a recent public upload within ACTIVE_DAYS.
            if published < cutoff:
                continue

            country_code = snippet.get("country", "")
            country = {
                "IN": "India",
                "US": "United States",
                "GB": "United Kingdom",
                "CA": "Canada",
                "AU": "Australia",
            }.get(country_code, country_code or "Unknown")

            channel_url = f"https://www.youtube.com/channel/{channel_id}"

            leads.append(
                make_lead(
                    name=title,
                    platform="YouTube",
                    platform_id=channel_id,
                    profile_url=channel_url,
                    description=description,
                    audience=audience,
                    country=country,
                    recent_upload=published_at,
                    source="YouTube Data API",
                )
            )

        log(f"YouTube channels searched: {len(channel_ids)}")
        log(f"Active YouTube leads found: {len(leads)}")

    except requests.RequestException as exc:
        log(f"YouTube API request failed: {exc}")

    return leads


# =====================================================
# X / TWITTER
# =====================================================

def collect_x():
    leads = []

    if not X_BEARER_TOKEN:
        log("X skipped: X_BEARER_TOKEN secret is missing.")
        return leads

    endpoint = "https://api.x.com/2/tweets/search/recent"

    # Search for likely creators and potential editing clients.
    # Follower count is deliberately NOT used as a filter.
    query = (
        '("video editor" OR "looking for an editor" OR '
        '"need an editor" OR "hire an editor" OR '
        '"content creator" OR YouTuber OR podcast OR '
        '"thumbnail designer") -is:retweet'
    )

    params = {
        "query": query,
        "max_results": 100,
        "expansions": "author_id",
        "user.fields": (
            "id,name,username,description,public_metrics,"
            "location,url,verified"
        ),
    }

    try:
        response = requests.get(
            endpoint,
            headers={
                "Authorization": f"Bearer {X_BEARER_TOKEN}"
            },
            params=params,
            timeout=TIMEOUT,
        )

        if response.status_code in (401, 403):
            log(
                f"X API access/authentication error: "
                f"HTTP {response.status_code}"
            )
            log(response.text[:400])
            return leads

        response.raise_for_status()
        payload = response.json()

    except requests.RequestException as exc:
        log(f"X API request failed: {exc}")
        return leads

    users = payload.get("includes", {}).get("users", [])
    seen = set()

    for user in users:
        user_id = user.get("id", "")
        username = user.get("username", "").strip()

        if not user_id or not username or user_id in seen:
            continue

        seen.add(user_id)

        # No follower limit.
        followers = user.get("public_metrics", {}).get(
            "followers_count", ""
        )

        profile_url = f"https://x.com/{username}"
        description = user.get("description", "")

        leads.append(
            make_lead(
                name=user.get("name", username),
                platform="X",
                platform_id=user_id,
                profile_url=profile_url,
                description=description,
                audience=followers,
                country=user.get("location", "") or "Unknown",
                source="X API recent search",
            )
        )

    log(f"X public profiles discovered: {len(users)}")
    log(f"X potential leads saved: {len(leads)}")
    return leads


# =====================================================
# GOOGLE SHEETS
# =====================================================

HEADER_ALIASES = {
    "name": ["name", "creator_name", "channel_name"],
    "platform_id": ["platform_id", "user_id", "channel_id", "id"],
    "profile_url": [
        "profile_url", "profile link", "profile url",
        "channel_url", "channel link", "channel url",
        "url", "profile"
    ],
    "channel_url": [
        "channel_url", "channel link", "channel url",
        "profile_url", "profile link", "profile url", "url"
    ],
    "subscribers": [
        "subscribers", "subscriber_count", "followers",
        "followers_count", "audience"
    ],
    "business_email": [
        "business_email", "contact_email", "email", "business email"
    ],
    "twitter_x": ["twitter_x", "twitter", "x", "x_url"],
    "recent_upload": ["recent_upload", "last_upload", "latest_video"],
}


def map_sheet_value(header, lead):
    normalized = (header or "").strip().lower()

    for field in FIELDS:
        if normalized == field.lower():
            return lead.get(field, "")

    for field, aliases in HEADER_ALIASES.items():
        if normalized in aliases:
            return lead.get(field, "")

    return ""


def upload_to_google_sheets(new_leads):
    if not GOOGLE_SERVICE_ACCOUNT_JSON or not GOOGLE_SHEET_ID:
        log("Google Sheets error: required secrets are missing.")
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

        # Find profile URL columns in the existing worksheet.
        url_aliases = set(HEADER_ALIASES["profile_url"])
        url_indices = [
            index for index, header in enumerate(headers)
            if (header or "").strip().lower() in url_aliases
        ]

        # If the existing sheet has no URL column, add one without
        # deleting or rewriting any existing data.
        if not url_indices:
            headers.append("profile_url")
            worksheet.update(
                range_name="A1",
                values=[headers],
            )
            url_indices = [len(headers) - 1]

            # Existing rows receive an empty new URL cell.
            values = worksheet.get_all_values()
            headers = values[0]

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
            log("No new rows to append; matching profiles were skipped.")
            log(f"Sheet data rows now: {max(0, len(values) - 1)}")
            return True

        rows = [
            [str(map_sheet_value(header, lead)) for header in headers]
            for lead in pending
        ]

        worksheet.append_rows(
            rows,
            value_input_option="USER_ENTERED",
            insert_data_option="INSERT_ROWS",
        )

        # Read back to verify profile URLs were saved.
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

        log(f"New leads uploaded: {len(pending)}")
        log(f"Uploaded rows verified: {verified}/{len(pending)}")
        log(f"Sheet data rows now: {max(0, len(updated_values) - 1)}")

        if verified != len(pending):
            log("ERROR: Google Sheets verification incomplete.")
            return False

        log("GOOGLE SHEETS UPLOAD VERIFIED.")
        return True

    except Exception as exc:
        log(f"GOOGLE SHEETS ERROR: {type(exc).__name__}: {exc}")
        return False


# =====================================================
# MAIN
# =====================================================

def main():
    log("=" * 60)
    log("LEAD AUTOMATION STARTED")
    log("Audience limit: NONE")
    log(f"YouTube active window: {ACTIVE_DAYS} days")
    log("=" * 60)

    collected = []

    log("\n=== YOUTUBE COLLECTION ===")
    collected.extend(collect_youtube())

    log("\n=== X / TWITTER COLLECTION ===")
    collected.extend(collect_x())

    # These platforms are not falsely marked as collected.
    for platform, env_name in [
        ("Instagram", "INSTAGRAM_ACCESS_TOKEN"),
        ("Facebook", "FACEBOOK_ACCESS_TOKEN"),
        ("LinkedIn", "LINKEDIN_ACCESS_TOKEN"),
    ]:
        if os.getenv(env_name, "").strip():
            log(
                f"{platform}: token detected, but a separate "
                "platform-specific collector is still required."
            )
        else:
            log(f"{platform}: skipped; {env_name} is missing.")

    # Keep historical CSV leads, but upload only leads from this run.
    all_csv_leads = save_csv(collected)

    log("\n=== GOOGLE SHEETS UPLOAD ===")
    sheets_ok = upload_to_google_sheets(collected)

    log("\n" + "=" * 60)
    log(f"New leads collected this run: {len(collected)}")
    log(f"Total unique CSV profiles: {len(all_csv_leads)}")
    log(f"Google Sheets success: {sheets_ok}")
    log("LEAD AUTOMATION FINISHED")
    log("=" * 60)

    if not sheets_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
