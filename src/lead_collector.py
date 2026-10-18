import os
import sys
import json
import re
import time
import requests
from googleapiclient.discovery import build
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# 1. Environment Secrets & Config Setup
# ==========================================
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
WORKSHEET_NAME = os.environ.get("GOOGLE_SHEET_WORKSHEET") or "Sheet1"
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
SEARCH_ENGINE_ID = os.environ.get("SEARCH_ENGINE_ID")
CUSTOM_QUERY = os.environ.get("YOUTUBE_SEARCH_QUERY") or os.environ.get("SEARCH_QUERY")

if not all([YOUTUBE_API_KEY, GOOGLE_SHEET_ID, SERVICE_ACCOUNT_JSON]):
    print("❌ Critical Error: Required secrets (YOUTUBE_API_KEY, GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON) missing!")
    sys.exit(1)

# ==========================================
# 2. Google Sheets Setup & Connection
# ==========================================
def connect_google_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        creds_dict = json.loads(SERVICE_ACCOUNT_JSON)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

        try:
            worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        except Exception:
            worksheet = spreadsheet.sheet1

        existing_rows = worksheet.get_all_values()
        if not existing_rows:
            headers = [
                "Name / Title", "Platform", "Profile URL", 
                "Channel / Alternate Link", "Subscribers / Info", "Business Email", "Social Profile"
            ]
            worksheet.append_row(headers)

        return worksheet
    except Exception as e:
        print(f"❌ Google Sheets Connection Error: {e}")
        sys.exit(1)

# ==========================================
# 3. Deep Extraction Regex Utilities
# ==========================================
def extract_email(text):
    if not text:
        return "N/A"
    clean_text = text.replace("[at]", "@").replace("(at)", "@").replace(" at ", "@")
    clean_text = clean_text.replace("[dot]", ".").replace("(dot)", ".").replace(" dot ", ".")
    pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    matches = re.findall(pattern, clean_text)
    invalid_exts = ('.png', '.jpg', '.jpeg', '.webp', '.svg', '.gif')
    valid = [m for m in matches if not m.lower().endswith(invalid_exts)]
    return valid[0] if valid else "N/A"

def extract_social_handle(text):
    if not text:
        return "N/A"
    insta = re.search(r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/([a-zA-Z0-9_.]+)', text, re.IGNORECASE)
    x_handle = re.search(r'(?:https?:\/\/)?(?:www\.)?(?:twitter\.com|x\.com)\/([a-zA-Z0-9_]+)', text, re.IGNORECASE)
    linkedin = re.search(r'(?:https?:\/\/)?(?:www\.)?linkedin\.com\/(?:in|company)\/([a-zA-Z0-9_-]+)', text, re.IGNORECASE)

    if insta:
        return f"https://instagram.com/{insta.group(1)}"
    elif x_handle:
        return f"https://x.com/{x_handle.group(1)}"
    elif linkedin:
        return f"https://linkedin.com/in/{linkedin.group(1)}"
    return "N/A"

# ==========================================
# 4. YouTube Scraper (10k+ Filter)
# ==========================================
def collect_youtube_leads(existing_ids):
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

    default_queries = [
        "podcast clips hindi", "tech creator india", "finance creator hindi",
        "roast video creators india", "gaming highlights hindi", "fitness coach india",
        "podcast clips usa", "finance creator uk", "fitness coach us"
    ]

    queries = [CUSTOM_QUERY] if CUSTOM_QUERY else default_queries
    new_leads = []

    for q in queries:
        try:
            print(f"🎥 YouTube Searching: {q}")
            req = youtube.search().list(
                q=q,
                part="snippet",
                type="channel",
                maxResults=15
            )
            res = req.execute()

            channel_ids = [item["id"]["channelId"] for item in res.get("items", [])]
            unique_ids = [
                cid for cid in channel_ids 
                if cid not in existing_ids and f"https://www.youtube.com/channel/{cid}" not in existing_ids
            ]

            if not unique_ids:
                continue

            chan_req = youtube.channels().list(
                part="snippet,statistics",
                id=",".join(unique_ids)
            )
            chan_res = chan_req.execute()

            for chan in chan_res.get("items", []):
                cid = chan["id"]
                stats = chan.get("statistics", {})
                subs = int(stats.get("subscriberCount", 0))

                if subs < 10000:
                    continue

                snippet = chan.get("snippet", {})
                title = snippet.get("title", "")
                desc = snippet.get("description", "")
                channel_url = f"https://www.youtube.com/channel/{cid}"

                email = extract_email(desc)
                social = extract_social_handle(desc)

                row = [title, "YouTube", channel_url, channel_url, f"{subs:,} subs", email, social]
                new_leads.append(row)
                existing_ids.add(channel_url)
                existing_ids.add(cid)

        except Exception as e:
            print(f"⚠️ YouTube error on query '{q}': {e}")

    return new_leads

# ==========================================
# 5. Multi-Platform Web Scraper (Google CSE)
# ==========================================
def collect_web_leads(existing_ids):
    if not SEARCH_ENGINE_ID:
        print("ℹ️ SEARCH_ENGINE_ID missing. Skipping Web search.")
        return []

    # High-intent targeted queries
    search_queries = [
        # Instagram
        'site:instagram.com "video creator" "gmail.com"',
        'site:instagram.com "podcaster" "contact"',
        'site:instagram.com "reels creator" India',

        # Twitter / X Hiring Posts
        'site:twitter.com "looking for video editor"',
        'site:twitter.com "hiring video editor"',
        'site:twitter.com "need a video editor"',

        # LinkedIn Creators / Founders
        'site:linkedin.com/in/ "content creator" India',
        'site:linkedin.com/in/ "founder" "podcast"',

        # Facebook Pages
        'site:facebook.com "video creator" "gmail.com"'
    ]

    new_leads = []
    base_url = "https://www.googleapis.com/customsearch/v1"

    for query in search_queries:
        try:
            params = {
                "key": YOUTUBE_API_KEY,
                "cx": SEARCH_ENGINE_ID,
                "q": query,
                "num": 5
            }
            resp = requests.get(base_url, params=params, timeout=15).json()

            if "error" in resp:
                print(f"⚠️ Google CSE Error: {resp['error'].get('message')}")
                continue

            items = resp.get("items", [])
            print(f"🌐 Query: {query} -> Found: {len(items)}")

            for item in items:
                link = item.get("link", "")
                if link in existing_ids:
                    continue

                title = item.get("title", "")
                snippet = item.get("snippet", "")
                full_text = f"{title} {snippet} {link}"

                platform = "Web"
                if "instagram.com" in link:
                    platform = "Instagram"
                elif "linkedin.com" in link:
                    platform = "LinkedIn"
                elif "twitter.com" in link or "x.com" in link:
                    platform = "Twitter/X"
                elif "facebook.com" in link:
                    platform = "Facebook"

                email = extract_email(full_text)
                social = extract_social_handle(full_text)
                if social == "N/A":
                    social = link

                row = [title, platform, link, link, "Targeted Lead", email, social]
                new_leads.append(row)
                existing_ids.add(link)

        except Exception as e:
            print(f"⚠️ Web query error for '{query}': {e}")

    return new_leads

# ==========================================
# 6. Main Orchestrator
# ==========================================
def main():
    print("=" * 50)
    print("🚀 Lead Generator Running...")
    print("=" * 50)

    print("Connecting to Google Sheets...")
    sheet = connect_google_sheet()

    # Index all links across the entire sheet for robust deduplication
    all_values = sheet.get_all_values()
    existing_ids = set()
    for row in all_values:
        for cell in row:
            val = cell.strip()
            if val.startswith("http") or val.startswith("UC"):
                existing_ids.add(val)

    print(f"📊 Sheet mein pehle se maujood links/IDs: {len(existing_ids)}")

    print("\n🔍 Fetching YouTube Leads...")
    yt_leads = collect_youtube_leads(existing_ids)
    print(f"✅ YouTube se fresh leads mili: {len(yt_leads)}")

    print("\n🔍 Fetching Multi-Platform Web Leads (Instagram / Twitter / LinkedIn / Facebook)...")
    web_leads = collect_web_leads(existing_ids)
    print(f"✅ Web platforms se fresh leads mili: {len(web_leads)}")

    all_leads = yt_leads + web_leads

    if all_leads:
        print(f"\n📝 Writing {len(all_leads)} leads to Google Sheet...")
        chunk_size = 50
        for i in range(0, len(all_leads), chunk_size):
            sheet.append_rows(all_leads[i:i + chunk_size])
            time.sleep(1)
        print("🎉 SUCCESS: Data successfully saved in Google Sheet!")
    else:
        print("\nℹ️ Zero new leads to write (all were duplicates or empty).")

if __name__ == "__main__":
    main()import os
import sys
import json
import re
import time
import requests
from googleapiclient.discovery import build
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# 1. Environment Secrets & Config Setup
# ==========================================
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
WORKSHEET_NAME = os.environ.get("GOOGLE_SHEET_WORKSHEET") or "Sheet1"
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
SEARCH_ENGINE_ID = os.environ.get("SEARCH_ENGINE_ID")
CUSTOM_QUERY = os.environ.get("YOUTUBE_SEARCH_QUERY") or os.environ.get("SEARCH_QUERY")

if not all([YOUTUBE_API_KEY, GOOGLE_SHEET_ID, SERVICE_ACCOUNT_JSON]):
    print("❌ Critical Error: Required secrets (YOUTUBE_API_KEY, GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON) missing!")
    sys.exit(1)

# ==========================================
# 2. Google Sheets Setup & Connection
# ==========================================
def connect_google_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        creds_dict = json.loads(SERVICE_ACCOUNT_JSON)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(GOOGLE_SHEET_ID)

        try:
            worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        except Exception:
            worksheet = spreadsheet.sheet1

        existing_rows = worksheet.get_all_values()
        if not existing_rows:
            headers = [
                "Name / Title", "Platform", "Profile URL", 
                "Channel / Alternate Link", "Subscribers / Info", "Business Email", "Social Profile"
            ]
            worksheet.append_row(headers)

        return worksheet
    except Exception as e:
        print(f"❌ Google Sheets Connection Error: {e}")
        sys.exit(1)

# ==========================================
# 3. Deep Extraction Regex Utilities
# ==========================================
def extract_email(text):
    if not text:
        return "N/A"
    clean_text = text.replace("[at]", "@").replace("(at)", "@").replace(" at ", "@")
    clean_text = clean_text.replace("[dot]", ".").replace("(dot)", ".").replace(" dot ", ".")
    pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    matches = re.findall(pattern, clean_text)
    invalid_exts = ('.png', '.jpg', '.jpeg', '.webp', '.svg', '.gif')
    valid = [m for m in matches if not m.lower().endswith(invalid_exts)]
    return valid[0] if valid else "N/A"

def extract_social_handle(text):
    if not text:
        return "N/A"
    insta = re.search(r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/([a-zA-Z0-9_.]+)', text, re.IGNORECASE)
    x_handle = re.search(r'(?:https?:\/\/)?(?:www\.)?(?:twitter\.com|x\.com)\/([a-zA-Z0-9_]+)', text, re.IGNORECASE)
    linkedin = re.search(r'(?:https?:\/\/)?(?:www\.)?linkedin\.com\/(?:in|company)\/([a-zA-Z0-9_-]+)', text, re.IGNORECASE)

    if insta:
        return f"https://instagram.com/{insta.group(1)}"
    elif x_handle:
        return f"https://x.com/{x_handle.group(1)}"
    elif linkedin:
        return f"https://linkedin.com/in/{linkedin.group(1)}"
    return "N/A"

# ==========================================
# 4. YouTube Scraper (10k+ Filter)
# ==========================================
def collect_youtube_leads(existing_ids):
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

    default_queries = [
        "podcast clips hindi", "tech creator india", "finance creator hindi",
        "roast video creators india", "gaming highlights hindi", "fitness coach india",
        "podcast clips usa", "finance creator uk", "fitness coach us"
    ]

    queries = [CUSTOM_QUERY] if CUSTOM_QUERY else default_queries
    new_leads = []

    for q in queries:
        try:
            print(f"🎥 YouTube Searching: {q}")
            req = youtube.search().list(
                q=q,
                part="snippet",
                type="channel",
                maxResults=15
            )
            res = req.execute()

            channel_ids = [item["id"]["channelId"] for item in res.get("items", [])]
            unique_ids = [
                cid for cid in channel_ids 
                if cid not in existing_ids and f"https://www.youtube.com/channel/{cid}" not in existing_ids
            ]

            if not unique_ids:
                continue

            chan_req = youtube.channels().list(
                part="snippet,statistics",
                id=",".join(unique_ids)
            )
            chan_res = chan_req.execute()

            for chan in chan_res.get("items", []):
                cid = chan["id"]
                stats = chan.get("statistics", {})
                subs = int(stats.get("subscriberCount", 0))

                if subs < 10000:
                    continue

                snippet = chan.get("snippet", {})
                title = snippet.get("title", "")
                desc = snippet.get("description", "")
                channel_url = f"https://www.youtube.com/channel/{cid}"

                email = extract_email(desc)
                social = extract_social_handle(desc)

                row = [title, "YouTube", channel_url, channel_url, f"{subs:,} subs", email, social]
                new_leads.append(row)
                existing_ids.add(channel_url)
                existing_ids.add(cid)

        except Exception as e:
            print(f"⚠️ YouTube error on query '{q}': {e}")

    return new_leads

# ==========================================
# 5. Multi-Platform Web Scraper (Google CSE)
# ==========================================
def collect_web_leads(existing_ids):
    if not SEARCH_ENGINE_ID:
        print("ℹ️ SEARCH_ENGINE_ID missing. Skipping Web search.")
        return []

    # High-intent targeted queries
    search_queries = [
        # Instagram
        'site:instagram.com "video creator" "gmail.com"',
        'site:instagram.com "podcaster" "contact"',
        'site:instagram.com "reels creator" India',

        # Twitter / X Hiring Posts
        'site:twitter.com "looking for video editor"',
        'site:twitter.com "hiring video editor"',
        'site:twitter.com "need a video editor"',

        # LinkedIn Creators / Founders
        'site:linkedin.com/in/ "content creator" India',
        'site:linkedin.com/in/ "founder" "podcast"',

        # Facebook Pages
        'site:facebook.com "video creator" "gmail.com"'
    ]

    new_leads = []
    base_url = "https://www.googleapis.com/customsearch/v1"

    for query in search_queries:
        try:
            params = {
                "key": YOUTUBE_API_KEY,
                "cx": SEARCH_ENGINE_ID,
                "q": query,
                "num": 5
            }
            resp = requests.get(base_url, params=params, timeout=15).json()

            if "error" in resp:
                print(f"⚠️ Google CSE Error: {resp['error'].get('message')}")
                continue

            items = resp.get("items", [])
            print(f"🌐 Query: {query} -> Found: {len(items)}")

            for item in items:
                link = item.get("link", "")
                if link in existing_ids:
                    continue

                title = item.get("title", "")
                snippet = item.get("snippet", "")
                full_text = f"{title} {snippet} {link}"

                platform = "Web"
                if "instagram.com" in link:
                    platform = "Instagram"
                elif "linkedin.com" in link:
                    platform = "LinkedIn"
                elif "twitter.com" in link or "x.com" in link:
                    platform = "Twitter/X"
                elif "facebook.com" in link:
                    platform = "Facebook"

                email = extract_email(full_text)
                social = extract_social_handle(full_text)
                if social == "N/A":
                    social = link

                row = [title, platform, link, link, "Targeted Lead", email, social]
                new_leads.append(row)
                existing_ids.add(link)

        except Exception as e:
            print(f"⚠️ Web query error for '{query}': {e}")

    return new_leads

# ==========================================
# 6. Main Orchestrator
# ==========================================
def main():
    print("=" * 50)
    print("🚀 Lead Generator Running...")
    print("=" * 50)

    print("Connecting to Google Sheets...")
    sheet = connect_google_sheet()

    # Index all links across the entire sheet for robust deduplication
    all_values = sheet.get_all_values()
    existing_ids = set()
    for row in all_values:
        for cell in row:
            val = cell.strip()
            if val.startswith("http") or val.startswith("UC"):
                existing_ids.add(val)

    print(f"📊 Sheet mein pehle se maujood links/IDs: {len(existing_ids)}")

    print("\n🔍 Fetching YouTube Leads...")
    yt_leads = collect_youtube_leads(existing_ids)
    print(f"✅ YouTube se fresh leads mili: {len(yt_leads)}")

    print("\n🔍 Fetching Multi-Platform Web Leads (Instagram / Twitter / LinkedIn / Facebook)...")
    web_leads = collect_web_leads(existing_ids)
    print(f"✅ Web platforms se fresh leads mili: {len(web_leads)}")

    all_leads = yt_leads + web_leads

    if all_leads:
        print(f"\n📝 Writing {len(all_leads)} leads to Google Sheet...")
        chunk_size = 50
        for i in range(0, len(all_leads), chunk_size):
            sheet.append_rows(all_leads[i:i + chunk_size])
            time.sleep(1)
        print("🎉 SUCCESS: Data successfully saved in Google Sheet!")
    else:
        print("\nℹ️ Zero new leads to write (all were duplicates or empty).")

if __name__ == "__main__":
    main()
