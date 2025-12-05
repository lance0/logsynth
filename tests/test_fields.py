"""Tests for field type generators."""

import random
from datetime import datetime

import pytest

from logsynth.fields import get_generator, list_types


class TestFieldRegistry:
    """Tests for field type registry."""

    def test_list_types(self):
        """Should list all registered field types."""
        types = list_types()
        assert "timestamp" in types
        assert "choice" in types
        assert "int" in types
        assert "float" in types
        assert "string" in types
        assert "uuid" in types
        assert "ip" in types
        assert "sequence" in types
        assert "literal" in types

    def test_unknown_type_raises(self):
        """Should raise ValueError for unknown type."""
        with pytest.raises(ValueError, match="Unknown field type"):
            get_generator("nonexistent", {})


class TestTimestampGenerator:
    """Tests for timestamp field generator."""

    def test_basic_timestamp(self):
        """Should generate timestamp strings."""
        gen = get_generator("timestamp", {"step": "1s"})
        ts = gen.generate()
        # Should be parseable as datetime
        datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")

    def test_custom_format(self):
        """Should respect custom format."""
        gen = get_generator("timestamp", {
            "step": "1s",
            "format": "%Y/%m/%d"
        })
        ts = gen.generate()
        datetime.strptime(ts, "%Y/%m/%d")

    def test_step_progression(self):
        """Should advance by step amount."""
        gen = get_generator("timestamp", {
            "step": "1s",
            "jitter": "0s",
            "format": "%H:%M:%S"
        })
        ts1 = gen.generate()
        ts2 = gen.generate()
        # Parse and compare
        t1 = datetime.strptime(ts1, "%H:%M:%S")
        t2 = datetime.strptime(ts2, "%H:%M:%S")
        diff = (t2 - t1).total_seconds()
        assert diff == 1.0

    def test_reset(self):
        """Should reset to initial time."""
        gen = get_generator("timestamp", {
            "step": "1s",
            "start": "2025-01-01T00:00:00"
        })
        gen.generate()
        gen.generate()
        gen.reset()
        ts = gen.generate()
        assert "2025-01-01" in ts


class TestChoiceGenerator:
    """Tests for choice field generator."""

    def test_basic_choice(self):
        """Should return values from list."""
        gen = get_generator("choice", {"values": ["a", "b", "c"]})
        for _ in range(10):
            assert gen.generate() in ["a", "b", "c"]

    def test_weighted_choice(self):
        """Should respect weights approximately."""
        random.seed(42)
        gen = get_generator("choice", {
            "values": ["common", "rare"],
            "weights": [0.9, 0.1]
        })
        results = [gen.generate() for _ in range(1000)]
        common_count = results.count("common")
        # Should be roughly 90% (with some tolerance)
        assert 800 < common_count < 950

    def test_empty_values_raises(self):
        """Should raise for empty values."""
        with pytest.raises(ValueError, match="non-empty"):
            get_generator("choice", {"values": []})

    def test_mismatched_weights_raises(self):
        """Should raise for mismatched weights."""
        with pytest.raises(ValueError, match="match"):
            get_generator("choice", {
                "values": ["a", "b"],
                "weights": [0.5]
            })


class TestIntGenerator:
    """Tests for integer field generator."""

    def test_range(self):
        """Should generate within range."""
        gen = get_generator("int", {"min": 10, "max": 20})
        for _ in range(100):
            val = gen.generate()
            assert 10 <= val <= 20
            assert isinstance(val, int)

    def test_invalid_range_raises(self):
        """Should raise for min > max."""
        with pytest.raises(ValueError, match="cannot be greater"):
            get_generator("int", {"min": 100, "max": 10})


class TestFloatGenerator:
    """Tests for float field generator."""

    def test_range(self):
        """Should generate within range."""
        gen = get_generator("float", {"min": 0.0, "max": 1.0})
        for _ in range(100):
            val = gen.generate()
            assert 0.0 <= val <= 1.0
            assert isinstance(val, float)

    def test_precision(self):
        """Should respect precision."""
        gen = get_generator("float", {
            "min": 0.0,
            "max": 100.0,
            "precision": 2
        })
        val = gen.generate()
        # Check decimal places
        str_val = str(val)
        if "." in str_val:
            decimals = len(str_val.split(".")[1])
            assert decimals <= 2


class TestUUIDGenerator:
    """Tests for UUID field generator."""

    def test_format(self):
        """Should generate valid UUID format."""
        gen = get_generator("uuid", {})
        uuid = gen.generate()
        # UUID format: 8-4-4-4-12 hex chars
        parts = uuid.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    def test_uppercase(self):
        """Should support uppercase option."""
        gen = get_generator("uuid", {"uppercase": True})
        uuid = gen.generate()
        assert uuid == uuid.upper()


class TestIPGenerator:
    """Tests for IP field generator."""

    def test_random_ipv4(self):
        """Should generate valid IPv4 addresses."""
        gen = get_generator("ip", {})
        for _ in range(10):
            ip = gen.generate()
            parts = ip.split(".")
            assert len(parts) == 4
            for part in parts:
                assert 0 <= int(part) <= 255

    def test_cidr_range(self):
        """Should generate within CIDR range."""
        gen = get_generator("ip", {"cidr": "192.168.1.0/24"})
        for _ in range(10):
            ip = gen.generate()
            assert ip.startswith("192.168.1.")


class TestSequenceGenerator:
    """Tests for sequence field generator."""

    def test_basic_sequence(self):
        """Should generate sequential values."""
        gen = get_generator("sequence", {"start": 1})
        assert gen.generate() == 1
        assert gen.generate() == 2
        assert gen.generate() == 3

    def test_custom_step(self):
        """Should respect custom step."""
        gen = get_generator("sequence", {"start": 0, "step": 10})
        assert gen.generate() == 0
        assert gen.generate() == 10
        assert gen.generate() == 20

    def test_reset(self):
        """Should reset to start."""
        gen = get_generator("sequence", {"start": 100})
        gen.generate()
        gen.generate()
        gen.reset()
        assert gen.generate() == 100


class TestLiteralGenerator:
    """Tests for literal field generator."""

    def test_constant_value(self):
        """Should always return same value."""
        gen = get_generator("literal", {"value": "constant"})
        for _ in range(10):
            assert gen.generate() == "constant"

    def test_missing_value_raises(self):
        """Should raise for missing value."""
        with pytest.raises(ValueError, match="requires 'value'"):
            get_generator("literal", {})
