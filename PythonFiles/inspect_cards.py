import gzip
import json


FILE_PATH = "data/default_cards.jsonl.gz"


with gzip.open(
    FILE_PATH,
    "rt",
    encoding="utf-8"
) as file:

    first_line = file.readline()

    first_card = json.loads(first_line)


print("First card:")
print()

for key, value in first_card.items():
    print(f"{key}: {value}")