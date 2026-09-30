import requests


url = "https://api.scryfall.com/bulk-data"

headers = {
    "User-Agent": "MTGCardScanner/1.0",
    "Accept": "application/json;q=0.9,*/*;q=0.8"
}

response = requests.get(
    url,
    headers=headers,
    timeout=30
)

print("Status:", response.status_code)

# If Scryfall gives us an error, print it instead of crashing
if response.status_code != 200:
    print()
    print("Scryfall returned an error:")
    print(response.text)
    raise SystemExit()

data = response.json()

print()
print("Bulk datasets:")
print()

for item in data["data"]:
    print(
        item["type"],
        "-",
        item["name"]
    )