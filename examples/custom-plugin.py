"""
Example: Custom Plugin for LogSynth

This plugin adds two custom field types:
1. 'hash' - Generates random hash values (SHA256)
2. 'useragent' - Generates realistic user agent strings

Installation:
    cp examples/custom-plugin.py ~/.config/logsynth/plugins/

Usage in templates:
    fields:
      request_id:
        type: hash
        algorithm: sha256
        length: 12

      browser:
        type: useragent
        ua_type: desktop  # or mobile, bot
"""

import hashlib
import random

from logsynth.fields import FieldGenerator, register


class HashGenerator(FieldGenerator):
    """Generate random hash values."""

    def __init__(self, config: dict) -> None:
        self.algorithm = config.get("algorithm", "sha256")
        self.length = config.get("length", 16)

    def generate(self) -> str:
        data = str(random.random()).encode()
        h = hashlib.new(self.algorithm, data)
        return h.hexdigest()[: self.length]

    def reset(self) -> None:
        pass


class UserAgentGenerator(FieldGenerator):
    """Generate realistic user agent strings."""

    DESKTOP_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0.0.0",
    ]

    MOBILE_AGENTS = [
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2) Mobile/15E148",
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) Chrome/120.0.0.0 Mobile",
        "Mozilla/5.0 (iPad; CPU OS 17_2) Mobile/15E148 Safari/604.1",
    ]

    BOT_AGENTS = [
        "Googlebot/2.1 (+http://www.google.com/bot.html)",
        "Mozilla/5.0 (compatible; Bingbot/2.0)",
        "curl/8.4.0",
        "python-requests/2.31.0",
    ]

    def __init__(self, config: dict) -> None:
        ua_type = config.get("ua_type", "mixed")
        if ua_type == "desktop":
            self.agents = self.DESKTOP_AGENTS
        elif ua_type == "mobile":
            self.agents = self.MOBILE_AGENTS
        elif ua_type == "bot":
            self.agents = self.BOT_AGENTS
        else:
            self.agents = self.DESKTOP_AGENTS + self.MOBILE_AGENTS + self.BOT_AGENTS

    def generate(self) -> str:
        return random.choice(self.agents)

    def reset(self) -> None:
        pass


@register("hash")
def create_hash_generator(config: dict) -> FieldGenerator:
    """Factory function for hash generator."""
    return HashGenerator(config)


@register("useragent")
def create_useragent_generator(config: dict) -> FieldGenerator:
    """Factory function for user agent generator."""
    return UserAgentGenerator(config)
