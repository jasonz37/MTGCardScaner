import gzip
import json

from database import get_connection


# ============================================================
# CONFIGURATION
# ============================================================

FILE_PATH = "data/default_cards.jsonl.gz"

# None = import the entire Scryfall file.
# For testing, change to something like 5000.
IMPORT_LIMIT = None

# Number of valid Scryfall records processed at once.
BATCH_SIZE = 1000

# File containing details about anything we truly skip.
SKIPPED_FILE_PATH = "skipped_cards.jsonl"

# Only print this many skipped-record examples to the console.
MAX_SKIP_EXAMPLES = 25


# ============================================================
# BASIC HELPERS
# ============================================================

def list_to_string(value):

    if not value:
        return None

    if isinstance(value, list):
        return ",".join(str(item) for item in value)

    return str(value)


def bool_value(value):

    return 1 if value else 0


def normalize_id(value):
    """
    Normalize Scryfall/Oracle IDs so database values and JSON
    values compare consistently.
    """

    if value is None:
        return None

    return str(value).lower()


def get_primary_image_url(card):
    """
    Return the normal-sized image URL.

    Single-faced cards normally have image_uris directly on
    the card.

    Multi-faced cards may have image_uris inside card_faces.
    """

    image_uris = card.get("image_uris")

    if image_uris:
        return image_uris.get("normal")

    faces = card.get("card_faces") or []

    for face in faces:

        face_images = face.get("image_uris")

        if face_images:

            image_url = face_images.get("normal")

            if image_url:
                return image_url

    return None


def build_placeholders(count):
    """
    Build placeholders for SQL IN statements.

    Example:
        ?,?,?,?
    """

    return ",".join("?" for _ in range(count))


# ============================================================
# SKIP LOGGING
# ============================================================

def log_skip(
    card,
    reason,
    skipped_file,
    skip_reasons,
    skip_examples_shown
):

    skip_reasons[reason] = (
        skip_reasons.get(reason, 0) + 1
    )

    record = {
        "reason": reason,
        "name": card.get("name"),
        "scryfall_id": card.get("id"),
        "oracle_id": card.get("oracle_id"),
        "object": card.get("object"),
        "layout": card.get("layout"),
        "set": card.get("set"),
        "set_name": card.get("set_name"),
        "collector_number": card.get("collector_number"),
        "lang": card.get("lang"),
        "released_at": card.get("released_at")
    }

    skipped_file.write(
        json.dumps(
            record,
            ensure_ascii=False
        )
        + "\n"
    )

    if skip_examples_shown < MAX_SKIP_EXAMPLES:

        name = record["name"] or "UNKNOWN"
        set_code = record["set"] or "NO SET"
        collector_number = (
            record["collector_number"]
            or "NO NUMBER"
        )

        print(
            f"SKIPPED: {name} | "
            f"Reason: {reason} | "
            f"{set_code} #{collector_number}"
        )

        skip_examples_shown += 1

    return skip_examples_shown


# ============================================================
# LOAD DATABASE CACHES
# ============================================================

def load_caches(cursor):

    print()
    print("Loading existing database IDs into memory...")
    print()

    # --------------------------------------------------------
    # SETS
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT SetCode
        FROM Sets
        """
    )

    sets_cache = {
        row[0]
        for row in cursor.fetchall()
        if row[0] is not None
    }

    print(
        f"Sets:                 "
        f"{len(sets_cache):,}"
    )

    # --------------------------------------------------------
    # NORMAL CARDS
    #
    # Only cards with Oracle IDs belong in this dictionary.
    #
    # OracleId -> CardId
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT
            OracleId,
            CardId
        FROM Cards
        WHERE OracleId IS NOT NULL
        """
    )

    cards_cache = {
        normalize_id(row[0]): row[1]
        for row in cursor.fetchall()
    }

    print(
        f"Oracle cards:         "
        f"{len(cards_cache):,}"
    )

    # --------------------------------------------------------
    # PRINTINGS
    #
    # Store both PrintingId and CardId.
    #
    # ScryfallId -> (PrintingId, CardId)
    #
    # This lets us identify previously imported NULL-Oracle
    # cards on future runs.
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT
            p.ScryfallId,
            p.PrintingId,
            p.CardId,
            c.OracleId
        FROM Printings p
        INNER JOIN Cards c
            ON c.CardId = p.CardId
        WHERE p.ScryfallId IS NOT NULL
        """
    )

    printings_cache = {}

    null_oracle_cards_cache = {}

    for row in cursor.fetchall():

        scryfall_id = normalize_id(
            row[0]
        )

        printing_id = row[1]
        card_id = row[2]
        oracle_id = row[3]

        printings_cache[scryfall_id] = (
            printing_id,
            card_id
        )

        # If the associated Cards row has OracleId NULL,
        # remember which Scryfall object owns that CardId.
        if oracle_id is None:

            null_oracle_cards_cache[
                scryfall_id
            ] = card_id

    print(
        f"Printings:            "
        f"{len(printings_cache):,}"
    )

    print(
        f"NULL-Oracle cards:    "
        f"{len(null_oracle_cards_cache):,}"
    )

    # --------------------------------------------------------
    # IMAGES
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT
            PrintingId,
            ImageType
        FROM CardImages
        """
    )

    images_cache = {
        (
            row[0],
            row[1]
        )
        for row in cursor.fetchall()
    }

    print(
        f"Images:               "
        f"{len(images_cache):,}"
    )

    # --------------------------------------------------------
    # CARD FACES
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT
            PrintingId,
            FaceIndex
        FROM CardFaces
        """
    )

    faces_cache = {
        (
            row[0],
            row[1]
        )
        for row in cursor.fetchall()
    }

    print(
        f"Card faces:           "
        f"{len(faces_cache):,}"
    )

    print()
    print("Cache loading complete.")
    print()

    return (
        sets_cache,
        cards_cache,
        null_oracle_cards_cache,
        printings_cache,
        images_cache,
        faces_cache
    )


# ============================================================
# SET BATCH
# ============================================================

def batch_insert_sets(
    cursor,
    cards,
    sets_cache
):

    rows = []
    batch_codes = set()

    for card in cards:

        set_code = card.get("set")

        if not set_code:
            continue

        if set_code in sets_cache:
            continue

        if set_code in batch_codes:
            continue

        rows.append(
            (
                set_code,
                card.get("set_name"),
                card.get("set_type"),
                card.get("released_at")
            )
        )

        batch_codes.add(
            set_code
        )

    if not rows:
        return 0

    cursor.executemany(
        """
        INSERT INTO Sets
        (
            SetCode,
            SetName,
            SetType,
            ReleaseDate
        )
        VALUES
        (
            ?, ?, ?, ?
        )
        """,
        rows
    )

    sets_cache.update(
        batch_codes
    )

    return len(rows)


# ============================================================
# CARD BATCH
# ============================================================

def batch_insert_cards(
    cursor,
    cards,
    cards_cache,
    null_oracle_cards_cache,
    printings_cache
):
    """
    Insert new Cards rows.

    NORMAL CARDS:
        OracleId identifies the logical card.
        These are batch inserted.

    NULL-ORACLE CARDS:
        ScryfallId identifies the object.
        Each receives its own Cards row where OracleId = NULL.

        These use OUTPUT INSERTED.CardId because there is no
        OracleId available to query the generated CardId later.
    """

    normal_rows = []
    new_oracle_ids = []
    batch_oracle_ids = set()

    null_oracle_added = 0

    for card in cards:

        scryfall_id = normalize_id(
            card.get("id")
        )

        oracle_id = normalize_id(
            card.get("oracle_id")
        )

        # ====================================================
        # NORMAL ORACLE CARD
        # ====================================================

        if oracle_id:

            if oracle_id in cards_cache:
                continue

            if oracle_id in batch_oracle_ids:
                continue

            normal_rows.append(
                (
                    oracle_id,
                    card.get("name"),
                    card.get("mana_cost"),
                    card.get("cmc"),
                    card.get("type_line"),
                    card.get("oracle_text"),
                    card.get("power"),
                    card.get("toughness"),
                    card.get("loyalty"),
                    list_to_string(
                        card.get("colors")
                    ),
                    list_to_string(
                        card.get("color_identity")
                    )
                )
            )

            new_oracle_ids.append(
                oracle_id
            )

            batch_oracle_ids.add(
                oracle_id
            )

            continue

        # ====================================================
        # NULL ORACLE CARD
        # ====================================================

        # If this Scryfall object already has a printing,
        # its Card row already exists.
        if scryfall_id in printings_cache:

            existing = (
                printings_cache[
                    scryfall_id
                ]
            )

            null_oracle_cards_cache[
                scryfall_id
            ] = existing[1]

            continue

        # Already created during this run/batch.
        if (
            scryfall_id
            in null_oracle_cards_cache
        ):
            continue

        # Insert this special object's Cards row and return
        # the generated CardId immediately.
        cursor.execute(
            """
            INSERT INTO Cards
            (
                OracleId,
                Name,
                ManaCost,
                ManaValue,
                TypeLine,
                OracleText,
                Power,
                Toughness,
                Loyalty,
                Colors,
                ColorIdentity
            )

            OUTPUT INSERTED.CardId

            VALUES
            (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            )
            """,
            None,
            card.get("name"),
            card.get("mana_cost"),
            card.get("cmc"),
            card.get("type_line"),
            card.get("oracle_text"),
            card.get("power"),
            card.get("toughness"),
            card.get("loyalty"),
            list_to_string(
                card.get("colors")
            ),
            list_to_string(
                card.get("color_identity")
            )
        )

        row = cursor.fetchone()

        if row is None:

            raise RuntimeError(
                "Failed to retrieve CardId for "
                f"NULL-Oracle card: "
                f"{card.get('name')} "
                f"({scryfall_id})"
            )

        card_id = row[0]

        null_oracle_cards_cache[
            scryfall_id
        ] = card_id

        null_oracle_added += 1

    # ========================================================
    # BATCH INSERT NORMAL ORACLE CARDS
    # ========================================================

    if normal_rows:

        cursor.executemany(
            """
            INSERT INTO Cards
            (
                OracleId,
                Name,
                ManaCost,
                ManaValue,
                TypeLine,
                OracleText,
                Power,
                Toughness,
                Loyalty,
                Colors,
                ColorIdentity
            )
            VALUES
            (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            )
            """,
            normal_rows
        )

        # ----------------------------------------------------
        # Retrieve all generated CardIds in one query.
        # ----------------------------------------------------

        placeholders = build_placeholders(
            len(new_oracle_ids)
        )

        sql = f"""
            SELECT
                OracleId,
                CardId
            FROM Cards
            WHERE OracleId IN
            (
                {placeholders}
            )
        """

        cursor.execute(
            sql,
            *new_oracle_ids
        )

        for row in cursor.fetchall():

            oracle_id = normalize_id(
                row[0]
            )

            cards_cache[
                oracle_id
            ] = row[1]

    return (
        len(normal_rows),
        null_oracle_added
    )


# ============================================================
# PRINTING BATCH
# ============================================================

def batch_insert_printings(
    cursor,
    cards,
    cards_cache,
    null_oracle_cards_cache,
    printings_cache
):

    rows = []

    new_scryfall_ids = []
    batch_scryfall_ids = set()

    for card in cards:

        scryfall_id = normalize_id(
            card.get("id")
        )

        oracle_id = normalize_id(
            card.get("oracle_id")
        )

        if not scryfall_id:
            continue

        # Already imported.
        if scryfall_id in printings_cache:
            continue

        if scryfall_id in batch_scryfall_ids:
            continue

        # ====================================================
        # FIND CARD ID
        # ====================================================

        if oracle_id:

            card_id = cards_cache.get(
                oracle_id
            )

        else:

            card_id = (
                null_oracle_cards_cache.get(
                    scryfall_id
                )
            )

        if card_id is None:

            raise RuntimeError(
                "Could not determine CardId for "
                f"{card.get('name')} | "
                f"Scryfall ID: {scryfall_id} | "
                f"Oracle ID: {oracle_id}"
            )

        rows.append(
            (
                scryfall_id,
                card_id,
                card.get("set"),
                card.get("collector_number"),
                card.get("rarity"),
                card.get("artist"),
                card.get("released_at"),
                card.get("lang"),
                list_to_string(
                    card.get("finishes")
                ),
                card.get("border_color"),
                card.get("frame"),
                bool_value(
                    card.get("full_art")
                ),
                bool_value(
                    card.get("textless")
                ),
                bool_value(
                    card.get("promo")
                )
            )
        )

        new_scryfall_ids.append(
            scryfall_id
        )

        batch_scryfall_ids.add(
            scryfall_id
        )

    if not rows:
        return 0

    # ========================================================
    # FAST BATCH INSERT
    # ========================================================

    cursor.executemany(
        """
        INSERT INTO Printings
        (
            ScryfallId,
            CardId,
            SetCode,
            CollectorNumber,
            Rarity,
            Artist,
            ReleasedAt,
            LanguageCode,
            Finish,
            BorderColor,
            Frame,
            FullArt,
            Textless,
            Promo
        )
        VALUES
        (
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?
        )
        """,
        rows
    )

    # ========================================================
    # RETRIEVE GENERATED PRINTING IDs
    # ========================================================

    placeholders = build_placeholders(
        len(new_scryfall_ids)
    )

    sql = f"""
        SELECT
            ScryfallId,
            PrintingId,
            CardId
        FROM Printings
        WHERE ScryfallId IN
        (
            {placeholders}
        )
    """

    cursor.execute(
        sql,
        *new_scryfall_ids
    )

    for row in cursor.fetchall():

        scryfall_id = normalize_id(
            row[0]
        )

        printings_cache[
            scryfall_id
        ] = (
            row[1],
            row[2]
        )

    return len(rows)


# ============================================================
# IMAGE BATCH
# ============================================================

def batch_insert_images(
    cursor,
    cards,
    printings_cache,
    images_cache
):

    rows = []

    for card in cards:

        scryfall_id = normalize_id(
            card.get("id")
        )

        printing_info = (
            printings_cache.get(
                scryfall_id
            )
        )

        if printing_info is None:
            continue

        printing_id = printing_info[0]

        image_url = (
            get_primary_image_url(
                card
            )
        )

        if not image_url:
            continue

        cache_key = (
            printing_id,
            "normal"
        )

        if cache_key in images_cache:
            continue

        rows.append(
            (
                printing_id,
                "normal",
                image_url,
                None
            )
        )

        images_cache.add(
            cache_key
        )

    if not rows:
        return 0

    cursor.executemany(
        """
        INSERT INTO CardImages
        (
            PrintingId,
            ImageType,
            ImageUrl,
            LocalImagePath
        )
        VALUES
        (
            ?, ?, ?, ?
        )
        """,
        rows
    )

    return len(rows)


# ============================================================
# CARD FACE BATCH
# ============================================================

def batch_insert_faces(
    cursor,
    cards,
    printings_cache,
    faces_cache
):

    rows = []

    for card in cards:

        scryfall_id = normalize_id(
            card.get("id")
        )

        printing_info = (
            printings_cache.get(
                scryfall_id
            )
        )

        if printing_info is None:
            continue

        printing_id = printing_info[0]

        faces = card.get(
            "card_faces"
        )

        if not faces:
            continue

        for face_index, face in enumerate(
            faces
        ):

            cache_key = (
                printing_id,
                face_index
            )

            if cache_key in faces_cache:
                continue

            image_url = None

            face_images = face.get(
                "image_uris"
            )

            if face_images:

                image_url = face_images.get(
                    "normal"
                )

            rows.append(
                (
                    printing_id,
                    face_index,
                    face.get("name"),
                    face.get("mana_cost"),
                    face.get("type_line"),
                    face.get("oracle_text"),
                    face.get("power"),
                    face.get("toughness"),
                    face.get("loyalty"),
                    image_url
                )
            )

            faces_cache.add(
                cache_key
            )

    if not rows:
        return 0

    cursor.executemany(
        """
        INSERT INTO CardFaces
        (
            PrintingId,
            FaceIndex,
            FaceName,
            ManaCost,
            TypeLine,
            OracleText,
            Power,
            Toughness,
            Loyalty,
            ImageUrl
        )
        VALUES
        (
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?
        )
        """,
        rows
    )

    return len(rows)


# ============================================================
# PROCESS ONE BATCH
# ============================================================

def process_batch(
    cursor,
    cards,
    sets_cache,
    cards_cache,
    null_oracle_cards_cache,
    printings_cache,
    images_cache,
    faces_cache
):

    sets_added = batch_insert_sets(
        cursor,
        cards,
        sets_cache
    )

    (
        oracle_cards_added,
        null_oracle_cards_added
    ) = batch_insert_cards(
        cursor,
        cards,
        cards_cache,
        null_oracle_cards_cache,
        printings_cache
    )

    printings_added = (
        batch_insert_printings(
            cursor,
            cards,
            cards_cache,
            null_oracle_cards_cache,
            printings_cache
        )
    )

    images_added = (
        batch_insert_images(
            cursor,
            cards,
            printings_cache,
            images_cache
        )
    )

    faces_added = (
        batch_insert_faces(
            cursor,
            cards,
            printings_cache,
            faces_cache
        )
    )

    return (
        sets_added,
        oracle_cards_added,
        null_oracle_cards_added,
        printings_added,
        images_added,
        faces_added
    )


# ============================================================
# MAIN IMPORT
# ============================================================

def import_cards():

    print()
    print("=" * 72)
    print(
        "MTG CARD DATABASE - HIGH SPEED BATCH IMPORT"
    )
    print("=" * 72)
    print()

    print(
        "Opening SQL Server connection..."
    )

    connection = get_connection()
    cursor = connection.cursor()

    # Faster pyodbc batch inserts.
    cursor.fast_executemany = True

    # Suppress unnecessary SQL row-count messages.
    cursor.execute(
        "SET NOCOUNT ON"
    )

    # ========================================================
    # COUNTERS
    # ========================================================

    input_records = 0
    processed = 0
    skipped = 0

    total_sets_added = 0
    total_oracle_cards_added = 0
    total_null_oracle_cards_added = 0
    total_printings_added = 0
    total_images_added = 0
    total_faces_added = 0

    skip_reasons = {}
    skip_examples_shown = 0

    card_name = "UNKNOWN CARD"
    scryfall_id = "UNKNOWN ID"

    batch = []

    try:

        (
            sets_cache,
            cards_cache,
            null_oracle_cards_cache,
            printings_cache,
            images_cache,
            faces_cache
        ) = load_caches(
            cursor
        )

        print(
            f"Batch size: {BATCH_SIZE:,}"
        )

        print()
        print(
            "Opening Scryfall bulk data..."
        )
        print()

        with open(
            SKIPPED_FILE_PATH,
            "w",
            encoding="utf-8"
        ) as skipped_file:

            with gzip.open(
                FILE_PATH,
                "rt",
                encoding="utf-8"
            ) as file:

                for line in file:

                    input_records += 1

                    card = json.loads(
                        line
                    )

                    card_name = (
                        card.get("name")
                        or "UNKNOWN CARD"
                    )

                    scryfall_id = (
                        card.get("id")
                        or "UNKNOWN ID"
                    )

                    # ========================================
                    # WE NO LONGER SKIP MISSING ORACLE IDs.
                    #
                    # OracleId = NULL is now valid.
                    # ========================================

                    # ========================================
                    # SKIP: MISSING SCRYFALL ID
                    #
                    # We must have this because ScryfallId
                    # uniquely identifies the printing/object.
                    # ========================================

                    if not card.get("id"):

                        skipped += 1

                        skip_examples_shown = log_skip(
                            card,
                            "missing_scryfall_id",
                            skipped_file,
                            skip_reasons,
                            skip_examples_shown
                        )

                        continue

                    # ========================================
                    # SKIP: MISSING NAME
                    #
                    # Cards.Name is NOT NULL in our schema.
                    # ========================================

                    if not card.get("name"):

                        skipped += 1

                        skip_examples_shown = log_skip(
                            card,
                            "missing_name",
                            skipped_file,
                            skip_reasons,
                            skip_examples_shown
                        )

                        continue

                    # ========================================
                    # VALID RECORD
                    # ========================================

                    batch.append(
                        card
                    )

                    processed += 1

                    # ========================================
                    # PROCESS FULL BATCH
                    # ========================================

                    if len(batch) >= BATCH_SIZE:

                        (
                            sets_added,
                            oracle_cards_added,
                            null_oracle_cards_added,
                            printings_added,
                            images_added,
                            faces_added
                        ) = process_batch(
                            cursor,
                            batch,
                            sets_cache,
                            cards_cache,
                            null_oracle_cards_cache,
                            printings_cache,
                            images_cache,
                            faces_cache
                        )

                        connection.commit()

                        total_sets_added += (
                            sets_added
                        )

                        total_oracle_cards_added += (
                            oracle_cards_added
                        )

                        total_null_oracle_cards_added += (
                            null_oracle_cards_added
                        )

                        total_printings_added += (
                            printings_added
                        )

                        total_images_added += (
                            images_added
                        )

                        total_faces_added += (
                            faces_added
                        )

                        print(
                            f"Processed {processed:,} | "
                            f"Skipped {skipped:,} | "
                            f"New cards "
                            f"{total_oracle_cards_added + total_null_oracle_cards_added:,} | "
                            f"NULL Oracle "
                            f"{total_null_oracle_cards_added:,} | "
                            f"New printings "
                            f"{total_printings_added:,}"
                        )

                        batch.clear()

                    # ========================================
                    # OPTIONAL TEST LIMIT
                    # ========================================

                    if (
                        IMPORT_LIMIT is not None
                        and processed >= IMPORT_LIMIT
                    ):
                        break

            # =================================================
            # FINAL PARTIAL BATCH
            # =================================================

            if batch:

                (
                    sets_added,
                    oracle_cards_added,
                    null_oracle_cards_added,
                    printings_added,
                    images_added,
                    faces_added
                ) = process_batch(
                    cursor,
                    batch,
                    sets_cache,
                    cards_cache,
                    null_oracle_cards_cache,
                    printings_cache,
                    images_cache,
                    faces_cache
                )

                connection.commit()

                total_sets_added += (
                    sets_added
                )

                total_oracle_cards_added += (
                    oracle_cards_added
                )

                total_null_oracle_cards_added += (
                    null_oracle_cards_added
                )

                total_printings_added += (
                    printings_added
                )

                total_images_added += (
                    images_added
                )

                total_faces_added += (
                    faces_added
                )

                batch.clear()

        # ====================================================
        # IMPORT COMPLETE
        # ====================================================

        print()
        print("=" * 72)
        print("IMPORT COMPLETE")
        print("=" * 72)
        print()

        print(
            f"Input records read:            "
            f"{input_records:,}"
        )

        print(
            f"Valid records processed:       "
            f"{processed:,}"
        )

        print(
            f"Skipped records:               "
            f"{skipped:,}"
        )

        # ====================================================
        # INSERT SUMMARY
        # ====================================================

        print()
        print(
            "DATABASE INSERT SUMMARY"
        )

        print("-" * 72)

        print(
            f"New Sets inserted:             "
            f"{total_sets_added:,}"
        )

        print(
            f"New Oracle Cards inserted:     "
            f"{total_oracle_cards_added:,}"
        )

        print(
            f"New NULL-Oracle Cards inserted:"
            f" {total_null_oracle_cards_added:,}"
        )

        total_cards_added = (
            total_oracle_cards_added
            + total_null_oracle_cards_added
        )

        print(
            f"Total new Cards inserted:      "
            f"{total_cards_added:,}"
        )

        print(
            f"New Printings inserted:        "
            f"{total_printings_added:,}"
        )

        print(
            f"New Images inserted:           "
            f"{total_images_added:,}"
        )

        print(
            f"New Card Faces inserted:       "
            f"{total_faces_added:,}"
        )

        # ====================================================
        # SKIP SUMMARY
        # ====================================================

        print()
        print("=" * 72)
        print(
            "SKIP REASON SUMMARY"
        )
        print("=" * 72)
        print()

        if not skip_reasons:

            print(
                "No records were skipped."
            )

        else:

            for reason, count in sorted(
                skip_reasons.items()
            ):

                print(
                    f"{reason:<35}"
                    f"{count:>10,}"
                )

        print()

        print(
            f"Skipped-record details: "
            f"{SKIPPED_FILE_PATH}"
        )

        # ====================================================
        # CACHE TOTALS
        # ====================================================

        print()
        print("=" * 72)
        print(
            "DATABASE CACHE TOTALS"
        )
        print("=" * 72)
        print()

        print(
            f"Sets cached:                   "
            f"{len(sets_cache):,}"
        )

        print(
            f"Oracle Cards cached:           "
            f"{len(cards_cache):,}"
        )

        print(
            f"NULL-Oracle Cards cached:      "
            f"{len(null_oracle_cards_cache):,}"
        )

        print(
            f"Printings cached:              "
            f"{len(printings_cache):,}"
        )

        print(
            f"Images cached:                 "
            f"{len(images_cache):,}"
        )

        print(
            f"Card Faces cached:             "
            f"{len(faces_cache):,}"
        )

        print()

    # ========================================================
    # ERROR HANDLING
    # ========================================================

    except Exception as error:

        connection.rollback()

        print()
        print("=" * 72)
        print(
            "IMPORT FAILED"
        )
        print("=" * 72)
        print()

        print(
            f"Failure occurred after "
            f"{processed:,} valid records."
        )

        print()

        print(
            "Last Scryfall record being processed:"
        )

        print(
            "Name:",
            card_name
        )

        print(
            "Scryfall ID:",
            scryfall_id
        )

        print()

        print(
            "Error:"
        )

        print(
            error
        )

        raise

    # ========================================================
    # CLEANUP
    # ========================================================

    finally:

        cursor.close()
        connection.close()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    import_cards()
