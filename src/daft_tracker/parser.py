from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
import csv
import re
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - fallback for minimal installs
    BeautifulSoup = None  # type: ignore[assignment]

from .config import TrackerConfig, normalize_location

SUPPORTED_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:daft\.ie|rent\.ie)/[^\s<'\"\)]+",
    re.IGNORECASE,
)
IMAGE_URL_RE = re.compile(
    r"https?://[^\s<'\"\)]+\.(?:jpg|jpeg|png|webp)(?:\?[^\s<'\"\)]*)?",
    re.IGNORECASE,
)
PRICE_RE = re.compile(
    r"(?:€|EUR\s*)(?P<amount>[0-9][0-9,]*(?:\.\d{2})?)"
    r"\s*(?P<period>per\s*(?:month|week)|/\s*(?:month|week)|monthly|weekly|p\.?m\.?|p\.?w\.?|pm|pw)?",
    re.IGNORECASE,
)
POSTCODE_RE = re.compile(r"\bDublin\s*(1|2|4|6|7|8|9|10|12|14|16)\b", re.IGNORECASE)
DOUBLE_BEDS_RE = re.compile(
    r"(?:(?P<count>\d+)\s*)?(?:double\s+(?:bed(?:room)?s?|room)s?|manželsk(?:á|e|é)\s+postel(?:e|í)?)",
    re.IGNORECASE,
)
PAREN_DOUBLE_RE = re.compile(r"\b(?P<count>\d+)\s+double\b", re.IGNORECASE)
COUPLE_UNSUITABLE_RE = re.compile(
    r"\b(?:no\s+couples?|couples?\s+not\s+(?:allowed|accepted|considered)|not\s+suitable\s+for\s+(?:a\s+)?couple|single\s+occupancy|sole\s+occupancy|(?:one|1)\s+person\s+only|single\s+(?:person|tenant)\s+only|(?:one|1)\s+tenant\s+only)\b",
    re.IGNORECASE,
)
SINGLE_BED_RE = re.compile(r"\b(?:single\s+(?:bed(?:room)?|room)|box\s+room)\b", re.IGNORECASE)
BEDROOM_RE = re.compile(r"\b(?P<count>[1-9])\s*(?:bed|bedroom)s?\b", re.IGNORECASE)
AD_ID_RE = re.compile(r"(?:^|/)(?P<id>[1-9][0-9]{4,})(?:[/?#]|$)")
TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "fbclid", "gclid"}


@dataclass(slots=True)
class ParsedListing:
    id: str
    url: str
    title: str | None = None
    location: str | None = None
    postcode: str | None = None
    price_eur: int | None = None
    double_beds: int | None = None
    image_urls: list[str] = field(default_factory=list)
    thumbnail_url: str | None = None
    source: str = "daft_email"
    source_message_id: str | None = None
    source_subject: str | None = None
    seen_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    status: str = "active"
    rent_period: str = "month"
    needs_review: bool = False
    review_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def html_to_text(html: str) -> str:
    html = unescape(html or "")
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text("\n")
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return unescape(text)


def clean_url(url: str) -> str:
    url = unescape(url).strip().rstrip(".,;:])}\"")
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS]
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))


def source_site_from_url(url: str) -> str | None:
    host = urlsplit(url).netloc.lower().split(":", 1)[0]
    if host == "daft.ie" or host.endswith(".daft.ie"):
        return "daft"
    if host == "rent.ie" or host.endswith(".rent.ie"):
        return "rent_ie"
    return None


def is_listing_url(url: str) -> bool:
    path = urlsplit(url).path.lower()
    source_site = source_site_from_url(url)
    if source_site == "daft":
        return any(part in path for part in ("/for-rent/", "/share/", "/rooms-to-rent/", "/property-for-rent/"))
    if source_site == "rent_ie":
        return any(part in path for part in ("/houses-to-let/", "/rooms-to-rent/", "/house-sharing/", "/student-accommodation/"))
    return False


def listing_id_from_url(url: str) -> str | None:
    parts = urlsplit(url)
    match = AD_ID_RE.search(parts.path + "/")
    if not match:
        return None
    source_site = source_site_from_url(url)
    if source_site == "daft":
        return f"daft-{match.group('id')}"
    if source_site == "rent_ie":
        return f"rentie-{match.group('id')}"
    return None


def extract_price_and_period(text: str) -> tuple[int | None, str]:
    candidates: list[tuple[int, str]] = []
    for match in PRICE_RE.finditer(text or ""):
        amount = match.group("amount").replace(",", "")
        try:
            value = int(round(float(amount)))
        except ValueError:
            continue
        if not 250 <= value <= 20000:
            continue
        raw_period = (match.group("period") or "").lower().replace(" ", "").replace(".", "")
        period = "week" if "week" in raw_period or raw_period in {"pw", "p/w"} else "month"
        candidates.append((value, period))
    if not candidates:
        return None, "month"
    return min(candidates, key=lambda item: item[0])


def extract_price(text: str) -> int | None:
    return extract_price_and_period(text)[0]


def extract_postcode(text: str) -> tuple[str | None, str | None]:
    match = POSTCODE_RE.search(text or "")
    if not match:
        return None, None
    postcode = f"Dublin {match.group(1)}"
    return postcode, postcode


def extract_double_beds(text: str) -> int | None:
    text = text or ""
    if COUPLE_UNSUITABLE_RE.search(text):
        return 0
    if SINGLE_BED_RE.search(text) and not DOUBLE_BEDS_RE.search(text):
        return 0

    compact_match = PAREN_DOUBLE_RE.search(text)
    if compact_match:
        return int(compact_match.group("count"))

    match = DOUBLE_BEDS_RE.search(text)
    if match:
        raw = match.group("count")
        if raw:
            return int(raw)
        return 1
    return None


def extract_title(snippet: str, subject: str | None = None) -> str | None:
    lines = [" ".join(line.strip().split()) for line in snippet.splitlines()]
    lines = [line for line in lines if line and "daft.ie" not in line.lower() and "rent.ie" not in line.lower()]
    banned = {"view", "view property", "see more", "daft.ie", "rent.ie", "open", "click here"}
    for line in lines[:8]:
        clean = line.strip(" -–|•")
        if len(clean) >= 8 and clean.lower() not in banned and not PRICE_RE.search(clean):
            return clean[:180]
    if subject:
        return " ".join(subject.split())[:180]
    return None


def nearby_text(text: str, needle: str, radius: int = 900) -> str:
    idx = text.find(needle)
    if idx < 0:
        return text[: radius * 2]
    return text[max(0, idx - radius): idx + len(needle) + radius]


def _source_name_for_url(url: str, transport: str) -> str:
    source_site = source_site_from_url(url)
    if source_site == "rent_ie":
        return f"rent_ie_{transport}"
    return f"daft_{transport}"


def parse_email_message(
    *,
    subject: str | None,
    html: str | None,
    text: str | None,
    message_id: str | None,
    received_at: str | None = None,
) -> list[ParsedListing]:
    body_text = "\n".join(part for part in [html_to_text(html or ""), text or ""] if part).strip()
    raw = "\n".join(part for part in [html or "", text or ""] if part)
    seen_at = received_at or datetime.now(timezone.utc).isoformat(timespec="seconds")

    urls: list[str] = []
    for match in SUPPORTED_URL_RE.finditer(raw + "\n" + body_text):
        url = clean_url(match.group(0))
        if is_listing_url(url) and url not in urls:
            urls.append(url)

    listings: list[ParsedListing] = []
    for url in urls:
        listing_id = listing_id_from_url(url)
        if not listing_id:
            continue
        snippet = nearby_text(body_text, url)
        if len(snippet) < 50:
            snippet = body_text[:1800]
        postcode, location = extract_postcode(snippet)
        if not postcode:
            postcode, location = extract_postcode(body_text)
        image_urls = []
        for img in IMAGE_URL_RE.findall(nearby_text(raw, url, radius=1600)):
            img = clean_url(img)
            if img not in image_urls:
                image_urls.append(img)
        double_beds = extract_double_beds(snippet)
        if double_beds is None:
            double_beds = extract_double_beds(body_text)
        price_eur, rent_period = extract_price_and_period(snippet)
        if price_eur is None:
            price_eur, rent_period = extract_price_and_period(body_text)

        listing = ParsedListing(
            id=listing_id,
            url=url,
            title=extract_title(snippet, subject),
            postcode=postcode,
            location=location,
            price_eur=price_eur,
            rent_period=rent_period,
            double_beds=double_beds,
            image_urls=image_urls[:10],
            thumbnail_url=image_urls[0] if image_urls else None,
            source=_source_name_for_url(url, "email"),
            source_message_id=message_id,
            source_subject=subject,
            seen_at=seen_at,
        )
        listings.append(listing)
    return listings


def apply_filters(listing: ParsedListing, cfg: TrackerConfig) -> ParsedListing | None:
    reasons: list[str] = list(listing.review_reasons or [])
    preserve_manual_non_active = listing.source == "manual_seed" and listing.status not in ("active", "")
    visibility_context = "feed" if listing.source.endswith("_rss") else "email"

    if listing.price_eur is None:
        if not cfg.include_unknown_price:
            return None
        reasons.append(f"price_not_visible_in_{visibility_context}")
    else:
        monthly_equivalent = listing.price_eur * 52 / 12 if listing.rent_period == "week" else listing.price_eur
        if monthly_equivalent > cfg.max_monthly_rent_eur:
            if preserve_manual_non_active:
                reasons.append("current_detail_price_above_filter")
            else:
                return None

    if listing.postcode is None:
        if not cfg.include_unknown_location:
            return None
        reasons.append(f"postcode_not_visible_in_{visibility_context}")
    elif normalize_location(listing.postcode) not in cfg.normalized_locations:
        return None

    if listing.double_beds is None:
        if not cfg.include_unknown_bed_count:
            return None
        reasons.append(f"double_bed_count_not_visible_in_{visibility_context}")
    elif listing.double_beds < cfg.min_double_beds:
        if preserve_manual_non_active:
            reasons.append("double_bed_below_filter")
        else:
            return None

    listing.needs_review = listing.needs_review or bool(reasons) or listing.status != "active"
    listing.review_reasons = list(dict.fromkeys(reasons))
    return listing


def _bool_from_csv(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "ano"}


def parse_seed_csv(path: str | Path, now_iso: str | None = None) -> list[ParsedListing]:
    p = Path(path)
    if not p.exists():
        return []
    now_iso = now_iso or datetime.now(timezone.utc).isoformat(timespec="seconds")
    listings: list[ParsedListing] = []
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = clean_url(row.get("url", ""))
            if not url:
                continue
            listing_id = row.get("id") or listing_id_from_url(url)
            if not listing_id:
                continue
            price = row.get("price_eur") or None
            beds = row.get("double_beds") or None
            image = row.get("thumbnail_url") or None
            status = (row.get("status") or "active").strip() or "active"
            rent_period = (row.get("rent_period") or "month").strip().lower() or "month"
            raw_reasons = row.get("review_reasons") or ""
            review_reasons = [r.strip() for r in re.split(r"[;|]", raw_reasons) if r.strip()]
            listings.append(ParsedListing(
                id=listing_id,
                url=url,
                title=row.get("title") or None,
                location=row.get("location") or row.get("postcode") or None,
                postcode=row.get("postcode") or row.get("location") or None,
                price_eur=int(price) if price else None,
                double_beds=int(beds) if beds else None,
                image_urls=[image] if image else [],
                thumbnail_url=image,
                source=row.get("source") or "manual_seed",
                source_message_id=None,
                seen_at=row.get("last_seen") or row.get("first_seen") or now_iso,
                status=status,
                rent_period=rent_period,
                needs_review=_bool_from_csv(row.get("needs_review")) or status != "active" or bool(review_reasons),
                review_reasons=review_reasons,
            ))
    return listings
