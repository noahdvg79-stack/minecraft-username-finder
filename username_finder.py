import os
import random
import string
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


USERNAME_LENGTH = 3
CHARACTERS = string.ascii_lowercase + string.digits + "_"
BATCH_SIZE = 10
DELAY_BETWEEN_REQUESTS = 1.0

CHECKED_FILE = Path("checked.txt")
FOUND_FILE = Path("found.txt")

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")


def send_discord(username):
    if not DISCORD_WEBHOOK:
        print("ERROR: DISCORD_WEBHOOK secret is missing.")
        return

    found_time = datetime.now(timezone.utc).strftime(
        "%d %B %Y, %H:%M:%S UTC"
    )

    message = (
        f"🎉 Minecraft username found: `{username}`\n"
        f"Found: {found_time}"
    )

    try:
        response = requests.post(
            DISCORD_WEBHOOK,
            json={"content": message},
            timeout=15
        )

        if response.status_code not in (200, 204):
            print(
                f"Discord error: {response.status_code} "
                f"{response.text}"
            )

    except requests.RequestException as error:
        print(f"Discord network error: {error}")


def load_names(filename):
    if not filename.exists():
        return set()

    return {
        line.strip().lower()
        for line in filename.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    }


def save_name(filename, username):
    with filename.open("a", encoding="utf-8") as file:
        file.write(username.lower() + "\n")


def check_batch(usernames):
    url = "https://api.mojang.com/profiles/minecraft"

    try:
        response = requests.post(
            url,
            json=usernames,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "MinecraftUsernameFinder/1.0"
            },
            timeout=20
        )
    except requests.RequestException as error:
        print(f"Network error: {error}")
        return None

    print(f"Mojang HTTP status: {response.status_code}")

    if response.status_code == 429:
        print("Mojang rate limit reached.")
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

    return {
        profile["name"].lower()
        for profile in profiles
        if "name" in profile
    }


def random_username():
    return "".join(
        random.choice(CHARACTERS)
        for _ in range(USERNAME_LENGTH)
    )


def generate_random_batch(checked):
    batch = []

    while len(batch) < BATCH_SIZE:
        username = random_username()

        if username in checked:
            continue

        if username in batch:
            continue

        batch.append(username)

    return batch


def main():
    print("=" * 50)
    print("   Minecraft 3-Letter Username Finder")
    print("=" * 50)
    print()
    print("Username length: EXACTLY 3")
    print(f"Characters: {CHARACTERS}")
    print(f"Batch size: {BATCH_SIZE}")
    print("Mode: RANDOM")
    print("Mode: RUN FOREVER")
    print()

    checked = load_names(CHECKED_FILE)
    found = load_names(FOUND_FILE)

    total_combinations = len(CHARACTERS) ** USERNAME_LENGTH

    print(f"Total possible combinations: {total_combinations:,}")
    print(f"Previously checked: {len(checked):,}")
    print(f"Previously found: {len(found):,}")
    print()

    batch_number = 0

    while True:
        if len(checked) >= total_combinations:
            print("Every possible 3-character name has been checked.")
            break

        batch_number += 1
        batch = generate_random_batch(checked)

        print(f"Batch #{batch_number}")
        print("Random names:")
        print("  " + ", ".join(batch))

        taken = check_batch(batch)

        if taken is None:
            print("Request failed. Waiting 10 seconds...")
            time.sleep(10)
            continue

        for username in batch:
            username_lower = username.lower()

            if username_lower in taken:
                print(f"TAKEN: {username}")
            else:
                print(f"POSSIBLY AVAILABLE: {username}")

                if username_lower not in found:
                    send_discord(username)
                    save_name(FOUND_FILE, username)
                    found.add(username_lower)

            if username_lower not in checked:
                save_name(CHECKED_FILE, username)
                checked.add(username_lower)

        print(
            f"Progress: {len(checked):,}/"
            f"{total_combinations:,}"
        )
        print()

        time.sleep(DELAY_BETWEEN_REQUESTS)


if __name__ == "__main__":
    main()
