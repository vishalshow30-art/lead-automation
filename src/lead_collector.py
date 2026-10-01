def upload_to_google_sheets(leads):
    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        print("ERROR: GOOGLE_SERVICE_ACCOUNT_JSON is missing.")
        return

    if not GOOGLE_SHEET_ID:
        print("ERROR: GOOGLE_SHEET_ID is missing.")
        return

    if not leads:
        print("No leads available for Google Sheets.")
        return

    try:
        import gspread
        from google.oauth2.service_account import Credentials

        print("Connecting to Google Sheets...")

        service_account_info = json.loads(
            GOOGLE_SERVICE_ACCOUNT_JSON
        )

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        credentials = Credentials.from_service_account_info(
            service_account_info,
            scopes=scopes,
        )

        client = gspread.authorize(credentials)

        spreadsheet = client.open_by_key(
            GOOGLE_SHEET_ID
        )

        worksheet = spreadsheet.sheet1

        print(
            f"Connected to Google Sheet: {spreadsheet.title}"
        )

        worksheet.update(
            "A1:T1",
            [CSV_HEADERS],
        )

        existing_values = worksheet.get_all_values()

        existing_keys = set()

        for row_values in existing_values[1:]:
            row = {}

            for index, header in enumerate(CSV_HEADERS):
                if index < len(row_values):
                    row[header] = row_values[index]
                else:
                    row[header] = ""

            existing_keys.add(
                lead_key(row)
            )

        rows_to_add = []

        for lead in leads:
            normalized = normalize_lead(lead)
            key = lead_key(normalized)

            if key in existing_keys:
                continue

            rows_to_add.append(
                [
                    normalized[header]
                    for header in CSV_HEADERS
                ]
            )

            existing_keys.add(key)

        print(
            f"Leads received: {len(leads)}"
        )

        print(
            f"New leads to upload: {len(rows_to_add)}"
        )

        if not rows_to_add:
            print(
                "Google Sheet already contains these leads."
            )
            return

        worksheet.append_rows(
            rows_to_add,
            value_input_option="USER_ENTERED",
        )

        print(
            f"SUCCESS: Uploaded {len(rows_to_add)} "
            "new leads to Google Sheets."
        )

    except Exception as error:
        print(
            "ERROR: Google Sheets upload failed."
        )
        print(
            f"ERROR DETAILS: {type(error).__name__}: {error}"
        )
        raise
