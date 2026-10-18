import os
import sys
import json
import re
import time
import urllib.parse
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

# Standard User-Agent for resilient fallback requests
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

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
# 4. Fallback Search Engine (DuckDuckGo HTML)
# ==========================================
def fallback_search(query, max_results=8):
    """Fallback searcher when Google Custom Search API is restricted or quota exceeded"""
    items = []
    try:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        resp = requests.post(url, headers=HEADERS, timeout=12)
        if resp.status_code == 200:
            # Extract links and snippets from HTML
            links = re.findall(r'<a class="result__url" href="([^"]+)"', resp.text)
            snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)<\/a>', resp.text, re.DOTALL)
            titles = re.findall(r'<h2 class="result__title">.*?<a[^>]*>(.*?)<\/a>', resp.text, re.DOTALL)

            for i in range(min(len(links), max_results)):
                raw_link = links[i].strip()
                # DuckDuckGo sometimes wraps links via /l/?kh=-1&uddg=...
                if "uddg=" in raw_link:
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_link).query)
                    final_link = parsed.get("uddg", [raw_link])[0]
                else:
                    final_link = "https://" + raw_link if not raw_link.startswith("http") else raw_link
                
                title_clean = re.sub(r'<[^>]+>', '', titles[i]).strip() if i < len(titles) else "Lead Profile"
                snippet_clean = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ""

                items.append({
                    "title": title_clean,
                    "link": final_link,
                    "snippet": snippet_clean
                })
    except Exception as e:
        print(f"   ℹ️ Fallback engine warning: {e}")
    return items

# ==========================================
# 5. PRIORITY #1: Instagram Search Engine
# ==========================================
def collect_instagram_leads(existing_ids):
    insta_queries = [
        'site:instagram.com "video creator" "gmail.com"',
        'site:instagram.com "podcaster" "contact" "gmail.com"',
        'site:instagram.com "reels creator" india "gmail.com"',
        'site:instagram.com "fitness coach" "gmail.com"',
        'site:instagram.com "content creator" "dm for edits"'
    ]

    new_leads = []
    base_url = "https://www.googleapis.com/customsearch/v1"

    print("\n" + "=" * 40)
    print("📸 PRIORITY 1: Scanning Instagram Leads...")
    print("=" * 40)

    for query in insta_queries:
        items = []
        # Attempt via Google Custom Search API
        if SEARCH_ENGINE_ID and YOUTUBE_API_KEY:
            try:
                print(f"🔍 Searching Instagram: {query}")
                params = {
                    "key": YOUTUBE_API_KEY,
                    "cx": SEARCH_ENGINE_ID,
                    "q": query,
                    "num": 10
                }
                resp = requests.get(base_url, params=params, timeout=12).json()
                if "error" in resp:
                    print(f"⚠️ Google API Notice: {resp['error'].get('message')}. Using Fallback Search Engine...")
                    items = fallback_search(query)
                else:
                    items = resp.get("items", [])
            except Exception:
                items = fallback_search(query)
        else:
            items = fallback_search(query)

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

        time.sleep(1)

    print(f"🎯 Total Fresh Instagram Leads Extracted: {len(new_leads)}\n")
    return new_leads

# ==========================================
# 6. PRIORITY #2: Twitter, LinkedIn & Facebook
# ==========================================
def collect_other_social_leads(existing_ids):
    other_queries = [
        ('Twitter/X', 'site:twitter.com "looking for video editor"'),
        ('Twitter/X', 'site:twitter.com "hiring video editor"'),
        ('LinkedIn', 'site:linkedin.com/in "content creator" india'),
        ('LinkedIn', 'site:linkedin.com/in "video editor" founder'),
        ('Facebook', 'site:facebook.com "video creator" contact "gmail.com"')
    ]

    new_leads = []
    base_url = "https://www.googleapis.com/customsearch/v1"

    print("=" * 40)
    print("🌐 PRIORITY 2: Scanning Twitter, LinkedIn & Facebook...")
    print("=" * 40)

    for platform_tag, query in other_queries:
        items = []
        if SEARCH_ENGINE_ID and YOUTUBE_API_KEY:
            try:
                print(f"🔍 Searching {platform_tag}: {query}")
                params = {
                    "key": YOUTUBE_API_KEY,
                    "cx": SEARCH_ENGINE_ID,
                    "q": query,
                    "num": 5
                }
                resp = requests.get(base_url, params=params, timeout=12).json()
                if "error" in resp:
                    print(f"⚠️ Google API Notice: {resp['error'].get('message')}. Using Fallback Engine...")
                    items = fallback_search(query)
                else:
                    items = resp.get("items", [])
            except Exception:
                items = fallback_search(query)
        else:
            items = fallback_search(query)

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

        time.sleep(1)

    return new_leads

# ==========================================
# 7. PRIORITY #3: YouTube Scraper (Last)
# ==========================================
def collect_youtube_leads(existing_ids):
    new_leads = []
    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    except Exception as e:
        print(f"⚠️ YouTube client initialize nahi ho saka: {e}")
        return []

    queries = [
        "podcast clips hindi", "tech creator india", "finance creator hindi",
        "roast video creators india", "fitness coach india"
    ]
    if CUSTOM_QUERY:
        queries = [CUSTOM_QUERY]

    print("\n" + "=" * 40)
    print("🎥 PRIORITY 3: Scanning YouTube Channels...")
    print("=" * 40)

    for q in queries:
        try:
            print(f"🔍 Searching YouTube: {q}")
            req = youtube.search().list(q=q, part="snippet", type="channel", maxResults=10)
            res = req.execute()

            channel_ids = [item["id"]["channelId"] for item in res.get("items", []) if "channelId" in item.get("id", {})]
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
# 8. Main Orchestration Flow
# ==========================================
def main():
    print("=" * 50)
    print("🚀 Lead Automation Engine Started (Deep Lead Mining)")
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
        print(f"\n📝 Writing {len(all_leads)} fresh leads into Google Sheet...")
        chunk_size = 50
        for i in range(0, len(all_leads), chunk_size):
            sheet.append_rows(all_leads[i:i + chunk_size])
            time.sleep(1)
        print("🎉 SUCCESS: Data successfully saved in Google Sheet!")
    else:
        print("\nℹ️ Zero new leads to write (all found profiles were duplicates or already exist in sheet).")

if __name__ == "__main__":
    main()
