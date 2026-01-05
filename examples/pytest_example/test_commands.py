"""
Example pytest tests for MUD commands.

Run with: pytest examples/pytest_example/ -v
"""

import pytest
from mudprod import assert_contains, assert_prompt, assert_line_count


class TestBasicCommands:
    """Test basic MUD commands."""

    def test_look_returns_room(self, client):
        """Test that 'look' returns a room description."""
        response = client.send_command("look")

        assert_prompt(response)
        # Most MUDs show exits in room descriptions
        # Adjust this assertion for your MUD
        assert len(response.lines) > 0, "Look should return some text"

    def test_who_command(self, client):
        """Test that 'who' shows online players."""
        response = client.send_command("who")

        assert_prompt(response)
        # Our test user should appear in who list
        # Adjust for your MUD's who format

    def test_help_command(self, client):
        """Test that 'help' returns help text."""
        response = client.send_command("help")

        assert_prompt(response)
        assert_line_count(response, min_lines=1)

    def test_invalid_command(self, client):
        """Test that invalid commands get an error response."""
        response = client.send_command("xyzzy_not_a_real_command")

        assert_prompt(response)
        # Most MUDs say something like "Huh?" or "Unknown command"
        # Adjust for your MUD's error message


class TestCommunication:
    """Test communication commands."""

    def test_say_command(self, client):
        """Test the say command."""
        response = client.send_command("say Hello, world!")

        assert_prompt(response)
        # Most MUDs echo back what you said
        assert_contains(response, "Hello", case_sensitive=False)


class TestMovement:
    """Test movement commands."""

    def test_cardinal_directions(self, client):
        """Test that cardinal directions work or give sensible errors."""
        for direction in ["north", "south", "east", "west"]:
            response = client.send_command(direction)
            assert_prompt(response)
            # Should either move or say "You can't go that way"
