from daft_tracker.config import TrackerConfig
from daft_tracker.parser import apply_filters
from daft_tracker.rent_ie import (
    parse_rent_ie_feed,
    parse_rent_ie_reader_text,
    parse_rent_ie_search_page,
    rent_ie_reader_url,
    rent_ie_search_url,
)


RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Rent Dublin</title>
    <link>https://www.rent.ie/houses-to-let/dublin/co-dublin/</link>
    <description>Latest Dublin properties</description>
    <item>
      <title>45 Harrington Street, Portobello, Dublin 8</title>
      <link>https://www.rent.ie/houses-to-let/45-Harrington-Street-Portobello-Dublin-8/6623555/</link>
      <guid>rent-6623555</guid>
      <pubDate>Fri, 17 Jul 2026 08:30:00 +0000</pubDate>
      <description><![CDATA[
        <p>€1,495 monthly</p>
        <p>1 bedroom (1 double), 1 bathroom, furnished</p>
        <img src="https://photos-a.propertyimages.ie/media/5/5/5/6623555/test.jpg">
      ]]></description>
    </item>
    <item>
      <title>Expensive Apartment, Dublin 2</title>
      <link>https://www.rent.ie/houses-to-let/Expensive-Apartment-Dublin-2/6623999/</link>
      <description><![CDATA[
        <p>€2,400 monthly</p>
        <p>2 bedrooms (2 double)</p>
      ]]></description>
    </item>
  </channel>
</rss>
"""


SEARCH_HTML = """
<html><body>
  <div class="search-result">
    <a href="/rooms-to-rent/Cooke-Hall-Clancy-Quay-Dublin-8/6561900/">
      <img src="https://photos-a.propertyimages.ie/media/0/0/9/6561900/search.jpg">
    </a>
    <h2>
      <a href="/rooms-to-rent/Cooke-Hall-Clancy-Quay-Dublin-8/6561900/">
        Cooke Hall, Clancy Quay, Dublin 8
      </a>
    </h2>
    <div>€960 monthly</div>
    <div>double bedroom €960 monthly</div>
    <p>Entered 10 hours ago</p>
  </div>
  <div class="search-result">
    <h2>
      <a href="/rooms-to-rent/Old-County-Road-Dublin-12/6561901/">
        Old County Road, Dublin 12
      </a>
    </h2>
    <div>€564 monthly</div>
    <div>single bedroom €564 monthly</div>
  </div>
</body></html>
"""


READER_MARKDOWN = """
Title: Rooms to Rent in Dublin

URL Source: https://www.rent.ie/rooms-to-rent/renting_dublin/

Markdown Content:
## [1. Cooke Hall, Clancy Quay, Dublin 8](https://www.rent.ie/rooms-to-rent/Cooke-Hall-Clancy-Quay-Dublin-8/6561900/)

#### €960 monthly

### double bedroom €960 monthly

Entered 10 hours ago

## [2. Old County Road, Dublin 12](https://www.rent.ie/rooms-to-rent/Old-County-Road-Dublin-12/6561901/)

#### €564 monthly

### single bedroom €564 monthly

Entered 1 day ago
"""


def test_parse_rent_ie_rss_and_filter():
    listings = parse_rent_ie_feed(
        RSS,
        feed_url="https://rss.rent.ie/houses-to-let/renting_dublin/",
        seen_at="2026-07-17T08:30:00+00:00",
    )
    assert len(listings) == 2

    listing = listings[0]
    assert listing.id == "rentie-6623555"
    assert listing.source == "rent_ie_rss"
    assert listing.title == "45 Harrington Street, Portobello, Dublin 8"
    assert listing.postcode == "Dublin 8"
    assert listing.price_eur == 1495
    assert listing.rent_period == "month"
    assert listing.double_beds == 1
    assert listing.thumbnail_url.endswith("/test.jpg")
    assert listing.seen_at == "2026-07-17T08:30:00+00:00"
    assert apply_filters(listing, TrackerConfig()) is not None

    assert apply_filters(listings[1], TrackerConfig()) is None


def test_rss_missing_bed_count_is_marked_for_review():
    xml = RSS.replace("1 bedroom (1 double), 1 bathroom, furnished", "studio apartment to rent")
    listing = parse_rent_ie_feed(xml)[0]
    kept = apply_filters(listing, TrackerConfig())
    assert kept is not None
    assert "double_bed_count_not_visible_in_feed" in kept.review_reasons


def test_search_page_fallback_parses_and_filters_rooms():
    source_url = "https://www.rent.ie/rooms-to-rent/renting_dublin/"
    listings = parse_rent_ie_search_page(
        SEARCH_HTML,
        source_url=source_url,
        seen_at="2026-07-17T12:00:00+00:00",
    )
    assert len(listings) == 2

    double_room = listings[0]
    assert double_room.id == "rentie-6561900"
    assert double_room.title == "Cooke Hall, Clancy Quay, Dublin 8"
    assert double_room.postcode == "Dublin 8"
    assert double_room.price_eur == 960
    assert double_room.rent_period == "month"
    assert double_room.double_beds == 1
    assert double_room.thumbnail_url.endswith("/search.jpg")
    assert apply_filters(double_room, TrackerConfig()) is not None

    assert listings[1].double_beds == 0
    assert apply_filters(listings[1], TrackerConfig()) is None


def test_feed_url_maps_to_public_search_page():
    assert rent_ie_search_url(
        "https://rss.rent.ie/rooms-to-rent/renting_dublin/"
    ) == "https://www.rent.ie/rooms-to-rent/renting_dublin/"


def test_reader_fallback_parses_and_filters_rooms():
    source_url = "https://www.rent.ie/rooms-to-rent/renting_dublin/"
    listings = parse_rent_ie_reader_text(
        READER_MARKDOWN,
        source_url=source_url,
        seen_at="2026-07-17T13:00:00+00:00",
    )
    assert len(listings) == 2

    double_room = listings[0]
    assert double_room.id == "rentie-6561900"
    assert double_room.title == "Cooke Hall, Clancy Quay, Dublin 8"
    assert double_room.postcode == "Dublin 8"
    assert double_room.price_eur == 960
    assert double_room.rent_period == "month"
    assert double_room.double_beds == 1
    assert double_room.source == "rent_ie_rss"
    assert apply_filters(double_room, TrackerConfig()) is not None

    assert listings[1].double_beds == 0
    assert apply_filters(listings[1], TrackerConfig()) is None


def test_public_search_url_maps_to_reader_url():
    assert rent_ie_reader_url(
        "https://www.rent.ie/rooms-to-rent/renting_dublin/"
    ) == "https://r.jina.ai/https://www.rent.ie/rooms-to-rent/renting_dublin/"
