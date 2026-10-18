import os
import sys
import json
import re
import time
import urllib.parse
from datetime import datetime, timezone
import requests
from googleapiclient.discovery import build
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# 1. Config & 5-Hour Session Setup
# ==========================================
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
WORKSHEET_NAME = os.environ.get("GOOGLE_SHEET_WORKSHEET") or "Sheet1"
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
SEARCH_ENGINE_ID = os.environ.get("SEARCH_ENGINE_ID")
CUSTOM_QUERY = os.environ.get("YOUTUBE_SEARCH_QUERY") or os.environ.get("SEARCH_QUERY")

TOTAL_RUN_SECONDS = 5 * 60 * 60  
SLEEP_INTERVAL_SECONDS = 300     

if not all([YOUTUBE_API_KEY, GOOGLE_SHEET_ID, SERVICE_ACCOUNT_JSON]):
    print("❌ Critical Error: Required secrets missing!")
    sys.exit(1)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}

TARGET_COLUMNS = [
    "name", "platform", "profile_url", "channel_url", "creator_or_business",
    "niche", "country", "city", "subscribers", "avg_views",
    "business_email", "instagram", "linkedin", "twitter_x", "website",
    "recent_upload", "contact_type", "lead_source", "status", "notes"
]

# Dynamic broader search pools to prevent hitting same results
INSTA_KEYWORD_POOL = [
    "video creator india gmail.com", "content creator contact gmail.com",
    "filmmaker delhi email", "vlogger mumbai business",
    "tech creator bangalore collaboration", "fitness coach india email",
    "digital creator jaipur contact", "youtuber kolkata business",
    "podcast host india email", "influencer hyderabad collab"
]

YOUTUBE_KEYWORD_POOL = [
    "tech unboxing hindi", "podcast clips india", "finance tips hindi",
    "fitness trainer hindi", "vlog channel india", "gaming creator hindi",
    "startup founder india", "digital marketing hindi", "movie review hindi",
    "education channel india"
]

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
            worksheet.append_row(TARGET_COLUMNS)
        else:
            first_row = [str(x).strip().lower() for x in existing_rows[0]]
            if not first_row or first_row[0] != "name":
                worksheet.insert_row(TARGET_COLUMNS, 1)

        return worksheet
    except Exception as e:
        print(f"❌ Google Sheets Connection Error: {e}")
        sys.exit(1)

# ==========================================
# 3. Extraction Regex Helpers
# ==========================================
def extract_email(text):
    if not text:
        return ""
    clean = text.replace("[at]", "@").replace("(at)", "@").replace(" at ", "@")
    clean = clean.replace("[dot]", ".").replace("(dot)", ".").replace(" dot ", ".")
    pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    matches = re.findall(pattern, clean)
    valid = [m for m in matches if not m.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif'))]
    return valid[0] if valid else ""

def extract_socials_and_web(text):
    data = {"instagram": "", "linkedin": "", "twitter_x": "", "website": ""}
    if not text:
        return data

    insta = re.search(r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/([a-zA-Z0-9_.]+)', text, re.IGNORECASE)
    if insta and insta.group(1).lower() not in ["p", "reel", "stories", "explore", "tv"]:
        data["instagram"] = f"https://www.instagram.com/{insta.group(1)}"

    linkedin = re.search(r'(?:https?:\/\/)?(?:www\.)?linkedin\.com\/(?:in|company)\/([a-zA-Z0-9_-]+)', text, re.IGNORECASE)
    if linkedin:
        data["linkedin"] = f"https://www.linkedin.com/in/{linkedin.group(1)}"

    x_handle = re.search(r'(?:https?:\/\/)?(?:www\.)?(?:twitter\.com|x\.com)\/([a-zA-Z0-9_]+)', text, re.IGNORECASE)
    if x_handle and x_handle.group(1).lower() not in ["share", "intent", "home", "search"]:
        data["twitter_x"] = f"https://x.com/{x_handle.group(1)}"

    web = re.search(r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?', text)
    if web:
        url = web.group(0).rstrip('.,;)')
        ignored = ["instagram.com", "youtube.com", "youtu.be", "twitter.com", "x.com", "linkedin.com", "facebook.com", "google.com"]
        if not any(ig in url.lower() for ig in ignored):
            data["website"] = url

    return data

def detect_niche(query_str, content=""):
    combined = f"{query_str} {content}".lower()
    niches = [
        ("tech/gadgets", ["tech", "gadget", "smartphone", "laptop", "unboxing", "review", "computer", "pc"]),
        ("podcast", ["podcast", "interview", "clips", "conversation", "show"]),
        ("fitness", ["fitness", "gym", "workout", "coach", "diet", "bodybuilding", "trainer"]),
        ("finance", ["finance", "crypto", "trading", "stocks", "money", "investing", "business"]),
        ("entertainment", ["roast", "comedy", "funny", "vlog", "lifestyle", "meme", "entertainment"])
    ]
    for name, keywords in niches:
        if any(kw in combined for kw in keywords):
            return name
    return "creator"

def extract_city(text):
    if not text:
        return ""
    cities = [
        "Mumbai", "Delhi", "Bengaluru", "Bangalore", "Hyderabad", "Ahmedabad",
        "Chennai", "Kolkata", "Surat", "Pune", "Jaipur", "Lucknow", "Kanpur",
        "Nagpur", "Indore", "Thane", "Bhopal", "Visakhapatnam", "Patna", "Vadodara",
        "Ghaziabad", "Ludhiana", "Agra", "Nashik", "Faridabad", "Varanasi", "Noida", "Chandigarh"
    ]
    for city in cities:
        if re.search(rf'\b{city}\b', text, re.IGNORECASE):
            return city
    return ""

def fallback_search(query, max_results=8):
    items = []
    try:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        resp = requests.post(url, headers=HEADERS, timeout=12)
        if resp.status_code == 200:
            links = re.findall(r'<a class="result__url" href="([^"]+)"', resp.text)
            snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)<\/a>', resp.text, re.DOTALL)
            titles = re.findall(r'<h2 class="result__title">.*?<a[^>]*>(.*?)<\/a>', resp.text, re.DOTALL)

            for i in range(min(len(links), max_results)):
                raw_link = links[i].strip()
                if "uddg=" in raw_link:
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw_link).query)
                    final_link = parsed.get("uddg", [raw_link])[0]
                else:
                    final_link = "https://" + raw_link if not raw_link.startswith("http") else raw_link

                title_clean = re.sub(r'<[^>]+>', '', titles[i]).strip() if i < len(titles) else "Lead Profile"
                snippet_clean = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ""
                items.append({"title": title_clean, "link": final_link, "snippet": snippet_clean})
    except Exception:
        pass
    return items

# ==========================================
# 4. Multi-Platform Scraper Cycle
# ==========================================
def run_scrape_batch(existing_ids, round_num):
    print(f"\n==========================================")
    print(f"🔄 BATCH #{round_num} IN PROGRESS...")
    print(f"==========================================")
    new_leads = []

    # 1. Dynamic Instagram Search
    import random
    selected_insta_queries = random.sample(INSTA_KEYWORD_POOL, 3)
    base_url = "https://www.googleapis.com/customsearch/v1"

    for q in selected_insta_queries:
        query_terms = f"site:instagram.com {q}"
        items = []
        if SEARCH_ENGINE_ID and YOUTUBE_API_KEY:
            try:
                params = {"key": YOUTUBE_API_KEY, "cx": SEARCH_ENGINE_ID, "q": query_terms, "num": 10}
                resp = requests.get(base_url, params=params, timeout=12).json()
                items = resp.get("items", []) if "error" not in resp else fallback_search(query_terms)
            except Exception:
                items = fallback_search(query_terms)
        else:
            items = fallback_search(query_terms)

        for item in items:
            link = item.get("link", "").strip()
            if not link or link in existing_ids:
                continue

            title = item.get("title", "")
            snippet = item.get("snippet", "")
            full_text = f"{title} {snippet} {link}"

            email = extract_email(full_text)
            socials = extract_socials_and_web(full_text)
            if not socials["instagram"] and "instagram.com" in link:
                socials["instagram"] = link

            clean_name = title.split("(@")[0].split("•")[0].split("-")[0].replace("on Instagram", "").strip()

            row = [
                clean_name or "Instagram Creator", "Instagram", link, "", "creator",
                detect_niche(q, full_text), "India", extract_city(full_text), "", "",
                email, socials["instagram"], socials["linkedin"], socials["twitter_x"], socials["website"],
                datetime.now(timezone.utc).strftime("%Y-%m-%d"), "public", "web", "new", "Public creator lead"
            ]
            new_leads.append(row)
            existing_ids.add(link)

    # 2. Dynamic YouTube Search
    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        yt_queries = random.sample(YOUTUBE_KEYWORD_POOL, 2)
        if CUSTOM_QUERY:
            yt_queries = [CUSTOM_QUERY]

        for q in yt_queries:
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
                snippet = chan.get("snippet", {})
                subs = int(stats.get("subscriberCount", 0))

                if subs < 5000:
                    continue

                title = snippet.get("title", "")
                custom_url = snippet.get("customUrl", "")
                desc = snippet.get("description", "")
                channel_url = f"https://www.youtube.com/channel/{cid}"
                profile_url = f"https://www.youtube.com/{custom_url}" if custom_url else channel_url

                view_count = int(stats.get("viewCount", 0))
                video_count = max(1, int(stats.get("videoCount", 1)))
                avg_views = str(view_count // video_count) if video_count > 0 else ""
                published_at = snippet.get("publishedAt", "")
                date_str = published_at[:10] if published_at else datetime.now(timezone.utc).strftime("%Y-%m-%d")

                socials = extract_socials_and_web(desc)
                email = extract_email(desc)

                row = [
                    title, "YouTube", profile_url, channel_url, "creator",
                    detect_niche(q, f"{title} {desc}"), "India", extract_city(desc),
                    str(subs), avg_views, email, socials["instagram"], socials["linkedin"],
                    socials["twitter_x"], socials["website"], date_str, "public", "youtube", "new", "Public creator lead"
                ]
                new_leads.append(row)
                existing_ids.add(channel_url)
                existing_ids.add(profile_url)
                existing_ids.add(cid)
    except Exception as e:
        print(f"⚠️ YouTube search round notice: {e}")

    return new_leads

# ==========================================
# 5. Continuous 5-Hour Runner
# ==========================================
def main():
    start_time = time.time()
    end_time = start_time + TOTAL_RUN_SECONDS

    print("=" * 60)
    print("🚀 DYNAMIC 5-HOUR ENGINE STARTED")
    print(f"⏱️ Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("⏱️ System rotating keywords to maximize fresh leads.")
    print("=" * 60)

    sheet = connect_google_sheet()
    all_values = sheet.get_all_values()
    existing_ids = set()
    for row in all_values:
        for cell in row:
            val = cell.strip()
            if val.startswith("http") or val.startswith("UC") or val.startswith("@"):
                existing_ids.add(val)

    print(f"📊 Starting with {len(existing_ids)} pre-existing leads in Google Sheet.")

    batch_count = 1
    total_leads_added = 0

    while time.time() < end_time:
        remaining_sec = int(end_time - time.time())
        rem_hrs = remaining_sec // 3600
        rem_mins = (remaining_sec % 3600) // 60
        print(f"\n⏳ Time Remaining in Session: {rem_hrs} hours, {rem_mins} minutes")

        fresh_leads = run_scrape_batch(existing_ids, batch_count)

        if fresh_leads:
            print(f"📝 Appending {len(fresh_leads)} fresh leads into Google Sheet right now...")
            chunk_size = 30
            for i in range(0, len(fresh_leads), chunk_size):
                sheet.append_rows(fresh_leads[i:i + chunk_size])
                time.sleep(1)
            total_leads_added += len(fresh_leads)
            print(f"✅ Leads added! Total saved in this session: {total_leads_added}")
        else:
            print("ℹ️ No new unique leads this batch (avoiding duplicates).")

        batch_count += 1

        if time.time() + SLEEP_INTERVAL_SECONDS >= end_time:
            break

        print(f"💤 Sleeping for {SLEEP_INTERVAL_SECONDS // 60} minutes before next fetch...")
        time.sleep(SLEEP_INTERVAL_SECONDS)

    print("\n" + "=" * 60)
    print("🎉 5 HOURS COMPLETED!")
    print(f"🏆 Total Leads Added: {total_leads_added}")
    print("🛑 System automatically shutting down now. Exiting.")
    print("=" * 60)

if __name__ == "__main__":
    main()
