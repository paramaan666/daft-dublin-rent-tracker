from daft_tracker.config import TrackerConfig
from daft_tracker.parser import parse_email_message, apply_filters, clean_url, listing_id_from_url


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
    assert listing.price_eur == 1450
    assert listing.postcode == "Dublin 8"
    assert listing.double_beds == 1
    assert listing.thumbnail_url == "https://photos.daft.ie/test-image.jpg"
    kept = apply_filters(listing, TrackerConfig())
    assert kept is not None
    assert kept.needs_review is False


def test_filter_rejects_over_budget():
    html = """
    Dublin 2 €1,700 per month 1 double bedroom
    https://www.daft.ie/for-rent/apartment-expensive-dublin-2/7654321
    """
    listing = parse_email_message(subject=None, html=None, text=html, message_id="abc")[0]
    assert apply_filters(listing, TrackerConfig()) is None


def test_url_cleaning_and_id():
    url = clean_url("https://www.daft.ie/for-rent/apartment-x/5555555?utm_source=email&utm_campaign=test&x=1)")
    assert url == "https://www.daft.ie/for-rent/apartment-x/5555555?x=1"
    assert listing_id_from_url(url) == "daft-5555555"
