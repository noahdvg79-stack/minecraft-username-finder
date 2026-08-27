import os
import random
import string
import time
from pathlib import Path

import requests


# ============================================================
# CONFIGURATION
# ============================================================

# Minimum and maximum username length.
#
# Minecraft Java usernames are 3-16 characters.
MIN_LENGTH = 3
MAX_LENGTH = 4


# Characters supported by Minecraft Java usernames.
CHARACTERS = string.ascii_lowercase + string.digits + "_"


# How many random usernames to check per GitHub Actions run.
#
# Each Mojang request can contain up to 10 usernames.
BATCH_SIZE = 10
MAX_BATCHES_PER_RUN = 10


# Delay between API requests.
#
# Keep this reasonable so we don't hammer Mojang.
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
    """Send an available-name candidate to Discord."""

    if not DISCORD_WEBHOOK:
        print("ERROR: DISCORD_WEBHOOK secret is missing.")
        return False

    payload = {
        "embeds": [
            {
                "title": "🟢 Possible Minecraft Username",
                "description": (
                    f"**Username:** `{username}`\n\n"
                    "Mojang did not return a profile for this "
                    "username.\n\n"
                    "⚠️ This is a possible available name, "
                    "not a guarantee. It may be on cooldown "
                    "or otherwise unavailable."
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
# CHECKED NAME DATABASE
# ============================================================

def load_checked():
    """Load usernames that have already been checked."""

    if not CHECKED_FILE.exists():
        return set()

    return {
        line.strip().lower()
        for line in CHECKED_FILE.read_text().splitlines()
        if line.strip()
    }


def save_checked(usernames):
    """Save usernames that were checked."""

    with CHECKED_FILE.open("a") as file:
        for username in usernames:
            file.write(username.lower() + "\n")


def load_found():
    """Load usernames already sent to Discord."""

    if not FOUND_FILE.exists():
        return set()

    return {
        line.strip().lower()
        for line in FOUND_FILE.read_text().splitlines()
        if line.strip()
    }


def save_found(username):
    """Remember a username that was sent to Discord."""

    with FOUND_FILE.open("a") as file:
        file.write(username.lower() + "\n")


# ============================================================
# RANDOM USERNAME GENERATOR
# ============================================================

def generate_random_username():
    """Generate a completely random Minecraft username."""

    length = random.randint(
        MIN_LENGTH,
        MAX_LENGTH
    )

    return "".join(
        random.choice(CHARACTERS)
        for _ in range(length)
    )


def generate_unique_batch(checked):
    """
    Generate a batch of random usernames that haven't
    already been checked.
    """

    usernames = []

    attempts = 0
    maximum_attempts = BATCH_SIZE * 100

    while (
        len(usernames) < BATCH_SIZE
        and attempts < maximum_attempts
    ):

        username = generate_random_username()

        attempts += 1

        if username.lower() in checked:
            continue

        if username.lower() in {
            name.lower()
            for name in usernames
        }:
            continue

        usernames.append(username)

    return usernames


# ============================================================
# MINECRAFT LOOKUP
# ============================================================

def check_batch(usernames):
    """
    Check up to 10 Minecraft usernames.

    Names returned by Mojang currently resolve to profiles.

    Names NOT returned are treated as possible candidates.
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
    print("   Minecraft RANDOM Username Finder")
    print("==========================================")

    print()
    print(
        f"Length range: "
        f"{MIN_LENGTH}-{MAX_LENGTH}"
    )

    print(
        f"Characters: "
        f"{CHARACTERS}"
    )

    print(
        f"Batches this run: "
        f"{MAX_BATCHES_PER_RUN}"
    )

    checked = load_checked()
    found = load_found()

    print()
    print(
        f"Previously checked names: "
        f"{len(checked):,}"
    )

    print(
        f"Previously found candidates: "
        f"{len(found):,}"
    )

    print()

    batches_processed = 0

    while batches_processed < MAX_BATCHES_PER_RUN:

        batch = generate_unique_batch(
            checked
        )

        if not batch:
            print(
                "Could not generate a unique batch."
            )
            break

        print(
            f"Batch {batches_processed + 1}/"
            f"{MAX_BATCHES_PER_RUN}"
        )

        print(
            "Random names:"
        )

        print(
            "  " + ", ".join(batch)
        )

        taken = check_batch(batch)

        if taken is None:

            print(
                "Stopping this run because "
                "the Minecraft lookup failed."
            )

            break

        # ----------------------------------------------------
        # Save everything we successfully checked.
        # ----------------------------------------------------

        save_checked(batch)

        checked.update(
            name.lower()
            for name in batch
        )

        # ----------------------------------------------------
        # Find names that Mojang did NOT return.
        # ----------------------------------------------------

        for username in batch:

            if username.lower() in taken:

                print(
                    f"TAKEN: {username}"
                )

                continue

            # ------------------------------------------------
            # Only possible available names get here.
            # ------------------------------------------------

            print(
                f"POSSIBLE AVAILABLE: "
                f"{username}"
            )

            if username.lower() not in found:

                if send_discord(username):

                    save_found(username)

                    found.add(
                        username.lower()
                    )

        batches_processed += 1

        if batches_processed >= MAX_BATCHES_PER_RUN:
            break

        time.sleep(
            DELAY_BETWEEN_REQUESTS
        )

    print()
    print("==========================================")
    print("Run complete.")
    print(
        f"Total checked this run: "
        f"{batches_processed * BATCH_SIZE}"
    )
    print(
        f"Total names remembered: "
        f"{len(checked):,}"
    )
    print("==========================================")


if __name__ == "__main__":
    main()
