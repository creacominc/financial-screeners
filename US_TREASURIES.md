# US Treasury analyser

## Steps in brief

1. Install this project using the setup in `README.md` (Python 3.11+).
2. Run the command below with your USD budget, fee and settlement date.
3. Open `reports/us_treasuries.xlsx` or `.csv`.
4. Confirm a shortlisted security's CUSIP, current price and minimum purchase size at Schwab.

```bash
us-treasury-analyser --investment 5000 --fee 0 \
  --settlement-date 2026-10-15 --output reports/us_treasuries
```

With no input CSV, the command fetches the latest public [WSJ Treasury quote tables](https://www.wsj.com/market-data/bonds/treasuries) and analyses bills and fixed-coupon notes/bonds maturing strictly after settlement and within the next **24 calendar months**, inclusive of the end date. `--fetch-wsj` makes that choice explicit. `--months 12` changes the window.

The budget and fee are USD amounts **per security comparison**, not a single portfolio allocation. The example settlement date is an assumption; supply the actual intended settlement date. Output files are:

- `us_treasuries.csv`: ranked comparison.
- `us_treasuries.xlsx`: the same comparison in Excel.
- `us_treasuries_input.csv`: normalized fetched prices, assumptions and provenance.
- `us_treasuries_source.json`: raw source tables, their published dates and fetch timestamp.
- `us_treasuries_excluded.csv`: offers exceeding the calculation budget, if `--skip-unaffordable` is supplied.

Fetch errors, missing or malformed quotes, ambiguous duplicate terms, and stale data cause failure. The command does not fall back to old CSVs or illustrative prices. The default maximum quote age is seven calendar days before the supplied settlement date, allowing for weekends and nearby settlement dates. Quotes dated after settlement are rejected. `--max-quote-age-days 3` tightens the age limit. Published quote dates can differ between tables and are retained per security; fetch time is separate. The source is not guaranteed to be intraday or simultaneous with Schwab.

## What the public source can establish

WSJ identifies the quote source as Tullett Prebon. It supplies maturity, bid, ask and ask yield, plus coupon for notes/bonds. These are **indicative market quotes**, not executable Schwab offers.

The public tables do not supply CUSIPs or dealer minimums, increments and maximum quantities. The app leaves `cusip` blank and uses a separate `security_id`, such as `WSJ:bill:2027-04-15:0`. That reference identifies terms within the source; it is not a CUSIP and does not independently confirm a tradable instrument. Because WSJ combines notes and bonds, fixed-coupon rows are labelled `note_or_bond` rather than guessing their original issue type. Duplicate terms cause failure instead of inventing distinct identifiers. TIPS, floating-rate notes and STRIPS are not imported from their separate categories or calculated by this model.

For public quotes, calculations use assumed $1,000 minimum face amount and $1,000 increments. Reports label `quantity_basis=assumed`, leave the dealer `minimum_nominal`, `nominal_increment` and `maximum_nominal` blank, and show the calculation assumptions separately as `analysis_minimum_nominal` and `analysis_nominal_increment`. They do not establish availability at that size. Supply broker offers in a CSV to enforce the actual minimum and maximum sizes. `quote_status=indicative` appears near the front of the public-source report.

## Quote conversion and calculations

All financial parsing and arithmetic uses `Decimal`. Binary float conversion occurs only when writing final values to Excel cells.

**Notes and bonds:** WSJ uses padded Treasury cash-price notation. For example, `99.0320` means `99 + 3/32 + 2/256 = 99.1015625` per $100; it does not mean a decimal price of 99.0320. The conversion follows the worked cash-market examples in [CME's Treasury pricing guide](https://www.cmegroup.com/education/courses/introduction-to-treasuries/calculating-us-treasury-pricing). The parser rejects unknown notation. `source_ask_quote` preserves the original string; `price_basis` identifies the conversion.

**Bills:** the Ask column is a bank-discount percentage, not a dollar price. At the requested analysis settlement, the app derives an indicative price per $100 as `100 - ask_discount_rate_pct * actual_days_to_maturity / 360`, using [TreasuryDirect's bill pricing formula](https://www.treasurydirect.gov/marketable-securities/understanding-pricing/). The published discount rate is held constant for this calculation. This estimates a price for the requested settlement; it does not reconstruct a broker's historical cash quote or guarantee that the rate is still available. The assumption is explicit in `price_basis`, and `price_settlement_date` records the date used. No settlement calendar or holidays are inferred. Reusing a normalized derived bill-price CSV with a different settlement date is rejected; fetch again for the new date. The calculation retains full precision rather than applying auction or broker-specific rounding.

Fixed-coupon securities pay regular semiannual coupons. Dates are constructed backwards from maturity, preserving month-end dates including leap-year February. Coupons are strictly after settlement, with redemption at maturity. Accrued interest uses half the annual coupon per $100 multiplied by actual elapsed days / actual days in the coupon period. See [Treasury auction regulations, Appendix B](https://www.treasurydirect.gov/files/laws-and-regulations/auction-regulations-uoc/31-cfr-part-356.pdf).

Purchases are rounded down to the minimum-plus-increment grid after dirty price and the fee, with a supplied maximum limiting face amount when available. The report separates gross coupons, redemption proceeds, redemption minus clean consideration, accrued interest paid, fee, total cash profit and unused cash. Redemption gain has no UK CGT-exempt label or implied tax treatment. Yield is measured on cash actually deployed.

`net_annualised_return_pct` is annual effective money-weighted yield after the dealing fee and before personal income tax, with dated cash flows and Actual/365 exponents. `source_ask_yield_pct` preserves WSJ's quoted yield separately. Supplied broker quotes may use `broker_ytm_pct`. These fields are not substituted for our calculated yield. Coupons are not assumed to be reinvested.

Reports use the UK app's descending 0.1 percentage-point yield bands, shorter maturity first within each band, then precise yield and identifier. Common cash-flow and return fields retain the gilt report names. UK calculations and workflows are unchanged.

This model assumes regular, seasoned fixed-principal securities. It does not calculate TIPS, floating-rate notes, STRIPS, savings bonds, CDs, irregular coupons, personal tax, FX conversion, settlement calendars, weekend/holiday payment delays or broker cash rounding. A USD yield alone does not establish a better GBP outcome; a future combined US/UK comparison needs explicit currency, conversion-cost and tax assumptions.

## Supplied broker CSV

```bash
us-treasury-analyser examples/us_treasuries_schwab.csv \
  --investment 5000 --fee 0 --settlement-date 2026-10-15 \
  --skip-unaffordable --output reports/us_treasuries_schwab
```

Required columns are `cusip,name,security_type,coupon_rate,maturity_date,clean_buy_price`. `security_type` is `bill`, `note` or `bond`; coupon is an annual percentage (`4.125`, not `0.04125`), with `0` for bills. Dates use ISO format. Price is a decimal clean **offer** per $100 face value, not yield or dollars per bond.

Optional fields: `minimum_nominal` and `nominal_increment` default to $1,000; `maximum_nominal` caps the available face amount; `broker_ytm_pct`, `quote_date` and `price_source` record source information. Check actual broker limits rather than relying on those defaults. CSV mode does not independently verify quote freshness or CUSIP checksums. Additional provenance columns in fetched input are retained on round-trip.

`examples/us_treasuries_schwab.csv` preserves the 14 conventional quotes supplied on 14 October 2026. Its quote date is the supplied date, not an independently verified market timestamp. Schwab quantities are in $1,000 face-value units: `Min=600` is $600,000, and `Max=15001` is $15,001,000. The pasted table does not state an increment, so a one-unit increment is documented as the example assumption. Four offers fit the $5,000 example budget; ten are recorded as unaffordable. The two TIPS rows are preserved with reasons in `examples/us_treasuries_schwab_excluded.csv` and are not calculated.

`examples/us_treasuries.csv` contains fictitious identifiers and prices for testing only. It is not used by the default live command.

`--skip-unaffordable` records valid offers exceeding the budget rather than aborting. Invalid or unsupported inputs still fail. When no offers fit, the comparison is header-only and the exclusions file records every offer; the console states the count.

## Fetch without analysis

```bash
us-treasury-fetch-wsj reports/us_treasuries_input.csv \
  --as-of 2026-10-15 --months 24
```

This creates normalized input and a `.source.json` snapshot. Use the same settlement date when analysing that input.

## Run from a phone with GitHub Actions

1. In the repository's **Actions** tab, choose **Run US Treasury analysis**.
2. Select **Run workflow**. Enter the USD investment budget, fee and actual intended settlement date.
3. Leave **Price data source** on **Fetch current WSJ indicative quotes**, and **Maturity window** at `24` for the same range as the UK analyser.
4. Wait for the green tick, then open the run's **Summary** page.
5. Under **Artifacts**, download `us-treasury-reports-YYYY-MM-DD`. Extract the ZIP and open `us_treasuries.xlsx` or `.csv`.

The run page Summary shows up to 50 ranked Treasury selections with maturity, annualised return, actual cash profit and coupon income, followed by quote status/date/source, broker YTM and calculation-lot details. Unaffordable offers are counted and listed separately. The ZIP includes normalized input, raw source snapshot, CSV/Excel reports, the Markdown summary and exclusions. The workflow runs the full test suite first and retains artifacts for 30 days. Select **Use repository CSV** to analyse supplied broker quotes instead; enter the repository CSV path. The source selection is a workflow input, not a login requirement. The workflow becomes available on GitHub once these changes are committed and pushed. It has been validated locally; remote GitHub execution requires those published files.

## Validation

Run `pytest`. Focused tests cover Treasury fractional prices, official bill-pricing examples, source parsing, quote age, maturity-window boundaries, metadata and assumptions, input round-trips, and the combined fetch-to-report command, alongside the original cash-flow and gilt tests. Public website changes or blocking can still make future fetches fail; the supplied-CSV path remains available.
