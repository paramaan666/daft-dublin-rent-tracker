from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import os
from typing import Any, Iterator

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
TOKEN_URI = "https://oauth2.googleapis.com/token"


@dataclass(slots=True)
class GmailMessage:
    id: str
    subject: str | None
    internal_date: str | None
    html: str
    text: str


def credentials_from_env() -> Credentials | None:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
    if not (client_id and client_secret and refresh_token):
        return None
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds


def gmail_service_from_env() -> Any | None:
    creds = credentials_from_env()
    if creds is None:
        return None
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def list_message_ids(service: Any, query: str, max_messages: int = 50) -> list[str]:
    ids: list[str] = []
    page_token: str | None = None
    while len(ids) < max_messages:
        request = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=min(100, max_messages - len(ids)),
            pageToken=page_token,
        )
        response = request.execute()
        ids.extend([item["id"] for item in response.get("messages", [])])
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return ids


def fetch_message(service: Any, message_id: str) -> GmailMessage:
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    headers = {h.get("name", "").lower(): h.get("value") for h in msg.get("payload", {}).get("headers", [])}
    html_parts: list[str] = []
    text_parts: list[str] = []
    collect_parts(msg.get("payload", {}), html_parts, text_parts)
    internal_date = msg.get("internalDate")
    internal_iso = None
    if internal_date:
        internal_iso = datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc).isoformat(timespec="seconds")
    return GmailMessage(
        id=message_id,
        subject=headers.get("subject"),
        internal_date=internal_iso,
        html="\n".join(html_parts),
        text="\n".join(text_parts),
    )


def collect_parts(payload: dict[str, Any], html_parts: list[str], text_parts: list[str]) -> None:
    mime = payload.get("mimeType", "")
    body_data = (payload.get("body") or {}).get("data")
    if body_data:
        decoded = decode_body(body_data)
        if mime == "text/html":
            html_parts.append(decoded)
        elif mime == "text/plain":
            text_parts.append(decoded)
    for part in payload.get("parts", []) or []:
        collect_parts(part, html_parts, text_parts)


def decode_body(data: str) -> str:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii")).decode("utf-8", errors="replace")
