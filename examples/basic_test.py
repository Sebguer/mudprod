"""
Basic example of using mudprod to test a MUD server.

This example shows:
1. Connecting to a server
2. Logging in with a custom login flow
3. Sending commands and validating responses
4. Using assertions

Adapt the HOST, PORT, and login steps to match your MUD.
"""

from mudprod import (
    MUDClient,
    LoginConfig,
    PromptConfig,
    assert_contains,
    assert_prompt,
)

# Configure for your MUD
HOST = "localhost"
PORT = 4000


def main():
    # Optional: customize prompt detection
    prompt_config = PromptConfig(
        patterns=[r">\s*$", r":\s*$"],
        end_chars=">:",
    )

    # Create client
    client = MUDClient(HOST, PORT, prompt_config=prompt_config)

    print(f"Connecting to {HOST}:{PORT}...")
    if not client.connect():
        print("Failed to connect!")
        return

    print("Connected! Logging in...")

    # Configure login flow for your MUD
    # These are example steps - adjust for your MUD's login sequence
    login_config = LoginConfig(
        steps=[
            # Each tuple: (pattern to wait for, text to send)
            ("name", "testuser"),      # Wait for "name", send username
            ("password", "testpass"),  # Wait for "password", send password
        ],
        success_patterns=[
            r"Welcome",
            r">\s*$",
        ],
        failure_patterns=[
            r"[Ii]nvalid",
            r"[Ff]ailed",
        ],
    )

    if not client.login(login_config):
        print("Login failed!")
        client.disconnect()
        return

    print("Logged in! Testing commands...")

    # Test 'look' command
    response = client.send_command("look")
    print(f"\n=== LOOK ===\n{response.clean}")

    try:
        assert_prompt(response)
        print("[PASS] Prompt detected")
    except AssertionError as e:
        print(f"[FAIL] {e}")

    # Test 'who' command
    response = client.send_command("who")
    print(f"\n=== WHO ===\n{response.clean}")

    # Test 'help' command
    response = client.send_command("help")
    print(f"\n=== HELP ===\n{response.clean[:500]}...")

    # Clean up
    client.send_command("quit")
    client.disconnect()
    print("\nDone!")


if __name__ == "__main__":
    main()
