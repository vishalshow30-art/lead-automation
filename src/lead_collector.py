
name: lead-automation

on:
  workflow_dispatch:

  # GitHub Actions scheduled workflows have a
  # minimum interval of 5 minutes, not 1 minute.
  # Enable this schedule only when ready for automation.
  # schedule:
  #   - cron: "*/5 * * * *"

permissions:
  contents: read

concurrency:
  group: lead-automation
  cancel-in-progress: false

jobs:
  lead-automation:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: requirements.txt

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -r requirements.txt

      - name: Check required secrets
        env:
          YOUTUBE_API_KEY: ${{ secrets.YOUTUBE_API_KEY }}
          GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}
          GOOGLE_SHEET_ID: ${{ secrets.GOOGLE_SHEET_ID }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: |
          python - <<'PY'
          import os
          import sys

          required = [
              "YOUTUBE_API_KEY",
              "GOOGLE_SERVICE_ACCOUNT_JSON",
              "GOOGLE_SHEET_ID",
          ]

          missing = [
              key for key in required
              if not os.environ.get(key, "").strip()
          ]

          if missing:
              print("Missing required GitHub secrets:")
              for key in missing:
                  print(f"- {key}")
              sys.exit(1)

          print("Required YouTube and Google Sheets secrets are present.")

          if os.environ.get("GEMINI_API_KEY", "").strip():
              print("Gemini API key is present.")
          else:
              print("Gemini API key is missing; Gemini features will be unavailable.")
          PY

      - name: Run lead collector
        env:
          YOUTUBE_API_KEY: ${{ secrets.YOUTUBE_API_KEY }}
          YOUTUBE_SEARCH_QUERY: ${{ vars.YOUTUBE_SEARCH_QUERY }}
          ACTIVE_DAYS: "180"

          X_BEARER_TOKEN: ${{ secrets.X_BEARER_TOKEN }}

          GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}
          GOOGLE_SHEET_ID: ${{ secrets.GOOGLE_SHEET_ID }}
          GOOGLE_SHEET_WORKSHEET: ${{ secrets.GOOGLE_SHEET_WORKSHEET }}

          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}

        run: python -u src/lead_collector.py
