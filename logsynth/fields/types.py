"""Field type generators for log synthesis."""

from __future__ import annotations

import ipaddress
import random
import re
import uuid as uuid_module
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from logsynth.fields.registry import register

try:
    import zoneinfo

    HAS_ZONEINFO = True
except ImportError:
    HAS_ZONEINFO = False


def _parse_duration(value: str) -> timedelta:
    """Parse a duration string like '1s', '100ms', '5m', '1h' into timedelta."""
    match = re.match(r"^(\d+(?:\.\d+)?)(ms|s|m|h)$", value.strip().lower())
    if not match:
        raise ValueError(f"Invalid duration format: {value}. Use format like '1s', '100ms', '5m'")

    amount = float(match.group(1))
    unit = match.group(2)

    if unit == "ms":
        return timedelta(milliseconds=amount)
    elif unit == "s":
        return timedelta(seconds=amount)
    elif unit == "m":
        return timedelta(minutes=amount)
    elif unit == "h":
        return timedelta(hours=amount)
    else:
        raise ValueError(f"Unknown duration unit: {unit}")


class FieldGenerator(ABC):
    """Abstract base class for field generators."""

    @abstractmethod
    def generate(self) -> Any:
        """Generate a single field value."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset generator state (for reproducibility with seeds)."""
        pass


@register("timestamp")
def create_timestamp_generator(config: dict[str, Any]) -> FieldGenerator:
    """Create a timestamp field generator."""
    return TimestampGenerator(config)


class TimestampGenerator(FieldGenerator):
    """Generate timestamps with configurable step, jitter, timezone, and format."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.step = _parse_duration(config.get("step", "1s"))
        self.jitter = _parse_duration(config.get("jitter", "0s"))
        self.format = config.get("format", "%Y-%m-%d %H:%M:%S")
        self.tz_name = config.get("tz", "UTC")
        self.start = config.get("start")  # Optional start time

        # Resolve timezone
        self.tz = self._resolve_timezone(self.tz_name)

        # Initialize current time
        self._init_time()

    def _resolve_timezone(self, tz_name: str) -> timezone:
        """Resolve timezone name to timezone object."""
        if tz_name.upper() == "UTC":
            return UTC
        if HAS_ZONEINFO:
            try:
                zi = zoneinfo.ZoneInfo(tz_name)
                # Return a fixed offset for current time
                now = datetime.now(zi)
                return timezone(now.utcoffset())  # type: ignore
            except Exception:
                pass
        # Fallback: try to parse as offset like +05:00
        match = re.match(r"^([+-])(\d{2}):?(\d{2})$", tz_name)
        if match:
            sign = 1 if match.group(1) == "+" else -1
            hours = int(match.group(2))
            minutes = int(match.group(3))
            return timezone(timedelta(hours=sign * hours, minutes=sign * minutes))
        # Default to UTC if nothing works
        return UTC

    def _init_time(self) -> None:
        """Initialize or reset the current time."""
        if self.start:
            # Parse start time
            self.current = datetime.fromisoformat(self.start).replace(tzinfo=self.tz)
        else:
            self.current = datetime.now(self.tz)

    def generate(self) -> str:
        """Generate a timestamp string."""
        # Apply jitter
        jitter_delta = timedelta(
            seconds=random.uniform(-self.jitter.total_seconds(), self.jitter.total_seconds())
        )
        ts = self.current + jitter_delta

        # Format the timestamp
        result = ts.strftime(self.format)

        # Advance current time by step
        self.current += self.step

        return result

    def reset(self) -> None:
        """Reset to initial time."""
        self._init_time()


@register("choice")
def create_choice_generator(config: dict[str, Any]) -> FieldGenerator:
    """Create a choice field generator."""
    return ChoiceGenerator(config)


class ChoiceGenerator(FieldGenerator):
    """Generate values from a list with optional weights."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.values = config.get("values", [])
        if not self.values:
            raise ValueError("Choice field requires non-empty 'values' list")
        self.weights = config.get("weights")
        if self.weights and len(self.weights) != len(self.values):
            raise ValueError("Weights list must match values list length")

    def generate(self) -> Any:
        """Generate a random choice."""
        if self.weights:
            return random.choices(self.values, weights=self.weights, k=1)[0]
        return random.choice(self.values)

    def reset(self) -> None:
        """No state to reset."""
        pass


@register("int")
def create_int_generator(config: dict[str, Any]) -> FieldGenerator:
    """Create an integer field generator."""
    return IntGenerator(config)


class IntGenerator(FieldGenerator):
    """Generate random integers within a range."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.min = config.get("min", 0)
        self.max = config.get("max", 100)
        if self.min > self.max:
            raise ValueError(f"min ({self.min}) cannot be greater than max ({self.max})")

    def generate(self) -> int:
        """Generate a random integer."""
        return random.randint(self.min, self.max)

    def reset(self) -> None:
        """No state to reset."""
        pass


@register("float")
def create_float_generator(config: dict[str, Any]) -> FieldGenerator:
    """Create a float field generator."""
    return FloatGenerator(config)


class FloatGenerator(FieldGenerator):
    """Generate random floats within a range with configurable precision."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.min = config.get("min", 0.0)
        self.max = config.get("max", 1.0)
        self.precision = config.get("precision", 2)
        if self.min > self.max:
            raise ValueError(f"min ({self.min}) cannot be greater than max ({self.max})")

    def generate(self) -> float:
        """Generate a random float."""
        value = random.uniform(self.min, self.max)
        return round(value, self.precision)

    def reset(self) -> None:
        """No state to reset."""
        pass


@register("string")
def create_string_generator(config: dict[str, Any]) -> FieldGenerator:
    """Create a string field generator."""
    return StringGenerator(config)


class StringGenerator(FieldGenerator):
    """Generate strings from a list of values."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.values = config.get("values", [])
        if not self.values:
            raise ValueError("String field requires non-empty 'values' list")

    def generate(self) -> str:
        """Generate a random string."""
        return random.choice(self.values)

    def reset(self) -> None:
        """No state to reset."""
        pass


@register("uuid")
def create_uuid_generator(config: dict[str, Any]) -> FieldGenerator:
    """Create a UUID field generator."""
    return UUIDGenerator(config)


class UUIDGenerator(FieldGenerator):
    """Generate random UUIDs."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.uppercase = config.get("uppercase", False)

    def generate(self) -> str:
        """Generate a random UUID."""
        result = str(uuid_module.uuid4())
        if self.uppercase:
            result = result.upper()
        return result

    def reset(self) -> None:
        """No state to reset."""
        pass


@register("ip")
def create_ip_generator(config: dict[str, Any]) -> FieldGenerator:
    """Create an IP address field generator."""
    return IPGenerator(config)


class IPGenerator(FieldGenerator):
    """Generate random IP addresses, optionally from a CIDR range."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.cidr = config.get("cidr")
        self.ipv6 = config.get("ipv6", False)

        if self.cidr:
            self.network = ipaddress.ip_network(self.cidr, strict=False)
            self.hosts = list(self.network.hosts())
            if not self.hosts:
                # For /32 or /128, use the network address itself
                self.hosts = [self.network.network_address]
        else:
            self.network = None
            self.hosts = None

    def generate(self) -> str:
        """Generate a random IP address."""
        if self.hosts:
            return str(random.choice(self.hosts))

        if self.ipv6:
            # Random IPv6
            return str(
                ipaddress.IPv6Address(random.randint(0, 2**128 - 1))
            )
        else:
            # Random IPv4 (avoiding reserved ranges for realism)
            # Generate from common ranges: 10.x.x.x, 192.168.x.x, 172.16-31.x.x
            range_type = random.choice(["public", "private_10", "private_192", "private_172"])

            def rand_octet() -> int:
                return random.randint(0, 255)

            def rand_host() -> int:
                return random.randint(1, 254)

            if range_type == "public":
                # Simplified public IP (avoiding 0, 127, 224-255)
                excluded = (10, 127, 172, 192)
                first = random.choice([i for i in range(1, 224) if i not in excluded])
                return f"{first}.{rand_octet()}.{rand_octet()}.{rand_host()}"
            elif range_type == "private_10":
                return f"10.{rand_octet()}.{rand_octet()}.{rand_host()}"
            elif range_type == "private_192":
                return f"192.168.{rand_octet()}.{rand_host()}"
            else:  # private_172
                return f"172.{random.randint(16, 31)}.{rand_octet()}.{rand_host()}"

    def reset(self) -> None:
        """No state to reset."""
        pass


@register("sequence")
def create_sequence_generator(config: dict[str, Any]) -> FieldGenerator:
    """Create a sequence field generator."""
    return SequenceGenerator(config)


class SequenceGenerator(FieldGenerator):
    """Generate sequential integers."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.start = config.get("start", 1)
        self.step = config.get("step", 1)
        self.current = self.start

    def generate(self) -> int:
        """Generate the next sequence value."""
        result = self.current
        self.current += self.step
        return result

    def reset(self) -> None:
        """Reset to start value."""
        self.current = self.start


@register("literal")
def create_literal_generator(config: dict[str, Any]) -> FieldGenerator:
    """Create a literal value generator."""
    return LiteralGenerator(config)


class LiteralGenerator(FieldGenerator):
    """Generate a constant literal value."""

    def __init__(self, config: dict[str, Any]) -> None:
        if "value" not in config:
            raise ValueError("Literal field requires 'value'")
        self.value = config["value"]

    def generate(self) -> Any:
        """Return the literal value."""
        return self.value

    def reset(self) -> None:
        """No state to reset."""
        pass
