import os
import random
import string
import time
from pathlib import Path

import requests


# ============================================================
# CONFIGURATION
# ============================================================

# EXACTLY 3 CHARACTERS
USERNAME_LENGTH = 3

# Minecraft Java username characters
CHARACTERS = string.ascii_lowercase + string.digits + "_"

# Mojang batch size
BATCH_SIZE = 10

# Wait between Mojang requests
DELAY_BETWEEN_REQUESTS = 2


# ============================================================
# FILES
# ============================================================

CHECKED_FILE = Path("checked.txt")
FOUND_FILE = Path("found.txt")


# ============================================================
# DISCORD
# ============================================================

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")


def send_discord(username):

    if not DISCORD_WEBHOOK:
        print("ERROR: DISCORD_WEBHOOK is missing.")
        return False

    payload = {
        "embeds": [
            {
                "title": "🟢 Possible 3-Letter Minecraft Username",
                "description": (
                    f"**Username:** `{username}`\n\n"
                    "Mojang did not return a profile for "
                    "this username.\n\n"
                    "⚠️ This is a possible candidate, "
                    "not a guarantee that the name can "
                    "immediately be claimed."
                )
            }
        ]
    }

    try:
        response = requests.post(
            DISCORD_WEBHOOK,
            json=payload,
            timeout=15
        )

    except requests.RequestException as error:
        print(f"Discord network error: {error}")
        return False

    if response.status_code not in (200, 204):
        print(
            f"Discord error: "
            f"{response.status_code} "
            f"{response.text}"
        )
        return False

    print(
        f"Discord notification sent: {username}"
    )

    return True


# ============================================================
# DATABASE
# ============================================================

def load_checked():

    if not CHECKED_FILE.exists():
        return set()

    return {
        line.strip().lower()
        for line in CHECKED_FILE.read_text().splitlines()
        if line.strip()
    }


def save_checked(usernames):

    with CHECKED_FILE.open("a") as file:

        for username in usernames:
            file.write(
                username.lower() + "\n"
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
        file.write(
            username.lower() + "\n"
        )


# ============================================================
# RANDOM USERNAME GENERATOR
# ============================================================

def generate_random_username():

    return "".join(
        random.choice(CHARACTERS)
        for _ in range(USERNAME_LENGTH)
    )


def generate_unique_batch(checked):

    usernames = []
    batch_lower = set()

    attempts = 0

    while len(usernames) < BATCH_SIZE:

        username = generate_random_username()

        username_lower = username.lower()

        attempts += 1

        if username_lower in checked:
            continue

        if username_lower in batch_lower:
            continue

        usernames.append(username)

        batch_lower.add(username_lower)

    return usernames


# ============================================================
# MINECRAFT LOOKUP
# ============================================================

def check_batch(usernames):

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

        print(
            f"Mojang network error: {error}"
        )

        return None

    print(
        f"Mojang HTTP status: "
        f"{response.status_code}"
    )

    if response.status_code == 429:

        print(
            "Mojang rate limit reached."
        )

        return None

    if response.status_code != 200:

        print(
            f"Mojang API error: "
            f"{response.text}"
        )

        return None

    try:

        profiles = response.json()

    except ValueError:

        print(
            "Mojang returned invalid JSON."
        )

        return None

    taken = set()

    for profile in profiles:

        name = profile.get("name")

        if name:
            taken.add(
                name.lower()
            )

    return taken


# ============================================================
# MAIN
# ============================================================

def main():

    print("==========================================")
    print(" Minecraft 3-Letter Username Finder")
    print(" CONTINUOUS MODE")
    print("==========================================")

    print()

    print(
        "Username length: EXACTLY 3"
    )

    print(
        f"Characters: {CHARACTERS}"
    )

    print(
        "Mode: RUN UNTIL GITHUB STOPS THE JOB"
    )

    checked = load_checked()
    found = load_found()

    print()

    print(
        f"Previously checked: "
        f"{len(checked):,}"
    )

    print(
        f"Previously found: "
        f"{len(found):,}"
    )

    print()

    batch_number = 0

    while True:

        # ----------------------------------------------------
        # Check whether all 3-character combinations
        # have eventually been exhausted.
        # ----------------------------------------------------

        total_possible = (
            len(CHARACTERS)
            ** USERNAME_LENGTH
        )

        if len(checked) >= total_possible:

            print()
            print(
                "=========================================="
            )

            print(
                "ALL 3-CHARACTER NAMES HAVE BEEN CHECKED."
            )

            print(
                "=========================================="
            )

            break

        # ----------------------------------------------------
        # Generate a completely random unused batch.
        # ----------------------------------------------------

        batch = generate_unique_batch(
            checked
        )

        batch_number += 1

        print()
        print(
            f"Batch #{batch_number}"
        )

        print(
            "Random names:"
        )

        print(
            "  " + ", ".join(batch)
        )

        # ----------------------------------------------------
        # Ask Mojang.
        # ----------------------------------------------------

        taken = check_batch(batch)

        # ----------------------------------------------------
        # If Mojang fails, stop this run.
        # GitHub can start it again later.
        # ----------------------------------------------------

        if taken is None:

            print()

            print(
                "Mojang lookup failed or was "
                "rate-limited."
            )

            print(
                "Stopping this run safely."
            )

            break

        # ----------------------------------------------------
        # Remember every checked name.
        # ----------------------------------------------------

        save_checked(batch)

        checked.update(
            username.lower()
            for username in batch
        )

        # ----------------------------------------------------
        # ONLY send possible candidates to Discord.
        # ----------------------------------------------------

        for username in batch:

            username_lower = username.lower()

            if username_lower in taken:

                print(
                    f"TAKEN: {username}"
                )

                continue

            print(
                f"POSSIBLE AVAILABLE: "
                f"{username}"
            )

            if username_lower not in found:

                if send_discord(username):

                    save_found(username)

                    found.add(
                        username_lower
                    )

        # ----------------------------------------------------
        # Show progress.
        # ----------------------------------------------------

        print(
            f"Progress: "
            f"{len(checked):,}/"
            f"{total_possible:,}"
        )

        # ----------------------------------------------------
        # Wait before the next request.
        # ----------------------------------------------------

        time.sleep(
            DELAY_BETWEEN_REQUESTS
        )


if __name__ == "__main__":
    main()
