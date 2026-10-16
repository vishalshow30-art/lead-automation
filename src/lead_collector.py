
from pathlib import Path
import csv
import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import requests
from requests.auth import HTTPBasicAuth

# ============================================================
# CONFIG — PRESERVE EXISTING SETTINGS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DATA_FILE = DATA_DIR / "leads.csv"

MIN_SUBSCRIBERS = int(os.getenv("MIN_SUBSCRIBERS", "20000"))
MAX_LEADS_PER_RUN = int(os.getenv("MAX_LEADS_PER_RUN", "200"))
ACTIVE_DAYS = int(os.getenv("ACTIVE_DAYS", "60"))
REQUEST_TIMEOUT = 30

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()

X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "").strip()
X_API_KEY = os.getenv("X_API_KEY", "").strip()
X_API_SECRET = os.getenv("X_API_SECRET", "").strip()

GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON", ""
).strip()
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "").strip()

CSV_HEADERS = [
    "name", "platform", "profile_url", "channel_url",
    "creator_or_business", "niche", "country", "city",
    "subscribers", "avg_views", "business_email",
    "instagram", "linkedin", "twitter_x", "website",
    "recent_upload", "contact_type", "lead_source",
    "status", "notes",
]

YOUTUBE_SEARCH_QUERIES = [
    "YouTuber creator", "content creator channel",
    "video creator", "gaming channel", "gameplay creator",
    "comedy channel", "entertainment channel",
    "education channel", "technology channel",
    "tech review channel", "gadget review channel",
    "business channel", "finance channel", "lifestyle channel",
    "daily vlog channel", "travel channel",
    "food cooking channel", "fitness workout channel",
    "beauty makeup channel", "fashion channel",
    "automotive car channel", "photography filmmaking channel",
    "USA YouTuber creator", "UK YouTuber creator",
    "Canadian YouTuber creator", "Australian YouTuber creator",
    "Indian YouTuber creator",
]

X_SEARCH_QUERIES = [
    '"content creator" India',
    '"video editor" India',
    '"YouTuber" India',
    '"gaming creator" India',
    '"tech creator" India',
    '"video production" creator',
]

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
YOUTUBE_PLAYLIST_ITEMS_URL = (
    "https://www.googleapis.com/youtube/v3/playlistItems"
)

# ============================================================
# HELPERS
# ============================================================

def clean(value):
    return "" if value is None else str(value).strip()


def safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize_url(value):
    value = clean(value)
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    return "https://" + value


def extract_email(text):
    matches = re.findall(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        clean(text),
    )
    for email in matches:
        email = email.lower().strip()
        if not email.endswith((".png", ".jpg", ".jpeg", ".webp")):
            return email
    return ""


def extract_public_contacts(description):
    found = {
        "instagram": "",
        "linkedin": "",
        "twitter_x": "",
        "website": "",
    }

    candidates = re.findall(
        r"(?:https?://|www\.)[^\s<>\"']+|"
        r"(?:[A-Za-z0-9-]+\.)+"
        r"(?:com|net|org|co|io|me|tv|in|uk|us)"
        r"(?:/[^\s<>\"']*)?",
        clean(description),
        flags=re.IGNORECASE,
    )

    excluded_domains = (
        "youtube.com", "youtu.be", "instagram.com",
        "linkedin.com", "twitter.com", "facebook.com",
        "tiktok.com", "x.com", "google.com", "discord.gg",
        "twitch.tv",
    )

    for candidate in candidates:
        candidate = candidate.rstrip(".,;:!?)\\]")
        url = normalize_url(candidate)

        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            continue

        if not host:
            continue

        if "instagram.com" in host and not found["instagram"]:
            found["instagram"] = url
        elif "linkedin.com" in host and not found["linkedin"]:
            found["linkedin"] = url
        elif (
            ("twitter.com" in host or host == "x.com"
             or host.endswith(".x.com"))
            and not found["twitter_x"]
        ):
            found["twitter_x"] = url
        elif (
            not any(domain in host for domain in excluded_domains)
            and not found["website"]
        ):
            found["website"] = url

    return found


def is_recent_upload(value, days=ACTIVE_DAYS):
    if not value:
        return False

    try:
        parsed = datetime.fromisoformat(
            clean(value).replace("Z", "+00:00")
        )
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        age = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
        return timedelta(0) <= age <= timedelta(days=days)
    except (ValueError, TypeError):
        return False


def detect_niche(text):
    text = clean(text).lower()

    niche_map = {
        "Gaming": ["gaming", "gamer", "gameplay", "esports"],
        "Tech": ["tech", "technology", "gadget", "computer", "pc"],
        "Mobile": ["mobile", "smartphone", "iphone", "android"],
        "Lifestyle": ["lifestyle", "daily life"],
        "Education": ["education", "study", "learning", "student"],
        "Entertainment": ["entertainment", "movie", "movies", "celebrity"],
        "Fitness": ["fitness", "workout", "gym"],
        "Fashion": ["fashion", "style", "beauty"],
        "Travel": ["travel", "travelling", "tour"],
        "Finance": ["finance", "stock", "investing", "trading"],
        "Automotive": ["car", "cars", "automotive", "bike", "bikes"],
        "Comedy": ["comedy", "funny"],
        "Vlogging": ["vlog", "vlogging", "vlogger"],
        "Video Editing": [
            "video editor", "video editing", "premiere pro",
            "after effects", "post production",
        ],
    }

    for niche, keywords in niche_map.items():
        if any(keyword in text for keyword in keywords):
            return niche

    return "Other/Unclassified"


# ============================================================
# CSV AND DUPLICATE PROTECTION
# ============================================================

def ensure_csv():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not DATA_FILE.exists() or DATA_FILE.stat().st_size == 0:
        with DATA_FILE.open("w", newline="", encoding="utf-8-sig") as file:
            csv.DictWriter(file, fieldnames=CSV_HEADERS).writeheader()


def normalize_lead(lead):
    result = {
        header: clean(lead.get(header, ""))
        for header in CSV_HEADERS
    }
    result["subscribers"] = safe_int(result["subscribers"])
    return result


def lead_key(lead):
    platform = clean(lead.get("platform", "")).lower()
    channel_url = clean(lead.get("channel_url", "")).lower().rstrip("/")
    profile_url = clean(lead.get("profile_url", "")).lower().rstrip("/")

    if channel_url:
        return "youtube:" + channel_url
    if profile_url:
        return platform + ":" + profile_url

    email = clean(lead.get("business_email", "")).lower()
    if email:
        return "email:" + email

    name = clean(lead.get("name", "")).lower()
    return platform + ":" + name


def read_csv():
    ensure_csv()
    with DATA_FILE.open("r", newline="", encoding="utf-8-sig") as file:
        return [
            normalize_lead(row)
            for row in csv.DictReader(file)
        ]


def save_leads(leads):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with DATA_FILE.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(normalize_lead(lead) for lead in leads)

    print(f"Saved {len(leads)} leads to {DATA_FILE}")


# ============================================================
# HTTP HELPER
# ============================================================

def get_json(url, params, headers=None):
    response = requests.get(
        url,
        params=params,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code != 200:
        try:
            error_data = response.json()
        except Exception:
            error_data = response.text[:500]

        raise RuntimeError(
            f"HTTP {response.status_code} from {url}: {error_data}"
        )

    return response.json()


# ============================================================
# YOUTUBE API
# ============================================================

def youtube_search(query):
    data = get_json(
        YOUTUBE_SEARCH_URL,
        {
            "part": "snippet",
            "q": query,
            "type": "channel",
            "maxResults": 50,
            "key": YOUTUBE_API_KEY,
        },
    )

    return [
        clean(item.get("snippet", {}).get("channelId", ""))
        for item in data.get("items", [])
        if item.get("snippet", {}).get("channelId")
    ]


def youtube_get_channels(channel_ids):
    results = []

    for start in range(0, len(channel_ids), 50):
        batch = channel_ids[start:start + 50]

        data = get_json(
            YOUTUBE_CHANNELS_URL,
            {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(batch),
                "key": YOUTUBE_API_KEY,
            },
        )
        results.extend(data.get("items", []))
        time.sleep(0.1)

    return results


def youtube_latest_upload(channel):
    playlist_id = clean(
        channel.get("contentDetails", {})
        .get("relatedPlaylists", {})
        .get("uploads", "")
    )

    if not playlist_id:
        return ""

    try:
        data = get_json(
            YOUTUBE_PLAYLIST_ITEMS_URL,
            {
                "part": "snippet",
                "playlistId": playlist_id,
                "maxResults": 1,
                "key": YOUTUBE_API_KEY,
            },
        )

        items = data.get("items", [])
        if not items:
            return ""

        return clean(items[0].get("snippet", {}).get("publishedAt", ""))

    except Exception as error:
        print(f"Warning: could not read latest upload: {error}")
        return ""


def collect_youtube():
    print("\n=== YOUTUBE COLLECTION ===")

    if not YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY is missing.")

    channel_ids = []

    for query in YOUTUBE_SEARCH_QUERIES:
        print(f"YouTube search: {query}")
        try:
            channel_ids.extend(youtube_search(query))
        except Exception as error:
            print(f"Search failed for '{query}': {error}")

    channel_ids = list(dict.fromkeys(channel_ids))
    print(f"Unique YouTube channels discovered: {len(channel_ids)}")

    channels = youtube_get_channels(channel_ids)
    leads = []

    for channel in channels:
        snippet = channel.get("snippet", {})
        stats = channel.get("statistics", {})
        subscribers = safe_int(stats.get("subscriberCount", 0))

        if subscribers < MIN_SUBSCRIBERS:
            continue

        title = clean(snippet.get("title", ""))
        description = clean(snippet.get("description", ""))
        channel_id = clean(channel.get("id", ""))
        custom_url = clean(snippet.get("customUrl", ""))

        profile_url = (
            "https://www.youtube.com/" + custom_url.lstrip("/")
            if custom_url
            else f"https://www.youtube.com/channel/{channel_id}"
        )
        channel_url = f"https://www.youtube.com/channel/{channel_id}"

        latest_upload = youtube_latest_upload(channel)
        if not is_recent_upload(latest_upload):
            continue

        contacts = extract_public_contacts(description)
        email = extract_email(description)

        contact_methods = []
        if email:
            contact_methods.append("Business Email")
        if contacts["instagram"]:
            contact_methods.append("Instagram")
        if contacts["linkedin"]:
            contact_methods.append("LinkedIn")
        if contacts["twitter_x"]:
            contact_methods.append("X/Twitter")
        if contacts["website"]:
            contact_methods.append("Website")

        if not contact_methods:
            continue

        score = 50
        score += 25 if email else 0
        score += 15 if (
            contacts["instagram"] or contacts["linkedin"]
            or contacts["twitter_x"]
        ) else 0
        score += 10 if contacts["website"] else 0
        score = min(score, 100)

        leads.append(normalize_lead({
            "name": title,
            "platform": "YouTube",
            "profile_url": profile_url,
            "channel_url": channel_url,
            "creator_or_business": "Creator",
            "niche": detect_niche(f"{title} {description}"),
            "country": clean(snippet.get("country", "")),
            "city": "",
            "subscribers": subscribers,
            "avg_views": "",
            "business_email": email,
            "instagram": contacts["instagram"],
            "linkedin": contacts["linkedin"],
            "twitter_x": contacts["twitter_x"],
            "website": contacts["website"],
            "recent_upload": latest_upload,
            "contact_type": ", ".join(contact_methods),
            "lead_source": "YouTube Data API",
            "status": "New",
            "notes": (
                f"Public contact found; lead score {score}/100. "
                f"Recent upload within {ACTIVE_DAYS} days. "
                "Monetization status is not verified."
            ),
        }))

        if MAX_LEADS_PER_RUN > 0 and len(leads) >= MAX_LEADS_PER_RUN:
            print(f"Reached MAX_LEADS_PER_RUN={MAX_LEADS_PER_RUN}.")
            break

    print(f"YouTube leads after filtering: {len(leads)}")
    return leads


# ============================================================
# X API AUTHENTICATION
# ============================================================

def get_x_access_token():
    if X_BEARER_TOKEN:
        print("Using configured X Bearer Token.")
        return X_BEARER_TOKEN

    if not X_API_KEY or not X_API_SECRET:
        print(
            "X collection skipped: configure X_BEARER_TOKEN "
            "or both X_API_KEY and X_API_SECRET."
        )
        return ""

    token_url = "https://api.x.com/oauth2/token"

    try:
        response = requests.post(
            token_url,
            auth=HTTPBasicAuth(X_API_KEY, X_API_SECRET),
            data={"grant_type": "client_credentials"},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code != 200:
            print(
                f"X token request failed: HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )
            return ""

        token = clean(response.json().get("access_token", ""))

        if not token:
            print("X token request returned no access token.")
            return ""

        print("X API authentication successful.")
        return token

    except requests.RequestException as error:
        print(f"X authentication request failed: {error}")
        return ""


# ============================================================
# X.COM API — RECENT POSTS AND PUBLIC PROFILES
# ============================================================

def collect_x():
    token = get_x_access_token()

    if not token:
        print("X collection skipped: authentication unavailable.")
        return []

    print("\n=== X.COM COLLECTION ===")

    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "lead-automation",
    }

    leads = []
    endpoint = "https://api.x.com/2/tweets/search/recent"
    seen_users = set()

    for term in X_SEARCH_QUERIES:
        print(f"X search: {term}")

        try:
            data = get_json(
                endpoint,
                {
                    "query": f"{term} -is:retweet",
                    "max_results": 10,
                    "expansions": "author_id",
                    "user.fields": (
                        "name,username,description,public_metrics,url"
                    ),
                },
                headers=headers,
            )
        except Exception as error:
            print(f"X API request failed for '{term}': {error}")
            continue

        users = data.get("includes", {}).get("users", [])

        for user in users:
            username = clean(user.get("username", ""))
            if not username:
                continue

            user_key = username.lower()
            if user_key in seen_users:
                continue
            seen_users.add(user_key)

            metrics = user.get("public_metrics", {})
            followers = safe_int(metrics.get("followers_count", 0))

            if followers < MIN_SUBSCRIBERS:
                continue

            description = clean(user.get("description", ""))
            email = extract_email(description)
            public_url = clean(user.get("url", ""))

            contacts = extract_public_contacts(
                f"{description} {public_url}"
            )

            leads.append(normalize_lead({
                "name": clean(user.get("name", "")),
                "platform": "X",
                "profile_url": f"https://x.com/{username}",
                "channel_url": "",
                "creator_or_business": "Creator/Business",
                "niche": detect_niche(f"{term} {description}"),
                "country": "India" if "India" in term else "",
                "city": "",
                "subscribers": followers,
                "avg_views": "",
                "business_email": email,
                "instagram": contacts["instagram"],
                "linkedin": contacts["linkedin"],
                "twitter_x": f"https://x.com/{username}",
                "website": public_url or contacts["website"],
                "recent_upload": "",
                "contact_type": "Public X profile" + (
                    ", Business Email" if email else ""
                ),
                "lead_source": "X API Recent Search",
                "status": "New",
                "notes": (
                    "Profile discovered from recent public post search. "
                    "Follower count stored in subscribers column. "
                    "Confirm business relevance and contact details manually."
                ),
            }))

            if MAX_LEADS_PER_RUN > 0 and len(leads) >= MAX_LEADS_PER_RUN:
                print(f"Reached MAX_LEADS_PER_RUN={MAX_LEADS_PER_RUN}.")
                print("Stopping X collection at configured limit.")
                print(f"X leads collected: {len(leads)}")
                return leads

    print(f"X leads collected before deduplication: {len(leads)}")
    return leads


# ============================================================
# GOOGLE SHEETS — SAME 20-COLUMN FORMAT
# ============================================================

def upload_to_google_sheets(leads):
    print("\n=== GOOGLE SHEETS UPLOAD ===")

    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        print("ERROR: GOOGLE_SERVICE_ACCOUNT_JSON is missing.")
        return False

    if not GOOGLE_SHEET_ID:
        print("ERROR: GOOGLE_SHEET_ID is missing.")
        return False

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        service_account_info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        credentials = Credentials.from_service_account_info(
            service_account_info,
            scopes=scopes,
        )
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

        worksheet = (
            spreadsheet.worksheet(GOOGLE_SHEET_NAME)
            if GOOGLE_SHEET_NAME
            else spreadsheet.sheet1
        )

        print(f"Google Sheet connected: {spreadsheet.title}")
        print(f"Worksheet: {worksheet.title}")

        worksheet.update(
            range_name="A1:T1",
            values=[CSV_HEADERS],
        )

        existing_values = worksheet.get_all_values()
        existing_keys = set()

        for values in existing_values[1:]:
            row = {
                header: values[i] if i < len(values) else ""
                for i, header in enumerate(CSV_HEADERS)
            }
            existing_keys.add(lead_key(row))

        rows_to_add = []

        for lead in leads:
            lead = normalize_lead(lead)
            key = lead_key(lead)

            if key in existing_keys:
                continue

            rows_to_add.append([lead[h] for h in CSV_HEADERS])
            existing_keys.add(key)

        print(f"New rows ready for Google Sheets: {len(rows_to_add)}")

        if rows_to_add:
            worksheet.append_rows(
                rows_to_add,
                value_input_option="USER_ENTERED",
            )

        updated_values = worksheet.get_all_values()
        final_keys = set()

        for values in updated_values[1:]:
            row = {
                header: values[i] if i < len(values) else ""
                for i, header in enumerate(CSV_HEADERS)
            }
            final_keys.add(lead_key(row))

        verified = 0

        for values in rows_to_add:
            row = {
                header: values[i] if i < len(values) else ""
                for i, header in enumerate(CSV_HEADERS)
            }
            if lead_key(row) in final_keys:
                verified += 1

        print(f"New leads uploaded: {len(rows_to_add)}")
        print(f"Uploaded rows verified: {verified}/{len(rows_to_add)}")
        print(f"Sheet data rows now: {max(0, len(updated_values) - 1)}")

        if verified != len(rows_to_add):
            print("ERROR: Google Sheets verification did not match.")
            return False

        print("GOOGLE SHEETS UPLOAD VERIFIED.")
        return True

    except Exception as error:
        print(f"ERROR: Google Sheets upload failed: {error}")
        return False


# ============================================================
# MAIN — PRESERVE CSV AND SHEETS WORKFLOW
# ============================================================

def main():
    print("\n" + "=" * 60)
    print("LEAD AUTOMATION STARTED")
    print("=" * 60)

    if not YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY is missing.")

    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is missing.")

    if not GOOGLE_SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID is missing.")

    ensure_csv()
    existing_leads = read_csv()
    print(f"Existing CSV leads: {len(existing_leads)}")

    # Collect from YouTube and X.
    collected = collect_youtube()
    collected.extend(collect_x())

    # Preserve existing CSV rows and deduplicate.
    merged = []
    seen = set()

    for lead in existing_leads + collected:
        lead = normalize_lead(lead)
        key = lead_key(lead)

        if key not in seen:
            seen.add(key)
            merged.append(lead)

    save_leads(merged)

    # Upload all existing and newly collected rows.
    if not upload_to_google_sheets(merged):
        raise RuntimeError("Google Sheets upload failed.")

    print("\n" + "=" * 60)
    print(f"CSV total leads: {len(merged)}")
    print(f"Leads collected this run: {len(collected)}")
    print("LEAD AUTOMATION FINISHED")
    print("=" * 60)


if __name__ == "__main__":
    main()
