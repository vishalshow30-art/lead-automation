import os
import sys
import json
import re
import requests
from googleapiclient.discovery import build
import gspread
from google.oauth2.service_account import Credentials

# 1. Environment Variables
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
WORKSHEET_NAME = os.environ.get("GOOGLE_SHEET_WORKSHEET") or "Sheet1"
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
SEARCH_ENGINE_ID = os.environ.get("SEARCH_ENGINE_ID")  # Free Google CSE ID

if not all([YOUTUBE_API_KEY, GOOGLE_SHEET_ID, SERVICE_ACCOUNT_JSON]):
    print("❌ Critical Error: Environment secrets missing.")
    sys.exit(1)

# 2. Google Sheets Setup
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
        except:
            worksheet = spreadsheet.sheet1

        existing_rows = worksheet.get_all_values()
        if not existing_rows:
            headers = [
                "Platform", "Lead ID / Link", "Title / Name", "Details / Subs", 
                "Email", "Social Link"
            ]
            worksheet.append_row(headers)
        
        return worksheet
    except Exception as e:
        print(f"❌ Google Sheets Connection Error: {e}")
        sys.exit(1)

# Helpers for contacts
def parse_email(text):
    match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
    return match.group(0) if match else "N/A"

def parse_socials(text):
    insta = re.search(r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/([a-zA-Z0-9_.]+)', text, re.IGNORECASE)
    x_acc = re.search(r'(?:https?:\/\/)?(?:www\.)?(?:twitter\.com|x\.com)\/([a-zA-Z0-9_]+)', text, re.IGNORECASE)
    
    social = "N/A"
    if insta:
        social = insta.group(0)
    elif x_acc:
        social = x_acc.group(0)
    return social

# 3. YouTube Leads Fetcher
def collect_youtube_leads(existing_ids):
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    queries = [
        "podcast clips hindi", "tech creator india", "vlog creator usa",
        "finance creator uk", "fitness coach international"
    ]
    
    new_leads = []
    for q in queries:
        try:
            req = youtube.search().list(q=q, part="snippet", type="channel", maxResults=10)
            res = req.execute()
            channel_ids = [item["id"]["channelId"] for item in res.get("items", [])]
            unique_ids = [cid for cid in channel_ids if cid not in existing_ids]

            if not unique_ids:
                continue

            chan_req = youtube.channels().list(part="snippet,statistics", id=",".join(unique_ids))
            chan_res = chan_req.execute()

            for chan in chan_res.get("items", []):
                cid = chan["id"]
                stats = chan.get("statistics", {})
                subs = int(stats.get("subscriberCount", 0))

                if subs < 20000:  # 20k+ filter
                    continue

                snippet = chan.get("snippet", {})
                title = snippet.get("title", "")
                desc = snippet.get("description", "")
                channel_url = f"https://www.youtube.com/channel/{cid}"

                email = parse_email(desc)
                social = parse_socials(desc)

                lead_row = ["YouTube", channel_url, title, f"{subs} subs", email, social]
                new_leads.append(lead_row)
                existing_ids.add(channel_url)

        except Exception as e:
            print(f"⚠️ YouTube Query '{q}' error: {e}")

    return new_leads

# 4. Google Free Search (Instagram, LinkedIn, Twitter) Fetcher
def collect_web_social_leads(existing_ids):
    if not SEARCH_ENGINE_ID:
        print("ℹ️ SEARCH_ENGINE_ID secret not found. Skipping Google CSE web search.")
        return []

    # Dork queries jo Instagram, LinkedIn aur Twitter par video editing clients khojti hain
    search_queries = [
        'site:instagram.com ("podcaster" OR "content creator") ("@gmail.com" OR "contact")',
        'site:linkedin.com/in/ ("YouTuber" OR "Video Creator" OR "Founder") India',
        'site:twitter.com ("looking for video editor" OR "need video editor")'
    ]

    new_leads = []
    base_url = "https://www.googleapis.com/customsearch/v1"

    for query in search_queries:
        try:
            params = {
                "key": YOUTUBE_API_KEY,  # Same Google API key works
                "cx": SEARCH_ENGINE_ID,
                "q": query,
                "num": 5
            }
            resp = requests.get(base_url, params=params).json()
            items = resp.get("items", [])

            for item in items:
                link = item.get("link", "")
                if link in existing_ids:
                    continue

                title = item.get("title", "")
                snippet = item.get("snippet", "")
                
                # Platform identify karna
                platform = "Web"
                if "instagram.com" in link:
                    platform = "Instagram"
                elif "linkedin.com" in link:
                    platform = "LinkedIn"
                elif "twitter.com" in link or "x.com" in link:
                    platform = "Twitter/X"

                email = parse_email(snippet + " " + title)

                lead_row = [platform, link, title, "Web Lead", email, link]
                new_leads.append(lead_row)
                existing_ids.add(link)

        except Exception as e:
            print(f"⚠️ Web Search Error for '{query}': {e}")

    return new_leads

# 5. Main Automation
def main():
    print("Connecting to Google Sheets...")
    sheet = connect_google_sheet()

    # Column 2 (Link/ID) check karke duplicates filter karenge
    existing_links = set(sheet.col_values(2))
    print(f"Total existing leads in sheet: {len(existing_links)}")

    print("Fetching leads from YouTube...")
    yt_leads = collect_youtube_leads(existing_links)

    print("Fetching leads from Instagram / LinkedIn / Twitter via Google CSE...")
    web_leads = collect_web_social_leads(existing_links)

    all_leads = yt_leads + web_leads

    if all_leads:
        print(f"Saving {len(all_leads)} new leads into Google Sheet...")
        sheet.append_rows(all_leads)
        print("✅ Data successfully saved in Google Sheet!")
    else:
        print("ℹ️ No new leads found matching criteria.")

if __name__ == "__main__":
    main()
