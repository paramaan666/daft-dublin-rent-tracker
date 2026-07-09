from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Iterable

from .config import load_config
from .gmail_client import gmail_service_from_env, list_message_ids, fetch_message
from .parser import parse_email_message, apply_filters, parse_seed_csv
from .store import load_store, merge_listings, load_state, save_state
from .site import build_site


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
        description="Track Daft Dublin rental listings from Gmail alerts.",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    update = sub.add_parser("update", parents=[common], help="Import seed + Gmail alerts, update data, build site")
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
