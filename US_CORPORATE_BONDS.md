# USD corporate bonds

Steps in brief: open **Actions → Run US corporate bond comparison → Run workflow**, leave **Fetch public indicative research** selected, choose the calculation date, USD budget and fee, and run. No pasted quotes, account or API key is needed for this mode. Open the completed run's **Summary** for the top 50; under **Artifacts**, download CSV, XLSX, exclusions and all source-page snapshots. The workflow must be on the default branch to appear in Actions. Relevant pushes to `main` also fetch and generate reports automatically. There is no scheduled trigger.

This is separate from the gilt, Treasury and FTSE screeners. The public mode discovers issues from [Public.com's public bond screener](https://public.com/bonds/screener), retrieves all advertised pages, and screens the records locally. The public query can return rows outside some requested filters, so server-side filtering is never treated as proof of eligibility. Failed, duplicate, changing or incomplete pagination stops the run rather than silently reporting a partial universe. There is no fallback to supplied or fictional examples.

## Automatically fetched public research (default)

The public source contains CUSIP, price, coupon, maturity, next coupon, callable status and an S&P rating field. [Public's own CLI documentation](https://github.com/PublicDotCom/publicdotcom-cli/blob/main/README.md) identifies its bond rating filter as S&P. This fetcher uses the public HTML page's embedded data, not the account-authenticated trading API. No Moody's ratings are returned, so public mode uses **S&P A− or higher**, with a maximum **24-calendar-month** maturity window. It does not claim to have checked a missing Moody's rating or both agencies. The Moody's Action input applies only to supplied CSV mode. Public mode rejects S&P floors below A−.

**All public rows are REVIEW research projections, never execution-cleared selections.** Public prices are treated as indicative: they do not establish current Schwab inventory, an executable ask, purchase minimums/increments or available size. The public response lacks quote timestamps and rating effective dates. Fetch time is recorded separately and never represented as either of those dates; freshness cannot be established from retrieval alone. An outlook date is preserved as an outlook date.

Public marks `89115A3A8` non-callable, contradicting the user-supplied Schwab Make Whole Call/Callable Yes row. That conflict is explicitly excluded. The known callable Baker Hughes issue `05724BAD1` is also excluded. These user-supplied conflicts persist until independently resolved; a fresh fetch cannot clear them. Other source non-callable flags also require verification, which is one reason every row remains REVIEW.

The source does not establish all contractual coupon/redemption terms. The return column is therefore **projected_annualised_return_pct**, a hypothetical regular fixed semiannual bullet-to-par model, not the independently validated return on an available offer. It uses the supplied coupon and price, an assumed 30/360 accrual basis, and assumed USD 1,000 minimum/increment calculation lots. USD is assumed from the source's US dollar bond market; explicit non-USD records are excluded. Nominal is rounded down to fit the budget after the configured total USD fee. Cash-flow yields are solved with Decimal using Actual/365 exponents. No model assumption constitutes human execution or evidence clearance.

Only outstanding whole, non-perpetual corporate records with explicit non-callable flags, no call dates/prices, semiannual coupons, positive coupon/price, USD 1,000 source par, and S&P at the requested floor are modelled. Known variable/step/structured/convertible descriptions are excluded. Missing fields and unsupported terms are excluded with reasons. The model excludes maturity days 28–31 to avoid unverified month-end schedules and accrual variants; the source next coupon must agree with the regular maturity-anchored schedule, and the issue must predate the current coupon period. These checks reduce ambiguities but do not establish fixed coupon terms or rule out undisclosed contractual features.

Public describes its displayed bond yield as **yield to worst (YTW)** in [its yield documentation](https://help.public.com/en/articles/9205243-what-is-yield-and-how-is-it-calculated). Its raw `currentYield` field is therefore reported as `source_ytw_pct` in CSV/XLSX exports. This replaces the ambiguous `source_current_yield_pct` heading; values are unchanged. The source does not supply a separate YTM. `projected_annualised_return_pct` remains our hypothetical annual effective return, distinct from the provider-reported YTW. Projected annualised returns include the configured purchase fee, exclude personal tax, assume all model cash flows are paid and are not adjusted for default. Reports preserve model costs, coupons, cash profit, unused cash, S&P outlook/watch fields, blank unavailable Moody's/quote dates, source URLs, retrieval time and assumptions. They rank by descending 0.1 percentage-point projection bands, shorter maturity, precise projection, then CUSIP; only the top 50 appear in the Summary, with full artifacts downloadable.

```sh
python -m pip install -e '.[dev]'
us-corporate-fetch-public --settlement-date 2026-10-20 --investment 5000 --fee 0
# Equivalent without reinstalling the command entry point:
python -m us_corporate_analyser.public_fetcher --settlement-date 2026-10-20 --investment 5000 --fee 0
```

The example date above is a model date, not broker-confirmed settlement. Blank Action dates and automatic pushes use the London calendar date, without holiday/settlement adjustments. Files use `reports/us-corporate-research-YYYY-MM-DD.*`; the `_source/` directory contains each fetched page and a manifest. Empty research results still produce a clear zero-count summary and exclusions. A public website's schema may change; this is not a vendor-supported API.

## Optional supplied broker quotes

Select **Use repository CSV** to analyse verified supplied inputs in `data/us_corporate_bonds.csv`. That file is an empty template, not a live universe. Supplied mode requires a populated file; it is never the automatic mode's fallback. This route defaults to Moody's **A2** / S&P **A−**: one recognised rating is enough; if both are supplied, both must pass. Quote observations older than 7 calendar days and rating observations older than 90 days relative to settlement are excluded, as are future observations. Supplied broker accrued interest must match the requested settlement date. No manual evidence date is refreshed by fetching public data.

Sources: [Schwab bond search](https://www.schwab.com/content/how-to-research-bonds), [FINRA TRACE](https://syndication.finra.org/content/what-trace-and-how-can-it-help-me), [FINRA accrued-interest calculator](https://accruedinterest.nga.finra.org/), [FINRA bond due diligence](https://syndication.finra.org/content/bond-investing-and-due-diligence).

The sections below describe this optional supplied-quote contract. Manually normalize any optional broker quotes to the documented CSV contract; do not guess missing contractual terms, accrued interest or ratings.

## Input contract

All template columns are required. Numbers use decimal points without currency symbols, commas or percent signs; dates use YYYY-MM-DD. UTF-8 CSV, including a BOM, is supported.

| Field | Meaning |
|---|---|
| `cusip`, `name` | Nine-character issue identifier and description; unique CUSIP per input |
| `coupon_rate` | Annual percentage, e.g. `5` for 5%; positive fixed coupon |
| `maturity_date` | Contractual bullet maturity, redemption at 100 per 100 nominal |
| `clean_buy_price` | Broker clean ask per USD 100 face value; include any price markup already embedded in the ask |
| `accrued_interest_per_100` | Broker accrued interest per USD 100 for the exact requested settlement date; not total order accrual |
| `price_settlement_date` | Settlement date used by the offer/accrual quote; must match the requested date |
| `moodys`, `sp` | Exact issue ratings such as `Baa3`, `BBB-`; blank or `NR` for an unavailable agency |
| `ratings_date` | Date on which both supplied issue ratings were checked |
| `currency` | Must be `USD` |
| `terms` | Use `fixed_semiannual_noncallable_bullet_regular` only after verifying all those terms |
| `minimum_nominal`, `nominal_increment` | Actual broker minimum face value and increments above that minimum in USD, not bond counts |
| `maximum_nominal` | Maximum face value offered at this ask; blank if unavailable (availability then remains unverified) |
| `quote_date`, `price_source` | Offer observation date and provenance, e.g. Schwab BondSource |
| `broker_ytm_pct` | Optional broker YTM retained separately; not used to calculate independent return |

Supported coupon dates are the maturity day every six months backwards, clamped to the last valid calendar day of the month. Confirm the remaining coupon schedule matches this convention. Irregular first/last coupons, a different end-of-month convention, floating/step coupons, zero-coupon issues, amortization, defaulted/flat trading, convertibles, puts, sinking funds, structured debt and any early redemption rights (including make-whole calls) are unsupported. Leave `terms` blank or describe the actual unsupported terms to get an exclusion, rather than assigning the supported token. No contractual features are inferred from the name.

Corporate accrual is often based on a 360-day year; this package deliberately requires broker-supplied accrual and does not reuse Treasury Actual/Actual accrual. On a coupon date, supplied accrual must be zero; otherwise it must lie between zero and one semiannual coupon. No holiday adjustment or settlement entitlement engine is implemented.

## Calculation and ranking

All financial calculations use Decimal. Dirty price = clean ask + supplied accrued interest. Choose the largest affordable nominal on the broker minimum/increment grid, capped by supplied ask size; add the configured total purchase fee. The fee is a total USD order fee, not a per-bond rate: calculate the appropriate broker charge before supplying it. There is no assumed Schwab corporate commission schedule. Unaffordable offers are excluded with reasons.

Coupons are annual percentage / 2 per 100 nominal, strictly after settlement, plus par redemption at maturity. Profit subtracts dirty consideration and fee. Redemption gain is par minus clean consideration; **no gilt CGT exemption is applied**. Annualised return is annual effective money-weighted yield after the configured fee and before personal tax, using dated cash flows and Actual/365 exponents on cash actually deployed. It assumes all promised payments occur, and is not adjusted for default risk. Broker YTM may use a different convention. Callable bonds are excluded; yield-to-worst is not calculated.

Ranking matches the other bond screeners: descending 0.1 percentage-point return bands, shorter actual maturity within a band, precise return, then CUSIP. The leading report columns are Name → months to maturity → annualised return. Months displayed use actual days × 12 / 365; the eligibility window uses calendar months. The budget applies independently to each bond, not a diversified portfolio allocation.

```sh
python -m pip install -e '.[dev]'
us-corporate-analyser data/us_corporate_bonds.csv \
  --settlement-date 2026-10-19 --investment 5000 --fee 0
pytest
```

For a reproducible demonstration only, substitute `examples/us_corporate_bonds_illustrative.csv` with the same settlement date. This fictional row is never fetched or used as the action's default. Full CSV/XLSX results preserve quote provenance, ratings, broker YTM, lot limits, coupon income, profit and unused cash. No matches produces header-only reports and explicit zero-ranked summary; malformed inputs fail rather than being silently omitted.
