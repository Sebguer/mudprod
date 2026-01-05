"""
mudprod - Integration testing framework for MUD servers.

Connect to MUD servers via telnet, send commands, and validate responses.
"""

__version__ = "0.1.0"

from .client import MUDClient, PromptConfig, LoginConfig, quick_connect
from .response import MUDResponse
from .ansi import clean_output, strip_ansi, strip_telnet_codes
from .assertions import (
    assert_contains,
    assert_not_contains,
    assert_matches,
    assert_prompt,
    assert_line_count,
    MUDAssertionError,
)

__all__ = [
    "MUDClient",
    "MUDResponse",
    "PromptConfig",
    "LoginConfig",
    "quick_connect",
    "clean_output",
    "strip_ansi",
    "strip_telnet_codes",
    "assert_contains",
    "assert_not_contains",
    "assert_matches",
    "assert_prompt",
    "assert_line_count",
    "MUDAssertionError",
]
