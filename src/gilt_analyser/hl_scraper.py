import argparse
import calendar
import csv
import json
import time
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

HL_GILTS_URL = "https://www.hl.co.uk/shares/corporate-bonds-gilts/bond-prices/uk-gilts"
USER_AGENT = "uk-gilt-analyser/0.2 (+https://github.com/creacominc/uk-gilt-analyser)"


@dataclass(frozen=True)
class HLListing:
    isin: str
    hl_code: str
    name: str
    coupon_rate: str
    maturity_date: date
    detail_url: str


class _GiltTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[tuple[str | None, str]]] = []
        self._row: list[tuple[str | None, str]] | None = None
        self._cell_text: list[str] | None = None
        self._cell_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell_text, self._cell_href = [], None
        elif tag == "a" and self._cell_text is not None and self._cell_href is None:
            self._cell_href = values.get("href")

    def handle_data(self, data: str) -> None:
        if self._cell_text is not None:
            self._cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._row is not None and self._cell_text is not None:
            self._row.append((self._cell_href, " ".join("".join(self._cell_text).split())))
            self._cell_text = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year, month = value.year + month_index // 12, month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def parse_listings(html: str, as_of: date, months: int = 24) -> list[HLListing]:
    parser = _GiltTableParser()
    parser.feed(html)
    cutoff = _add_months(as_of, months)
    listings = []
    for row in parser.rows:
        if len(row) < 4 or "GBP | GB" not in row[0][1]:
            continue
        first = row[0][1]
        name, identifiers = first.split("GBP |", 1)
        identifier_parts = [part.strip() for part in identifiers.split("|")]
        isin = identifier_parts[0]
        hl_code = identifier_parts[1] if len(identifier_parts) > 1 else ""
        try:
            maturity = datetime.strptime(row[2][1], "%d %B %Y").date()
        except (ValueError, IndexError):
            continue
        if name.strip().lower().startswith("treasury") and as_of < maturity <= cutoff:
            listings.append(HLListing(isin, hl_code, name.strip(), row[1][1], maturity, urljoin(HL_GILTS_URL, row[0][0] or "")))
    return listings


def parse_buy_price(html: str, expected_isin: str) -> str:
    marker = '<script id="__NEXT_DATA__" type="application/json">'
    start = html.find(marker)
    if start < 0:
        raise ValueError("HL factsheet did not contain its structured price data")
    start += len(marker)
    end = html.find("</script>", start)
    data = json.loads(html[start:end])
    details = data["props"]["pageProps"]["investmentDetails"]
    if details.get("isin") != expected_isin:
        raise ValueError(f"HL factsheet ISIN mismatch for {expected_isin}")
    value = details.get("buy", {}).get("value")
    if value is None or str(value) == "0":
        raise ValueError(f"HL has no usable buy price for {expected_isin}")
    return str(value)


def _fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def fetch_hl_gilts(as_of: date, months: int = 24, pause_seconds: float = 0.25) -> list[dict[str, str]]:
    rows = []
    for listing in parse_listings(_fetch(HL_GILTS_URL), as_of, months):
        rows.append({
            "isin": listing.isin, "hl_code": listing.hl_code, "name": listing.name,
            "coupon_rate": listing.coupon_rate,
            "maturity_date": listing.maturity_date.isoformat(),
            "clean_buy_price": parse_buy_price(_fetch(listing.detail_url), listing.isin),
            "redemption_value": "100",
        })
        if pause_seconds:
            time.sleep(pause_seconds)
    if not rows:
        raise ValueError("HL returned no conventional gilts in the requested maturity window")
    return rows


def write_input_csv(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("isin", "hl_code", "name", "coupon_rate", "maturity_date", "clean_buy_price", "redemption_value"))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch current HL buy prices for conventional gilts")
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today(), help="start of maturity window (YYYY-MM-DD)")
    parser.add_argument("--months", type=int, default=24, help="maturity window in calendar months (default: 24)")
    args = parser.parse_args()
    if args.months < 1:
        parser.error("--months must be at least 1")
    rows = fetch_hl_gilts(args.as_of, args.months)
    write_input_csv(rows, args.output_csv)
    print(f"Wrote {len(rows)} current HL gilt prices to {args.output_csv}")
