from pathlib import Path
import csv


def get_project_root() -> Path:
    current = Path(__file__).resolve()

    for parent in current.parents:
        if (parent / "requirements.txt").exists():
            return parent

    return current.parent


PROJECT_ROOT = get_project_root()
DATA_FILE = PROJECT_ROOT / "data" / "leads.csv"

CSV_HEADERS = [
    "name",
    "platform",
    "channel_url",
    "subscriber_count",
    "niche",
    "country",
    "contact_email",
    "business_email",
    "website",
    "instagram_url",
    "notes",
]


def ensure_leads_file() -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not DATA_FILE.exists():
        with DATA_FILE.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=CSV_HEADERS)
            writer.writeheader()


def main() -> None:
    ensure_leads_file()
    print(f"Lead data file: {DATA_FILE}")


if __name__ == "__main__":
    main()
