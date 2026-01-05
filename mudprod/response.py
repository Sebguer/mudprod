"""
MUDResponse - Structured response from MUD server commands.
"""

from dataclasses import dataclass, field
from typing import List

from .ansi import clean_output


@dataclass
class MUDResponse:
    """
    Structured response from the MUD server.

    Attributes:
        raw: Raw server output with ANSI codes and telnet sequences
        clean: Cleaned output (ANSI stripped, normalized)
        prompt_detected: Whether a prompt was detected at the end
        lines: Non-empty lines from the cleaned output
    """
    raw: str
    clean: str = field(default="")
    prompt_detected: bool = False
    lines: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.clean:
            self.clean = clean_output(self.raw)
        if not self.lines:
            self.lines = [line for line in self.clean.split('\n') if line.strip()]

    def __contains__(self, item: str) -> bool:
        """Allow 'text in response' syntax."""
        return item in self.clean

    def __str__(self) -> str:
        return self.clean
