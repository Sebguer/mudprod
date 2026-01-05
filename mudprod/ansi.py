"""
ANSI escape code and telnet sequence handling for MUD output.

MUD servers typically use ANSI escape sequences for colors and formatting.
This module strips them for clean text comparison in tests.
"""

import re

# Standard ANSI escape sequence pattern (colors, formatting)
ANSI_ESCAPE_PATTERN = re.compile(r'\x1b\[[0-9;]*m')

# Extended ANSI (cursor movement, etc.)
ANSI_EXTENDED_PATTERN = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')

# Telnet IAC sequences (0xFF followed by command bytes)
TELNET_PATTERN = re.compile(r'[\xff][\xfb-\xfe].|\xff\xff')

# Bell character
BELL_PATTERN = re.compile(r'\x07')

# Carriage return (often paired with newlines)
CR_PATTERN = re.compile(r'\r')


def strip_ansi(text: str) -> str:
    """Remove all ANSI escape sequences from text."""
    text = ANSI_ESCAPE_PATTERN.sub('', text)
    text = ANSI_EXTENDED_PATTERN.sub('', text)
    return text


def strip_telnet_codes(text: str) -> str:
    """Remove telnet IAC/negotiation sequences."""
    return TELNET_PATTERN.sub('', text)


def strip_bell(text: str) -> str:
    """Remove bell characters."""
    return BELL_PATTERN.sub('', text)


def clean_output(text: str) -> str:
    """
    Fully clean MUD output for comparison.

    Removes ANSI codes, telnet sequences, bells, and normalizes line endings.
    """
    text = strip_telnet_codes(text)
    text = strip_ansi(text)
    text = strip_bell(text)
    text = CR_PATTERN.sub('', text)
    return text


def normalize_whitespace(text: str) -> str:
    """Normalize line endings and collapse multiple blank lines."""
    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # Collapse multiple blank lines to single
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
