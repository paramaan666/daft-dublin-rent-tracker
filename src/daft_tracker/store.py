from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import csv
import json
from typing import Any, Iterable

from dateutil.parser import isoparse

from .config import TrackerConfig
from .parser import ParsedListing

LISTING_FIELDNAMES = [
    "id", "status", "needs_review", "review_reasons", "title", "location", "postcode",
    "price_eur", "double_beds", "url", "thumbnail_url", "first_seen", "last_seen",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: str | Path, default: Any) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8") or "null") or default
    except json.JSONDecodeError:
        return default


def write_json(path: str | Path, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def load_state(data_dir: str | Path) -> dict[str, Any]:
    state = load_json(Path(data_dir) / "state.json", {"processed_gmail_message_ids": []})
    state.setdefault("processed_gmail_message_ids", [])
    return state


def save_state(data_dir: str | Path, state: dict[str, Any]) -> None:
    # Keep the state file from growing forever.
    seen = list(dict.fromkeys(state.get("processed_gmail_message_ids", [])))
    state["processed_gmail_message_ids"] = seen[-5000:]
    write_json(Path(data_dir) / "state.json", state)


def load_store(data_dir: str | Path) -> dict[str, Any]:
    base = load_json(Path(data_dir) / "listings.json", {"updated_at": None, "filters": {}, "listings": []})
    base.setdefault("listings", [])
    return base


def append_events(data_dir: str | Path, events: Iterable[dict[str, Any]]) -> None:
    p = Path(data_dir) / "events.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False, sort_keys=False) + "\n")


def to_listing_record(parsed: ParsedListing, cfg: TrackerConfig) -> dict[str, Any]:
    first_seen = parsed.seen_at or now_iso()
    record = {
        "id": parsed.id,
        "status": "active",
        "needs_review": parsed.needs_review,
        "review_reasons": parsed.review_reasons,
        "title": parsed.title,
        "location": parsed.location,
        "postcode": parsed.postcode,
        "price_eur": parsed.price_eur,
        "rent_period": "month",
        "double_beds": parsed.double_beds,
        "url": parsed.url,
        "thumbnail_url": parsed.thumbnail_url,
        "image_urls": parsed.image_urls,
        "source": parsed.source,
        "source_message_ids": [parsed.source_message_id] if parsed.source_message_id else [],
        "source_subjects": [parsed.source_subject] if parsed.source_subject else [],
        "first_seen": first_seen,
        "last_seen": parsed.seen_at or first_seen,
        "price_history": [
            {"seen_at": parsed.seen_at or first_seen, "price_eur": parsed.price_eur}
        ] if parsed.price_eur is not None else [],
        "change_history": [],
    }
    return record


def merge_listings(
    store: dict[str, Any],
    parsed_listings: Iterable[ParsedListing],
    cfg: TrackerConfig,
    data_dir: str | Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ts = now_iso()
    existing: dict[str, dict[str, Any]] = {item["id"]: item for item in store.get("listings", []) if item.get("id")}
    events: list[dict[str, Any]] = []

    for parsed in parsed_listings:
        current = existing.get(parsed.id)
        if current is None:
            current = to_listing_record(parsed, cfg)
            existing[parsed.id] = current
            events.append({"at": ts, "type": "new_listing", "listing_id": parsed.id, "url": parsed.url, "price_eur": parsed.price_eur})
            continue

        changed_fields: dict[str, dict[str, Any]] = {}
        if current.get("status") != "active":
            changed_fields["status"] = {"old": current.get("status"), "new": "active"}
            current["status"] = "active"

        for field in ["title", "location", "postcode", "double_beds", "thumbnail_url", "url"]:
            value = getattr(parsed, field)
            if value and value != current.get(field):
                changed_fields[field] = {"old": current.get(field), "new": value}
                current[field] = value

        if parsed.image_urls:
            known_images = current.setdefault("image_urls", []) or []
            for img in parsed.image_urls:
                if img not in known_images:
                    known_images.append(img)
            current["image_urls"] = known_images[:25]
            if not current.get("thumbnail_url"):
                current["thumbnail_url"] = known_images[0]

        if parsed.price_eur is not None and parsed.price_eur != current.get("price_eur"):
            changed_fields["price_eur"] = {"old": current.get("price_eur"), "new": parsed.price_eur}
            current["price_eur"] = parsed.price_eur
            current.setdefault("price_history", []).append({"seen_at": parsed.seen_at or ts, "price_eur": parsed.price_eur})
            events.append({"at": ts, "type": "price_changed", "listing_id": parsed.id, "change": changed_fields["price_eur"]})

        current["last_seen"] = parsed.seen_at or ts
        current["needs_review"] = parsed.needs_review or current.get("needs_review", False)
        merged_reasons = list(dict.fromkeys((current.get("review_reasons") or []) + parsed.review_reasons))
        current["review_reasons"] = merged_reasons
        if parsed.source_message_id and parsed.source_message_id not in current.setdefault("source_message_ids", []):
            current["source_message_ids"].append(parsed.source_message_id)
        if parsed.source_subject and parsed.source_subject not in current.setdefault("source_subjects", []):
            current["source_subjects"].append(parsed.source_subject)

        if changed_fields:
            current.setdefault("change_history", []).append({"at": ts, "changes": changed_fields})
            if "price_eur" not in changed_fields:
                events.append({"at": ts, "type": "listing_updated", "listing_id": parsed.id, "changes": changed_fields})

    mark_possibly_removed(existing.values(), cfg, events, ts)

    listings = sorted(existing.values(), key=lambda x: (x.get("status") != "active", x.get("price_eur") or 999999, x.get("first_seen") or ""))
    store["updated_at"] = ts
    store["filters"] = cfg.as_public_dict()
    store["listings"] = listings
    write_outputs(data_dir, store)
    append_events(data_dir, events)
    return store, events


def mark_possibly_removed(records: Iterable[dict[str, Any]], cfg: TrackerConfig, events: list[dict[str, Any]], ts: str) -> None:
    now_dt = datetime.now(timezone.utc)
    for item in records:
        if item.get("status") not in ("active", None):
            continue
        last_seen = item.get("last_seen") or item.get("first_seen")
        if not last_seen:
            continue
        try:
            last_dt = isoparse(last_seen)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        age_days = (now_dt - last_dt).days
        if age_days >= cfg.stale_after_days:
            item["status"] = "possibly_removed"
            item.setdefault("change_history", []).append({"at": ts, "changes": {"status": {"old": "active", "new": "possibly_removed"}}})
            events.append({"at": ts, "type": "possibly_removed", "listing_id": item.get("id"), "age_days": age_days})


def write_outputs(data_dir: str | Path, store: dict[str, Any]) -> None:
    data_path = Path(data_dir)
    write_json(data_path / "listings.json", store)
    with (data_path / "listings.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LISTING_FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for item in store.get("listings", []):
            row = {field: item.get(field) for field in LISTING_FIELDNAMES}
            row["review_reasons"] = ";".join(item.get("review_reasons") or [])
            writer.writerow(row)
