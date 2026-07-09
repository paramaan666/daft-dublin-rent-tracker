from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
import os
from typing import Any

import yaml

DEFAULT_LOCATIONS = [
    "Dublin 1", "Dublin 2", "Dublin 4", "Dublin 6", "Dublin 7", "Dublin 8",
    "Dublin 9", "Dublin 10", "Dublin 12", "Dublin 14", "Dublin 16",
]


@dataclass(slots=True)
class TrackerConfig:
    locations: list[str] = field(default_factory=lambda: list(DEFAULT_LOCATIONS))
    max_monthly_rent_eur: int = 1500
    min_double_beds: int = 1
    include_unknown_location: bool = True
    include_unknown_bed_count: bool = True
    include_unknown_price: bool = False
    gmail_query: str = 'from:(daft.ie) newer_than:30d (rent OR rental OR property OR Daft)'
    gmail_max_messages: int = 50
    stale_after_days: int = 45

    @property
    def normalized_locations(self) -> set[str]:
        return {normalize_location(x) for x in self.locations}

    def as_public_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_location(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.strip().lower().replace(",", " ").split())


def load_config(path: str | Path | None) -> TrackerConfig:
    data: dict[str, Any] = {}
    if path:
        p = Path(path)
        if p.exists():
            loaded = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            if not isinstance(loaded, dict):
                raise ValueError(f"Config {p} must contain a YAML mapping")
            data.update(loaded)

    cfg = TrackerConfig(**{k: v for k, v in data.items() if k in TrackerConfig.__dataclass_fields__})

    if os.getenv("MAX_MONTHLY_RENT_EUR"):
        cfg.max_monthly_rent_eur = int(os.environ["MAX_MONTHLY_RENT_EUR"])
    if os.getenv("GMAIL_QUERY"):
        cfg.gmail_query = os.environ["GMAIL_QUERY"]
    if os.getenv("GMAIL_MAX_MESSAGES"):
        cfg.gmail_max_messages = int(os.environ["GMAIL_MAX_MESSAGES"])
    if os.getenv("STALE_AFTER_DAYS"):
        cfg.stale_after_days = int(os.environ["STALE_AFTER_DAYS"])

    return cfg
