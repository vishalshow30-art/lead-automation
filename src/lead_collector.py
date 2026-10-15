
from pathlib import Path
import csv
import json
import os
import re
import time
import requests

# ================= CONFIG =================

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_FILE = DATA_DIR / "leads.csv"

MIN_SUBSCRIBERS = int(os.getenv("MIN_SUBSCRIBERS", "20000"))
MAX_LEADS_PER_RUN = int(os.getenv("MAX_LEADS_PER_RUN", "200"))
TIMEOUT = 30

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON", ""
).strip()
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "").strip()
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "").strip()

HEADERS = [
    "name", "platform", "profile_url", "channel_url",
    "creator_or_business", "niche", "country", "city",
    "subscribers", "avg_views", "business_email",
    "instagram", "linkedin", "twitter_x", "website",
    "recent_upload", "contact_type", "lead_source",
    "status", "notes"
]

SEARCH_QUERIES = [
    "YouTuber creator", "content creator channel",
    "video creator", "podcast channel", "interview podcast",
    "gaming channel", "gameplay creator", "esports channel",
    "comedy channel", "entertainment channel", "reaction channel",
    "movie review channel", "music creator", "animation channel",
    "education channel", "science channel", "history channel",
    "technology channel", "tech review channel", "gadget review",
    "business channel", "entrepreneur channel", "finance channel",
    "investing education", "lifestyle channel", "daily vlog",
    "travel channel", "food cooking channel", "fitness workout",
    "beauty makeup", "fashion channel", "automotive car channel",
    "DIY home improvement", "photography filmmaking",
    "real estate channel", "parenting family", "sports channel",
    "book review channel", "USA YouTuber", "UK YouTuber",
    "Canadian YouTuber", "Australian YouTuber",
    "German YouTuber", "French YouTuber", "Spanish YouTuber",
    "Brazilian YouTuber", "Japanese YouTuber", "Korean YouTuber",
    "UAE YouTuber", "Saudi YouTuber", "Singapore YouTuber",
    "Indian YouTuber"
]

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
PLAYLIST_URL = "https://www.googleapis.com/youtube/v3/playlistItems"


# ================= HELPERS =================

def clean(value):
    return str(value or "").strip()


def safe_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def get_json(url, params):
    response = requests.get(url, params=params, timeout=TIMEOUT)
    if response.status_code != 200:
        raise RuntimeError(
            f"YouTube API HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )
    return response.json()


def extract_email(text):
    matches = re.findall(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        clean(text)
    )
    return matches[0].lower() if matches else ""


def detect_niche(text):
    text = clean(text).lower()
    categories = {
        "Gaming": ["gaming", "gamer", "gameplay", "esports"],
        "Tech": ["technology", "tech", "gadget", "computer"],
        "Mobile": ["mobile", "smartphone", "iphone", "android"],
        "Education": ["education", "study", "learning", "student"],
        "Entertainment": ["entertainment", "movie", "celebrity"],
        "Fitness": ["fitness", "workout", "gym"],
        "Fashion": ["fashion", "style", "beauty", "makeup"],
        "Travel": ["travel", "travelling", "tour"],
        "Finance": ["finance", "stock", "investing", "trading"],
        "Automotive": ["automotive", "car", "cars", "motorcycle"],
        "Comedy": ["comedy", "funny"],
        "Food": ["food", "cooking", "recipe"],
        "Lifestyle": ["lifestyle", "daily life"],
        "Vlogging": ["vlog", "vlogging", "vlogger"],
        "Business": ["business", "entrepreneur", "marketing"],
        "Sports": ["sports", "football", "cricket", "basketball"],
        "Music": ["music", "singer", "musician"],
        "Photography": ["photography", "filmmaking", "camera"],
        "Science": ["science", "scientific", "experiment"],
        "Gaming": ["game", "gamer", "gaming"]
    }

    for category, keywords in categories.items():
        if any(word in text for word in keywords):
            return category
    return "Other/Unclassified"


def normalize_lead(lead):
    result = {key: clean(lead.get(key, "")) for key in HEADERS}
    result["subscribers"] = safe_int(result["subscribers"])
    return result


def lead_key(lead):
    channel = clean(lead.get("channel_url")).lower().rstrip("/")
    if channel:
        return "youtube:" + channel

    profile = clean(lead.get("profile_url")).lower().rstrip("/")
    if profile:
        return clean(lead.get("platform")).lower() + ":" + profile

    email = clean(lead.get("business_email")).lower()
    if email:
        return "email:" + email

    return clean(lead.get("name")).lower()


# ================= CSV =================

def ensure_csv():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists() or DATA_FILE.stat().st_size == 0:
        with DATA_FILE.open("w", newline="", encoding="utf-8-sig") as f:
            csv.DictWriter(f, fieldnames=HEADERS).writeheader()


def read_csv():
    ensure_csv()
    with DATA_FILE.open("r", newline="", encoding="utf-8-sig") as f:
        return [normalize_lead(row) for row in csv.DictReader(f)]


def save_csv(leads):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows([normalize_lead(x) for x in leads])
    print(f"CSV saved: {len(leads)} total leads")


# ================= YOUTUBE =================

def search_channels(query):
    data = get_json(SEARCH_URL, {
        "part": "snippet",
        "q": query,
        "type": "channel",
        "maxResults": 50,
        "key": YOUTUBE_API_KEY
    })
    return [
        item.get("id", {}).get("channelId", "")
        for item in data.get("items", [])
        if item.get("id", {}).get("channelId")
    ]


def get_channel_details(channel_ids):
    results = []
    for start in range(0, len(channel_ids), 50):
        batch = channel_ids[start:start + 50]
        data = get_json(CHANNELS_URL, {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(batch),
            "key": YOUTUBE_API_KEY
        })
        results.extend(data.get("items", []))
        time.sleep(0.1)
    return results


def get_latest_upload(channel):
    playlist_id = (
        channel.get("contentDetails", {})
        .get("relatedPlaylists", {})
        .get("uploads", "")
    )
    if not playlist_id:
        return ""

    try:
        data = get_json(PLAYLIST_URL, {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 1,
            "key": YOUTUBE_API_KEY
        })
        items = data.get("items", [])
        if items:
            return clean(items[0].get("snippet", {}).get("publishedAt"))
    except Exception as exc:
        print(f"Latest upload lookup warning: {exc}")
    return ""


def collect_youtube():
    if not YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY is missing.")

    channel_ids = []
    for query in SEARCH_QUERIES:
        print(f"Searching: {query}")
        try:
            channel_ids.extend(search_channels(query))
        except Exception as exc:
            print(f"Search warning for '{query}': {exc}")

    channel_ids = list(dict.fromkeys(channel_ids))
    print(f"Unique channels found: {len(channel_ids)}")

    details = get_channel_details(channel_ids)
    leads = []

    for channel in details:
        snippet = channel.get("snippet", {})
        stats = channel.get("statistics", {})
        subscribers = safe_int(stats.get("subscriberCount"))

        # Minimum 20K subscribers; no maximum subscriber limit.
        if subscribers < MIN_SUBSCRIBERS:
            continue

        title = clean(snippet.get("title"))
        description = clean(snippet.get("description"))
        channel_id = clean(channel.get("id"))
        custom_url = clean(snippet.get("customUrl")).strip("/")

        if custom_url:
            profile_url = "https://www.youtube.com/" + custom_url
        else:
            profile_url = f"https://www.youtube.com/channel/{channel_id}"

        channel_url = f"https://www.youtube.com/channel/{channel_id}"
        email = extract_email(description)

        lead = {
            "name": title,
            "platform": "YouTube",
            "profile_url": profile_url,
            "channel_url": channel_url,
            "creator_or_business": "Creator",
            "niche": detect_niche(title + " " + description),
            "country": clean(snippet.get("country")),
            "city": "",
            "subscribers": subscribers,
            "avg_views": "",
            "business_email": email,
            "instagram": "",
            "linkedin": "",
            "twitter_x": "",
            "website": "",
            "recent_upload": get_latest_upload(channel),
            "contact_type": "Business Email" if email else "Public Profile",
            "lead_source": "YouTube Data API",
            "status": "New",
            "notes": (
                "Public YouTube channel meeting subscriber threshold. "
                "Actual monetization status is not verified by the API."
            )
        }
        leads.append(normalize_lead(lead))

        if MAX_LEADS_PER_RUN > 0 and len(leads) >= MAX_LEADS_PER_RUN:
            print(f"Reached per-run limit: {MAX_LEADS_PER_RUN}")
            break

    print(f"Qualified channels collected: {len(leads)}")
    return leads


# ================= GOOGLE SHEETS =================

def upload_to_google_sheets(leads):
    if not GOOGLE_SERVICE_ACCOUNT_JSON or not GOOGLE_SHEET_ID:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SHEET_ID is missing."
        )

    import gspread
    from google.oauth2.service_account import Credentials

    service_account_info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials = Credentials.from_service_account_info(
        service_account_info, scopes=scopes
    )
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

    worksheet = (
        spreadsheet.worksheet(GOOGLE_SHEET_NAME)
        if GOOGLE_SHEET_NAME
        else spreadsheet.sheet1
    )

    # The 20-column header occupies A:T.
    worksheet.update(range_name="A1:T1", values=[HEADERS])
    existing_values = worksheet.get_all_values()

    existing_keys = set()
    for values in existing_values[1:]:
        row = {
            header: values[i] if i < len(values) else ""
            for i, header in enumerate(HEADERS)
        }
        existing_keys.add(lead_key(row))

    rows_to_add = []
    for lead in leads:
        lead = normalize_lead(lead)
        key = lead_key(lead)
        if key in existing_keys:
            continue
        rows_to_add.append([lead[h] for h in HEADERS])
        existing_keys.add(key)

    print(f"New Google Sheets rows to add: {len(rows_to_add)}")

    if not rows_to_add:
        print("No new rows. Google Sheets is already up to date.")
        return True

    worksheet.append_rows(rows_to_add, value_input_option="USER_ENTERED")
    print(f"Uploaded {len(rows_to_add)} new leads to Google Sheets.")
    return True


# ================= MAIN =================

def main():
    print("=" * 55)
    print("LEAD AUTOMATION STARTED")
    print("=" * 55)

    if not YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY is missing.")
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is missing.")
    if not GOOGLE_SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID is missing.")

    existing_leads = read_csv()
    print(f"Existing CSV leads: {len(existing_leads)}")

    youtube_leads = collect_youtube()

    existing_keys = {lead_key(x) for x in existing_leads}
    new_csv_leads = []

    for lead in youtube_leads:
        lead = normalize_lead(lead)
        key = lead_key(lead)
        if key not in existing_keys:
            existing_keys.add(key)
            new_csv_leads.append(lead)

    all_leads = existing_leads + new_csv_leads
    save_csv(all_leads)
    print(f"New CSV leads added: {len(new_csv_leads)}")

    if not upload_to_google_sheets(youtube_leads):
        raise RuntimeError("Google Sheets upload failed.")

    print("=" * 55)
    print("LEAD AUTOMATION FINISHED")
    print("=" * 55)


if __name__ == "__main__":
    main()
