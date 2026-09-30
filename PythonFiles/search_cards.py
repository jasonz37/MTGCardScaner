from database import get_connection


def search_card(card_name):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            c.Name,
            c.ManaCost,
            c.TypeLine,

            s.SetName,
            p.SetCode,
            p.CollectorNumber,
            p.Rarity

        FROM Cards c

        INNER JOIN Printings p
            ON c.CardId = p.CardId

        INNER JOIN Sets s
            ON p.SetCode = s.SetCode

        WHERE c.Name = ?

        ORDER BY p.ReleasedAt
        """,
        card_name
    )

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    return rows


name = input("Enter a Magic card name: ")

results = search_card(name)

print()

if not results:

    print("No cards found.")

else:

    print(
        f"Found {len(results)} printing(s)."
    )

    print()

    for row in results:

        print("------------------------------")
        print("Name:", row.Name)
        print("Mana:", row.ManaCost)
        print("Type:", row.TypeLine)
        print("Set:", row.SetName)
        print("Set Code:", row.SetCode)
        print(
            "Collector #:",
            row.CollectorNumber
        )
        print("Rarity:", row.Rarity)