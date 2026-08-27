import itertools
import json
import os
import string
import time
from pathlib import Path

import requests


# ============================================================
# CONFIG
# ============================================================

# How many characters to check.
# Start with 3. You can later add 4, but 4-character names
# create 456,976 combinations with letters only.
LENGTHS = [3]

# Characters allowed in usernames.
# Minecraft usernames use letters, numbers and underscores.
CHARACTERS = string.ascii_lowercase + string.digits

# Set to True if you want underscores included.
USE_UNDERSCORE = False

# Maximum number of usernames sent to Mojang per request.
BATCH_SIZE = 10

# Seconds to wait between API requests.
# Keep this conservative.
DELAY_BETWEEN_REQUESTS = 2

# Maximum number of batches to process during one GitHub Actions run.
# This prevents the workflow from running forever.
MAX_BATCHES_PER_RUN = 10

# Files used to remember progress.
PROGRESS_FILE = Path("progress.json")
FOUND_FILE = Path("found.txt")


# ============================================================
# DISCORD
# ============================================================

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")


def send_discord(username):
    if not DISCORD_WEBHOOK:
        print("DISCORD_WEBHOOK secret is missing.")
        return

    message = {
        "content": f"🎉 **Minecraft username found:** `{username}`"
    }

    response = requests.post(
        DISCORD_WEBHOOK,
        json=message,
        timeout=15
    )

    if response.status_code not in (200, 204):
        print(
            f"Discord error: {response.status_code} "
            f"{response.text}"
        )


# ============================================================
# PROGRESS
# ============================================================

def load_progress():
    if not PROGRESS_FILE.exists():
        return {
            "length_index": 0,
            "combination_index": 0
        }

    try:
        return json.loads(PROGRESS_FILE.read_text())
    except Exception:
        return {
            "length_index": 0,
            "combination_index": 0
        }


def save_progress(length_index, combination_index):
    PROGRESS_FILE.write_text(
        json.dumps(
            {
                "length_index": length_index,
                "combination_index": combination_index
            },
            indent=2
        )
    )


def load_found():
    if not FOUND_FILE.exists():
        return set()

    return {
        line.strip().lower()
        for line in FOUND_FILE.read_text().splitlines()
        if line.strip()
    }


def save_found(username):
    with FOUND_FILE.open("a") as file:
        file.write(username + "\n")


# ============================================================
# MINECRAFT LOOKUP
# ============================================================

def check_batch(usernames):
    """
    Mojang's public endpoint accepts up to 10 usernames at once.

    It returns profiles that currently resolve to Minecraft
    usernames. Names not returned are candidates for further
    investigation, but are NOT guaranteed to be immediately
    claimable.
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
        print(f"Network error: {error}")
        return None

    if response.status_code == 429:
        print("Mojang rate limit reached. Stopping this run.")
        return None

    if response.status_code != 200:
        print(
            f"Mojang API error: "
            f"{response.status_code} {response.text}"
        )
        return None

    try:
        profiles = response.json()
    except Exception:
        print("Could not read Mojang response.")
        return None

    taken = {
        profile["name"].lower()
        for profile in profiles
        if "name" in profile
    }

    return taken


# ============================================================
# NAME GENERATOR
# ============================================================

def get_characters():
    chars = CHARACTERS

    if USE_UNDERSCORE:
        chars += "_"

    return chars


def generate_names(length):
    characters = get_characters()

    for combination in itertools.product(
        characters,
        repeat=length
    ):
        yield "".join(combination)


# ============================================================
# MAIN
# ============================================================

def main():
    print("======================================")
    print(" Minecraft Username Finder")
    print("======================================")

    if not DISCORD_WEBHOOK:
        print("WARNING: DISCORD_WEBHOOK is not configured.")

    progress = load_progress()
    found = load_found()

    length_index = progress["length_index"]
    combination_index = progress["combination_index"]

    batches_processed = 0

    for current_length_index in range(
        length_index,
        len(LENGTHS)
    ):
        length = LENGTHS[current_length_index]

        print(f"\nChecking {length}-character usernames...")

        generator = generate_names(length)

        # Resume from where the previous cloud run stopped.
        start_index = (
            combination_index
            if current_length_index == length_index
            else 0
        )

        for _ in range(start_index):
            try:
                next(generator)
            except StopIteration:
                break

        batch = []

        for username in generator:
            batch.append(username)

            if len(batch) < BATCH_SIZE:
                continue

            batches_processed += 1

            print(
                f"Checking batch #{batches_processed}: "
                f"{batch[0]} -> {batch[-1]}"
            )

            taken = check_batch(batch)

            if taken is None:
                save_progress(
                    current_length_index,
                    combination_index + len(batch)
                )
                return

            # Names returned by Mojang currently resolve to profiles.
            # Anything not returned is a candidate.
            for candidate in batch:
                if candidate.lower() not in taken:
                    if candidate.lower() not in found:
                        print(
                            f"Candidate found: {candidate}"
                        )

                        send_discord(candidate)
                        save_found(candidate)
                        found.add(candidate.lower())

            combination_index += len(batch)

            save_progress(
                current_length_index,
                combination_index
            )

            batch = []

            if batches_processed >= MAX_BATCHES_PER_RUN:
                print(
                    "\nMaximum batches reached. "
                    "GitHub Actions will continue from here "
                    "on the next scheduled run."
                )
                return

            time.sleep(DELAY_BETWEEN_REQUESTS)

        # Handle final partial batch.
        if batch:
            batches_processed += 1

            print(
                f"Checking final batch: "
                f"{batch[0]} -> {batch[-1]}"
            )

            taken = check_batch(batch)

            if taken is None:
                save_progress(
                    current_length_index,
                    combination_index + len(batch)
                )
                return

            for candidate in batch:
                if candidate.lower() not in taken:
                    if candidate.lower() not in found:
                        print(
                            f"Candidate found: {candidate}"
                        )

                        send_discord(candidate)
                        save_found(candidate)
                        found.add(candidate.lower())

            combination_index += len(batch)

        # Move to next username length.
        save_progress(
            current_length_index + 1,
            0
        )

        combination_index = 0

    print("\nFinished all configured names.")


if __name__ == "__main__":
    main()
