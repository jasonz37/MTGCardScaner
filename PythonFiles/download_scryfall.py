import requests
from pathlib import Path


BULK_DATA_API = "https://api.scryfall.com/bulk-data"

HEADERS = {
    "User-Agent": "MTGCardScanner/1.0",
    "Accept": "application/json;q=0.9,*/*;q=0.8"
}

DATA_FOLDER = Path("data")
OUTPUT_FILE = DATA_FOLDER / "default_cards.jsonl.gz"


def get_default_cards_download_url():
    print("Contacting Scryfall...")

    response = requests.get(
        BULK_DATA_API,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    bulk_data = response.json()

    for item in bulk_data["data"]:
        if item["type"] == "default_cards":
            print("Found Default Cards dataset.")
            return item["jsonl_download_uri"]

    raise RuntimeError(
        "Could not find the default_cards dataset."
    )


def download_file(url):
    DATA_FOLDER.mkdir(exist_ok=True)

    print("Downloading Scryfall card data...")

    with requests.get(
        url,
        headers=HEADERS,
        stream=True,
        timeout=120
    ) as response:

        response.raise_for_status()

        with open(OUTPUT_FILE, "wb") as file:
            for chunk in response.iter_content(
                chunk_size=1024 * 1024
            ):
                if chunk:
                    file.write(chunk)

    print()
    print("Download complete.")
    print("Saved to:", OUTPUT_FILE)


def main():
    download_url = get_default_cards_download_url()

    print()
    print("Download URL found.")

    download_file(download_url)


if __name__ == "__main__":
    main()