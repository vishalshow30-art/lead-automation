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
# 1. Environment Secrets & Config
# ==========================================
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
WORKSHEET_NAME = os.environ.get("GOOGLE_SHEET_WORKSHEET") or "Sheet1"
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
SEARCH_ENGINE_ID = os.environ.get("SEARCH_ENGINE_ID")

CUSTOM_QUERY = os.environ.get("YOUTUBE_SEARCH_QUERY") or os.environ.get("SEARCH_QUERY")

if not all([YOUTUBE_API_KEY, GOOGLE_SHEET_ID, SERVICE_ACCOUNT_JSON]):
    print("❌ Critical Error: Zaroori secrets (YOUTUBE_API_KEY, GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_JSON) missing hain!")
    sys.exit(1)

# ==========================================
# 2. Google Sheets Setup & Connect
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

        # Check and initialize proper professional headers
        existing_rows = worksheet.get_all_values()
        if not existing_rows:
            headers = [
                "Platform", "Lead Link / Channel ID", "Name / Title", 
                "Subscribers / Category", "Business Email", "Social Profile / Contact"
            ]
            worksheet.append_row(headers)

        return worksheet
    except Exception as e:
        print(f"❌ Google Sheets Connection Error: {e}")
        sys.exit(1)

# ==========================================
# 3. Deep Extraction Helpers (Regex Engine)
# ==========================================
def extract_deep_email(text):
    if not text:
        return "N/A"
    
    # Text normalization
    clean_text = text.replace("[at]", "@").replace("(at)", "@").replace(" at ", "@")
    clean_text = clean_text.replace("[dot]", ".").replace("(dot)", ".").replace(" dot ", ".")
    
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    matches = re.findall(email_pattern, clean_text)
    
    # Filter fake extension matches
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
# 4. Deep YouTube Collector (20k+ Minimum)
# ==========================================
def collect_youtube_deep(existing_ids):
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

    # Diverse Indian and High-Paying Tier-1 Niches
    niches = [
        # Indian Creators
        "podcast clips hindi", "tech creator india", "finance creator hindi", 
        "roast video creators india", "gaming highlights hindi", "fitness trainer india",
        # International Clients
        "podcast clips usa", "real estate investor vlog usa", "ecommerce dropshipping usa",
        "finance creator uk", "business mindset podcast canada", "fitness coach us"
    ]

    target_queries = [CUSTOM_QUERY] if CUSTOM_QUERY else niches
    new_leads = []

    for q in target_queries:
        try:
            print(f"🎥 YouTube Deep Searching: {q}")
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

            # Fetch Channel Details (Statistics + Snippet)
            chan_req = youtube.channels().list(
                part="snippet,statistics",
                id=",".join(unique_ids)
            )
            chan_res = chan_req.execute()

            for chan in chan_res.get("items", []):
                cid = chan["id"]
                stats = chan.get("statistics", {})
                subs = int(stats.get("subscriberCount", 0))

                # Criteria: 20k+ Subscribers
                if subs < 20000:
                    continue

                snippet = chan.get("snippet", {})
                title = snippet.get("title", "")
                desc = snippet.get("description", "")
                channel_url = f"https://www.youtube.com/channel/{cid}"

                email = extract_deep_email(desc)
                social = extract_social_handle(desc)

                lead_row = ["YouTube", channel_url, title, f"{subs:,} subs", email, social]
                new_leads.append(lead_row)
                existing_ids.add(channel_url)
                existing_ids.add(cid)

        except Exception as e:
            print(f"⚠️ YouTube error on query '{q}': {e}")

    return new_leads

# ==========================================
# 5. Multi-Platform Web Engine (Insta, X, LinkedIn, FB)
# ==========================================
def collect_multiplatform_web(existing_ids):
    if not SEARCH_ENGINE_ID:
        print("ℹ️ SEARCH_ENGINE_ID Secret missing. Skipping Web scraping.")
        return []

    # Laser-targeted queries across Instagram, Twitter/X, LinkedIn, Facebook
    search_queries = [
        # Instagram - Creators with explicit email in bio
        'site:instagram.com ("podcaster" OR "vlogger" OR "fitness creator") ("@gmail.com" OR "contact")',
        'site:instagram.com ("video creator" OR "reels creator") India ("@gmail.com")',
        'site:instagram.com ("content creator" OR "coach") USA ("@gmail.com" OR "@yahoo.com")',

        # Twitter / X - Clients looking for video editors right now
        'site:twitter.com ("looking for video editor" OR "need video editor" OR "hiring video editor")',
        'site:twitter.com ("need reel editor" OR "need short form editor" OR "dm for edits")',

        # LinkedIn - Founders, Creators, Agency Heads
        'site:linkedin.com/in/ ("content creator" OR "youtube creator" OR "founder") India',
        'site:linkedin.com/in/ ("creative director" OR "video producer" OR "head of marketing") USA',

        # Facebook - Creator business pages
        'site:facebook.com ("video creator" OR "digital creator") ("@gmail.com" OR "business inquiries")'
    ]

    new_leads = []
    base_url = "https://www.googleapis.com/customsearch/v1"

    for query in search_queries:
        try:
            print(f"🌐 Deep Scanning Web: {query[:60]}...")
            
            # 10 results per query (Full safe free allowance)
            params = {
                "key": YOUTUBE_API_KEY,
                "cx": SEARCH_ENGINE_ID,
                "q": query,
                "num": 10
            }
            resp = requests.get(base_url, params=params, timeout=15).json()
            items = resp.get("items", [])

            for item in items:
                link = item.get("link", "")
                if link in existing_ids:
                    continue

                title = item.get("title", "")
                snippet = item.get("snippet", "")
                full_text = f"{title} {snippet} {link}"

                # Detect Platform Accurately
                platform = "Web"
                if "instagram.com" in link:
                    platform = "Instagram"
                elif "linkedin.com" in link:
                    platform = "LinkedIn"
                elif "twitter.com" in link or "x.com" in link:
                    platform = "Twitter/X"
                elif "facebook.com" in link:
                    platform = "Facebook"

                email = extract_deep_email(full_text)
                social = extract_social_handle(full_text)
                if social == "N/A":
                    social = link

                lead_row = [platform, link, title, "High Intent Lead", email, social]
                new_leads.append(lead_row)
                existing_ids.add(link)

        except Exception as e:
            print(f"⚠️ Web search error for query '{query}': {e}")

    return new_leads

# ==========================================
# 6. Main Flow & Safe Sheet Insertion
# ==========================================
def main():
    print("=" * 50)
    print("🚀 Lead Generator Running...")
    print("=" * 50)

    print("Connecting to Google Sheets...")
    sheet = connect_google_sheet()

    # Column 2 holds Link / Channel ID for 100% duplicate protection
    existing_records = set(sheet.col_values(2))
    print(f"📊 Sheet mein pehle se maujood records: {len(existing_records)}")

    # 1. Fetch from YouTube
    print("\n🔍 Collecting YouTube Leads (20k+ Filter)...")
    yt_leads = collect_youtube_deep(existing_records)
    print(f"✅ YouTube se fresh leads mili: {len(yt_leads)}")

    # 2. Fetch from Web (Instagram, Twitter, LinkedIn, Facebook)
    print("\n🔍 Collecting Multi-Platform Web Leads...")
    web_leads = collect_multiplatform_web(existing_records)
    print(f"✅ Web (Insta/X/LinkedIn/FB) se fresh leads mili: {len(web_leads)}")

    all_leads = yt_leads + web_leads

    # 3. Write into Google Sheet
    if all_leads:
        print(f"\n📝 Google Sheet mein total {len(all_leads)} nayi leads add ho rahi hain...")
        # Chunk writing prevents Google Sheets API timeouts
        chunk_size = 50
        for i in range(0, len(all_leads), chunk_size):
            sheet.append_rows(all_leads[i:i + chunk_size])
            time.sleep(1)
        print("🎉 SUCCESS: Saari leads Google Sheet mein successfully save ho chuki hain!")
    else:
        print("\nℹ️ Is run mein koi nayi unique lead nahi mili (ya saari duplicate thi).")

if __name__ == "__main__":
    main()
