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
    print("❌ Critical Error: Required secrets missing!")
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
# 3. Extraction Regex Helpers
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
# 4. PRIORITY #1: Instagram Search Engine
# ==========================================
def collect_instagram_leads(existing_ids):
    if not SEARCH_ENGINE_ID:
        print("⚠️ SEARCH_ENGINE_ID missing! Instagram search nahi chal sakta.")
        return []

    # Instagram specific simplified search terms
    insta_queries = [
        'site:instagram.com video creator gmail.com',
        'site:instagram.com podcaster contact gmail.com',
        'site:instagram.com reels creator india gmail.com',
        'site:instagram.com fitness coach gmail.com',
        'site:instagram.com content creator dm for edits'
    ]

    new_leads = []
    base_url = "https://www.googleapis.com/customsearch/v1"

    print("\n" + "=" * 40)
    print("📸 PRIORITY 1: Scanning Instagram Leads...")
    print("=" * 40)

    for query in insta_queries:
        try:
            print(f"🔍 Searching Instagram: {query}")
            params = {
                "key": YOUTUBE_API_KEY,
                "cx": SEARCH_ENGINE_ID,
                "q": query,
                "num": 10
            }
            resp = requests.get(base_url, params=params, timeout=15).json()

            if "error" in resp:
                print(f"⚠️ Google API Error on Instagram: {resp['error'].get('message')}")
                continue

            items = resp.get("items", [])
            print(f"   -> Result: {len(items)} profiles mile")

            for item in items:
                link = item.get("link", "")
                if not link or link in existing_ids:
                    continue

                title = item.get("title", "")
                snippet = item.get("snippet", "")
                full_text = f"{title} {snippet} {link}"

                email = extract_email(full_text)
                social = extract_social_handle(full_text)
                if social == "N/A":
                    social = link

                row = [title, "Instagram", link, link, "Instagram Creator", email, social]
                new_leads.append(row)
                existing_ids.add(link)

        except Exception as e:
            print(f"⚠️ Instagram search error for '{query}': {e}")

    print(f"🎯 Total Fresh Instagram Leads Extracted: {len(new_leads)}\n")
    return new_leads

# ==========================================
# 5. PRIORITY #2: Twitter, LinkedIn & Facebook
# ==========================================
def collect_other_social_leads(existing_ids):
    if not SEARCH_ENGINE_ID:
        return []

    other_queries = [
        # Twitter/X
        ('Twitter/X', 'site:twitter.com looking for video editor'),
        ('Twitter/X', 'site:twitter.com hiring video editor'),
        # LinkedIn
        ('LinkedIn', 'site:linkedin.com/in content creator india'),
        ('LinkedIn', 'site:linkedin.com/in video editor founder'),
        # Facebook
        ('Facebook', 'site:facebook.com video creator contact gmail')
    ]

    new_leads = []
    base_url = "https://www.googleapis.com/customsearch/v1"

    print("=" * 40)
    print("🌐 PRIORITY 2: Scanning Twitter, LinkedIn & Facebook...")
    print("=" * 40)

    for platform_tag, query in other_queries:
        try:
            print(f"🔍 Searching {platform_tag}: {query}")
            params = {
                "key": YOUTUBE_API_KEY,
                "cx": SEARCH_ENGINE_ID,
                "q": query,
                "num": 5
            }
            resp = requests.get(base_url, params=params, timeout=15).json()

            if "error" in resp:
                print(f"⚠️ Google API Error on {platform_tag}: {resp['error'].get('message')}")
                continue

            items = resp.get("items", [])
            print(f"   -> Result: {len(items)} leads mili")

            for item in items:
                link = item.get("link", "")
                if not link or link in existing_ids:
                    continue

                title = item.get("title", "")
                snippet = item.get("snippet", "")
                full_text = f"{title} {snippet} {link}"

                email = extract_email(full_text)
                social = extract_social_handle(full_text)
                if social == "N/A":
                    social = link

                row = [title, platform_tag, link, link, "Targeted Lead", email, social]
                new_leads.append(row)
                existing_ids.add(link)

        except Exception as e:
            print(f"⚠️ Error for '{query}': {e}")

    return new_leads

# ==========================================
# 6. PRIORITY #3: YouTube Scraper (Last)
# ==========================================
def collect_youtube_leads(existing_ids):
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

    queries = [
        "podcast clips hindi", "tech creator india", "finance creator hindi",
        "roast video creators india", "fitness coach india"
    ]
    if CUSTOM_QUERY:
        queries = [CUSTOM_QUERY]

    new_leads = []
    print("\n" + "=" * 40)
    print("🎥 PRIORITY 3: Scanning YouTube Channels...")
    print("=" * 40)

    for q in queries:
        try:
            print(f"🔍 Searching YouTube: {q}")
            req = youtube.search().list(q=q, part="snippet", type="channel", maxResults=10)
            res = req.execute()

            channel_ids = [item["id"]["channelId"] for item in res.get("items", [])]
            unique_ids = [cid for cid in channel_ids if cid not in existing_ids and f"https://www.youtube.com/channel/{cid}" not in existing_ids]

            if not unique_ids:
                continue

            chan_req = youtube.channels().list(part="snippet,statistics", id=",".join(unique_ids))
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
            print(f"⚠️ YouTube error on '{q}': {e}")

    return new_leads

# ==========================================
# 7. Main Orchestration Flow
# ==========================================
def main():
    print("=" * 50)
    print("🚀 Lead Automation Engine Started")
    print("=" * 50)

    print("Connecting to Google Sheets...")
    sheet = connect_google_sheet()

    all_values = sheet.get_all_values()
    existing_ids = set()
    for row in all_values:
        for cell in row:
            val = cell.strip()
            if val.startswith("http") or val.startswith("UC"):
                existing_ids.add(val)

    print(f"📊 Sheet mein pehle se maujood links/IDs: {len(existing_ids)}")

    # 1. Instagram FIRST
    insta_leads = collect_instagram_leads(existing_ids)

    # 2. Other Social Media (Twitter, LinkedIn, FB)
    social_leads = collect_other_social_leads(existing_ids)

    # 3. YouTube LAST
    yt_leads = collect_youtube_leads(existing_ids)

    # Merge in exact priority order
    all_leads = insta_leads + social_leads + yt_leads

    if all_leads:
        print(f"\n📝 Writing {len(all_leads)} leads into Google Sheet...")
        chunk_size = 50
        for i in range(0, len(all_leads), chunk_size):
            sheet.append_rows(all_leads[i:i + chunk_size])
            time.sleep(1)
        print("🎉 SUCCESS: Data successfully saved in Google Sheet!")
    else:
        print("\nℹ️ Zero new leads to write.")

if __name__ == "__main__":
    main()
