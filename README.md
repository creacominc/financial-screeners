# UK Gilt Analyser

A small Python command-line application for comparing **conventional UK gilts held to maturity**. It can fetch current public Hargreaves Lansdown buy prices or use clean buy prices supplied in a CSV.

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
| `hl_code` | HL's short gilt code; included automatically when fetching from HL | `TS27` |
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

1. Open the repository's **Actions** tab and select **Run gilt analysis**.
2. Choose **Run workflow**, enter the investment amount, HL fee, and settlement date. Leave **Price data source** set to **Fetch current HL buy prices**.
3. Start the workflow. It downloads conventional gilts maturing after the settlement date and within the next 24 calendar months, then uses the displayed HL **Buy** prices.
4. Stay on **Actions → Run gilt analysis**. Your new run appears in the list of workflow runs; refresh the page if it has not appeared yet. Identify it by its start time and wait for a green tick, which means it succeeded.
5. Click or tap that run's title to open its **Summary** page. If you are viewing the **analyse** job's logs instead, select **Summary** to return to the run overview.
6. Scroll down to **Artifacts** and click or tap `gilt-reports-YYYY-MM-DD` (where the date is your settlement date) to download the ZIP. You must be signed into GitHub with access to this repository.
7. Open the downloaded ZIP and extract its files, then open the `.xlsx` report in Excel or the `.csv` report in a spreadsheet app.

If the run has a red cross, open the run and select **analyse** to inspect the failed step; a failed run may not have a report artifact. See [GitHub's artifact download instructions](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts) for more detail.

The downloaded ZIP contains the fetched input data, ranked CSV, and Excel report. The workflow runs the full test suite before fetching prices and retains the artifact for 30 days. To use hand-entered data instead, select **Use repository CSV** and supply its path.

## Fetch HL prices locally

```bash
gilt-fetch-hl reports/hl-current-gilts.csv --as-of 2026-07-22 --months 24
```

The fetcher reads the ISIN, HL short code (such as `TS27` or `T27A`), coupon, and maturity from HL's public conventional-gilt list. Because the list's single `Price` is not the executable offer, it visits each qualifying factsheet and records the displayed `Buy` value. Both report formats include the HL code near the front. Prices are delayed and indicative, so an actual dealing quote can differ. The command fails rather than using the midpoint when a factsheet has no usable buy price. Public-site layout changes or temporary blocking can also cause a run to fail; the manual CSV source remains available as a fallback.

## Calculation conventions and limitations

This version assumes normal cum-dividend settlement and a regular semi-annual coupon schedule whose month and day are anchored to maturity. It does not yet model the special UK gilt ex-dividend period, irregular first/last coupons, settlement holidays, index-linked gilts, strips, taxes, custody charges, or reinvestment of coupons. Use a settlement date before maturity.

## Development

All financial behavior must be covered by automated tests. Run `pytest` before committing. See `AGENTS.md` for the precise conventions contributors must preserve.
