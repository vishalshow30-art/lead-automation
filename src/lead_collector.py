
from pathlib import Path
import csv
import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import requests


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DATA_FILE = DATA_DIR / "leads.csv"

MIN_SUBSCRIBERS = int(os.getenv("MIN_SUBSCRIBERS", "20000"))
MAX_LEADS_PER_RUN = int(os.getenv("MAX_LEADS_PER_RUN", "200"))
ACTIVE_DAYS = int(os.getenv("ACTIVE_DAYS", "60"))
REQUEST_TIMEOUT = 30

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON", ""
).strip()
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "").strip()


# ============================================================
# SHEET COLUMNS — KEEP THESE IN SYNC WITH YOUR EXISTING SHEET
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
# SEARCH QUERIES
# ============================================================

YOUTUBE_SEARCH_QUERIES = [
    "YouTuber creator",
    "content creator channel",
    "video creator",
    "creator official channel",
    "popular YouTube channel",
    "podcast channel",
    "interview podcast",
    "creator vlog",
    "gaming channel",
    "gameplay creator",
    "esports channel",
    "comedy channel",
    "entertainment channel",
    "reaction channel",
    "movie review channel",
    "music creator channel",
    "animation channel",
    "education channel",
    "online learning channel",
    "science channel",
    "history channel",
    "technology channel",
    "tech review channel",
    "gadget review channel",
    "business channel",
    "entrepreneur channel",
    "finance channel",
    "investing education channel",
    "lifestyle channel",
    "daily vlog channel",
    "travel channel",
    "food cooking channel",
    "fitness workout channel",
    "health wellness channel",
    "beauty makeup channel",
    "fashion channel",
    "automotive car channel",
    "DIY home improvement channel",
    "photography filmmaking channel",
    "real estate channel",
    "parenting family channel",
    "sports channel",
    "book review channel",
    "USA YouTuber creator",
    "UK YouTuber creator",
    "Canadian YouTuber creator",
    "Australian YouTuber creator",
    "German YouTuber creator",
    "French YouTuber creator",
    "Spanish YouTuber creator",
    "Brazilian YouTuber creator",
    "Japanese YouTuber creator",
    "Korean YouTuber creator",
    "UAE YouTuber creator",
    "Saudi YouTuber creator",
    "Singapore YouTuber creator",
    "Indian YouTuber creator",
]


# ============================================================
# YOUTUBE API
# ============================================================

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
    text = clean(text)
    matches = re.findall(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        text,
    )
    for email in matches:
        email = email.lower().strip()
        if not email.endswith((".png", ".jpg", ".jpeg", ".webp")):
            return email
    return ""


def extract_public_contacts(description):
    """Extract social links and website URLs publicly listed in the description."""
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
        "tiktok.com", "x.com", "google.com",
        "discord.gg", "twitch.tv",
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
    }

    for niche, keywords in niche_map.items():
        if any(keyword in text for keyword in keywords):
            return niche

    return "Other/Unclassified"


# ============================================================
# CSV AND DUPLICATE HELPERS
# ============================================================

def ensure_csv():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not DATA_FILE.exists() or DATA_FILE.stat().st_size == 0:
        with DATA_FILE.open(
            "w", newline="", encoding="utf-8-sig"
        ) as file:
            writer = csv.DictWriter(file, fieldnames=CSV_HEADERS)
            writer.writeheader()


def normalize_lead(lead):
    result = {
        header: clean(lead.get(header, ""))
        for header in CSV_HEADERS
    }
    result["subscribers"] = safe_int(result["subscribers"])
    return result


def lead_key(lead):
    channel_url = clean(lead.get("channel_url", "")).lower().rstrip("/")
    if channel_url:
        return "youtube:" + channel_url

    profile_url = clean(lead.get("profile_url", "")).lower().rstrip("/")
    if profile_url:
        return clean(lead.get("platform", "")).lower() + ":" + profile_url

    email = clean(lead.get("business_email", "")).lower()
    if email:
        return "email:" + email

    name = clean(lead.get("name", "")).lower()
    return clean(lead.get("platform", "")).lower() + ":" + name


def read_csv():
    ensure_csv()
    leads = []

    with DATA_FILE.open(
        "r", newline="", encoding="utf-8-sig"
    ) as file:
        for row in csv.DictReader(file):
            leads.append(normalize_lead(row))

    return leads


def save_leads(leads):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with DATA_FILE.open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(normalize_lead(lead) for lead in leads)

    print(f"Saved {len(leads)} leads to {DATA_FILE}")


# ============================================================
# API REQUESTS
# ============================================================

def get_json(url, params):
    response = requests.get(
        url, params=params, timeout=REQUEST_TIMEOUT
    )

    if response.status_code != 200:
        try:
            error_data = response.json()
        except Exception:
            error_data = response.text[:500]

        raise RuntimeError(
            f"HTTP {response.status_code} from YouTube API: {error_data}"
        )

    return response.json()


def youtube_search(query):
    params = {
        "part": "snippet",
        "q": query,
        "type": "channel",
        "maxResults": 50,
        "key": YOUTUBE_API_KEY,
    }

    data = get_json(YOUTUBE_SEARCH_URL, params)
    channel_ids = []

    for item in data.get("items", []):
        channel_id = clean(
            item.get("snippet", {}).get("channelId", "")
        )
        if channel_id:
            channel_ids.append(channel_id)

    return channel_ids


def youtube_get_channels(channel_ids):
    if not channel_ids:
        return []

    results = []

    for start in range(0, len(channel_ids), 50):
        batch = channel_ids[start:start + 50]

        params = {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(batch),
            "key": YOUTUBE_API_KEY,
        }

        data = get_json(YOUTUBE_CHANNELS_URL, params)
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

    params = {
        "part": "snippet",
        "playlistId": playlist_id,
        "maxResults": 1,
        "key": YOUTUBE_API_KEY,
    }

    try:
        data = get_json(YOUTUBE_PLAYLIST_ITEMS_URL, params)
        items = data.get("items", [])

        if not items:
            return ""

        return clean(
            items[0].get("snippet", {}).get("publishedAt", "")
        )

    except Exception as error:
        print(f"Warning: could not read latest upload: {error}")
        return ""


# ============================================================
# COLLECT ACTIVE, CONTACTABLE YOUTUBE CREATORS
# ============================================================

def collect_youtube():
    print("\n" + "=" * 60)
    print("STARTING YOUTUBE COLLECTION")
    print("=" * 60)

    if not YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY is missing.")

    channel_ids = []

    for query in YOUTUBE_SEARCH_QUERIES:
        print(f"Searching: {query}")

        try:
            ids = youtube_search(query)
            print(f"Results received: {len(ids)}")
            channel_ids.extend(ids)
        except Exception as error:
            print(f"WARNING: search failed for '{query}': {error}")

    unique_channel_ids = list(dict.fromkeys(channel_ids))
    print(f"Unique channels found: {len(unique_channel_ids)}")

    if not unique_channel_ids:
        print("No YouTube channels found.")
        return []

    channel_details = youtube_get_channels(unique_channel_ids)
    print(f"Channel details received: {len(channel_details)}")

    leads = []

    for channel in channel_details:
        snippet = channel.get("snippet", {})
        statistics = channel.get("statistics", {})

        subscribers = safe_int(statistics.get("subscriberCount", 0))

        # Minimum subscriber threshold; there is no maximum.
        if subscribers < MIN_SUBSCRIBERS:
            continue

        title = clean(snippet.get("title", ""))
        description = clean(snippet.get("description", ""))
        custom_url = clean(snippet.get("customUrl", ""))
        channel_id = clean(channel.get("id", ""))

        niche = detect_niche(f"{title} {description}")

        if custom_url:
            custom_url = custom_url.replace("@", "").strip("/")
            profile_url = "https://www.youtube.com/" + custom_url
        else:
            profile_url = (
                "https://www.youtube.com/channel/" + channel_id
            )

        channel_url = (
            "https://www.youtube.com/channel/" + channel_id
        )

        email = extract_email(description)

        # Filter out channels with no recent public upload.
        latest_upload = youtube_latest_upload(channel)
        if not is_recent_upload(latest_upload, ACTIVE_DAYS):
            continue

        # Only public contact methods explicitly found in the description.
        contacts = extract_public_contacts(description)
        instagram = contacts["instagram"]
        linkedin = contacts["linkedin"]
        twitter_x = contacts["twitter_x"]
        website = contacts["website"]

        contact_methods = []
        if email:
            contact_methods.append("Business Email")
        if instagram:
            contact_methods.append("Instagram")
        if linkedin:
            contact_methods.append("LinkedIn")
        if twitter_x:
            contact_methods.append("X/Twitter")
        if website:
            contact_methods.append("Website")

        # Exclude creators if no public contact route was found.
        if not contact_methods:
            continue

        lead_score = 50
        if email:
            lead_score += 25
        if instagram or linkedin or twitter_x:
            lead_score += 15
        if website:
            lead_score += 10
        lead_score = min(lead_score, 100)

        # Country may not be exposed by YouTube's API.
        country = clean(snippet.get("country", ""))

        lead = {
            "name": title,
            "platform": "YouTube",
            "profile_url": profile_url,
            "channel_url": channel_url,
            "creator_or_business": "Creator",
            "niche": niche,
            "country": country,
            "city": "",
            "subscribers": subscribers,
            "avg_views": "",
            "business_email": email,
            "instagram": instagram,
            "linkedin": linkedin,
            "twitter_x": twitter_x,
            "website": website,
            "recent_upload": latest_upload,
            "contact_type": ", ".join(contact_methods),
            "lead_source": "YouTube Data API",
            "status": "New",
            "notes": (
                f"Active: uploaded within {ACTIVE_DAYS} days; "
                f"Contact available: yes ({', '.join(contact_methods)}); "
                f"Lead score: {lead_score}/100. "
                "YouTube monetization status is not verified."
            ),
        }

        leads.append(normalize_lead(lead))

        if MAX_LEADS_PER_RUN > 0 and len(leads) >= MAX_LEADS_PER_RUN:
            print(
                f"Reached MAX_LEADS_PER_RUN={MAX_LEADS_PER_RUN}. "
                "Set it to 0 to disable this additional cap."
            )
            break

    print(
        f"Filters: {MIN_SUBSCRIBERS:,}+ subscribers, "
        f"latest upload within {ACTIVE_DAYS} days, "
        "and at least one public contact method."
    )
    print(f"YOUTUBE LEADS AFTER FILTERING: {len(leads)}")

    return leads


# ============================================================
# GOOGLE SHEETS
# ============================================================

def upload_to_google_sheets(leads):
    print("\n" + "=" * 60)
    print("STARTING GOOGLE SHEETS UPLOAD")
    print("=" * 60)

    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        print("ERROR: GOOGLE_SERVICE_ACCOUNT_JSON is missing.")
        return False

    if not GOOGLE_SHEET_ID:
        print("ERROR: GOOGLE_SHEET_ID is missing.")
        return False

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except Exception as error:
        print(f"ERROR: Google Sheets libraries could not load: {error}")
        return False

    try:
        service_account_info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    except json.JSONDecodeError as error:
        print(f"ERROR: service-account JSON is invalid: {error}")
        return False

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    try:
        credentials = Credentials.from_service_account_info(
            service_account_info,
            scopes=scopes,
        )
        client = gspread.authorize(credentials)
    except Exception as error:
        print(f"ERROR: Google authorization failed: {error}")
        return False

    try:
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

        if GOOGLE_SHEET_NAME:
            worksheet = spreadsheet.worksheet(GOOGLE_SHEET_NAME)
        else:
            worksheet = spreadsheet.sheet1

        print(f"Google Sheet opened: {spreadsheet.title}")
        print(f"Worksheet: {worksheet.title}")

    except Exception as error:
        print(f"ERROR: Could not open Google Sheet/worksheet: {error}")
        return False

    # IMPORTANT:
    # This expects the sheet's first 20 columns to match CSV_HEADERS.
    # Back up your sheet before changing its header row.
    try:
        worksheet.update(
            range_name="A1:T1",
            values=[CSV_HEADERS],
        )
        existing_values = worksheet.get_all_values()
    except Exception as error:
        print(f"ERROR: Could not read/update sheet header: {error}")
        return False

    existing_keys = set()

    for row_values in existing_values[1:]:
        row = {
            header: (
                row_values[index] if index < len(row_values) else ""
            )
            for index, header in enumerate(CSV_HEADERS)
        }
        existing_keys.add(lead_key(row))

    rows_to_add = []

    for lead in leads:
        normalized = normalize_lead(lead)
        key = lead_key(normalized)

        if key in existing_keys:
            continue

        rows_to_add.append([
            normalized[header] for header in CSV_HEADERS
        ])
        existing_keys.add(key)

    print(f"New rows ready for upload: {len(rows_to_add)}")

    if not rows_to_add:
        print("No new rows to upload. Google Sheets connection is working.")
        return True

    try:
        worksheet.append_rows(
            rows_to_add,
            value_input_option="USER_ENTERED",
        )
    except Exception as error:
        print(f"ERROR: Google Sheets append failed: {error}")
        return False

    print(f"SUCCESS: {len(rows_to_add)} new leads uploaded.")

    try:
        updated_values = worksheet.get_all_values()
        expected_rows = len(existing_values) + len(rows_to_add)

        if len(updated_values) < expected_rows:
            print("ERROR: Google Sheet row-count verification failed.")
            return False

        final_keys = set()

        for row_values in updated_values[1:]:
            row = {
                header: (
                    row_values[index] if index < len(row_values) else ""
                )
                for index, header in enumerate(CSV_HEADERS)
            }
            final_keys.add(lead_key(row))

        verified_count = 0

        for row_values in rows_to_add:
            row = {
                header: (
                    row_values[index] if index < len(row_values) else ""
                )
                for index, header in enumerate(CSV_HEADERS)
            }
            if lead_key(row) in final_keys:
                verified_count += 1

        print(f"Uploaded rows verified: {verified_count}/{len(rows_to_add)}")

        if verified_count != len(rows_to_add):
            print("ERROR: Not all uploaded leads were verified.")
            return False

        print("GOOGLE SHEETS UPLOAD VERIFIED.")
        return True

    except Exception as error:
        print(f"ERROR: Google Sheets verification failed: {error}")
        return False


# ============================================================
# MAIN
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

    youtube_leads = collect_youtube()

    existing_keys = {lead_key(lead) for lead in existing_leads}
    new_csv_leads = []

    for lead in youtube_leads:
        normalized = normalize_lead(lead)
        key = lead_key(normalized)

        if key in existing_keys:
            continue

        existing_keys.add(key)
        new_csv_leads.append(normalized)

    all_leads = existing_leads + new_csv_leads
    print(f"New leads added to CSV: {len(new_csv_leads)}")
    save_leads(all_leads)

    sheets_success = upload_to_google_sheets(youtube_leads)

    if not sheets_success:
        raise RuntimeError("Google Sheets upload failed.")

    print("\n" + "=" * 60)
    print("LEAD AUTOMATION FINISHED")
    print("=" * 60)


if __name__ == "__main__":
    main()

from pathlib import Path
import csv
import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import requests


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DATA_FILE = DATA_DIR / "leads.csv"

MIN_SUBSCRIBERS = int(os.getenv("MIN_SUBSCRIBERS", "20000"))
MAX_LEADS_PER_RUN = int(os.getenv("MAX_LEADS_PER_RUN", "200"))
ACTIVE_DAYS = int(os.getenv("ACTIVE_DAYS", "60"))
REQUEST_TIMEOUT = 30

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON", ""
).strip()
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "").strip()


# ============================================================
# SHEET COLUMNS — KEEP THESE IN SYNC WITH YOUR EXISTING SHEET
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
# SEARCH QUERIES
# ============================================================

YOUTUBE_SEARCH_QUERIES = [
    "YouTuber creator",
    "content creator channel",
    "video creator",
    "creator official channel",
    "popular YouTube channel",
    "podcast channel",
    "interview podcast",
    "creator vlog",
    "gaming channel",
    "gameplay creator",
    "esports channel",
    "comedy channel",
    "entertainment channel",
    "reaction channel",
    "movie review channel",
    "music creator channel",
    "animation channel",
    "education channel",
    "online learning channel",
    "science channel",
    "history channel",
    "technology channel",
    "tech review channel",
    "gadget review channel",
    "business channel",
    "entrepreneur channel",
    "finance channel",
    "investing education channel",
    "lifestyle channel",
    "daily vlog channel",
    "travel channel",
    "food cooking channel",
    "fitness workout channel",
    "health wellness channel",
    "beauty makeup channel",
    "fashion channel",
    "automotive car channel",
    "DIY home improvement channel",
    "photography filmmaking channel",
    "real estate channel",
    "parenting family channel",
    "sports channel",
    "book review channel",
    "USA YouTuber creator",
    "UK YouTuber creator",
    "Canadian YouTuber creator",
    "Australian YouTuber creator",
    "German YouTuber creator",
    "French YouTuber creator",
    "Spanish YouTuber creator",
    "Brazilian YouTuber creator",
    "Japanese YouTuber creator",
    "Korean YouTuber creator",
    "UAE YouTuber creator",
    "Saudi YouTuber creator",
    "Singapore YouTuber creator",
    "Indian YouTuber creator",
]


# ============================================================
# YOUTUBE API
# ============================================================

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
    text = clean(text)
    matches = re.findall(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        text,
    )
    for email in matches:
        email = email.lower().strip()
        if not email.endswith((".png", ".jpg", ".jpeg", ".webp")):
            return email
    return ""


def extract_public_contacts(description):
    """Extract social links and website URLs publicly listed in the description."""
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
        "tiktok.com", "x.com", "google.com",
        "discord.gg", "twitch.tv",
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
    }

    for niche, keywords in niche_map.items():
        if any(keyword in text for keyword in keywords):
            return niche

    return "Other/Unclassified"


# ============================================================
# CSV AND DUPLICATE HELPERS
# ============================================================

def ensure_csv():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not DATA_FILE.exists() or DATA_FILE.stat().st_size == 0:
        with DATA_FILE.open(
            "w", newline="", encoding="utf-8-sig"
        ) as file:
            writer = csv.DictWriter(file, fieldnames=CSV_HEADERS)
            writer.writeheader()


def normalize_lead(lead):
    result = {
        header: clean(lead.get(header, ""))
        for header in CSV_HEADERS
    }
    result["subscribers"] = safe_int(result["subscribers"])
    return result


def lead_key(lead):
    channel_url = clean(lead.get("channel_url", "")).lower().rstrip("/")
    if channel_url:
        return "youtube:" + channel_url

    profile_url = clean(lead.get("profile_url", "")).lower().rstrip("/")
    if profile_url:
        return clean(lead.get("platform", "")).lower() + ":" + profile_url

    email = clean(lead.get("business_email", "")).lower()
    if email:
        return "email:" + email

    name = clean(lead.get("name", "")).lower()
    return clean(lead.get("platform", "")).lower() + ":" + name


def read_csv():
    ensure_csv()
    leads = []

    with DATA_FILE.open(
        "r", newline="", encoding="utf-8-sig"
    ) as file:
        for row in csv.DictReader(file):
            leads.append(normalize_lead(row))

    return leads


def save_leads(leads):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with DATA_FILE.open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(normalize_lead(lead) for lead in leads)

    print(f"Saved {len(leads)} leads to {DATA_FILE}")


# ============================================================
# API REQUESTS
# ============================================================

def get_json(url, params):
    response = requests.get(
        url, params=params, timeout=REQUEST_TIMEOUT
    )

    if response.status_code != 200:
        try:
            error_data = response.json()
        except Exception:
            error_data = response.text[:500]

        raise RuntimeError(
            f"HTTP {response.status_code} from YouTube API: {error_data}"
        )

    return response.json()


def youtube_search(query):
    params = {
        "part": "snippet",
        "q": query,
        "type": "channel",
        "maxResults": 50,
        "key": YOUTUBE_API_KEY,
    }

    data = get_json(YOUTUBE_SEARCH_URL, params)
    channel_ids = []

    for item in data.get("items", []):
        channel_id = clean(
            item.get("snippet", {}).get("channelId", "")
        )
        if channel_id:
            channel_ids.append(channel_id)

    return channel_ids


def youtube_get_channels(channel_ids):
    if not channel_ids:
        return []

    results = []

    for start in range(0, len(channel_ids), 50):
        batch = channel_ids[start:start + 50]

        params = {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(batch),
            "key": YOUTUBE_API_KEY,
        }

        data = get_json(YOUTUBE_CHANNELS_URL, params)
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

    params = {
        "part": "snippet",
        "playlistId": playlist_id,
        "maxResults": 1,
        "key": YOUTUBE_API_KEY,
    }

    try:
        data = get_json(YOUTUBE_PLAYLIST_ITEMS_URL, params)
        items = data.get("items", [])

        if not items:
            return ""

        return clean(
            items[0].get("snippet", {}).get("publishedAt", "")
        )

    except Exception as error:
        print(f"Warning: could not read latest upload: {error}")
        return ""


# ============================================================
# COLLECT ACTIVE, CONTACTABLE YOUTUBE CREATORS
# ============================================================

def collect_youtube():
    print("\n" + "=" * 60)
    print("STARTING YOUTUBE COLLECTION")
    print("=" * 60)

    if not YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY is missing.")

    channel_ids = []

    for query in YOUTUBE_SEARCH_QUERIES:
        print(f"Searching: {query}")

        try:
            ids = youtube_search(query)
            print(f"Results received: {len(ids)}")
            channel_ids.extend(ids)
        except Exception as error:
            print(f"WARNING: search failed for '{query}': {error}")

    unique_channel_ids = list(dict.fromkeys(channel_ids))
    print(f"Unique channels found: {len(unique_channel_ids)}")

    if not unique_channel_ids:
        print("No YouTube channels found.")
        return []

    channel_details = youtube_get_channels(unique_channel_ids)
    print(f"Channel details received: {len(channel_details)}")

    leads = []

    for channel in channel_details:
        snippet = channel.get("snippet", {})
        statistics = channel.get("statistics", {})

        subscribers = safe_int(statistics.get("subscriberCount", 0))

        # Minimum subscriber threshold; there is no maximum.
        if subscribers < MIN_SUBSCRIBERS:
            continue

        title = clean(snippet.get("title", ""))
        description = clean(snippet.get("description", ""))
        custom_url = clean(snippet.get("customUrl", ""))
        channel_id = clean(channel.get("id", ""))

        niche = detect_niche(f"{title} {description}")

        if custom_url:
            custom_url = custom_url.replace("@", "").strip("/")
            profile_url = "https://www.youtube.com/" + custom_url
        else:
            profile_url = (
                "https://www.youtube.com/channel/" + channel_id
            )

        channel_url = (
            "https://www.youtube.com/channel/" + channel_id
        )

        email = extract_email(description)

        # Filter out channels with no recent public upload.
        latest_upload = youtube_latest_upload(channel)
        if not is_recent_upload(latest_upload, ACTIVE_DAYS):
            continue

        # Only public contact methods explicitly found in the description.
        contacts = extract_public_contacts(description)
        instagram = contacts["instagram"]
        linkedin = contacts["linkedin"]
        twitter_x = contacts["twitter_x"]
        website = contacts["website"]

        contact_methods = []
        if email:
            contact_methods.append("Business Email")
        if instagram:
            contact_methods.append("Instagram")
        if linkedin:
            contact_methods.append("LinkedIn")
        if twitter_x:
            contact_methods.append("X/Twitter")
        if website:
            contact_methods.append("Website")

        # Exclude creators if no public contact route was found.
        if not contact_methods:
            continue

        lead_score = 50
        if email:
            lead_score += 25
        if instagram or linkedin or twitter_x:
            lead_score += 15
        if website:
            lead_score += 10
        lead_score = min(lead_score, 100)

        # Country may not be exposed by YouTube's API.
        country = clean(snippet.get("country", ""))

        lead = {
            "name": title,
            "platform": "YouTube",
            "profile_url": profile_url,
            "channel_url": channel_url,
            "creator_or_business": "Creator",
            "niche": niche,
            "country": country,
            "city": "",
            "subscribers": subscribers,
            "avg_views": "",
            "business_email": email,
            "instagram": instagram,
            "linkedin": linkedin,
            "twitter_x": twitter_x,
            "website": website,
            "recent_upload": latest_upload,
            "contact_type": ", ".join(contact_methods),
            "lead_source": "YouTube Data API",
            "status": "New",
            "notes": (
                f"Active: uploaded within {ACTIVE_DAYS} days; "
                f"Contact available: yes ({', '.join(contact_methods)}); "
                f"Lead score: {lead_score}/100. "
                "YouTube monetization status is not verified."
            ),
        }

        leads.append(normalize_lead(lead))

        if MAX_LEADS_PER_RUN > 0 and len(leads) >= MAX_LEADS_PER_RUN:
            print(
                f"Reached MAX_LEADS_PER_RUN={MAX_LEADS_PER_RUN}. "
                "Set it to 0 to disable this additional cap."
            )
            break

    print(
        f"Filters: {MIN_SUBSCRIBERS:,}+ subscribers, "
        f"latest upload within {ACTIVE_DAYS} days, "
        "and at least one public contact method."
    )
    print(f"YOUTUBE LEADS AFTER FILTERING: {len(leads)}")

    return leads


# ============================================================
# GOOGLE SHEETS
# ============================================================

def upload_to_google_sheets(leads):
    print("\n" + "=" * 60)
    print("STARTING GOOGLE SHEETS UPLOAD")
    print("=" * 60)

    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        print("ERROR: GOOGLE_SERVICE_ACCOUNT_JSON is missing.")
        return False

    if not GOOGLE_SHEET_ID:
        print("ERROR: GOOGLE_SHEET_ID is missing.")
        return False

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except Exception as error:
        print(f"ERROR: Google Sheets libraries could not load: {error}")
        return False

    try:
        service_account_info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    except json.JSONDecodeError as error:
        print(f"ERROR: service-account JSON is invalid: {error}")
        return False

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    try:
        credentials = Credentials.from_service_account_info(
            service_account_info,
            scopes=scopes,
        )
        client = gspread.authorize(credentials)
    except Exception as error:
        print(f"ERROR: Google authorization failed: {error}")
        return False

    try:
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

        if GOOGLE_SHEET_NAME:
            worksheet = spreadsheet.worksheet(GOOGLE_SHEET_NAME)
        else:
            worksheet = spreadsheet.sheet1

        print(f"Google Sheet opened: {spreadsheet.title}")
        print(f"Worksheet: {worksheet.title}")

    except Exception as error:
        print(f"ERROR: Could not open Google Sheet/worksheet: {error}")
        return False

    # IMPORTANT:
    # This expects the sheet's first 20 columns to match CSV_HEADERS.
    # Back up your sheet before changing its header row.
    try:
        worksheet.update(
            range_name="A1:T1",
            values=[CSV_HEADERS],
        )
        existing_values = worksheet.get_all_values()
    except Exception as error:
        print(f"ERROR: Could not read/update sheet header: {error}")
        return False

    existing_keys = set()

    for row_values in existing_values[1:]:
        row = {
            header: (
                row_values[index] if index < len(row_values) else ""
            )
            for index, header in enumerate(CSV_HEADERS)
        }
        existing_keys.add(lead_key(row))

    rows_to_add = []

    for lead in leads:
        normalized = normalize_lead(lead)
        key = lead_key(normalized)

        if key in existing_keys:
            continue

        rows_to_add.append([
            normalized[header] for header in CSV_HEADERS
        ])
        existing_keys.add(key)

    print(f"New rows ready for upload: {len(rows_to_add)}")

    if not rows_to_add:
        print("No new rows to upload. Google Sheets connection is working.")
        return True

    try:
        worksheet.append_rows(
            rows_to_add,
            value_input_option="USER_ENTERED",
        )
    except Exception as error:
        print(f"ERROR: Google Sheets append failed: {error}")
        return False

    print(f"SUCCESS: {len(rows_to_add)} new leads uploaded.")

    try:
        updated_values = worksheet.get_all_values()
        expected_rows = len(existing_values) + len(rows_to_add)

        if len(updated_values) < expected_rows:
            print("ERROR: Google Sheet row-count verification failed.")
            return False

        final_keys = set()

        for row_values in updated_values[1:]:
            row = {
                header: (
                    row_values[index] if index < len(row_values) else ""
                )
                for index, header in enumerate(CSV_HEADERS)
            }
            final_keys.add(lead_key(row))

        verified_count = 0

        for row_values in rows_to_add:
            row = {
                header: (
                    row_values[index] if index < len(row_values) else ""
                )
                for index, header in enumerate(CSV_HEADERS)
            }
            if lead_key(row) in final_keys:
                verified_count += 1

        print(f"Uploaded rows verified: {verified_count}/{len(rows_to_add)}")

        if verified_count != len(rows_to_add):
            print("ERROR: Not all uploaded leads were verified.")
            return False

        print("GOOGLE SHEETS UPLOAD VERIFIED.")
        return True

    except Exception as error:
        print(f"ERROR: Google Sheets verification failed: {error}")
        return False


# ============================================================
# MAIN
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

    youtube_leads = collect_youtube()

    existing_keys = {lead_key(lead) for lead in existing_leads}
    new_csv_leads = []

    for lead in youtube_leads:
        normalized = normalize_lead(lead)
        key = lead_key(normalized)

        if key in existing_keys:
            continue

        existing_keys.add(key)
        new_csv_leads.append(normalized)

    all_leads = existing_leads + new_csv_leads
    print(f"New leads added to CSV: {len(new_csv_leads)}")
    save_leads(all_leads)

    sheets_success = upload_to_google_sheets(youtube_leads)

    if not sheets_success:
        raise RuntimeError("Google Sheets upload failed.")

    print("\n" + "=" * 60)
    print("LEAD AUTOMATION FINISHED")
    print("=" * 60)


if __name__ == "__main__":
    main()
