from daft_tracker.config import TrackerConfig
from daft_tracker.parser import (
    parse_email_message,
    apply_filters,
    clean_url,
    listing_id_from_url,
    extract_price_and_period,
)


def test_parse_email_listing():
    html = """
    <html><body>
      <h2>Apartment to rent in Dublin 8</h2>
      <p>€1,450 per month</p>
      <p>1 double bedroom</p>
      <a href="https://www.daft.ie/for-rent/apartment-test-dublin-8/1234567?utm_source=email">View property</a>
      <img src="https://photos.daft.ie/test-image.jpg">
    </body></html>
    """
    listings = parse_email_message(subject="Daft alert", html=html, text=None, message_id="abc")
    assert len(listings) == 1
    listing = listings[0]
    assert listing.id == "daft-1234567"
    assert listing.source == "daft_email"
    assert listing.price_eur == 1450
    assert listing.postcode == "Dublin 8"
    assert listing.double_beds == 1
    assert listing.thumbnail_url == "https://photos.daft.ie/test-image.jpg"
    kept = apply_filters(listing, TrackerConfig())
    assert kept is not None
    assert kept.needs_review is False


def test_parse_rent_ie_email_listing():
    html = """
    <html><body>
      <h2>45 Harrington Street, Portobello, Dublin 8</h2>
      <p>€1,495 monthly</p>
      <p>1 bedroom (1 double), furnished</p>
      <a href="https://www.rent.ie/houses-to-let/45-Harrington-Street-Portobello-Dublin-8/6623555/?utm_source=email">View property</a>
    </body></html>
    """
    listings = parse_email_message(subject="Rent.ie alert", html=html, text=None, message_id="rent-msg")
    assert len(listings) == 1
    listing = listings[0]
    assert listing.id == "rentie-6623555"
    assert listing.source == "rent_ie_email"
    assert listing.price_eur == 1495
    assert listing.postcode == "Dublin 8"
    assert listing.double_beds == 1
    assert apply_filters(listing, TrackerConfig()) is not None


def test_filter_rejects_over_budget():
    html = """
    Dublin 2 €1,700 per month 1 double bedroom
    https://www.daft.ie/for-rent/apartment-expensive-dublin-2/7654321
    """
    listing = parse_email_message(subject=None, html=None, text=html, message_id="abc")[0]
    assert apply_filters(listing, TrackerConfig()) is None


def test_filter_rejects_single_room():
    html = """
    Dublin 7 €900 per month single room
    https://www.daft.ie/for-rent/single-room-dublin-7/7654322
    """
    listing = parse_email_message(subject=None, html=None, text=html, message_id="abc")[0]
    assert listing.double_beds == 0
    assert apply_filters(listing, TrackerConfig()) is None


def test_filter_rejects_no_couples_even_with_double_bed():
    html = """
    Dublin 8 €1,450 per month 1 double bedroom. No couples.
    https://www.daft.ie/for-rent/no-couples-dublin-8/7654323
    """
    listing = parse_email_message(subject=None, html=None, text=html, message_id="abc")[0]
    assert listing.double_beds == 0
    assert apply_filters(listing, TrackerConfig()) is None


def test_unknown_bed_count_stays_for_review():
    html = """
    Dublin 14 €1,300 per month apartment
    https://www.daft.ie/for-rent/apartment-unknown-bed-dublin-14/7654324
    """
    listing = parse_email_message(subject=None, html=None, text=html, message_id="abc")[0]
    kept = apply_filters(listing, TrackerConfig())
    assert kept is not None
    assert kept.needs_review is True
    assert "double_bed_count_not_visible_in_email" in kept.review_reasons


def test_url_cleaning_and_ids():
    daft_url = clean_url("https://www.daft.ie/for-rent/apartment-x/5555555?utm_source=email&utm_campaign=test&x=1)")
    assert daft_url == "https://www.daft.ie/for-rent/apartment-x/5555555?x=1"
    assert listing_id_from_url(daft_url) == "daft-5555555"

    rent_url = clean_url("https://www.rent.ie/houses-to-let/Apartment-X-Dublin-8/6666666/?utm_source=rss")
    assert rent_url == "https://www.rent.ie/houses-to-let/Apartment-X-Dublin-8/6666666"
    assert listing_id_from_url(rent_url) == "rentie-6666666"


def test_weekly_price_period():
    assert extract_price_and_period("€325 per week") == (325, "week")


def test_weekly_price_uses_monthly_equivalent_for_filter():
    html = """
    Dublin 8 €400 per week 1 double bedroom
    https://www.daft.ie/for-rent/weekly-apartment-dublin-8/7654999
    """
    listing = parse_email_message(subject=None, html=None, text=html, message_id="weekly")[0]
    assert listing.rent_period == "week"
    assert apply_filters(listing, TrackerConfig()) is None
