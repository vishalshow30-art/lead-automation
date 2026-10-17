import os
import sys
import json
import re
from googleapiclient.discovery import build
import gspread
from google.oauth2.service_account import Credentials

# 1. Environment Variables check
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
WORKSHEET_NAME = os.environ.get("GOOGLE_SHEET_WORKSHEET") or "Sheet1"
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
CUSTOM_QUERY = os.environ.get("YOUTUBE_SEARCH_QUERY")

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

        # Check agar headers banani hai
        existing_rows = worksheet.get_all_values()
        if not existing_rows:
            headers = [
                "Channel ID", "Channel Title", "Subscribers", 
                "Country", "Email", "Instagram", "Twitter/X", "Channel URL"
            ]
            worksheet.append_row(headers)
        
        return worksheet
    except Exception as e:
        print(f"❌ Google Sheets Connection Error: {e}")
        sys.exit(1)

# Contact info helper regex
def parse_contacts(text):
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    insta_pattern = r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/([a-zA-Z0-9_.]+)'
    x_pattern = r'(?:https?:\/\/)?(?:www\.)?(?:twitter\.com|x\.com)\/([a-zA-Z0-9_]+)'

    email = re.search(email_pattern, text)
    insta = re.search(insta_pattern, text, re.IGNORECASE)
    x_handle = re.search(x_pattern, text, re.IGNORECASE)

    return (
        email.group(0) if email else "N/A",
        insta.group(0) if insta else "N/A",
        x_handle.group(0) if x_handle else "N/A"
    )

# 3. YouTube Data Extraction
def collect_leads(existing_ids):
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    
    # Diverse Indian & International targets
    default_queries = [
        "podcast clips hindi", "tech creator india", "vlog creator usa",
        "finance creator uk", "fitness coach international", "gaming highlights india"
    ]
    
    queries = [CUSTOM_QUERY] if CUSTOM_QUERY else default_queries
    new_leads = []

    for q in queries:
        try:
            print(f"Searching niche: {q}")
            req = youtube.search().list(
                q=q,
                part="snippet",
                type="channel",
                maxResults=15
            )
            res = req.execute()

            channel_ids = [item["id"]["channelId"] for item in res.get("items", [])]
            # Pehle hi filter karlo taaki repeat call na ho
            unique_ids = [cid for cid in channel_ids if cid not in existing_ids]

            if not unique_ids:
                continue

            # Fetch detailed channel info
            chan_req = youtube.channels().list(
                part="snippet,statistics",
                id=",".join(unique_ids)
            )
            chan_res = chan_req.execute()

            for chan in chan_res.get("items", []):
                cid = chan["id"]
                snippet = chan.get("snippet", {})
                stats = chan.get("statistics", {})

                subs = int(stats.get("subscriberCount", 0))
                # 20k minimum subscribers condition
                if subs < 20000:
                    continue

                title = snippet.get("title", "")
                country = snippet.get("country", "Global")
                desc = snippet.get("description", "")
                url = f"https://www.youtube.com/channel/{cid}"

                email, insta, x_acc = parse_contacts(desc)

                lead_row = [cid, title, subs, country, email, insta, x_acc, url]
                new_leads.append(lead_row)
                existing_ids.add(cid)  # Same run me duplicate na aaye

        except Exception as err:
            print(f"⚠️ Query '{q}' me error: {err}")

    return new_leads

# 4. Main Process
def main():
    print("Connecting to Google Sheets...")
    sheet = connect_google_sheet()

    # Column 1 se saari existing Channel IDs nikal kar duplicate check karenge
    existing_channel_ids = set(sheet.col_values(1))
    print(f"Total existing leads in sheet: {len(existing_channel_ids)}")

    print("Fetching creator leads from YouTube...")
    leads = collect_leads(existing_channel_ids)

    if leads:
        print(f"Saving {len(leads)} new leads into Google Sheet...")
        sheet.append_rows(leads)
        print("✅ Data successfully saved in Google Sheet!")
    else:
        print("ℹ️ Koi nayi lead nahi mili ya criteria (<20k subs) match nahi hua.")

if __name__ == "__main__":
    main()
