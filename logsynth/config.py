"""Centralized configuration and path management."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _get_xdg_config_home() -> Path:
    """Get XDG_CONFIG_HOME or default to ~/.config."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".config"


# Paths
CONFIG_DIR: Path = _get_xdg_config_home() / "logsynth"
CONFIG_FILE: Path = CONFIG_DIR / "config.yaml"
GENERATED_DIR: Path = CONFIG_DIR / "generated"
PROFILES_DIR: Path = CONFIG_DIR / "profiles"
PLUGINS_DIR: Path = CONFIG_DIR / "plugins"

# Package paths
PACKAGE_DIR: Path = Path(__file__).parent
PRESETS_DIR: Path = PACKAGE_DIR / "presets"


@dataclass
class LLMConfig:
    """LLM provider configuration."""

    provider: str = "ollama"
    base_url: str = "http://localhost:11434/v1"
    api_key: str | None = None
    model: str = "llama3.2"


@dataclass
class DefaultsConfig:
    """Default values for CLI options."""

    rate: float = 10.0
    format: str = "plain"


@dataclass
class Config:
    """Application configuration."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        """Create Config from dictionary."""
        llm_data = data.get("llm", {})
        defaults_data = data.get("defaults", {})

        return cls(
            llm=LLMConfig(
                provider=llm_data.get("provider", "ollama"),
                base_url=llm_data.get("base_url", "http://localhost:11434/v1"),
                api_key=llm_data.get("api_key"),
                model=llm_data.get("model", "llama3.2"),
            ),
            defaults=DefaultsConfig(
                rate=defaults_data.get("rate", 10.0),
                format=defaults_data.get("format", "plain"),
            ),
        )


def ensure_dirs() -> None:
    """Create config directories if they don't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> Config:
    """Load configuration from file or return defaults."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            data = yaml.safe_load(f) or {}
        return Config.from_dict(data)
    return Config()


def get_llm_settings() -> LLMConfig:
    """Get LLM configuration."""
    return load_config().llm


def get_defaults() -> DefaultsConfig:
    """Get default values."""
    return load_config().defaults


def save_config(config: Config) -> None:
    """Save configuration to file."""
    ensure_dirs()
    data = {
        "llm": {
            "provider": config.llm.provider,
            "base_url": config.llm.base_url,
            "api_key": config.llm.api_key,
            "model": config.llm.model,
        },
        "defaults": {
            "rate": config.defaults.rate,
            "format": config.defaults.format,
        },
    }
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(data, f, default_flow_style=False)


@dataclass
class ProfileConfig:
    """Named configuration profile with optional overrides."""

    name: str
    rate: float | None = None
    format: str | None = None
    output: str | None = None
    duration: str | None = None
    count: int | None = None
    corrupt: float | None = None

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ProfileConfig:
        """Create ProfileConfig from dictionary."""
        return cls(
            name=name,
            rate=data.get("rate"),
            format=data.get("format"),
            output=data.get("output"),
            duration=data.get("duration"),
            count=data.get("count"),
            corrupt=data.get("corrupt"),
        )


def load_profile(name: str) -> ProfileConfig | None:
    """Load a profile by name from PROFILES_DIR.

    Returns None if profile doesn't exist.
    """
    profile_path = PROFILES_DIR / f"{name}.yaml"
    if not profile_path.exists():
        return None
    with open(profile_path) as f:
        data = yaml.safe_load(f) or {}
    return ProfileConfig.from_dict(name, data)


def list_profiles() -> list[str]:
    """List available profile names."""
    if not PROFILES_DIR.exists():
        return []
    return sorted(p.stem for p in PROFILES_DIR.glob("*.yaml"))


def save_profile(profile: ProfileConfig) -> Path:
    """Save a profile to PROFILES_DIR."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    profile_path = PROFILES_DIR / f"{profile.name}.yaml"
    data: dict[str, Any] = {}
    if profile.rate is not None:
        data["rate"] = profile.rate
    if profile.format is not None:
        data["format"] = profile.format
    if profile.output is not None:
        data["output"] = profile.output
    if profile.duration is not None:
        data["duration"] = profile.duration
    if profile.count is not None:
        data["count"] = profile.count
    if profile.corrupt is not None:
        data["corrupt"] = profile.corrupt
    with open(profile_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)
    return profile_path
