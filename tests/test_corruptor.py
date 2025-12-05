"""Tests for corruption engine."""

import random

import pytest

from logsynth.core.corruptor import (
    Corruptor,
    create_corruptor,
    garbage_timestamp,
    list_corruptions,
    missing_field,
    null_byte,
    swap_types,
    truncate,
)


class TestCorruptionFunctions:
    """Tests for individual corruption functions."""

    def test_truncate(self):
        """Should truncate the line."""
        line = "This is a test line"
        result = truncate(line)
        assert len(result) < len(line)
        assert line.startswith(result)

    def test_truncate_short_line(self):
        """Should handle short lines."""
        assert truncate("x") == "x"
        assert truncate("") == ""

    def test_garbage_timestamp_iso(self):
        """Should corrupt ISO timestamp."""
        line = "[2025-01-01 12:00:00] Log message"
        result = garbage_timestamp(line)
        assert "2025-01-01" not in result

    def test_garbage_timestamp_unix(self):
        """Should corrupt Unix timestamp."""
        line = "1704067200 Log message"
        result = garbage_timestamp(line)
        assert "1704067200" not in result

    def test_missing_field(self):
        """Should remove a field."""
        line = "field1 field2 field3 field4"
        result = missing_field(line)
        parts = result.split()
        assert len(parts) < 4

    def test_null_byte(self):
        """Should insert null byte."""
        line = "Test line"
        result = null_byte(line)
        assert "\x00" in result

    def test_swap_types_number(self):
        """Should swap number with string."""
        random.seed(42)
        line = "Error code 404 occurred"
        result = swap_types(line)
        # The number should be replaced
        assert result != line


class TestCorruptor:
    """Tests for Corruptor class."""

    def test_probability_zero(self):
        """Should not corrupt with probability 0."""
        corruptor = Corruptor(probability=0)
        line = "Test line"
        for _ in range(100):
            assert corruptor.maybe_corrupt(line) == line

    def test_probability_one(self):
        """Should always attempt corruption with probability 1."""
        # Use truncate which always produces different output
        corruptor = Corruptor(probability=1.0, corruption_types=["truncate"])
        line = "Test line with 123 numbers that is long enough"
        corrupted_count = 0
        for _ in range(100):
            result = corruptor.maybe_corrupt(line)
            if result != line:
                corrupted_count += 1
        assert corrupted_count == 100

    def test_probability_percentage(self):
        """Should accept percentage values."""
        corruptor = Corruptor(probability=50)  # 50%
        assert corruptor.probability == 0.5

    def test_invalid_probability_raises(self):
        """Should raise for invalid probability."""
        with pytest.raises(ValueError):
            Corruptor(probability=150)

    def test_specific_corruption_types(self):
        """Should use only specified corruption types."""
        corruptor = Corruptor(probability=1.0, corruption_types=["truncate"])
        line = "This is a test line"
        result = corruptor.maybe_corrupt(line)
        # Truncate should make it shorter
        assert len(result) < len(line)

    def test_unknown_corruption_type_raises(self):
        """Should raise for unknown corruption type."""
        with pytest.raises(ValueError, match="Unknown corruption"):
            Corruptor(probability=1.0, corruption_types=["nonexistent"])


class TestCreateCorruptor:
    """Tests for create_corruptor factory."""

    def test_zero_probability_returns_none(self):
        """Should return None for zero probability."""
        assert create_corruptor(0) is None

    def test_positive_probability_returns_corruptor(self):
        """Should return Corruptor for positive probability."""
        corruptor = create_corruptor(10)
        assert isinstance(corruptor, Corruptor)


class TestListCorruptions:
    """Tests for listing corruption types."""

    def test_list_corruptions(self):
        """Should list all corruption types."""
        types = list_corruptions()
        assert "truncate" in types
        assert "garbage_timestamp" in types
        assert "missing_field" in types
        assert "null_byte" in types
        assert "swap_types" in types
