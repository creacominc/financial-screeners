# Financial Screeners

Independent Python tools for UK gilts, US Treasuries and [FTSE equities](FTSE_SCREENER.md), with room for a future US equities package. Existing commands and input formats remain supported. GBP and USD analyses stay separate.

The UK gilt tool is a command-line application for comparing **conventional UK gilts held to maturity**. It can fetch current public Hargreaves Lansdown buy prices or use clean buy prices supplied in a CSV.

## Disclaimer

This software and its data, calculations, rankings and reports are provided for personal research and informational purposes only. They do not constitute investment, financial, tax or legal advice, or a recommendation to buy, sell or hold any investment.

**Use this software entirely at your own risk. You are solely responsible for your investment decisions and for any losses, costs or other consequences arising from your use of, or reliance on, this software or its outputs.** Independently verify prices, calculations, assumptions, eligibility and dealing terms before acting. Quotes may be delayed, incomplete or incorrect, and calculated returns are estimates, not guarantees. Investments can fall in value and you may lose capital.

The software is provided "as is" and "as available", without warranties of any kind, express or implied, including accuracy, completeness, fitness for a particular purpose or uninterrupted availability. To the fullest extent permitted by applicable law, the authors and contributors accept no liability for losses or damages arising from use of the software or reliance on its outputs. Nothing in this disclaimer excludes or limits liability that cannot lawfully be excluded or limited.

## What it calculates

- Semi-annual coupon dates, working backwards in six-month intervals from maturity.
- Accrued interest on an Actual/Actual coupon-period basis and the resulting dirty price.
- Nominal gilt quantity affordable within the investment budget after a configurable dealing fee.
- Remaining coupons, redemption at par, total cash profit, and annual effective yield (XIRR using Actual/365 timing).
- Coupon income separately from the redemption gain. Conventional UK gilts are generally exempt from UK Capital Gains Tax for individuals; coupon income can still be taxable. The program does not calculate personal tax and is not financial or tax advice.
- CSV and Excel reports include approximate `months_to_maturity`, measured from settlement as actual days × 12 / 365 and rounded to two decimals.
- Reports rank net annualised returns after the dealing fee in descending 0.1 percentage-point bands (for example, 4.20% up to but excluding 4.30%). Within each band, shorter time to maturity ranks first, then higher precise yield, then ISIN. Negative yields use the same floor-based bands. Precise yields remain in the report. Two yields on opposite sides of a band boundary stay in yield-band order even when very close.

Money and rate calculations use Python `Decimal`. Excel cells are converted to numeric values only when the already-calculated results are written.

A separate [US Treasury analyser](US_TREASURIES.md) fetches public indicative WSJ quotes for Treasury bills and fixed-rate notes/bonds in the next 24 months, or accepts supplied broker offer prices. It writes `us-treasury-comparison-YYYY-MM-DD.csv` and Excel using the same ranking approach, with its own command, input format and GitHub workflow.

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

1. Open the repository's **Actions** tab and select **Run gilt comparison**.
2. Choose **Run workflow**, enter the investment amount, HL fee, and settlement date. Leave **Price data source** set to **Fetch current HL buy prices**.
3. Start the workflow. It downloads conventional gilts maturing after the settlement date and within the next 24 calendar months, then uses the displayed HL **Buy** prices.
4. Stay on **Actions → Run gilt comparison**. Your new run appears in the list of workflow runs; refresh the page if it has not appeared yet. Identify it by its start time and wait for a green tick, which means it succeeded.
5. Click or tap that run's title to open its **Summary** page. If you are viewing the **analyse** job's logs instead, select **Summary** to return to the run overview.
6. Scroll down to **Artifacts** and click or tap `gilt-comparison-YYYY-MM-DD` (where the date is your settlement date) to download the ZIP. You must be signed into GitHub with access to this repository.
7. Open the downloaded ZIP and extract its files, then open the `.xlsx` report in Excel or the `.csv` report in a spreadsheet app.

If the run has a red cross, open the run and select **analyse** to inspect the failed step; a failed run may not have a report artifact. See [GitHub's artifact download instructions](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts) for more detail.

The run page Summary shows up to 50 ranked gilt selections, followed by quote and calculation details. It includes the budget, settlement date, annualised return and actual cash profit. The downloaded ZIP contains the fetched input data, ranked CSV, Excel report and the same Markdown summary. The workflow runs the full test suite before fetching prices and retains the artifact for 30 days. To use hand-entered data instead, select **Use repository CSV** and supply its path.

## Fetch HL prices locally

```bash
gilt-fetch-hl reports/hl-current-gilts.csv --as-of 2026-07-22 --months 24
```

The fetcher reads the ISIN, HL short code (such as `TS27` or `T27A`), coupon, and maturity from HL's public conventional-gilt list. Because the list's single `Price` is not the executable offer, it visits each qualifying factsheet and records the displayed `Buy` value. Both report formats include the HL code near the front. Prices are delayed and indicative, so an actual dealing quote can differ. The command fails rather than using the midpoint when a factsheet has no usable buy price. Public-site layout changes or temporary blocking can also cause a run to fail; the manual CSV source remains available as a fallback.

## Calculation conventions and limitations

This version assumes normal cum-dividend settlement and a regular semi-annual coupon schedule whose month and day are anchored to maturity. It does not yet model the special UK gilt ex-dividend period, irregular first/last coupons, settlement holidays, index-linked gilts, strips, taxes, custody charges, or reinvestment of coupons. Use a settlement date before maturity.

## Development

All financial behavior must be covered by automated tests. Run `pytest` before committing. See `AGENTS.md` for the precise conventions contributors must preserve.

## License

No open-source license has been granted for this repository at present. All rights are reserved by the respective copyright holders, except where applicable law permits otherwise. Public availability of the source code does not itself grant permission to use, copy, modify or redistribute it.

Third-party dependencies and data remain subject to their respective licenses and terms. The disclaimer above does not grant a software license.

Comparison reports default to dated prefixes: `gilt-comparison-YYYY-MM-DD`,
`us-treasury-comparison-YYYY-MM-DD`, and `ftse-comparison-YYYY-MM-DD`.
Bond dates are settlement dates; FTSE dates are the requested as-of dates.
An explicit `--output` prefix is preserved. Bond columns place months to maturity,
net annualised return and rank immediately after name. FTSE columns place existing
1-, 3- and 5-year price returns and research/portfolio ranks immediately after ISIN;
these historical returns are not annualised yields or forecasts.
