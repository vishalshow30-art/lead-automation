import os
import sys
import json
import re
import requests
from googleapiclient.discovery import build
import gspread
from google.oauth2.service_account import Credentials

# 1. Environment Secrets Setup
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
WORKSHEET_NAME = os.environ.get("GOOGLE_SHEET_WORKSHEET") or "Sheet1"
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
SEARCH_ENGINE_ID = os.environ.get("SEARCH_ENGINE_ID")
CUSTOM_QUERY = os.environ.get("YOUTUBE_SEARCH_QUERY")

if not all([YOUTUBE_API_KEY, GOOGLE_SHEET_ID, SERVICE_ACCOUNT_JSON]):
    print("❌ Error: Essential secrets missing!")
    sys.exit(1)

# 2. Google Sheets Connection
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
                "Platform", "Lead ID / Profile URL", "Name / Title", 
                "Subscribers / Info", "Email", "Instagram / Social Link"
            ]
            worksheet.append_row(headers)

        return worksheet
    except Exception as e:
        print(f"❌ Google Sheets Connection Error: {e}")
        sys.exit(1)

# Regex helpers
def extract_email(text):
    match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
    return match.group(0) if match else "N/A"

def extract_socials(text):
    insta = re.search(r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/([a-zA-Z0-9_.]+)', text, re.IGNORECASE)
    x_acc = re.search(r'(?:https?:\/\/)?(?:www\.)?(?:twitter\.com|x\.com)\/([a-zA-Z0-9_]+)', text, re.IGNORECASE)
    
    if insta:
        return insta.group(0)
    elif x_acc:
        return x_acc.group(0)
    return "N/A"

# 3. YouTube Scraping (Indian + International 20k+ Filter)
def collect_youtube_leads(existing_ids):
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

    default_queries = [
        # Indian Niches
        "podcast clips hindi", "tech review india", "roast video hindi", "vlog hindi",
        # International Niches
        "podcast clips usa", "finance creator uk", "fitness coach usa", "lifestyle vlog us", "business creator canada"
    ]

    queries = [CUSTOM_QUERY] if CUSTOM_QUERY else default_queries
    new_leads = []

    for q in queries:
        try:
            print(f"Searching YouTube: {q}")
            req = youtube.search().list(
                q=q,
                part="snippet",
                type="channel",
                maxResults=15
            )
            res = req.execute()

            channel_ids = [item["id"]["channelId"] for item in res.get("items", [])]
            unique_ids = [cid for cid in channel_ids if cid not in existing_ids and f"https://www.youtube.com/channel/{cid}" not in existing_ids]

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

                # 20k minimum subscribers filter
                if subs < 20000:
                    continue

                snippet = chan.get("snippet", {})
                title = snippet.get("title", "")
                desc = snippet.get("description", "")
                channel_url = f"https://www.youtube.com/channel/{cid}"

                email = extract_email(desc)
                social = extract_socials(desc)

                lead_row = ["YouTube", channel_url, title, f"{subs} subs", email, social]
                new_leads.append(lead_row)
                existing_ids.add(channel_url)
                existing_ids.add(cid)

        except Exception as e:
            print(f"⚠️ YouTube error on query '{q}': {e}")

    return new_leads

# 4. Multi-Platform Web Search via Google API (Instagram, Facebook, LinkedIn, Twitter/X)
def collect_web_social_leads(existing_ids):
    if not SEARCH_ENGINE_ID:
        print("ℹ️ SEARCH_ENGINE_ID missing. Skipping Web.")
        return []

    # High-intent targeted queries across platforms
    search_queries = [
        # Instagram Creators with emails in bio
        'site:instagram.com ("podcast" OR "vlogger" OR "fitness creator") ("@gmail.com" OR "contact")',
        'site:instagram.com ("creator" OR "reels creator") India ("@gmail.com")',
        
        # Twitter/X Clients looking for video editors right now
        'site:twitter.com ("looking for video editor" OR "need video editor" OR "hiring video editor")',
        'site:twitter.com ("dm for edits" OR "need short form editor")',

        # LinkedIn Creators & Founders
        'site:linkedin.com/in/ ("content creator" OR "youtube creator" OR "founder") India',
        'site:linkedin.com/in/ ("video creator" OR "creative director") USA',

        # Facebook Pages / Groups for content creators
        'site:facebook.com ("video creator" OR "content creator") ("contact" OR "@gmail.com")'
    ]

    new_leads = []
    base_url = "https://www.googleapis.com/customsearch/v1"

    for query in search_queries:
        try:
            print(f"Searching Web (Google CSE): {query}")
            params = {
                "key": YOUTUBE_API_KEY,
                "cx": SEARCH_ENGINE_ID,
                "q": query,
                "num": 10  # Maximum allowed per request
            }
            resp = requests.get(base_url, params=params).json()
            items = resp.get("items", [])

            for item in items:
                link = item.get("link", "")
                if link in existing_ids:
                    continue

                title = item.get("title", "")
                snippet = item.get("snippet", "")

                # Detect Platform
                platform = "Web"
                if "instagram.com" in link:
                    platform = "Instagram"
                elif "linkedin.com" in link:
                    platform = "LinkedIn"
                elif "twitter.com" in link or "x.com" in link:
                    platform = "Twitter/X"
                elif "facebook.com" in link:
                    platform = "Facebook"

                # Extract contact email from snippet + title
                email = extract_email(snippet + " " + title)

                lead_row = [platform, link, title, "Targeted Lead", email, link]
                new_leads.append(lead_row)
                existing_ids.add(link)

        except Exception as e:
            print(f"⚠️ Web search error for query '{query}': {e}")

    return new_leads

# 5. Main Execution
def main():
    print("Connecting to Google Sheets...")
    sheet = connect_google_sheet()

    existing_records = set(sheet.col_values(2))
    print(f"Total existing records in sheet: {len(existing_records)}")

    print("Fetching creator leads from YouTube...")
    yt_leads = collect_youtube_leads(existing_records)

    print("Fetching multi-platform leads from Instagram / LinkedIn / Twitter / Facebook...")
    web_leads = collect_web_social_leads(existing_records)

    all_leads = yt_leads + web_leads

    if all_leads:
        print(f"Writing {len(all_leads)} new leads into Google Sheet...")
        sheet.append_rows(all_leads)
        print("✅ Data successfully saved in Google Sheet!")
    else:
        print("ℹ️ No new unique leads found.")

if __name__ == "__main__":
    main()
