from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

from .config import load_config
from .gmail_client import gmail_service_from_env, list_message_ids, fetch_message
from .parser import parse_email_message, apply_filters, parse_seed_csv
from .rent_ie import (
    fetch_rent_ie_feed,
    fetch_rent_ie_reader_page,
    fetch_rent_ie_search_page,
    parse_rent_ie_feed,
    parse_rent_ie_reader_text,
    parse_rent_ie_search_page,
    rent_ie_search_url,
)
from .store import load_store, merge_listings, load_state, save_state, write_json
from .site import build_site


def _kept_after_filters(candidates: list, cfg) -> list:
    return [item for item in (apply_filters(x, cfg) for x in candidates) if item]


def _import_rent_ie(feed_url: str, cfg) -> tuple[list, str]:
    notes: list[str] = []

    try:
        feed_xml = fetch_rent_ie_feed(feed_url, timeout_seconds=cfg.rent_ie_timeout_seconds)
        candidates = parse_rent_ie_feed(feed_xml, feed_url=feed_url)
        kept = _kept_after_filters(candidates, cfg)
        if kept:
            return kept, f"RSS: {len(candidates)} candidate listing(s), {len(kept)} kept"
        if candidates:
            notes.append(f"RSS had {len(candidates)} candidate(s) but none matched")
        else:
            notes.append("RSS returned no parsable candidates")
    except Exception as exc:
        notes.append(f"RSS failed: {exc}")

    search_url = rent_ie_search_url(feed_url)
    try:
        page_html = fetch_rent_ie_search_page(search_url, timeout_seconds=cfg.rent_ie_timeout_seconds)
        page_candidates = parse_rent_ie_search_page(page_html, source_url=search_url)
        page_kept = _kept_after_filters(page_candidates, cfg)
        if page_kept:
            detail = (
                f"direct search fallback: {len(page_candidates)} candidate listing(s), "
                f"{len(page_kept)} kept"
            )
            if notes:
                detail += "; " + "; ".join(notes)
            return page_kept, detail
        if page_candidates:
            notes.append(f"direct search had {len(page_candidates)} candidate(s) but none matched")
        else:
            notes.append("direct search returned no parsable candidates")
    except Exception as exc:
        notes.append(f"direct search failed: {exc}")

    try:
        reader_text = fetch_rent_ie_reader_page(
            search_url,
            timeout_seconds=cfg.rent_ie_timeout_seconds,
        )
        reader_candidates = parse_rent_ie_reader_text(reader_text, source_url=search_url)
        reader_kept = _kept_after_filters(reader_candidates, cfg)
        detail = (
            f"Reader fallback: {len(reader_candidates)} candidate listing(s), "
            f"{len(reader_kept)} kept"
        )
        if notes:
            detail += "; " + "; ".join(notes)
        return reader_kept, detail
    except Exception as exc:
        notes.append(f"Reader fallback failed: {exc}")
        raise RuntimeError("; ".join(notes)) from exc


def run_update(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    data_dir = Path(args.data_dir)
    site_dir = Path(args.site_dir)
    parsed = []

    seed_path = Path(args.seed)
    if seed_path.exists():
        seed_listings = [item for item in (apply_filters(x, cfg) for x in parse_seed_csv(seed_path)) if item]
        parsed.extend(seed_listings)
        print(f"Loaded {len(seed_listings)} seed listing(s) from {seed_path}")

    if cfg.rent_ie_enabled:
        rent_ie_status = []
        for feed_url in cfg.rent_ie_feed_urls:
            try:
                kept, detail = _import_rent_ie(feed_url, cfg)
                parsed.extend(kept)
                rent_ie_status.append({
                    "feed_url": feed_url,
                    "ok": True,
                    "kept": len(kept),
                    "detail": detail,
                })
                print(f"{feed_url}: {detail}")
            except Exception as exc:
                rent_ie_status.append({
                    "feed_url": feed_url,
                    "ok": False,
                    "kept": 0,
                    "detail": str(exc),
                })
                print(f"{feed_url}: Rent.ie import failed: {exc}", file=sys.stderr)
        write_json(data_dir / "rent_ie_status.json", {
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "feeds": rent_ie_status,
        })

    state = load_state(data_dir)
    processed = set(state.get("processed_gmail_message_ids", []))
    service = gmail_service_from_env()
    if service is None:
        print("Gmail credentials are not configured; skipping Gmail alert import.")
    else:
        ids = list_message_ids(service, cfg.gmail_query, cfg.gmail_max_messages)
        print(f"Found {len(ids)} Gmail message(s) matching query.")
        new_ids = [message_id for message_id in ids if message_id not in processed]
        print(f"Processing {len(new_ids)} new Gmail message(s).")
        for message_id in new_ids:
            msg = fetch_message(service, message_id)
            candidates = parse_email_message(
                subject=msg.subject,
                html=msg.html,
                text=msg.text,
                message_id=msg.id,
                received_at=msg.internal_date,
            )
            kept = [item for item in (apply_filters(x, cfg) for x in candidates) if item]
            parsed.extend(kept)
            processed.add(message_id)
            print(f"{message_id}: {len(candidates)} candidate listing(s), {len(kept)} kept after filters")
        state["processed_gmail_message_ids"] = list(processed)
        save_state(data_dir, state)

    store = load_store(data_dir)
    store, events = merge_listings(store, parsed, cfg, data_dir)
    build_site(data_dir, site_dir)
    print(f"Store now contains {len(store.get('listings', []))} listing(s); {len(events)} event(s) written.")
    print(f"Site built in {site_dir}")
    return 0


def run_build_site(args: argparse.Namespace) -> int:
    build_site(args.data_dir, args.site_dir)
    print(f"Site built in {args.site_dir}")
    return 0


def run_import_seed(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    seed_listings = [item for item in (apply_filters(x, cfg) for x in parse_seed_csv(args.seed)) if item]
    store = load_store(args.data_dir)
    store, events = merge_listings(store, seed_listings, cfg, args.data_dir)
    build_site(args.data_dir, args.site_dir)
    print(f"Imported {len(seed_listings)} seed listing(s); store now has {len(store.get('listings', []))} listing(s); {len(events)} event(s).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default="config.yaml", help="Path to config YAML. Falls back to defaults if missing.")
    common.add_argument("--data-dir", default="data", help="Directory containing listings.json/listings.csv/state.json")
    common.add_argument("--site-dir", default="site", help="Static site output directory")

    parser = argparse.ArgumentParser(
        description="Track Dublin rental listings from Daft.ie alerts and Rent.ie feeds.",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    update = sub.add_parser("update", parents=[common], help="Import seed + Rent.ie feeds + Gmail alerts, update data, build site")
    update.add_argument("--seed", default="seeds/listings_seed.csv", help="CSV seed file")
    update.set_defaults(func=run_update)

    seed = sub.add_parser("import-seed", parents=[common], help="Import only a seed CSV")
    seed.add_argument("--seed", default="seeds/listings_seed.csv", help="CSV seed file")
    seed.set_defaults(func=run_import_seed)

    site = sub.add_parser("build-site", parents=[common], help="Build static site from existing data")
    site.set_defaults(func=run_build_site)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
