from datetime import datetime, timedelta, timezone
import json
import os
import random
import re
import sys
import time
from duckduckgo_search import DDGS
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import gspread

# ==========================================
# 1. Config & 1-Hour Production Timer
# ==========================================
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
WORKSHEET_NAME = os.environ.get("GOOGLE_SHEET_WORKSHEET") or "Sheet1"
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

# 1 Hour Production Run Timer
TOTAL_RUN_SECONDS = 3600  # Pura 1 ghanta (60 minutes) chalega
SLEEP_INTERVAL_SECONDS = 7  # Safe pacing to avoid IP rate limits

# Quality Filters for Paying & Active Channels
MIN_SUBSCRIBERS = 1000  # Monetization baseline
MIN_VIEWS = 30000  # Channel running proof
ACTIVE_DAYS_LIMIT = 90  # Pichle 90 din me upload hona zaroori hai

if not all([GOOGLE_SHEET_ID, SERVICE_ACCOUNT_JSON]):
  print(
      "❌ Critical Error: GOOGLE_SHEET_ID ya GOOGLE_SERVICE_ACCOUNT_JSON"
      " missing hai!"
  )
  sys.exit(1)

# YouTube Official Data API Client Setup
youtube_client = None
if YOUTUBE_API_KEY:
  try:
    youtube_client = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    print("✅ YouTube Data API v3 successfully connected!")
  except Exception as e:
    print(f"⚠️ YouTube API init error: {e}")

TARGET_COLUMNS = [
    "name",
    "platform",
    "profile_url",
    "channel_url",
    "creator_or_business",
    "niche",
    "country",
    "city",
    "subscribers",
    "avg_views",
    "business_email",
    "instagram",
    "linkedin",
    "twitter_x",
    "website",
    "recent_upload",
    "contact_type",
    "lead_source",
    "status",
    "notes",
]

# ==========================================
# Deep Search Query Engine (Multi-Platform)
# ==========================================
DEEP_SEARCH_POOLS = {
    "Instagram": [
        # Indian Podcasters & High Budget Creators
        (
            'site:instagram.com ("podcast host" OR "podcast show") "India"'
            ' ("@gmail.com" OR "contact")'
        ),
        (
            'site:instagram.com ("fitness coach" OR "nutritionist") ("Delhi" OR'
            ' "Mumbai" OR "Bangalore") "@gmail.com"'
        ),
        (
            'site:instagram.com ("tech creator" OR "gadget reviews") "India"'
            ' ("business" OR "@gmail.com")'
        ),
        (
            'site:instagram.com ("filmmaker" OR "director" OR "content'
            ' agency") "India" "@gmail.com"'
        ),
        # International Paying Clients (USA, UK, Canada, Australia)
        (
            'site:instagram.com ("podcast host" OR "show host") ("USA" OR "UK"'
            ' OR "Canada") ("@gmail.com" OR "inquiries")'
        ),
        (
            'site:instagram.com ("business coach" OR "agency owner" OR "real'
            ' estate") ("dm for collab" OR "@gmail.com")'
        ),
        (
            'site:instagram.com ("talking head" OR "vlogger") ("London" OR "Los'
            ' Angeles" OR "New York") "@gmail.com"'
        ),
    ],
    "LinkedIn": [
        # Indian Founders & Media Heads
        (
            'site:linkedin.com/in ("founder" OR "co-founder") "podcast" "India"'
            ' ("@gmail.com" OR "email")'
        ),
        (
            'site:linkedin.com/in ("content creator" OR "video producer")'
            ' "India" ("contact" OR "@gmail.com")'
        ),
        (
            'site:linkedin.com/in ("head of marketing" OR "growth lead")'
            ' "media" "India" ("@gmail.com" OR "email")'
        ),
        # International Clients & Live Hiring
        (
            'site:linkedin.com/in ("podcast host" OR "youtube creator")'
            ' ("United States" OR "United Kingdom") "@gmail.com"'
        ),
        (
            'site:linkedin.com ("looking for video editor" OR "hiring freelance'
            ' video editor") ("remotely" OR "budget")'
        ),
        (
            'site:linkedin.com ("hiring reel editor" OR "need youtube editor")'
            ' ("budget" OR "dm")'
        ),
    ],
    "Twitter_X": [
        # Live Hiring Leads (Immediate Work Available)
        (
            'site:x.com ("looking for a video editor" OR "need a video editor")'
            ' ("dm" OR "email" OR "portfolio")'
        ),
        (
            'site:twitter.com ("hiring video editor" OR "seeking video editor")'
            ' ("budget" OR "dm open")'
        ),
        (
            'site:x.com ("podcast editor" OR "shorts editor" OR "reel editor")'
            ' ("hiring" OR "paid gig")'
        ),
        (
            'site:twitter.com ("video editor needed" OR "editor for my'
            ' channel") ("budget" OR "dm")'
        ),
        # International Creators
        (
            'site:x.com ("youtube creator" OR "podcaster") ("business email" OR'
            ' "contact") ("USA" OR "UK") "@gmail.com"'
        ),
    ],
    "Facebook": [
        (
            'site:facebook.com ("video creator" OR "digital creator") "India"'
            ' ("contact" OR "@gmail.com")'
        ),
        (
            'site:facebook.com ("podcast show" OR "interview show") ("USA" OR'
            ' "UK") "@gmail.com"'
        ),
        (
            'site:facebook.com ("content creator" OR "media company") ("Delhi"'
            ' OR "Mumbai") "email"'
        ),
    ],
}

# YouTube High-Intent Target Queries for Paying Clients
YOUTUBE_TARGET_QUERIES = [
    "podcast India business inquiry",
    "talking head video hindi editor contact",
    "tech review channel contact email India",
    "finance creator India business email",
    "daily vloggers USA contact email",
    "crypto podcast host email inquiry USA",
    "documentary video essays business email",
    "real estate marketing video podcast USA email",
    "saas founder interview show email",
]


# ==========================================
# 2. Google Sheets Setup & Connection
# ==========================================
def connect_google_sheet():
  scopes = [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/drive",
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
  clean = (
      clean.replace("[dot]", ".").replace("(dot)", ".").replace(" dot ", ".")
  )
  pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
  matches = re.findall(pattern, clean)
  valid = [
      m
      for m in matches
      if not m.lower().endswith(
          (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif")
      )
  ]
  return valid[0] if valid else ""


def extract_socials_and_web(text):
  data = {"instagram": "", "linkedin": "", "twitter_x": "", "website": ""}
  if not text:
    return data

  insta = re.search(
      r"(?:https?:\/\/)?(?:www\.)?instagram\.com\/([a-zA-Z0-9_.]+)",
      text,
      re.IGNORECASE,
  )
  if (
      insta
      and insta.group(1).lower()
      not in ["p", "reel", "stories", "explore", "tv"]
  ):
    data["instagram"] = f"https://www.instagram.com/{insta.group(1)}"

  linkedin = re.search(
      r"(?:https?:\/\/)?(?:www\.)?linkedin\.com\/(?:in|company)\/([a-zA-Z0-9_-]+)",
      text,
      re.IGNORECASE,
  )
  if linkedin:
    data["linkedin"] = f"https://www.linkedin.com/in/{linkedin.group(1)}"

  x_handle = re.search(
      r"(?:https?:\/\/)?(?:www\.)?(?:twitter\.com|x\.com)\/([a-zA-Z0-9_]+)",
      text,
      re.IGNORECASE,
  )
  if x_handle and x_handle.group(1).lower() not in [
      "share",
      "intent",
      "home",
      "search",
  ]:
    data["twitter_x"] = f"https://x.com/{x_handle.group(1)}"

  web = re.search(r"https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?", text)
  if web:
    url = web.group(0).rstrip(".,;)")
    ignored = [
        "instagram.com",
        "youtube.com",
        "youtu.be",
        "twitter.com",
        "x.com",
        "linkedin.com",
        "facebook.com",
        "google.com",
        "duckduckgo.com",
    ]
    if not any(ig in url.lower() for ig in ignored):
      data["website"] = url

  return data


def detect_niche(query_str="", content=""):
  combined = f"{query_str} {content}".lower()
  niches = [
      (
          "tech/gadgets",
          [
              "tech",
              "gadget",
              "smartphone",
              "laptop",
              "unboxing",
              "review",
              "computer",
              "pc",
          ],
      ),
      ("podcast", ["podcast", "interview", "clips", "conversation", "show"]),
      (
          "fitness",
          [
              "fitness",
              "gym",
              "workout",
              "coach",
              "diet",
              "bodybuilding",
              "trainer",
          ],
      ),
      (
          "finance",
          [
              "finance",
              "crypto",
              "trading",
              "stocks",
              "money",
              "investing",
              "business",
          ],
      ),
      (
          "video/media",
          [
              "editor",
              "video editing",
              "filmmaker",
              "cinematographer",
              "producer",
          ],
      ),
      (
          "entertainment",
          ["roast", "comedy", "funny", "vlog", "lifestyle", "meme"],
      ),
  ]
  for name, keywords in niches:
    if any(kw in combined for kw in keywords):
      return name
  return "creator"


def extract_geo(text):
  if not text:
    return ("India", "")
  text_lower = text.lower()
  country = "India"
  if any(
      c in text_lower
      for c in [
          "usa",
          "united states",
          "california",
          "new york",
          "los angeles",
          "texas",
          "miami",
      ]
  ):
    country = "USA"
  elif any(c in text_lower for c in ["uk", "united kingdom", "london"]):
    country = "UK"
  elif "canada" in text_lower or "toronto" in text_lower:
    country = "Canada"
  elif "australia" in text_lower or "sydney" in text_lower:
    country = "Australia"

  cities = [
      "Mumbai",
      "Delhi",
      "Bengaluru",
      "Bangalore",
      "Hyderabad",
      "Ahmedabad",
      "Chennai",
      "Kolkata",
      "Pune",
      "Jaipur",
      "Lucknow",
      "Noida",
      "Chandigarh",
      "London",
      "New York",
      "Los Angeles",
      "Chicago",
      "Toronto",
      "Miami",
  ]
  detected_city = ""
  for city in cities:
    if re.search(rf"\b{city}\b", text, re.IGNORECASE):
      detected_city = city
      break
  return (country, detected_city)


def identify_platform(link):
  l = link.lower()
  if "instagram.com" in l:
    return "Instagram"
  elif "youtube.com" in l or "youtu.be" in l:
    return "YouTube"
  elif "linkedin.com" in l:
    return "LinkedIn"
  elif "twitter.com" in l or "x.com" in l:
    return "Twitter"
  elif "facebook.com" in l:
    return "Facebook"
  return "Web"


# ==========================================
# 4. Engine A: Official YouTube Data API v3
#    (With 90-Days Upload & Monetization Check)
# ==========================================
def fetch_youtube_api_leads(existing_ids):
  leads = []
  if not youtube_client:
    return leads

  query = random.choice(YOUTUBE_TARGET_QUERIES)
  print(f"🎬 [YouTube API] Searching Channels: {query}...")

  try:
    search_res = (
        youtube_client.search()
        .list(q=query, part="snippet", type="channel", maxResults=5)
        .execute()
    )

    channel_ids = [
        item["id"]["channelId"] for item in search_res.get("items", [])
    ]
    if not channel_ids:
      return leads

    channels_res = (
        youtube_client.channels()
        .list(
            id=",".join(channel_ids),
            part="snippet,statistics,contentDetails",
        )
        .execute()
    )

    cutoff_date = datetime.now(timezone.utc) - timedelta(
        days=ACTIVE_DAYS_LIMIT
    )

    for ch in channels_res.get("items", []):
      ch_id = ch.get("id")
      channel_url = f"https://www.youtube.com/channel/{ch_id}"
      if channel_url in existing_ids:
        continue

      snippet = ch.get("snippet", {})
      stats = ch.get("statistics", {})

      # --- 1. Monetization & Budget Check ---
      subs = int(stats.get("subscriberCount", 0))
      views = int(stats.get("viewCount", 0))
      if subs < MIN_SUBSCRIBERS or views < MIN_VIEWS:
        print(f"⏩ Dropped (Under Budget/Subs): {subs} subs, {views} views")
        continue

      # --- 2. Recent Upload Check (Last 90 Days) ---
      uploads_playlist_id = (
          ch.get("contentDetails", {})
          .get("relatedPlaylists", {})
          .get("uploads")
      )
      last_upload_date_str = ""

      if uploads_playlist_id:
        try:
          playlist_items = (
              youtube_client.playlistItems()
              .list(
                  playlistId=uploads_playlist_id,
                  part="snippet",
                  maxResults=1,
              )
              .execute()
          )
          items = playlist_items.get("items", [])
          if items:
            published_at = items[0]["snippet"]["publishedAt"]
            # Convert ISO string to datetime
            pub_date = datetime.fromisoformat(
                published_at.replace("Z", "+00:00")
            )
            last_upload_date_str = pub_date.strftime("%Y-%m-%d")

            if pub_date < cutoff_date:
              print(
                  f"⏩ Dropped (Inactive > 90 days): Last video on"
                  f" {last_upload_date_str}"
              )
              continue
        except Exception:
          last_upload_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

      title = snippet.get("title", "")
      description = snippet.get("description", "")
      full_text = f"{title} {description}"

      email = extract_email(full_text)
      if email and email in existing_ids:
        continue

      socials = extract_socials_and_web(description)
      country, city = extract_geo(full_text)

      row = [
          title,
          "YouTube",
          channel_url,
          channel_url,
          "creator",
          detect_niche(query, full_text),
          snippet.get("country", country),
          city,
          str(subs),
          str(views),
          email,
          socials["instagram"],
          socials["linkedin"],
          socials["twitter_x"],
          socials["website"],
          last_upload_date_str
          or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
          "public",
          "youtube_api_v3_active",
          "new",
          "Monetized Channel (Verified Upload < 90 days)",
      ]
      leads.append(row)
      existing_ids.add(channel_url)
      if email:
        existing_ids.add(email)

  except Exception as e:
    print(f"⚠️ YouTube API notice: {e}")

  return leads


# ==========================================
# 5. Engine B: Social Media Live Deep Search
# ==========================================
def fetch_social_leads(existing_ids):
  leads = []
  platform_key = random.choice(list(DEEP_SEARCH_POOLS.keys()))
  query = random.choice(DEEP_SEARCH_POOLS[platform_key])
  print(f"🔍 [Live Social] Searching [{platform_key}] -> {query[:55]}...")

  try:
    with DDGS() as ddgs:
      results = list(ddgs.text(query, max_results=8))
      for r in results:
        link = r.get("href", "").strip()
        if not link or link in existing_ids:
          continue

        title = r.get("title", "")
        snippet = r.get("body", "")
        full_text = f"{title} {snippet} {link}"

        email = extract_email(full_text)
        if email and email in existing_ids:
          continue

        socials = extract_socials_and_web(full_text)
        country, city = extract_geo(full_text)
        detected_platform = identify_platform(link)

        if detected_platform == "Instagram" and not socials["instagram"]:
          socials["instagram"] = link
        elif detected_platform == "LinkedIn" and not socials["linkedin"]:
          socials["linkedin"] = link
        elif detected_platform == "Twitter" and not socials["twitter_x"]:
          socials["twitter_x"] = link

        clean_name = (
            title.split("(@")[0]
            .split("•")[0]
            .split("-")[0]
            .split("|")[0]
            .strip()
        )
        for suffix in [
            "on Instagram",
            "on X",
            "LinkedIn",
            "YouTube",
            "Facebook",
            "...",
        ]:
          clean_name = clean_name.replace(suffix, "").strip()

        row = [
            clean_name or f"{detected_platform} Lead",
            detected_platform,
            link,
            link if detected_platform == "YouTube" else "",
            "creator",
            detect_niche(query, full_text),
            country,
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
            "live_web_deep",
            "new",
            f"Active {detected_platform} Outreach Target",
        ]
        leads.append(row)
        existing_ids.add(link)
        if email:
          existing_ids.add(email)

  except Exception as e:
    print(f"⚠️ Live Social Search notice: {e}")

  return leads


# ==========================================
# 6. Main 1-Hour Execution Loop
# ==========================================
def main():
  start_time = time.time()
  end_time = start_time + TOTAL_RUN_SECONDS

  print("=" * 65)
  print("🚀 1-HOUR HIGH-INTENT LEAD GENERATION SYSTEM INITIATED")
  print(f"⏱️ Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
  print(f"⏱️ Total Runtime: {TOTAL_RUN_SECONDS // 60} Minutes (Full Run)")
  print("🎯 Targets: Active Monetized YouTube Creators + Global Social Media")
  print("=" * 65)

  sheet = connect_google_sheet()
  all_values = sheet.get_all_values()
  existing_ids = set()

  for row in all_values:
    for cell in row:
      val = cell.strip()
      if val.startswith("http") or val.startswith("UC") or "@" in val:
        existing_ids.add(val)

  print(
      f"📊 Sheet has {len(existing_ids)} pre-existing unique markers (URLs &"
      " Emails)."
  )

  batch_count = 1
  total_leads_added = 0

  while time.time() < end_time:
    rem_sec = max(0, int(end_time - time.time()))
    print(
        f"\n⏳ Batch #{batch_count} | Remaining Time: {rem_sec // 60}m"
        f" {rem_sec % 60}s"
    )

    # 1. YouTube Official API Leads (Filtered: Active <90d + >1k subs)
    yt_leads = fetch_youtube_api_leads(existing_ids)
    # 2. Live Social Media Deep Leads (Twitter hiring, Insta, LinkedIn)
    social_leads = fetch_social_leads(existing_ids)

    batch_leads = yt_leads + social_leads

    if batch_leads:
      print(
          f"📝 Appending {len(batch_leads)} verified active leads into Google"
          " Sheet..."
      )
      sheet.append_rows(batch_leads)
      total_leads_added += len(batch_leads)
      print(f"✅ Saved! Total leads added so far: {total_leads_added}")
    else:
      print("ℹ️ No new unique leads passed filters in this pass.")

    batch_count += 1

    if time.time() + SLEEP_INTERVAL_SECONDS >= end_time:
      break

    print(f"💤 Safe cooldown {SLEEP_INTERVAL_SECONDS}s...")
    time.sleep(SLEEP_INTERVAL_SECONDS)

  print("\n" + "=" * 65)
  print("🎉 1-HOUR LEAD EXTRACTION COMPLETED!")
  print(f"🏆 Total High-Intent Leads Added: {total_leads_added}")
  print("🛑 System Shutdown Cleanly.")
  print("=" * 65)


if __name__ == "__main__":
  main()
