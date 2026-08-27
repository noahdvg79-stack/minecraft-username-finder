import itertools
import json
import os
import string
import time
from pathlib import Path

import requests


# ============================================================
# CONFIGURATION
# ============================================================

# Username lengths to scan.
#
# Start with 3.
#
# IMPORTANT:
# 3 characters = 37^3 = 50,653 combinations
# 4 characters = 37^4 = 1,874,161 combinations
#
# We will make the scanner continue where it left off.
LENGTHS = [3]


# Supported Minecraft Java username characters:
#
# a-z
# 0-9
# _
#
# Minecraft username lookup is case-insensitive, so checking
# uppercase versions separately is unnecessary.
CHARACTERS = string.ascii_lowercase + string.digits + "_"


# Mojang's public profile lookup accepts up to 10 usernames.
BATCH_SIZE = 10


# Delay between requests.
#
# Keep this conservative to reduce the chance of rate limiting.
DELAY_BETWEEN_REQUESTS = 2


# Maximum number of API batches during one GitHub Actions run.
#
# 10 batches x 10 usernames = 100 usernames per run.
MAX_BATCHES_PER_RUN = 10


# ============================================================
# FILES
# ============================================================

PROGRESS_FILE = Path("progress.json")

# Names that have already generated an alert.
FOUND_FILE = Path("found.txt")


# ============================================================
# DISCORD
# ============================================================

# This comes from the GitHub Actions secret.
#
# DO NOT put the actual webhook URL in this file.
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")


def send_discord(username):
    """Send a username notification to Discord."""

    if not DISCORD_WEBHOOK:
        print("ERROR: DISCORD_WEBHOOK secret is missing.")
        return False

    message = {
        "content": (
            "🎉 **Minecraft username candidate found!**\n"
            f"Username: `{username}`\n"
            "\n"
            "⚠️ This name was not found in Mojang's public "
            "profile lookup. It is a candidate and is NOT "
            "guaranteed to be immediately claimable."
        )
    }

    try:
        response = requests.post(
            DISCORD_WEBHOOK,
            json=message,
            timeout=15
        )
    except requests.RequestException as error:
        print(f"Discord network error: {error}")
        return False

    if response.status_code in (200, 204):
        print(f"Discord notification sent for: {username}")
        return True

    print(
        f"Discord error: {response.status_code} "
        f"{response.text}"
    )

    return False


# ============================================================
# PROGRESS
# ============================================================

def load_progress():
    """Load the scanner's saved position."""

    if not PROGRESS_FILE.exists():
        return {
            "length_index": 0,
            "combination_index": 0
        }

    try:
        data = json.loads(
            PROGRESS_FILE.read_text()
        )

        return {
            "length_index": int(
                data.get("length_index", 0)
            ),
            "combination_index": int(
                data.get("combination_index", 0)
            )
        }

    except (ValueError, TypeError, json.JSONDecodeError):
        print("Invalid progress file. Starting from the beginning.")

        return {
            "length_index": 0,
            "combination_index": 0
        }


def save_progress(length_index, combination_index):
    """Save the scanner's current position."""

    data = {
        "length_index": length_index,
        "combination_index": combination_index
    }

    PROGRESS_FILE.write_text(
        json.dumps(data, indent=2)
    )


def load_found():
    """Load usernames that have already generated alerts."""

    if not FOUND_FILE.exists():
        return set()

    return {
        line.strip().lower()
        for line in FOUND_FILE.read_text().splitlines()
        if line.strip()
    }


def save_found(username):
    """Remember a username that generated an alert."""

    with FOUND_FILE.open("a") as file:
        file.write(username.lower() + "\n")


# ============================================================
# MINECRAFT API
# ============================================================

def check_batch(usernames):
    """
    Check a batch of Minecraft usernames using Mojang's
    public profile lookup endpoint.

    Names returned by Mojang currently resolve to profiles.

    Names NOT returned are treated as CANDIDATES only.
    They are NOT guaranteed to be immediately claimable.
    """

    url = "https://api.mojang.com/profiles/minecraft"

    try:
        response = requests.post(
            url,
            json=usernames,
            headers={
                "Content-Type": "application/json"
            },
            timeout=20
        )

    except requests.RequestException as error:
        print(f"Mojang network error: {error}")
        return None

    if response.status_code == 429:
        print(
            "Mojang rate limit reached. "
            "Stopping this run."
        )
        return None

    if response.status_code != 200:
        print(
            f"Mojang API error: "
            f"{response.status_code} "
            f"{response.text}"
        )
        return None

    try:
        profiles = response.json()

    except ValueError:
        print("Could not read Mojang API response.")
        return None

    taken = set()

    for profile in profiles:
        name = profile.get("name")

        if name:
            taken.add(name.lower())

    return taken


# ============================================================
# NAME GENERATOR
# ============================================================

def generate_names(length):
    """Generate every username combination of a given length."""

    for combination in itertools.product(
        CHARACTERS,
        repeat=length
    ):
        yield "".join(combination)


# ============================================================
# MAIN
# ============================================================

def main():

    print("==========================================")
    print("     Minecraft Username Finder")
    print("==========================================")

    print(f"Lengths: {LENGTHS}")
    print(f"Characters: {CHARACTERS}")
    print(f"Batch size: {BATCH_SIZE}")
    print(
        f"Maximum batches this run: "
        f"{MAX_BATCHES_PER_RUN}"
    )

    if not DISCORD_WEBHOOK:
        print()
        print(
            "WARNING: DISCORD_WEBHOOK is not configured."
        )

    progress = load_progress()
    found = load_found()

    length_index = progress["length_index"]
    combination_index = progress["combination_index"]

    batches_processed = 0

    # --------------------------------------------------------
    # Process each configured username length.
    # --------------------------------------------------------

    for current_length_index in range(
        length_index,
        len(LENGTHS)
    ):

        length = LENGTHS[current_length_index]

        print()
        print(
            f"Checking {length}-character usernames..."
        )

        total_combinations = len(CHARACTERS) ** length

        print(
            f"Total combinations for this length: "
            f"{total_combinations:,}"
        )

        generator = generate_names(length)

        # ----------------------------------------------------
        # Resume from previous GitHub Actions run.
        # ----------------------------------------------------

        start_index = (
            combination_index
            if current_length_index == length_index
            else 0
        )

        if start_index > 0:
            print(
                f"Resuming from combination "
                f"{start_index:,}..."
            )

            for _ in range(start_index):
                try:
                    next(generator)
                except StopIteration:
                    break

        batch = []

        # ----------------------------------------------------
        # Generate batches.
        # ----------------------------------------------------

        for username in generator:

            batch.append(username)

            if len(batch) < BATCH_SIZE:
                continue

            batches_processed += 1

            print(
                f"Batch {batches_processed}/"
                f"{MAX_BATCHES_PER_RUN}: "
                f"{batch[0]} -> {batch[-1]}"
            )

            taken = check_batch(batch)

            # ------------------------------------------------
            # If the API fails or rate-limits us, stop.
            # Progress is saved so the next run continues.
            # ------------------------------------------------

            if taken is None:

                combination_index += len(batch)

                save_progress(
                    current_length_index,
                    combination_index
                )

                print(
                    "Progress saved. "
                    "The next run will continue from here."
                )

                return

            # ------------------------------------------------
            # Find candidates.
            # ------------------------------------------------

            for candidate in batch:

                if candidate.lower() not in taken:

                    if candidate.lower() not in found:

                        print(
                            f"Candidate found: "
                            f"{candidate}"
                        )

                        if send_discord(candidate):
                            save_found(candidate)
                            found.add(
                                candidate.lower()
                            )

            # ------------------------------------------------
            # Save progress after every successful batch.
            # ------------------------------------------------

            combination_index += len(batch)

            save_progress(
                current_length_index,
                combination_index
            )

            batch = []

            # ------------------------------------------------
            # Stop after the configured number of batches.
            # ------------------------------------------------

            if batches_processed >= MAX_BATCHES_PER_RUN:

                print()
                print(
                    "Maximum batches reached."
                )

                print(
                    "Progress has been saved."
                )

                print(
                    "GitHub Actions will continue "
                    "from here on the next run."
                )

                return

            time.sleep(
                DELAY_BETWEEN_REQUESTS
            )

        # ----------------------------------------------------
        # Process a final partial batch.
        # ----------------------------------------------------

        if batch:

            batches_processed += 1

            print(
                f"Checking final batch: "
                f"{batch[0]} -> {batch[-1]}"
            )

            taken = check_batch(batch)

            if taken is None:

                combination_index += len(batch)

                save_progress(
                    current_length_index,
                    combination_index
                )

                return

            for candidate in batch:

                if candidate.lower() not in taken:

                    if candidate.lower() not in found:

                        print(
                            f"Candidate found: "
                            f"{candidate}"
                        )

                        if send_discord(candidate):
                            save_found(candidate)
                            found.add(
                                candidate.lower()
                            )

            combination_index += len(batch)

        # ----------------------------------------------------
        # Finished this username length.
        # ----------------------------------------------------

        save_progress(
            current_length_index + 1,
            0
        )

        combination_index = 0

        print(
            f"Finished all {length}-character "
            "combinations."
        )

    print()
    print("==========================================")
    print("Finished all configured username lengths.")
    print("==========================================")


if __name__ == "__main__":
    main()
