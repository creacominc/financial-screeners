"""Fetch public WSJ Treasury tables for inspection, without converting prices.

Output is raw source data, not an input CSV for the financial analyser.
"""
import argparse
import csv
import json
import ssl
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from us_treasury_analyser.wsj_fetcher import extract_tables

URL = "https://www.wsj.com/market-data/bonds/treasuries"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("reports/wsj_probe"))
    parser.add_argument("--html", type=Path, help="inspect an already downloaded page instead of fetching")
    args = parser.parse_args()
    if args.html:
        html = args.html.read_text(encoding="utf-8")
    else:
        # Use the OS CA bundle where available. HTTPS verification stays enabled.
        ca = Path("/etc/ssl/cert.pem")
        context = ssl.create_default_context(cafile=str(ca) if ca.is_file() else None)
        request = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            html = response.read().decode("utf-8")
    tables = extract_tables(html)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"source_url": URL, "inspection_time_utc": datetime.now(timezone.utc).isoformat(),
               "data_kind": "raw indicative quotes; not analyser input", "tables": tables}
    args.output.with_suffix(".json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    with args.output.with_suffix(".csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("table", "source_date", "maturityDate", "coupon", "bid", "ask", "askYield", "change"))
        writer.writeheader()
        for kind, table in tables.items():
            for row in table["instruments"]:
                writer.writerow({"table": kind, "source_date": table["timestamp"], **row})
            print(f"{kind}: {len(table['instruments'])} rows; source date {table['timestamp']}")
    print(f"Saved raw data to {args.output.with_suffix('.json')} and {args.output.with_suffix('.csv')}")


if __name__ == "__main__":
    main()
