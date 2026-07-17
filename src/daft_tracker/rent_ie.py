from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from .parser import (
    IMAGE_URL_RE,
    ParsedListing,
    clean_url,
    extract_double_beds,
    extract_postcode,
    extract_price_and_period,
    html_to_text,
    is_listing_url,
    listing_id_from_url,
    source_site_from_url,
)

DEFAULT_USER_AGENT = "daft-dublin-rent-tracker/0.1 (+https://github.com/paramaan666/daft-dublin-rent-tracker)"
MAX_FEED_BYTES = 2_000_000


def fetch_rent_ie_feed(url: str, *, timeout_seconds: int = 20) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.1",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = response.read(MAX_FEED_BYTES + 1)
        if len(payload) > MAX_FEED_BYTES:
            raise ValueError(f"Rent.ie feed exceeded {MAX_FEED_BYTES} bytes")
        charset = response.headers.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(item: ElementTree.Element, name: str) -> str:
    for child in item:
        if _local_name(child.tag) == name.lower():
            return "".join(child.itertext()).strip()
    return ""


def _rss_items(root: ElementTree.Element) -> list[ElementTree.Element]:
    return [node for node in root.iter() if _local_name(node.tag) == "item"]


def _image_urls(description_html: str, item: ElementTree.Element) -> list[str]:
    urls: list[str] = []
    for raw_url in IMAGE_URL_RE.findall(description_html or ""):
        url = clean_url(raw_url)
        if url not in urls:
            urls.append(url)

    for child in item:
        if _local_name(child.tag) not in {"enclosure", "content", "thumbnail"}:
            continue
        raw_url = child.attrib.get("url") or child.attrib.get("href")
        if raw_url:
            url = clean_url(raw_url)
            if url not in urls:
                urls.append(url)
    return urls[:10]


def parse_rent_ie_feed(
    xml_text: str,
    *,
    feed_url: str | None = None,
    seen_at: str | None = None,
) -> list[ParsedListing]:
    root = ElementTree.fromstring(xml_text)
    feed_seen_at = seen_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    listings: list[ParsedListing] = []

    for item in _rss_items(root):
        title = unescape(_child_text(item, "title")).strip() or None
        link = clean_url(_child_text(item, "link") or _child_text(item, "guid"))
        if not link or source_site_from_url(link) != "rent_ie" or not is_listing_url(link):
            continue

        listing_id = listing_id_from_url(link)
        if not listing_id:
            continue

        description_html = unescape(_child_text(item, "description"))
        description_text = html_to_text(description_html)
        combined = "\n".join(part for part in [title or "", description_text] if part)
        postcode, location = extract_postcode(combined)
        price_eur, rent_period = extract_price_and_period(combined)
        images = _image_urls(description_html, item)
        guid = _child_text(item, "guid") or listing_id

        listings.append(ParsedListing(
            id=listing_id,
            url=link,
            title=title,
            location=location,
            postcode=postcode,
            price_eur=price_eur,
            rent_period=rent_period,
            double_beds=extract_double_beds(combined),
            image_urls=images,
            thumbnail_url=images[0] if images else None,
            source="rent_ie_rss",
            source_message_id=guid,
            source_subject=feed_url,
            seen_at=feed_seen_at,
        ))

    return listings
