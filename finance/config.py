"""Settings: read config.yaml (settings) and .env (secrets).

In plain English: this file knows where your settings live, checks they make sense,
and gives the rest of the app one tidy `Settings` object to read from.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, get_args

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator

Category = Literal["Grocery", "Travel", "Subscriptions", "Investments", "Savings", "Other", "Not an expense"]
SheetCategory = Literal["Grocery", "Travel", "Subscriptions", "Investments", "Savings", "Other"]
Confidence = Literal["high", "medium", "low"]

CATEGORIES: list[str] = list(get_args(Category))
SPENDING: list[str] = ["Grocery", "Travel", "Subscriptions", "Other"]
SET_ASIDE: list[str] = ["Investments", "Savings"]
NOT_EXPENSE = "Not an expense"
EMOJI = {
    "Grocery": "🛒",
    "Travel": "✈️",
    "Subscriptions": "🔁",
    "Investments": "📈",
    "Savings": "🏦",
    "Other": "🧾",
    "Not an expense": "↔️",
}

DEFAULT_CONFIG = "config.yaml"
PATH_FIELDS = ("service_account_file", "db_path", "statements_dir", "backups_dir", "inbox_dir", "logs_dir")


class ConfigError(Exception):
    """config.yaml is missing or has a mistake in it."""


class Price(BaseModel):
    input: float  # USD per million input tokens
    output: float  # USD per million output tokens


class ReviewSettings(BaseModel):
    review_if_confidence: list[Confidence] = ["low", "medium"]
    large_charge: float = 200


class Settings(BaseModel):
    sheets: dict[SheetCategory, str] = {}
    service_account_file: Path = Path("service_account.json")
    google_client_id: str | None = None
    fintrack_spreadsheet_id: str | None = None
    currency: str = "USD"
    model: str = "claude-opus-5-5"
    offline_mode: bool = False  # Use the local PDF parser and rules; no AI/network required.
    pages_per_chunk: int = Field(3, ge=1, le=20)
    categorize_batch_size: int = Field(100, ge=1, le=300)
    pricing_per_million_tokens: dict[str, Price] = {}
    keywords: dict[Category, list[str]] = {}
    review: ReviewSettings = Field(default_factory=ReviewSettings)
    auto_sync: bool = False
    db_path: Path = Path("data/ledger.db")
    statements_dir: Path = Path("data/statements")
    backups_dir: Path = Path("data/backups")
    inbox_dir: Path = Path("data/inbox")
    logs_dir: Path = Path("data/logs")

    @field_validator("sheets", mode="before")
    @classmethod
    def drop_empty_sheet_ids(cls, value):
        """Categories left as "" in config.yaml simply have no sheet yet."""
        return {k: v for k, v in (value or {}).items() if v and str(v).strip()}

    @field_validator("keywords", mode="before")
    @classmethod
    def none_to_empty(cls, value):
        return {k: v or [] for k, v in (value or {}).items()}


def config_path() -> Path:
    """config.yaml in the current folder, unless WDMMG_CONFIG points somewhere else."""
    return Path(os.environ.get("WDMMG_CONFIG", DEFAULT_CONFIG))


def load_settings(path: str | Path | None = None) -> Settings:
    """Read config.yaml, load secrets from the .env next to it, and resolve file paths."""
    path = Path(path) if path else config_path()
    if not path.exists():
        raise ConfigError(
            f"Settings file '{path}' not found. Create it with: cp config.example.yaml config.yaml"
        )
    base = path.resolve().parent
    load_dotenv(base / ".env")

    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"'{path}' isn't valid YAML (check indentation and colons):\n{e}") from e
    try:
        settings = Settings(**data)
    except ValidationError as e:
        raise ConfigError(f"There's a problem in '{path}':\n{e}") from e

    for name in PATH_FIELDS:  # relative paths are relative to the config file
        value: Path = getattr(settings, name)
        if not value.is_absolute():
            setattr(settings, name, base / value)
    return settings
