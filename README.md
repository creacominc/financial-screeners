# UK Gilt Analyser

A small Python command-line application for comparing **conventional UK gilts held to maturity** from clean buy prices supplied in a CSV. It does not scrape or download live prices.

## What it calculates

- Semi-annual coupon dates, working backwards in six-month intervals from maturity.
- Accrued interest on an Actual/Actual coupon-period basis and the resulting dirty price.
- Nominal gilt quantity affordable within the investment budget after a configurable dealing fee.
- Remaining coupons, redemption at par, total cash profit, and annual effective yield (XIRR using Actual/365 timing).
- Coupon income separately from the redemption gain. Conventional UK gilts are generally exempt from UK Capital Gains Tax for individuals; coupon income can still be taxable. The program does not calculate personal tax and is not financial or tax advice.
- Ranked CSV and Excel reports, ordered by net annualised return after the dealing fee.

Money and rate calculations use Python `Decimal`. Excel cells are converted to numeric values only when the already-calculated results are written.

## Setup

Requires Python 3.11 or later.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pytest
```

On Windows PowerShell, activate with `.venv\\Scripts\\Activate.ps1`.

## Input CSV

See `examples/gilts.csv`. Required columns are:

| Column | Meaning | Example |
|---|---|---|
| `isin` | Gilt ISIN | `GB00BL68HJ26` |
| `name` | Descriptive name | `Treasury 0.375% 2026` |
| `coupon_rate` | Annual coupon percentage, not a decimal fraction | `0.375` |
| `maturity_date` | ISO date | `2026-10-22` |
| `clean_buy_price` | Current clean offer price per £100 nominal | `98.86` |
| `redemption_value` | Optional; defaults to £100 | `100` |

Confirm that the price is a current **buy/offer** price, not the sell/bid price.

## Usage

Compare the cash flows from putting up to £5,000 into each gilt, using an £11.95 HL dealing fee and an explicit settlement date:

```bash
gilt-analyser examples/gilts.csv \\
  --investment 5000 \\
  --fee 11.95 \\
  --settlement-date 2026-07-22 \\
  --output reports/gilts-2026-07-22
```

This creates `reports/gilts-2026-07-22.csv` and `.xlsx`. If `--settlement-date` is omitted, today's date is used. The investment is a budget **per gilt comparison**, not divided across the rows. Nominal holdings are rounded down to the nearest £0.01 so the fee and dirty consideration do not exceed the budget; unused cash is reported. Yield is measured on capital actually deployed.


## Run from a phone with GitHub Actions

The repository includes a manually triggered workflow, so no local computer is required:

1. Update `examples/gilts.csv` with the current clean offer prices and commit the change.
2. Open the repository's **Actions** tab and select **Run gilt analysis**.
3. Choose **Run workflow**, enter the investment amount, HL fee, settlement date, and input CSV path, then start it.
4. Open the completed workflow run and download the `gilt-reports-YYYY-MM-DD` artifact.

The downloaded ZIP contains both the ranked CSV and Excel reports. The workflow runs the full test suite before generating them and retains the artifact for 30 days.

## Calculation conventions and limitations

This initial version assumes normal cum-dividend settlement and a regular semi-annual coupon schedule whose month and day are anchored to maturity. It does not yet model the special UK gilt ex-dividend period, irregular first/last coupons, settlement holidays, index-linked gilts, strips, taxes, custody charges, reinvestment of coupons, or live price retrieval. Use a settlement date before maturity.

## Development

All financial behavior must be covered by automated tests. Run `pytest` before committing. See `AGENTS.md` for the precise conventions contributors must preserve.

