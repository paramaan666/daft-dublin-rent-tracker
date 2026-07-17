from __future__ import annotations

from datetime import datetime, timezone
import gzip
from html import unescape
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from bs4 import BeautifulSoup

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

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
MAX_FEED_BYTES = 2_000_000
MAX_SEARCH_PAGE_BYTES = 4_000_000


def _fetch_text(
    url: str,
    *,
    timeout_seconds: int,
    accept: str,
    max_bytes: int,
) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": accept,
            "Accept-Language": "en-IE,en;q=0.9",
            "Accept-Encoding": "gzip",
            "Referer": "https://www.rent.ie/",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ValueError(f"Rent.ie response exceeded {max_bytes} bytes")
        if (response.headers.get("Content-Encoding") or "").lower() == "gzip":
            payload = gzip.decompress(payload)
        charset = response.headers.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def fetch_rent_ie_feed(url: str, *, timeout_seconds: int = 20) -> str:
    return _fetch_text(
        url,
        timeout_seconds=timeout_seconds,
        accept="application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.1",
        max_bytes=MAX_FEED_BYTES,
    )


def rent_ie_search_url(feed_url: str) -> str:
    parts = urlsplit(feed_url)
    return urlunsplit(("https", "www.rent.ie", parts.path.rstrip("/") + "/", "", ""))


def fetch_rent_ie_search_page(url: str, *, timeout_seconds: int = 20) -> str:
    return _fetch_text(
        url,
        timeout_seconds=timeout_seconds,
        accept="text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        max_bytes=MAX_SEARCH_PAGE_BYTES,
    )


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


def _listing_url_from_href(href: str, base_url: str) -> str | None:
    url = clean_url(urljoin(base_url, href))
    if source_site_from_url(url) != "rent_ie" or not is_listing_url(url):
        return None
    if not listing_id_from_url(url):
        return None
    return url


def _listing_urls_in_node(node: object, base_url: str) -> set[str]:
    urls: set[str] = set()
    find_all = getattr(node, "find_all", None)
    if find_all is None:
        return urls
    for anchor in find_all("a", href=True):
        url = _listing_url_from_href(str(anchor.get("href") or ""), base_url)
        if url:
            urls.add(url)
            if len(urls) > 1:
                break
    return urls


def _listing_context(anchor: object, base_url: str) -> tuple[object, str]:
    current = anchor
    fallback = anchor
    fallback_text = " ".join(getattr(anchor, "get_text")(" ", strip=True).split())
    for _ in range(10):
        current = getattr(current, "parent", None)
        if current is None:
            break
        text = " ".join(current.get_text(" ", strip=True).split())
        urls = _listing_urls_in_node(current, base_url)
        if len(urls) == 1:
            fallback = current
            fallback_text = text
            price, _ = extract_price_and_period(text)
            if price is not None:
                return current, text
        elif len(urls) > 1:
            break
    return fallback, fallback_text


def _node_images(node: object, base_url: str) -> list[str]:
    urls: list[str] = []
    find_all = getattr(node, "find_all", None)
    if find_all is None:
        return urls
    for image in find_all("img", src=True):
        raw_url = str(image.get("src") or "")
        url = clean_url(urljoin(base_url, raw_url))
        if IMAGE_URL_RE.search(url) and url not in urls:
            urls.append(url)
    return urls[:10]


def parse_rent_ie_search_page(
    html_text: str,
    *,
    source_url: str,
    seen_at: str | None = None,
) -> list[ParsedListing]:
    soup = BeautifulSoup(html_text or "", "html.parser")
    page_seen_at = seen_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    best_anchor_by_url: dict[str, object] = {}

    for anchor in soup.find_all("a", href=True):
        url = _listing_url_from_href(str(anchor.get("href") or ""), source_url)
        if not url:
            continue
        label = " ".join(anchor.get_text(" ", strip=True).split())
        previous = best_anchor_by_url.get(url)
        previous_label = " ".join(previous.get_text(" ", strip=True).split()) if previous else ""
        if previous is None or len(label) > len(previous_label):
            best_anchor_by_url[url] = anchor

    listings: list[ParsedListing] = []
    for url, anchor in best_anchor_by_url.items():
        listing_id = listing_id_from_url(url)
        if not listing_id:
            continue
        context_node, context_text = _listing_context(anchor, source_url)
        title = " ".join(anchor.get_text(" ", strip=True).split())[:180] or None
        postcode, location = extract_postcode(context_text)
        price_eur, rent_period = extract_price_and_period(context_text)
        images = _node_images(context_node, source_url)

        listings.append(ParsedListing(
            id=listing_id,
            url=url,
            title=title,
            location=location,
            postcode=postcode,
            price_eur=price_eur,
            rent_period=rent_period,
            double_beds=extract_double_beds(context_text),
            image_urls=images,
            thumbnail_url=images[0] if images else None,
            source="rent_ie_rss",
            source_message_id=listing_id,
            source_subject=source_url,
            seen_at=page_seen_at,
        ))

    return listings
