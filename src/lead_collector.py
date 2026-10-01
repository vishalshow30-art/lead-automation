from pathlib import Path
import csv
import json
import os
import re
import time
import requests


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
DATA_FILE = DATA_DIR / "leads.csv"

MIN_SUBSCRIBERS = 10_000
MAX_SUBSCRIBERS = 50_000

MAX_LEADS_PER_RUN = 50

REQUEST_TIMEOUT = 30


# ============================================================
# GITHUB SECRETS
# ============================================================

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()

GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    ""
).strip()

GOOGLE_SHEET_ID = os.getenv(
    "GOOGLE_SHEET_ID",
    ""
).strip()

# Optional.
# If this secret is not present, Sheet1 will be used.
GOOGLE_SHEET_NAME = os.getenv(
    "GOOGLE_SHEET_NAME",
    ""
).strip()


# ============================================================
# CSV HEADERS
# ============================================================

# IMPORTANT:
# There are exactly 20 columns here.
# Therefore Google Sheets range is A:T.

CSV_HEADERS = [
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


# ============================================================
# YOUTUBE SEARCH QUERIES
# ============================================================

YOUTUBE_SEARCH_QUERIES = [
    "Indian gaming YouTuber",
    "Indian tech YouTuber",
    "Indian gadgets YouTuber",
    "Indian PC computer YouTuber",
    "Indian mobile YouTuber",
    "Indian lifestyle YouTuber",
    "Indian education YouTuber",
    "Indian entertainment YouTuber",
    "Indian fitness YouTuber",
    "Indian fashion YouTuber",
    "Indian travel YouTuber",
    "Indian finance YouTuber",
    "Indian automotive YouTuber",
    "Indian comedy YouTuber",
    "Indian vlogging YouTuber",
]


# ============================================================
# YOUTUBE API URLS
# ============================================================

YOUTUBE_SEARCH_URL = (
    "https://www.googleapis.com/youtube/v3/search"
)

YOUTUBE_CHANNELS_URL = (
    "https://www.googleapis.com/youtube/v3/channels"
)

YOUTUBE_PLAYLIST_ITEMS_URL = (
    "https://www.googleapis.com/youtube/v3/playlistItems"
)


# ============================================================
# BASIC HELPERS
# ============================================================

def clean(value):
    """
    Convert value to a clean string.
    """
    if value is None:
        return ""

    return str(value).strip()


def safe_int(value):
    """
    Safely convert value to integer.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize_url(value):
    """
    Make sure a URL has https://.
    """
    value = clean(value)

    if not value:
        return ""

    if value.startswith("http://"):
        return value

    if value.startswith("https://"):
        return value

    return "https://" + value


def extract_email(text):
    """
    Extract first public email from text.
    """
    text = clean(text)

    if not text:
        return ""

    matches = re.findall(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        text,
    )

    for email in matches:
        email = email.lower().strip()

        if email.endswith(
            (".png", ".jpg", ".jpeg", ".webp")
        ):
            continue

        return email

    return ""


def detect_niche(text):
    """
    Detect creator niche from title + description.
    """
    text = clean(text).lower()

    niche_map = [
        (
            "Gaming",
            [
                "gaming",
                "gamer",
                "gameplay",
                "esports",
            ],
        ),
        (
            "Tech",
            [
                "tech",
                "technology",
                "gadget",
                "gadgets",
                "computer",
                "pc",
            ],
        ),
        (
            "Mobile",
            [
                "mobile",
                "smartphone",
                "iphone",
                "android",
            ],
        ),
        (
            "Lifestyle",
            [
                "lifestyle",
                "daily life",
            ],
        ),
        (
            "Education",
            [
                "education",
                "study",
                "learning",
                "student",
            ],
        ),
        (
            "Entertainment",
            [
                "entertainment",
                "movie",
                "movies",
                "celebrity",
            ],
        ),
        (
            "Fitness",
            [
                "fitness",
                "workout",
                "gym",
            ],
        ),
        (
            "Fashion",
            [
                "fashion",
                "style",
                "beauty",
            ],
        ),
        (
            "Travel",
            [
                "travel",
                "travelling",
                "tour",
            ],
        ),
        (
            "Finance",
            [
                "finance",
                "stock",
                "investing",
                "trading",
            ],
        ),
        (
            "Automotive",
            [
                "car",
                "cars",
                "automotive",
                "bike",
                "bikes",
            ],
        ),
        (
            "Comedy",
            [
                "comedy",
                "funny",
            ],
        ),
        (
            "Vlogging",
            [
                "vlog",
                "vlogging",
                "vlogger",
            ],
        ),
    ]

    for niche, keywords in niche_map:
        for keyword in keywords:
            if keyword in text:
                return niche

    return ""


# ============================================================
# CSV FUNCTIONS
# ============================================================

def ensure_csv():
    """
    Create data/leads.csv if it doesn't exist.
    """
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if (
        not DATA_FILE.exists()
        or DATA_FILE.stat().st_size == 0
    ):
        with DATA_FILE.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=CSV_HEADERS,
            )

            writer.writeheader()


def normalize_lead(lead):
    """
    Make sure every lead has all CSV columns.
    """
    result = {}

    for header in CSV_HEADERS:
        result[header] = clean(
            lead.get(header, "")
        )

    result["subscribers"] = safe_int(
        result["subscribers"]
    )

    return result


def lead_key(lead):
    """
    Create a unique key for duplicate checking.
    """

    channel_url = normalize_url(
        lead.get("channel_url", "")
    )

    if channel_url:
        return (
            "youtube:"
            + channel_url.lower().rstrip("/")
        )

    profile_url = normalize_url(
        lead.get("profile_url", "")
    )

    if profile_url:
        return (
            clean(
                lead.get("platform", "")
            ).lower()
            + ":"
            + profile_url.lower().rstrip("/")
        )

    email = clean(
        lead.get("business_email", "")
    ).lower()

    if email:
        return "email:" + email

    name = clean(
        lead.get("name", "")
    ).lower()

    return (
        clean(
            lead.get("platform", "")
        ).lower()
        + ":"
        + name
    )


def read_csv():
    """
    Read existing leads from CSV.
    """
    ensure_csv()

    leads = []

    with DATA_FILE.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:
            leads.append(
                normalize_lead(row)
            )

    return leads


def save_leads(leads):
    """
    Save all leads to CSV.
    """
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with DATA_FILE.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=CSV_HEADERS,
        )

        writer.writeheader()

        for lead in leads:
            writer.writerow(
                normalize_lead(lead)
            )

    print(
        f"Saved {len(leads)} leads to {DATA_FILE}"
    )


# ============================================================
# HTTP / YOUTUBE API
# ============================================================

def get_json(url, params):
    """
    GET JSON from an API.
    """
    response = requests.get(
        url,
        params=params,
        timeout=REQUEST_TIMEOUT,
    )

    if response.status_code != 200:

        try:
            error_data = response.json()
        except Exception:
            error_data = response.text[:500]

        raise RuntimeError(
            "HTTP "
            + str(response.status_code)
            + " from YouTube API: "
            + str(error_data)
        )

    return response.json()


def youtube_search(query):
    """
    Search YouTube channels.
    """
    params = {
        "part": "snippet",
        "q": query,
        "type": "channel",
        "regionCode": "IN",
        "maxResults": 50,
        "key": YOUTUBE_API_KEY,
    }

    data = get_json(
        YOUTUBE_SEARCH_URL,
        params,
    )

    channel_ids = []

    for item in data.get("items", []):

        channel_id = clean(
            item.get("snippet", {})
            .get("channelId", "")
        )

        if channel_id:
            channel_ids.append(
                channel_id
            )

    return channel_ids


def youtube_get_channels(channel_ids):
    """
    Get detailed information for channels.
    """
    if not channel_ids:
        return []

    results = []

    for start in range(
        0,
        len(channel_ids),
        50,
    ):

        batch = channel_ids[
            start:start + 50
        ]

        params = {
            "part": (
                "snippet,"
                "statistics,"
                "contentDetails"
            ),
            "id": ",".join(batch),
            "key": YOUTUBE_API_KEY,
        }

        data = get_json(
            YOUTUBE_CHANNELS_URL,
            params,
        )

        results.extend(
            data.get("items", [])
        )

        time.sleep(0.1)

    return results


def youtube_latest_upload(channel):
    """
    Get latest upload date.
    """
    playlist_id = clean(
        channel.get(
            "contentDetails",
            {},
        )
        .get(
            "relatedPlaylists",
            {},
        )
        .get(
            "uploads",
            "",
        )
    )

    if not playlist_id:
        return ""

    params = {
        "part": "snippet",
        "playlistId": playlist_id,
        "maxResults": 1,
        "key": YOUTUBE_API_KEY,
    }

    try:
        data = get_json(
            YOUTUBE_PLAYLIST_ITEMS_URL,
            params,
        )

        items = data.get(
            "items",
            [],
        )

        if not items:
            return ""

        return clean(
            items[0]
            .get("snippet", {})
            .get("publishedAt", "")
        )

    except Exception as error:

        print(
            "Warning: could not read "
            f"latest upload: {error}"
        )

        return ""


# ============================================================
# YOUTUBE COLLECTION
# ============================================================

def collect_youtube():

    print(
        "\n"
        + "=" * 60
    )

    print(
        "STARTING YOUTUBE COLLECTION"
    )

    print(
        "=" * 60
    )

    if not YOUTUBE_API_KEY:
        raise RuntimeError(
            "YOUTUBE_API_KEY is missing."
        )

    channel_ids = []

    for query in YOUTUBE_SEARCH_QUERIES:

        print(
            f"Searching: {query}"
        )

        try:

            ids = youtube_search(
                query
            )

            print(
                f"Results received: {len(ids)}"
            )

            channel_ids.extend(ids)

        except Exception as error:

            print(
                "WARNING: search failed "
                f"for '{query}': {error}"
            )

    unique_channel_ids = list(
        dict.fromkeys(channel_ids)
    )

    print(
        "Unique channels found: "
        f"{len(unique_channel_ids)}"
    )

    if not unique_channel_ids:

        print(
            "No YouTube channels found."
        )

        return []

    channel_details = (
        youtube_get_channels(
            unique_channel_ids
        )
    )

    print(
        "Channel details received: "
        f"{len(channel_details)}"
    )

    leads = []

    for channel in channel_details:

        snippet = channel.get(
            "snippet",
            {},
        )

        statistics = channel.get(
            "statistics",
            {},
        )

        subscribers = safe_int(
            statistics.get(
                "subscriberCount",
                0,
            )
        )

        # Subscriber filter
        if subscribers < MIN_SUBSCRIBERS:
            continue

        if subscribers > MAX_SUBSCRIBERS:
            continue

        title = clean(
            snippet.get(
                "title",
                "",
            )
        )

        description = clean(
            snippet.get(
                "description",
                "",
            )
        )

        custom_url = clean(
            snippet.get(
                "customUrl",
                "",
            )
        )

        channel_id = clean(
            channel.get(
                "id",
                "",
            )
        )

        combined_text = (
            f"{title} {description}"
        )

        niche = detect_niche(
            combined_text
        )

        if not niche:
            continue

        # Profile URL
        if custom_url:

            custom_url = (
                custom_url
                .replace("@", "")
                .strip("/")
            )

            profile_url = (
                "https://www.youtube.com/"
                + custom_url
            )

        else:

            profile_url = (
                "https://www.youtube.com/channel/"
                + channel_id
            )

        channel_url = (
            "https://www.youtube.com/channel/"
            + channel_id
        )

        # Public email
        email = extract_email(
            description
        )

        # Latest upload
        latest_upload = (
            youtube_latest_upload(
                channel
            )
        )

        if email:
            contact_type = (
                "Business Email"
            )
        else:
            contact_type = (
                "Public Profile"
            )

        country = clean(
            snippet.get(
                "country",
                "",
            )
        )

        if not country:
            country = "IN"

        lead = {
            "name": title,

            "platform": "YouTube",

            "profile_url": profile_url,

            "channel_url": channel_url,

            "creator_or_business": "Creator",

            "niche": niche,

            "country": country,

            "city": "",

            "subscribers": subscribers,

            "avg_views": "",

            "business_email": email,

            "instagram": "",

            "linkedin": "",

            "twitter_x": "",

            "website": "",

            "recent_upload": latest_upload,

            "contact_type": contact_type,

            "lead_source": (
                "YouTube Data API"
            ),

            "status": "New",

            "notes": (
                "Public YouTube channel. "
                "Subscriber range matched."
            ),
        }

        leads.append(
            normalize_lead(lead)
        )

        if len(leads) >= MAX_LEADS_PER_RUN:
            break

    print(
        "YOUTUBE LEADS AFTER FILTERING: "
        f"{len(leads)}"
    )

    print(
        "Total YouTube leads collected: "
        f"{len(leads)}"
    )

    return leads


# ============================================================
# GOOGLE SHEETS UPLOAD
# ============================================================

def upload_to_google_sheets(leads):

    print(
        "\n"
        + "=" * 60
    )

    print(
        "STARTING GOOGLE SHEETS UPLOAD"
    )

    print(
        "=" * 60
    )

    if not GOOGLE_SERVICE_ACCOUNT_JSON:

        print(
            "ERROR: "
            "GOOGLE_SERVICE_ACCOUNT_JSON "
            "is missing."
        )

        return False

    if not GOOGLE_SHEET_ID:

        print(
            "ERROR: GOOGLE_SHEET_ID "
            "is missing."
        )

        return False

    print(
        "Loading Google Sheets libraries..."
    )

    try:

        import gspread

        from google.oauth2.service_account import (
            Credentials
        )

    except Exception as error:

        print(
            "ERROR: Google Sheets "
            "libraries could not load: "
            f"{error}"
        )

        return False

    print(
        "Google Sheets libraries loaded."
    )

    # --------------------------------------------------------
    # Parse service account JSON
    # --------------------------------------------------------

    try:

        service_account_info = (
            json.loads(
                GOOGLE_SERVICE_ACCOUNT_JSON
            )
        )

    except json.JSONDecodeError as error:

        print(
            "ERROR: "
            "GOOGLE_SERVICE_ACCOUNT_JSON "
            "is not valid JSON:"
        )

        print(error)

        return False

    # --------------------------------------------------------
    # Google scopes
    # --------------------------------------------------------

    scopes = [
        (
            "https://www.googleapis.com/"
            "auth/spreadsheets"
        ),
        (
            "https://www.googleapis.com/"
            "auth/drive"
        ),
    ]

    # --------------------------------------------------------
    # Authorize Google
    # --------------------------------------------------------

    try:

        credentials = (
            Credentials
            .from_service_account_info(
                service_account_info,
                scopes=scopes,
            )
        )

        print(
            "Credentials created successfully."
        )

        client = gspread.authorize(
            credentials
        )

        print(
            "Google account authorization "
            "successful."
        )

    except Exception as error:

        print(
            "ERROR: Google authorization "
            f"failed: {error}"
        )

        return False

    # --------------------------------------------------------
    # Open spreadsheet
    # --------------------------------------------------------

    try:

        spreadsheet = client.open_by_key(
            GOOGLE_SHEET_ID
        )

        print(
            "Google Sheet opened successfully: "
            f"{spreadsheet.title}"
        )

        print(
            "Google Sheet URL: "
            f"{spreadsheet.url}"
        )

        if GOOGLE_SHEET_NAME:

            worksheet = (
                spreadsheet.worksheet(
                    GOOGLE_SHEET_NAME
                )
            )

        else:

            worksheet = spreadsheet.sheet1

        print(
            "Using worksheet: "
            f"{worksheet.title}"
        )

    except Exception as error:

        print(
            "ERROR: Could not open "
            "Google Sheet/worksheet:"
        )

        print(error)

        return False

    # --------------------------------------------------------
    # Update header
    #
    # EXACTLY 20 columns = A:T
    # --------------------------------------------------------

    try:

        worksheet.update(
            range_name="A1:T1",
            values=[CSV_HEADERS],
        )

        print(
            "Sheet header checked/updated."
        )

    except Exception as error:

        print(
            "ERROR: Could not update "
            f"sheet header: {error}"
        )

        return False

    # --------------------------------------------------------
    # Read existing sheet
    # --------------------------------------------------------

    try:

        existing_values = (
            worksheet.get_all_values()
        )

        print(
            "Existing Google Sheet rows: "
            f"{len(existing_values)}"
        )

    except Exception as error:

        print(
            "ERROR: Could not read "
            "existing Google Sheet rows:"
        )

        print(error)

        return False

    # --------------------------------------------------------
    # Existing duplicate keys
    # --------------------------------------------------------

    existing_keys = set()

    for row_values in existing_values[1:]:

        row = {}

        for index, header in enumerate(
            CSV_HEADERS
        ):

            if index < len(row_values):

                row[header] = (
                    row_values[index]
                )

            else:

                row[header] = ""

        existing_keys.add(
            lead_key(row)
        )

    # --------------------------------------------------------
    # Prepare new rows
    # --------------------------------------------------------

    rows_to_add = []

    for lead in leads:

        normalized = normalize_lead(
            lead
        )

        key = lead_key(
            normalized
        )

        if key in existing_keys:
            continue

        row_values = []

        for header in CSV_HEADERS:

            row_values.append(
                normalized[header]
            )

        rows_to_add.append(
            row_values
        )

        existing_keys.add(key)

    print(
        "New rows ready for upload: "
        f"{len(rows_to_add)}"
    )

    # --------------------------------------------------------
    # No new rows
    # --------------------------------------------------------

    if not rows_to_add:

        print(
            "No new rows to upload."
        )

        print(
            "Google Sheets connection "
            "is working."
        )

        print(
            "FINAL STATUS: "
            "GOOGLE SHEETS SUCCESS - "
            "NO NEW ROWS"
        )

        return True

    # --------------------------------------------------------
    # APPEND NEW ROWS
    # --------------------------------------------------------

    try:

        worksheet.append_rows(
            rows_to_add,
            value_input_option=(
                "USER_ENTERED"
            ),
        )

    except Exception as error:

        print(
            "ERROR: Google Sheets "
            f"append failed: {error}"
        )

        return False

    print(
        "SUCCESS: "
        f"{len(rows_to_add)} "
        "NEW LEADS UPLOADED TO "
        "GOOGLE SHEETS."
    )

    # --------------------------------------------------------
    # VERIFY AFTER UPLOAD
    # --------------------------------------------------------

    try:

        updated_values = (
            worksheet.get_all_values()
        )

        print(
            "Google Sheet rows after "
            "upload: "
            f"{len(updated_values)}"
        )

        expected_rows = (
            len(existing_values)
            + len(rows_to_add)
        )

        print(
            "Expected rows after upload: "
            f"{expected_rows}"
        )

        if len(updated_values) < expected_rows:

            print(
                "ERROR: Google Sheet "
                "row count verification "
                "failed."
            )

            return False

        # Build keys from the final sheet.
        final_keys = set()

        for row_values in updated_values[1:]:

            row = {}

            for index, header in enumerate(
                CSV_HEADERS
            ):

                if index < len(row_values):

                    row[header] = (
                        row_values[index]
                    )

                else:

                    row[header] = ""

            final_keys.add(
                lead_key(row)
            )

        # Verify every row that we attempted
        # to upload is actually present.
        verified_count = 0

        for row_values in rows_to_add:

            row = {}

            for index, header in enumerate(
                CSV_HEADERS
            ):

                if index < len(row_values):

                    row[header] = (
                        row_values[index]
                    )

                else:

                    row[header] = ""

            if lead_key(row) in final_keys:
                verified_count += 1

        print(
            "Uploaded rows verified: "
            f"{verified_count}/"
            f"{len(rows_to_add)}"
        )

        if verified_count != len(
            rows_to_add
        ):

            print(
                "ERROR: Not all uploaded "
                "leads were found during "
                "verification."
            )

            return False

        print(
            "GOOGLE SHEETS UPLOAD VERIFIED."
        )

        print(
            "FINAL STATUS: "
            "GOOGLE SHEETS SUCCESS"
        )

        return True

    except Exception as error:

        print(
            "ERROR: Google Sheets "
            "verification failed:"
        )

        print(error)

        return False


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n"
        + "=" * 60
    )

    print(
        "LEAD AUTOMATION STARTED"
    )

    print(
        "=" * 60
    )

    # --------------------------------------------------------
    # Required secrets
    # --------------------------------------------------------

    if not YOUTUBE_API_KEY:

        raise RuntimeError(
            "YOUTUBE_API_KEY is missing."
        )

    if not GOOGLE_SERVICE_ACCOUNT_JSON:

        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON "
            "is missing."
        )

    if not GOOGLE_SHEET_ID:

        raise RuntimeError(
            "GOOGLE_SHEET_ID is missing."
        )

    print(
        "Required GitHub Secrets detected."
    )

    # --------------------------------------------------------
    # CSV
    # --------------------------------------------------------

    ensure_csv()

    existing_leads = read_csv()

    print(
        "Existing CSV leads: "
        f"{len(existing_leads)}"
    )

    # --------------------------------------------------------
    # YouTube
    # --------------------------------------------------------

    youtube_leads = (
        collect_youtube()
    )

    # --------------------------------------------------------
    # Add only new leads to CSV
    # --------------------------------------------------------

    existing_keys = {
        lead_key(lead)
        for lead in existing_leads
    }

    new_csv_leads = []

    for lead in youtube_leads:

        normalized = normalize_lead(
            lead
        )

        key = lead_key(
            normalized
        )

        if key in existing_keys:
            continue

        existing_keys.add(key)

        new_csv_leads.append(
            normalized
        )

    all_leads = (
        existing_leads
        + new_csv_leads
    )

    print(
        "New leads added to CSV: "
        f"{len(new_csv_leads)}"
    )

    save_leads(
        all_leads
    )

    # --------------------------------------------------------
    # Google Sheets
    # --------------------------------------------------------

    sheets_success = (
        upload_to_google_sheets(
            youtube_leads
        )
    )

    if not sheets_success:

        print(
            "\n"
            "ERROR: GOOGLE SHEETS "
            "UPLOAD FAILED."
        )

        raise RuntimeError(
            "Google Sheets upload failed."
        )

    # --------------------------------------------------------
    # Final
    # --------------------------------------------------------

    print(
        "\n"
        + "=" * 60
    )

    print(
        "LEAD AUTOMATION FINISHED"
    )

    print(
        "=" * 60
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
