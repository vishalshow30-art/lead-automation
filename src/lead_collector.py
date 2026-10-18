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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

TARGET_COLUMNS = [
    "name", "platform", "profile_url", "channel_url", "creator_or_business",
    "niche", "country", "city", "subscribers", "avg_views",
    "business_email", "instagram", "linkedin", "twitter_x", "website",
    "recent_upload", "contact_type", "lead_source", "status", "notes"
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
                print("📋 Sheet header missing or mismatch. Adding header row...")
                worksheet.insert_row(TARGET_COLUMNS, 1)

        return worksheet
    except Exception as e:
        print(f"❌ Google Sheets Connection Error: {e}")
        sys.exit(1)

# ==========================================
# 3. Deep Extraction Regex Helpers
# ==========================================
def extract_email(text):
    if not text:
        return ""
    clean_text = text.replace("[at]", "@").replace("(at)", "@").replace(" at ", "@")
    clean_text = clean_text.replace("[dot]", ".").replace("(dot)", ".").replace(" dot ", ".")
    pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    matches = re.findall(pattern, clean_text)
    invalid_exts = ('.png', '.jpg', '.jpeg', '.webp', '.svg', '.gif')
    valid = [m for m in matches if not m.lower().endswith(invalid_exts)]
    return valid[0] if valid else ""

def extract_socials_and_web(text):
    data = {
        "instagram": "",
        "linkedin": "",
        "twitter_x": "",
        "website": ""
    }
    if not text:
        return data

    # Instagram
    insta = re.search(r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/([a-zA-Z0-9_.]+)', text, re.IGNORECASE)
    if insta and insta.group(1).lower() not in ["p", "reel", "stories", "explore"]:
        data["instagram"] = f"https://www.instagram.com/{insta.group(1)}"

    # LinkedIn
    linkedin = re.search(r'(?:https?:\/\/)?(?:www\.)?linkedin\.com\/(?:in|company)\/([a-zA-Z0-9_-]+)', text, re.IGNORECASE)
    if linkedin:
        data["linkedin"] = f"https://www.linkedin.com/in/{linkedin.group(1)}"

    # Twitter / X
    x_handle = re.search(r'(?:https?:\/\/)?(?:www\.)?(?:twitter\.com|x\.com)\/([a-zA-Z0-9_]+)', text, re.IGNORECASE)
    if x_handle and x_handle.group(1).lower() not in ["share", "intent", "home", "search"]:
        data["twitter_x"] = f"https://x.com/{x_handle.group(1)}"

    # External Website / Linktree
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
        ("tech/gadgets", ["tech", "gadget", "smartphone", "laptop", "unboxing", "review"]),
        ("tech/computer", ["computer", "pc build", "windows", "coding", "software"]),
        ("podcast", ["podcast", "interview", "clips", "conversation"]),
        ("fitness", ["fitness", "gym", "workout", "coach", "bodybuilding", "diet"]),
        ("finance", ["finance", "crypto", "trading", "stocks", "money", "investing"]),
        ("entertainment/comedy", ["roast", "comedy", "funny", "vlog", "lifestyle", "meme"])
    ]
    for name, keywords in niches:
        if any(kw in combined for kw in keywords):
            return name
    return "content/creator"

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

# ==========================================
# 4. Fallback DuckDuckGo Search Engine
# ==========================================
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

                items.append({
                    "title": title_clean,
                    "link": final_link,
                    "snippet": snippet_clean
                })
    except Exception as e:
        print(f"   ℹ️ Fallback search notice: {e}")
    return items

# ==========================================
# 5. PRIORITY #1: Instagram Lead Hunter
# ==========================================
def collect_instagram_leads(existing_ids):
    queries = [
        'site:instagram.com "video creator" "gmail.com"',
        'site:instagram.com "podcaster" "contact" "gmail.com"',
        'site:instagram.com "tech creator" india "gmail.com"',
        'site:instagram.com "reels creator" india "gmail.com"',
        'site:instagram.com "fitness coach" "gmail.com"'
    ]

    new_leads = []
    base_url = "https://www.googleapis.com/customsearch/v1"
    print("\n" + "=" * 40)
    print("📸 PRIORITY 1: Scanning Instagram Leads...")
    print("=" * 40)

    for q in queries:
        items = []
        if SEARCH_ENGINE_ID and YOUTUBE_API_KEY:
            try:
                print(f"🔍 Searching Instagram: {q}")
                params = {"key": YOUTUBE_API_KEY, "cx": SEARCH_ENGINE_ID, "q": q, "num": 10}
                resp = requests.get(base_url, params=params, timeout=12).json()
                if "error" in resp:
                    items = fallback_search(q)
                else:
                    items = resp.get("items", [])
            except Exception:
                items = fallback_search(q)
        else:
            items = fallback_search(q)

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
            niche = detect_niche(q, full_text)
            city = extract_city(full_text)

            row = [
                clean_name or "Instagram Creator",
                "Instagram",
                link,
                "",
                "creator",
                niche,
                "India" if "india" in full_text.lower() else "India",
                city,
                "",
                "",
                email,
                socials["instagram"],
                socials["linkedin"],
                socials["twitter_x"],
                socials["website"],
                datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "public",
                "web",
                "new",
                "Public creator lead"
            ]
            new_leads.append(row)
            existing_ids.add(link)

        time.sleep(1)

    print(f"🎯 Total Fresh Instagram Leads: {len(new_leads)}\n")
    return new_leads

# ==========================================
# 6. PRIORITY #2: Twitter, LinkedIn & Web
# ==========================================
def collect_other_social_leads(existing_ids):
    queries = [
        ('Twitter/X', 'site:twitter.com "looking for video editor" "gmail.com"'),
        ('LinkedIn', 'site:linkedin.com/in "content creator" india "gmail.com"'),
        ('LinkedIn', 'site:linkedin.com/in "video editor founder" india')
    ]

    new_leads = []
    base_url = "https://www.googleapis.com/customsearch/v1"
    print("=" * 40)
    print("🌐 PRIORITY 2: Scanning Twitter & LinkedIn...")
    print("=" * 40)

    for platform_tag, q in queries:
        items = []
        if SEARCH_ENGINE_ID and YOUTUBE_API_KEY:
            try:
                print(f"🔍 Searching {platform_tag}: {q}")
                params = {"key": YOUTUBE_API_KEY, "cx": SEARCH_ENGINE_ID, "q": q, "num": 5}
                resp = requests.get(base_url, params=params, timeout=12).json()
                if "error" in resp:
                    items = fallback_search(q)
                else:
                    items = resp.get("items", [])
            except Exception:
                items = fallback_search(q)
        else:
            items = fallback_search(q)

        for item in items:
            link = item.get("link", "").strip()
            if not link or link in existing_ids:
                continue

            title = item.get("title", "")
            snippet = item.get("snippet", "")
            full_text = f"{title} {snippet} {link}"

            email = extract_email(full_text)
            socials = extract_socials_and_web(full_text)
            if platform_tag == "Twitter/X" and not socials["twitter_x"]:
                socials["twitter_x"] = link
            elif platform_tag == "LinkedIn" and not socials["linkedin"]:
                socials["linkedin"] = link

            clean_name = title.split("-")[0].split("|")[0].split("on")[0].strip()
            city = extract_city(full_text)

            row = [
                clean_name or f"{platform_tag} Lead",
                platform_tag,
                link,
                "",
                "business" if "looking" in full_text.lower() or "hiring" in full_text.lower() else "creator",
                detect_niche(q, full_text),
                "India" if "india" in full_text.lower() else "India",
                city,
                "",
                "",
                email,
                socials["instagram"],
                socials["linkedin"],
                socials["twitter_x"],
                socials["website"],
                datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "public",
                "web",
                "new",
                "Public creator lead"
            ]
            new_leads.append(row)
            existing_ids.add(link)

        time.sleep(1)

    return new_leads

# ==========================================
# 7. PRIORITY #3: Deep YouTube Channel Miner
# ==========================================
def collect_youtube_leads(existing_ids):
    new_leads = []
    try:
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    except Exception as e:
        print(f"⚠️ YouTube client error: {e}")
        return []

    queries = [
        "tech review hindi", "computer unboxing hindi", "podcast clips hindi",
        "fitness trainer india", "finance creator hindi"
    ]
    if CUSTOM_QUERY:
        queries = [CUSTOM_QUERY]

    print("\n" + "=" * 40)
    print("🎥 PRIORITY 3: Deep Scanning YouTube Channels...")
    print("=" * 40)

    for q in queries:
        try:
            print(f"🔍 Searching YouTube: {q}")
            req = youtube.search().list(q=q, part="snippet", type="channel", maxResults=15)
            res = req.execute()

            channel_ids = [item["id"]["channelId"] for item in res.get("items", []) if "channelId" in item.get("id", {})]
            unique_ids = [cid for cid in channel_ids if cid not in existing_ids and f"https://www.youtube.com/channel/{cid}" not in existing_ids]

            if not unique_ids:
                continue

            # Fetch channel snippet, statistics, and branding settings
            chan_req = youtube.channels().list(
                part="snippet,statistics,contentDetails,brandingSettings",
                id=",".join(unique_ids)
            )
            chan_res = chan_req.execute()

            for chan in chan_res.get("items", []):
                cid = chan["id"]
                stats = chan.get("statistics", {})
                snippet = chan.get("snippet", {})
                branding = chan.get("brandingSettings", {}).get("channel", {})

                subs = int(stats.get("subscriberCount", 0))
                if subs < 8000:
                    continue

                title = snippet.get("title", "")
                custom_url = snippet.get("customUrl", "")
                desc = snippet.get("description", "") + " " + branding.get("description", "")
                country = snippet.get("country", "India")
                if country == "IN":
                    country = "India"

                # URLs
                channel_url = f"https://www.youtube.com/channel/{cid}"
                profile_url = f"https://www.youtube.com/{custom_url}" if custom_url else channel_url

                # Contact Extractions
                email = extract_email(desc)
                socials = extract_socials_and_web(desc)
                city = extract_city(desc)

                # Views & Upload Calculation
                view_count = int(stats.get("viewCount", 0))
                video_count = max(1, int(stats.get("videoCount", 1)))
                avg_views = str(view_count // video_count) if video_count > 0 else ""

                # Recent Upload date
                published_at = snippet.get("publishedAt", "")
                date_str = published_at[:10] if published_at else datetime.now(timezone.utc).strftime("%Y-%m-%d")

                row = [
                    title,
                    "YouTube",
                    profile_url,
                    channel_url,
                    "creator",
                    detect_niche(q, f"{title} {desc}"),
                    country,
                    city,
                    str(subs),
                    avg_views,
                    email,
                    socials["instagram"],
                    socials["linkedin"],
                    socials["twitter_x"],
                    socials["website"],
                    date_str,
                    "public",
                    "youtube",
                    "new",
                    "Public creator lead"
                ]

                new_leads.append(row)
                existing_ids.add(channel_url)
                existing_ids.add(profile_url)
                existing_ids.add(cid)

        except Exception as e:
            print(f"⚠️ YouTube error on '{q}': {e}")

    return new_leads

# ==========================================
# 8. Main Orchestration Flow
# ==========================================
def main():
    print("=" * 50)
    print("🚀 Lead Automation Engine Started (Optimized Format)")
    print("=" * 50)

    print("Connecting to Google Sheets...")
    sheet = connect_google_sheet()

    all_values = sheet.get_all_values()
    existing_ids = set()
    for row in all_values:
        for cell in row:
            val = cell.strip()
            if val.startswith("http") or val.startswith("UC") or val.startswith("@"):
                existing_ids.add(val)

    print(f"📊 Sheet mein pehle se maujood links/IDs: {len(existing_ids)}")

    insta_leads = collect_instagram_leads(existing_ids)
    social_leads = collect_other_social_leads(existing_ids)
    yt_leads = collect_youtube_leads(existing_ids)

    all_leads = insta_leads + social_leads + yt_leads

    if all_leads:
        print(f"\n📝 Writing {len(all_leads)} formatted leads into Google Sheet...")
        chunk_size = 50
        for i in range(0, len(all_leads), chunk_size):
            sheet.append_rows(all_leads[i:i + chunk_size])
            time.sleep(1)
        print("🎉 SUCCESS: Leads successfully saved in exact matching schema!")
    else:
        print("\nℹ️ Zero new leads to write (all discovered links already exist in sheet).")

if __name__ == "__main__":
    main()
