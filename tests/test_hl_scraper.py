from datetime import date

import pytest

from gilt_analyser.hl_scraper import _add_months, parse_buy_price, parse_listings


LIST_HTML = """
<table><tbody><tr><td><a href="https://www.hl.co.uk/shares/shares-search-results/AAA">Treasury 0.375% 22/10/2026</a><br><span>GBP | GB00AAA00001 | AAA</span></td><td>0.375</td><td>22 October 2026</td><td>99.100</td></tr>
<tr><td><a href="/shares/shares-search-results/BBB">Treasury 1.25% 22/07/2027</a><br><span>GBP | GB00BBB00002 | BBB</span></td><td>1.250</td><td>22 July 2027</td><td>97.100</td></tr>
<tr><td><a href="/strip">UK Treasury Strip</a><br><span>GBP | GB00STRIP000 | STRIP</span></td><td>0.000</td><td>7 December 2027</td><td>84.4</td></tr>
<tr><td><a href="/far">Treasury 1% 2029</a><br><span>GBP | GB00FAR00000 | FAR</span></td><td>1.000</td><td>31 July 2029</td><td>90</td></tr></tbody></table>
"""


def test_listings_are_conventional_and_within_calendar_month_window() -> None:
    rows = parse_listings(LIST_HTML, date(2026, 7, 22), months=24)
    assert [row.isin for row in rows] == ["GB00AAA00001", "GB00BBB00002"]
    assert [row.hl_code for row in rows] == ["AAA", "BBB"]
    assert rows[1].detail_url == "https://www.hl.co.uk/shares/shares-search-results/BBB"


def test_calendar_month_window_clamps_month_end() -> None:
    assert _add_months(date(2027, 1, 31), 1) == date(2027, 2, 28)
    assert _add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)


def test_buy_price_comes_from_structured_factsheet_data() -> None:
    html = '<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"investmentDetails":{"isin":"GB00AAA00001","buy":{"currency":"GBP","value":99.23}}}}}</script>'
    assert parse_buy_price(html, "GB00AAA00001") == "99.23"


def test_missing_buy_price_is_rejected() -> None:
    html = '<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"investmentDetails":{"isin":"GB00AAA00001","buy":{"currency":"GBP","value":0}}}}}</script>'
    with pytest.raises(ValueError, match="no usable buy price"):
        parse_buy_price(html, "GB00AAA00001")
