"""Log corruption engine for fault injection testing."""

from __future__ import annotations

import random
import re
import string
from collections.abc import Callable

CorruptionFn = Callable[[str], str]


def truncate(line: str) -> str:
    """Randomly truncate the line."""
    if len(line) <= 1:
        return line
    cut_point = random.randint(1, len(line) - 1)
    return line[:cut_point]


def garbage_timestamp(line: str) -> str:
    """Replace timestamp-like patterns with garbage."""
    # Match common timestamp patterns
    patterns = [
        r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}",  # ISO format
        r"\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2}",  # Apache CLF
        r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]",  # Bracketed
        r"\d{10,13}",  # Unix timestamp
    ]

    for pattern in patterns:
        if re.search(pattern, line):
            garbage = "".join(random.choices(string.ascii_letters + string.digits, k=10))
            line = re.sub(pattern, garbage, line, count=1)
            break

    return line


def missing_field(line: str) -> str:
    """Remove a random field-like segment from the line."""
    # Split on common delimiters and remove a segment
    delimiters = [" ", "\t", ",", "|"]

    for delim in delimiters:
        parts = line.split(delim)
        if len(parts) > 2:
            idx = random.randint(0, len(parts) - 1)
            parts.pop(idx)
            return delim.join(parts)

    return line


def null_byte(line: str) -> str:
    """Insert a null byte at a random position."""
    if not line:
        return "\x00"
    pos = random.randint(0, len(line))
    return line[:pos] + "\x00" + line[pos:]


def swap_types(line: str) -> str:
    """Swap a number with a string or vice versa."""
    # Find numbers in the line
    numbers = list(re.finditer(r"\b\d+(?:\.\d+)?\b", line))
    if numbers:
        match = random.choice(numbers)
        replacement = "".join(random.choices(string.ascii_lowercase, k=len(match.group())))
        return line[: match.start()] + replacement + line[match.end() :]

    # Find words and replace with numbers
    words = list(re.finditer(r"\b[a-zA-Z]{3,}\b", line))
    if words:
        match = random.choice(words)
        replacement = str(random.randint(100, 99999))
        return line[: match.start()] + replacement + line[match.end() :]

    return line


def duplicate_chars(line: str) -> str:
    """Duplicate random characters in the line."""
    if not line:
        return line
    result = list(line)
    num_dups = random.randint(1, min(3, len(line)))
    for _ in range(num_dups):
        pos = random.randint(0, len(result) - 1)
        result.insert(pos, result[pos])
    return "".join(result)


def case_flip(line: str) -> str:
    """Randomly flip the case of characters."""
    result = list(line)
    num_flips = random.randint(1, max(1, len(line) // 5))
    positions = random.sample(range(len(line)), min(num_flips, len(line)))
    for pos in positions:
        char = result[pos]
        if char.isalpha():
            result[pos] = char.lower() if char.isupper() else char.upper()
    return "".join(result)


# Registry of corruption functions
CORRUPTIONS: dict[str, CorruptionFn] = {
    "truncate": truncate,
    "garbage_timestamp": garbage_timestamp,
    "missing_field": missing_field,
    "null_byte": null_byte,
    "swap_types": swap_types,
    "duplicate_chars": duplicate_chars,
    "case_flip": case_flip,
}


def list_corruptions() -> list[str]:
    """List available corruption types."""
    return sorted(CORRUPTIONS.keys())


class Corruptor:
    """Applies random corruptions to log lines with a given probability."""

    def __init__(
        self,
        probability: float,
        corruption_types: list[str] | None = None,
    ) -> None:
        """Initialize corruptor.

        Args:
            probability: Probability of corruption (0.0 to 1.0, or 0 to 100 for percentage)
            corruption_types: List of corruption types to use (None for all)
        """
        # Handle percentage input
        if probability > 1.0:
            probability = probability / 100.0

        if not 0.0 <= probability <= 1.0:
            raise ValueError("Probability must be between 0 and 1 (or 0-100 for percentage)")

        self.probability = probability

        # Select corruption functions
        if corruption_types:
            self.corruptions = []
            for name in corruption_types:
                if name not in CORRUPTIONS:
                    available = ", ".join(list_corruptions())
                    raise ValueError(f"Unknown corruption type '{name}'. Available: {available}")
                self.corruptions.append(CORRUPTIONS[name])
        else:
            self.corruptions = list(CORRUPTIONS.values())

    def maybe_corrupt(self, line: str) -> str:
        """Possibly corrupt a line based on probability."""
        if random.random() < self.probability:
            corruption = random.choice(self.corruptions)
            return corruption(line)
        return line


def create_corruptor(
    probability: float,
    corruption_types: list[str] | None = None,
) -> Corruptor | None:
    """Create a corruptor if probability > 0, otherwise return None."""
    if probability <= 0:
        return None
    return Corruptor(probability, corruption_types)
