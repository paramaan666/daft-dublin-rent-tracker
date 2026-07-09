#!/usr/bin/env python3
"""Create a Gmail readonly refresh token for GitHub Actions secrets.

Usage:
  python scripts/get_google_refresh_token.py --client-secret client_secret.json

The Google OAuth app must be a Desktop app. The script prints the values that should
be saved as GitHub repository secrets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-secret", required=True, help="Downloaded OAuth client JSON from Google Cloud Console")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    client_secret_path = Path(args.client_secret)
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
    creds = flow.run_local_server(port=args.port, prompt="consent")
    payload = json.loads(client_secret_path.read_text(encoding="utf-8"))
    client_info = payload.get("installed") or payload.get("web") or {}

    print("\nSave these as GitHub Actions repository secrets:\n")
    print(f"GOOGLE_CLIENT_ID={client_info.get('client_id')}")
    print(f"GOOGLE_CLIENT_SECRET={client_info.get('client_secret')}")
    print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
    print("\nNever commit these values to GitHub.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
