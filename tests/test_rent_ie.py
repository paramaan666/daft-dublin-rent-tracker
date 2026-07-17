from daft_tracker.config import TrackerConfig
from daft_tracker.parser import apply_filters
from daft_tracker.rent_ie import parse_rent_ie_feed


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
