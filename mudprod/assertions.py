"""
Custom assertion helpers for MUD testing.

These assertions provide clear error messages with context
when tests fail.
"""

import re
from typing import Union, Optional

from .response import MUDResponse


class MUDAssertionError(AssertionError):
    """Custom assertion error with MUD context."""
    pass


def _get_text(response: Union[MUDResponse, str]) -> str:
    """Extract clean text from response or string."""
    if isinstance(response, MUDResponse):
        return response.clean
    return response


def assert_contains(
    response: Union[MUDResponse, str],
    pattern: str,
    msg: str = "",
    regex: bool = False,
    case_sensitive: bool = True
) -> None:
    """
    Assert that response contains pattern.

    Args:
        response: MUDResponse or string to check
        pattern: String or regex pattern to find
        msg: Additional context for failure message
        regex: Treat pattern as regex
        case_sensitive: Whether to do case-sensitive matching

    Raises:
        MUDAssertionError: If pattern not found
    """
    text = _get_text(response)

    if not case_sensitive:
        check_text = text.lower()
        check_pattern = pattern if regex else pattern.lower()
    else:
        check_text = text
        check_pattern = pattern

    if regex:
        flags = 0 if case_sensitive else re.IGNORECASE
        if not re.search(check_pattern, text, flags):
            raise MUDAssertionError(
                f"Pattern '{pattern}' not found in response. {msg}\n"
                f"Response:\n{text[:500]}"
            )
    else:
        if check_pattern not in check_text:
            raise MUDAssertionError(
                f"'{pattern}' not found in response. {msg}\n"
                f"Response:\n{text[:500]}"
            )


def assert_not_contains(
    response: Union[MUDResponse, str],
    pattern: str,
    msg: str = "",
    regex: bool = False,
    case_sensitive: bool = True
) -> None:
    """
    Assert that response does NOT contain pattern.

    Args:
        response: MUDResponse or string to check
        pattern: String or regex pattern that should not be present
        msg: Additional context for failure message
        regex: Treat pattern as regex
        case_sensitive: Whether to do case-sensitive matching

    Raises:
        MUDAssertionError: If pattern is found
    """
    text = _get_text(response)

    if not case_sensitive:
        check_text = text.lower()
        check_pattern = pattern if regex else pattern.lower()
    else:
        check_text = text
        check_pattern = pattern

    if regex:
        flags = 0 if case_sensitive else re.IGNORECASE
        if re.search(check_pattern, text, flags):
            raise MUDAssertionError(
                f"Pattern '{pattern}' was found but should not be present. {msg}\n"
                f"Response:\n{text[:500]}"
            )
    else:
        if check_pattern in check_text:
            raise MUDAssertionError(
                f"'{pattern}' was found but should not be present. {msg}\n"
                f"Response:\n{text[:500]}"
            )


def assert_matches(
    response: Union[MUDResponse, str],
    regex_pattern: str,
    msg: str = "",
    flags: int = 0
) -> re.Match:
    """
    Assert response matches regex and return match object.

    Args:
        response: MUDResponse or string to check
        regex_pattern: Regex pattern to match
        msg: Additional context for failure message
        flags: Regex flags (e.g., re.IGNORECASE)

    Returns:
        The match object for extracting groups

    Raises:
        MUDAssertionError: If pattern doesn't match
    """
    text = _get_text(response)

    match = re.search(regex_pattern, text, flags)
    if not match:
        raise MUDAssertionError(
            f"Response does not match pattern '{regex_pattern}'. {msg}\n"
            f"Response:\n{text[:500]}"
        )
    return match


def assert_prompt(response: MUDResponse, msg: str = "") -> None:
    """
    Assert that a prompt was detected in the response.

    Args:
        response: MUDResponse to check
        msg: Additional context for failure message

    Raises:
        MUDAssertionError: If no prompt detected
    """
    if not response.prompt_detected:
        raise MUDAssertionError(
            f"No prompt detected in response. {msg}\n"
            f"Response:\n{response.clean[:500]}"
        )


def assert_line_count(
    response: Union[MUDResponse, str],
    min_lines: int = 0,
    max_lines: Optional[int] = None,
    msg: str = ""
) -> None:
    """
    Assert response has expected line count.

    Args:
        response: MUDResponse or string to check
        min_lines: Minimum expected lines
        max_lines: Maximum expected lines (None for no limit)
        msg: Additional context for failure message

    Raises:
        MUDAssertionError: If line count out of range
    """
    if isinstance(response, MUDResponse):
        lines = response.lines
    else:
        lines = [line for line in response.split('\n') if line.strip()]

    count = len(lines)

    if count < min_lines:
        raise MUDAssertionError(
            f"Expected at least {min_lines} lines, got {count}. {msg}\n"
            f"Lines: {lines[:10]}"
        )

    if max_lines is not None and count > max_lines:
        raise MUDAssertionError(
            f"Expected at most {max_lines} lines, got {count}. {msg}\n"
            f"Lines: {lines[:10]}"
        )
