import os
import requests


# ============================================================
# TEST CONFIGURATION
# ============================================================

# These are specific names we want to test.
#
# IMPORTANT:
# We are NOT generating every possible 10-character name.
# There are far too many combinations for that to be practical.
#
# Put any 3-16 character Minecraft username you want to test here.
TEST_NAMES = [
    "abcdefghij",
]


# ============================================================
# DISCORD
# ============================================================

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")


def send_discord(title, message):
    """Send a formatted result to Discord."""

    if not DISCORD_WEBHOOK:
        print("ERROR: DISCORD_WEBHOOK is missing.")
        return False

    payload = {
        "embeds": [
            {
                "title": title,
                "description": message
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
        print(f"Discord error: {error}")
        return False

    if response.status_code not in (200, 204):
        print(
            f"Discord returned "
            f"{response.status_code}: "
            f"{response.text}"
        )
        return False

    print("Discord notification sent.")
    return True


# ============================================================
# MINECRAFT LOOKUP
# ============================================================

def check_names(usernames):
    """
    Ask Mojang which of the supplied usernames currently
    resolve to Minecraft profiles.

    The endpoint supports up to 10 usernames per request.
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

    print(f"Mojang HTTP status: {response.status_code}")

    if response.status_code == 429:
        print("Mojang rate-limited the request.")
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
        print("Mojang returned invalid JSON.")
        return None

    taken = set()

    for profile in profiles:
        name = profile.get("name")

        if name:
            taken.add(name.lower())

    return taken


# ============================================================
# MAIN
# ============================================================

def main():

    print("==========================================")
    print("     Minecraft Username Finder TEST")
    print("==========================================")

    print()
    print("Names being tested:")

    for name in TEST_NAMES:
        print(f"  - {name}")

    print()

    taken = check_names(TEST_NAMES)

    if taken is None:
        print("The Minecraft lookup failed.")
        return

    print()
    print("Results:")
    print("------------------------------------------")

    for username in TEST_NAMES:

        if username.lower() in taken:

            print(
                f"{username}: "
                "PROFILE FOUND"
            )

            send_discord(
                "🔴 Minecraft Username Test",
                (
                    f"Username: `{username}`\n\n"
                    "Mojang currently returned a "
                    "Minecraft profile for this name."
                )
            )

        else:

            print(
                f"{username}: "
                "NO PROFILE RETURNED"
            )

            send_discord(
                "🟡 Minecraft Username Test",
                (
                    f"Username: `{username}`\n\n"
                    "Mojang did not return a profile "
                    "for this name.\n\n"
                    "⚠️ This does NOT guarantee that the "
                    "name is immediately claimable. "
                    "It may be unused, on cooldown, or "
                    "associated with a deleted profile."
                )
            )

    print()
    print("Test completed successfully.")


if __name__ == "__main__":
    main()
