import os
import sys
import json
import re
from googleapiclient.discovery import build
import gspread
from google.oauth2.service_account import Credentials

# Environment Variables
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
WORKSHEET_NAME = os.environ.get("GOOGLE_SHEET_WORKSHEET", "Sheet1")
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

if not all([YOUTUBE_API_KEY, GOOGLE_SHEET_ID, SERVICE_ACCOUNT_JSON]):
    print("❌ Error: Missing required environment variables!")
    sys.exit(1)

def get_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds_dict = json.loads(SERVICE_ACCOUNT_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(GOOGLE_SHEET_ID)
    try:
        worksheet = sh.worksheet(WORKSHEET_NAME)
    except:
        worksheet = sh.sheet1
    
    headers = [
        "Channel ID", "Channel Name", "Subscribers", 
        "Email", "Instagram", "Twitter/X", "Channel URL"
    ]
    existing = worksheet.get_all_values()
    if not existing:
        worksheet.append_row(headers)
    return worksheet

def extract_contact_info(text):
    email_match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
    email = email_match.group(0) if email_match else "N/A"
    
    insta_match = re.search(r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/([a-zA-Z0-9_.]+)', text, re.IGNORECASE)
    instagram = insta_match.group(0) if insta_match else "N/A"
    
    twitter_match = re.search(r'(?:https?:\/\/)?(?:www\.)?(?:twitter\.com|x\.com)\/([a-zA-Z0-9_]+)', text, re.IGNORECASE)
    twitter = twitter_match.group(0) if twitter_match else "N/A"
    
    return email, instagram, twitter

def fetch_creators(existing_ids):
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    
    # Mix of Indian and International niches
    queries = [
        "vlog hindi", "tech unboxing india", "gaming live hindi",
        "finance creator usa", "lifestyle vlog uk", "fitness coach us"
    ]
    
    new_leads = []

    for query in queries:
        try:
            req = youtube.search().list(
                q=query,
                part="snippet",
                type="channel",
                maxResults=10
            )
            res = req.execute()

            channel_ids = [item["id"]["channelId"] for item in res.get("items", [])]
            channel_ids = [cid for cid in channel_ids if cid not in existing_ids]

            if not channel_ids:
                continue

            chan_req = youtube.channels().list(
                part="snippet,statistics",
                id=",".join(channel_ids)
            )
            chan_res = chan_req.execute()

            for chan in chan_res.get("items", []):
                cid = chan["id"]
                snippet = chan.get("snippet", {})
                stats = chan.get("statistics", {})

                subs = int(stats.get("subscriberCount", 0))
                if subs < 20000:  # 20k minimum limit
                    continue

                desc = snippet.get("description", "")
                title = snippet.get("title", "")
                email, insta, twitter = extract_contact_info(desc)
                channel_url = f"https://www.youtube.com/channel/{cid}"

                lead = [cid, title, subs, email, insta, twitter, channel_url]
                new_leads.append(lead)
                existing_ids.add(cid)

        except Exception as e:
            print(f"Error fetching '{query}': {e}")

    return new_leads

def main():
    print("Setting up Google Sheet connection...")
    sheet = get_sheet()
    
    existing_records = sheet.col_values(1)
    existing_ids = set(existing_records)
    print(f"Already tracking {len(existing_ids)} channels.")

    print("Searching for new creator leads...")
    leads = fetch_creators(existing_ids)

    if leads:
        print(f"Appending {len(leads)} new creators to sheet.")
        sheet.append_rows(leads)
        print("✅ Success!")
    else:
        print("ℹ️ No new unique leads found.")

if __name__ == "__main__":
    main()
