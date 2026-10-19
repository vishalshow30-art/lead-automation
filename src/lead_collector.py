from datetime import datetime, timezone
import json
import os
import random
import re
import sys
import time
from duckduckgo_search import DDGS
from google.oauth2.service_account import Credentials
import gspread

# ==========================================
# 1. Config & Setup (No Search Engine ID Needed)
# ==========================================
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
WORKSHEET_NAME = os.environ.get("GOOGLE_SHEET_WORKSHEET") or "Sheet1"
SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

# 1-Minute Fast Test
TOTAL_RUN_SECONDS = 60  # 1 minute run
SLEEP_INTERVAL_SECONDS = 8  # Safe delay between queries

if not all([GOOGLE_SHEET_ID, SERVICE_ACCOUNT_JSON]):
  print(
      "❌ Critical Error: GOOGLE_SHEET_ID or GOOGLE_SERVICE_ACCOUNT_JSON"
      " missing!"
  )
  sys.exit(1)

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
        (
            'site:instagram.com "video editor" OR "filmmaker" "india"'
            ' ("@gmail.com" OR "contact")'
        ),
        (
            'site:instagram.com "podcast" OR "content creator" "india"'
            ' "@gmail.com"'
        ),
        (
            'site:instagram.com "tech reviews" OR "gadgets" "india"'
            ' ("collab" OR "business") "@gmail.com"'
        ),
        (
            'site:instagram.com "fitness coach" OR "vlogger" "india" "dm for'
            ' work" "@gmail.com"'
        ),
    ],
    "YouTube_Web": [
        (
            'site:youtube.com "business inquiries" ("podcast" OR "finance" OR'
            ' "tech") "india" "@gmail.com"'
        ),
        'site:youtube.com/@ "business email" OR "contact:" "hindi" "@gmail.com"',
        (
            'site:youtube.com "video editing agency" OR "content agency" india'
            ' "@gmail.com"'
        ),
    ],
    "LinkedIn": [
        (
            'site:linkedin.com/in "content creator" OR "video producer" "india"'
            ' ("@gmail.com" OR "contact")'
        ),
        (
            'site:linkedin.com/in "founder" "podcast" "india" ("email" OR'
            ' "@gmail.com")'
        ),
    ],
    "Twitter_X": [
        (
            'site:x.com "youtube creator" OR "video editor" "india" ("email" OR'
            ' "@gmail.com")'
        ),
        (
            'site:x.com "looking for video editor" OR "hiring editor" ("dm" OR'
            ' "email")'
        ),
    ],
    "Facebook": [
        (
            'site:facebook.com "video creator" OR "digital creator" "india"'
            ' "@gmail.com"'
        ),
        (
            'site:facebook.com "content creator" "delhi" OR "mumbai" "email"'
            ' "@gmail.com"'
        ),
    ],
}


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


def detect_niche(query_str, content=""):
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


def extract_city(text):
  if not text:
    return ""
  cities = [
      "Mumbai",
      "Delhi",
      "Bengaluru",
      "Bangalore",
      "Hyderabad",
      "Ahmedabad",
      "Chennai",
      "Kolkata",
      "Surat",
      "Pune",
      "Jaipur",
      "Lucknow",
      "Kanpur",
      "Nagpur",
      "Indore",
      "Thane",
      "Bhopal",
      "Visakhapatnam",
      "Patna",
      "Vadodara",
      "Ghaziabad",
      "Ludhiana",
      "Agra",
      "Nashik",
      "Faridabad",
      "Varanasi",
      "Noida",
      "Chandigarh",
  ]
  for city in cities:
    if re.search(rf"\b{city}\b", text, re.IGNORECASE):
      return city
  return ""


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


def live_duckduckgo_search(query, max_results=10):
  """Official DDGS Client - Bypasses all bot-blocks and gets real search results."""
  items = []
  try:
    with DDGS() as ddgs:
      results = ddgs.text(query, max_results=max_results)
      for r in results:
        items.append({
            "title": r.get("title", ""),
            "link": r.get("href", ""),
            "snippet": r.get("body", ""),
        })
  except Exception as e:
    print(f"⚠️ Search error for query: {e}")
  return items


# ==========================================
# 4. Multi-Platform Batch Runner
# ==========================================
def run_scrape_batch(existing_ids, round_num):
  print(f"\n==========================================")
  print(f"🔄 BATCH #{round_num} RUNNING (ALL SOCIAL MEDIA)...")
  print(f"==========================================")
  new_leads = []

  active_platforms = list(DEEP_SEARCH_POOLS.keys())
  random.shuffle(active_platforms)

  for platform_key in active_platforms[:3]:
    query = random.choice(DEEP_SEARCH_POOLS[platform_key])
    print(f"🔍 Live Search: [{platform_key}] -> {query[:55]}...")

    items = live_duckduckgo_search(query, max_results=8)

    for item in items:
      link = item.get("link", "").strip()
      if not link or link in existing_ids:
        continue

      title = item.get("title", "")
      snippet = item.get("snippet", "")
      full_text = f"{title} {snippet} {link}"

      email = extract_email(full_text)
      socials = extract_socials_and_web(full_text)
      detected_platform = identify_platform(link)

      if detected_platform == "Instagram" and not socials["instagram"]:
        socials["instagram"] = link
      elif detected_platform == "LinkedIn" and not socials["linkedin"]:
        socials["linkedin"] = link
      elif detected_platform == "Twitter" and not socials["twitter_x"]:
        socials["twitter_x"] = link

      clean_name = (
          title.split("(@")[0].split("•")[0].split("-")[0].split("|")[0].strip()
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
          "India",
          extract_city(full_text),
          "",
          "",
          email,
          socials["instagram"],
          socials["linkedin"],
          socials["twitter_x"],
          socials["website"],
          datetime.now(timezone.utc).strftime("%Y-%m-%d"),
          "public",
          "duckduckgo_live",
          "new",
          f"Sourced via {detected_platform} live search",
      ]
      new_leads.append(row)
      existing_ids.add(link)

  return new_leads


# ==========================================
# 5. 1-Minute Runner Logic
# ==========================================
def main():
  start_time = time.time()
  end_time = start_time + TOTAL_RUN_SECONDS

  print("=" * 60)
  print("🚀 1-MINUTE QUICK TEST INITIATED")
  print(f"⏱️ Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
  print("⏱️ System testing all platforms live without CSE restriction.")
  print("=" * 60)

  sheet = connect_google_sheet()
  all_values = sheet.get_all_values()
  existing_ids = set()
  for row in all_values:
    for cell in row:
      val = cell.strip()
      if (
          val.startswith("http")
          or val.startswith("UC")
          or val.startswith("@")
          or "@" in val
      ):
        existing_ids.add(val)

  print(f"📊 Loaded {len(existing_ids)} pre-existing leads.")

  batch_count = 1
  total_leads_added = 0

  while time.time() < end_time:
    rem_sec = max(0, int(end_time - time.time()))
    print(f"\n⏳ Remaining Test Time: {rem_sec} seconds")

    fresh_leads = run_scrape_batch(existing_ids, batch_count)

    if fresh_leads:
      print(f"📝 Appending {len(fresh_leads)} fresh leads into Google Sheet...")
      sheet.append_rows(fresh_leads)
      total_leads_added += len(fresh_leads)
      print(f"✅ Saved! Total leads added: {total_leads_added}")
    else:
      print("ℹ️ No new unique leads found in this check.")

    batch_count += 1

    if time.time() + SLEEP_INTERVAL_SECONDS >= end_time:
      break

    print(f"💤 Waiting {SLEEP_INTERVAL_SECONDS}s before next query...")
    time.sleep(SLEEP_INTERVAL_SECONDS)

  print("\n" + "=" * 60)
  print("🎉 1-MINUTE TEST COMPLETE!")
  print(f"🏆 Total Leads Added: {total_leads_added}")
  print("🛑 System shutting down automatically. Success.")
  print("=" * 60)


if __name__ == "__main__":
  main()
