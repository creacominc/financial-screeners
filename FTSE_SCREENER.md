# FTSE 350 screener

## Steps in brief

1. In GitHub, open **Actions → Run FTSE comparison → Run workflow** on `main`.
2. Keep **Configuration path** as `config/ftse_live.json` and **Refresh HL public data** enabled. These are the defaults; they fetch real data without an HL login.
3. Optionally enter a **GBP amount per share** to see whole-share affordability in both your Stocks and Shares ISA and Fund and Share Account. This amount is a scenario for each candidate separately, not a total budget or automatic allocation.
4. When the run finishes, read the stock-selection shortlist in its Summary and download the `ftse-reports-…` artifact for CSV, JSON, Markdown and input snapshots. Allow roughly 15–30 minutes for a cold full-market fetch, depending on HL response times. Prices, membership, performance and HL terms are cached within the UTC date. Financial pages (including forecasts) are reused for up to seven days across runs; forecast observation dates and reported period dates are preserved. The report states how many pages were downloaded versus reused.
5. Use the shortlist to consider adding a monthly purchase or increasing an existing one, after checking ownership and the exact share class in HL Monthly Savings. The program never changes instructions or submits orders.

Start a **new run** after a code update. GitHub's “Re-run jobs” uses the original run's commit. The explicit demo input remains `examples/ftse_snapshot.json`; it always produces labelled fictitious data, even if refresh is checked. It is no longer the default.

## What the live run produces

The public HL FTSE350 listing supplies the universe and exact identifiers. Every constituent gets an audit record with real indicative prices where available, source links, metric dates, classifications, evidence status and reasons. Discovery follows pagination and checks 300–400 unique factsheet links; this is a structural check rather than independent verification against FTSE's licensed official constituent file.

The adapter follows each factsheet's **actual financial-statements link**. Legacy SEDOL URLs cannot reliably be extended with a tab suffix. It reads five annual income statements, cash flows and balance sheets where available, projected EPS, and HL's public constituent performance table. JSON numbers are parsed into Decimal; all financial formulas and rankings remain Decimal. GBP and GBX are explicit, including GBX-to-GBP conversion for purchase estimates. No broker credentials or undocumented service-layer APIs are used.

Annual metrics keep their **period-end dates**. Refreshing a page does not renew old fundamentals. Quotes retain the provider's timestamp; forecast data retains the observation date and forecast year. Missing/null financial fields do not become zero. A financial-page gap is retained with ticker, URL and error; affected metrics and insufficiently covered scores are withheld. A failed universe/price-page fetch fails the run rather than publishing a silently truncated universe. No fixture fallback occurs on a live run.

Company names in the summary ranking link to the exact HL security factsheet for its current chart and price. Ctrl-click (Windows/Linux) or Cmd-click (Mac) opens a new tab; GitHub controls normal-click navigation.

The live report separates:

- **Stock research ranking:** current-universe PASS and REVIEW cases with sufficient financial data; investment components normalized to 100. This can run without a supplied portfolio.
- **Account checks:** separate public eligibility indications and optional affordability scenarios for ISA and Fund and Share Account.
- **PASS detail, REVIEW queue and EXCLUDE audit:** evidence and underlying metrics remain visible. REVIEW cases receive research scores and retain their gate reasons; EXCLUDE cases receive no investment scores.

The first full validation on 16 October 2026 processed **351 securities** and found **three financial-statement gaps**. Counts are recalculated each run; these are validation results, not hardcoded expected outcomes.

## Evidence gate and the current coverage limit

The security/PFIC gate is assessed before scoring, but unresolved REVIEW cases are included in research rankings as requested on 16 October 2026. Their status is not promoted to PASS, and they are not marked actionable. Investment trusts, ETFs/funds, VCTs, closed-end funds, SPACs and cash shells are prohibited. Property/REIT structures and unknown classifications remain REVIEW unless explicitly resolved. A company name, ticker, sector or HL membership never clears the gate.

`config/ftse_live.json` includes six dated, identified **source reviews** under `issuer-statement-v1`: AstraZeneca, Unilever, Diageo, HSBC, British American Tobacco and National Grid. Each has a primary annual-report source, applicable year, rationale, reviewer, review date and recheck date. These are Codex source reviews of explicit issuer assessments, not an invented human signoff or independent tax opinion. Unilever uses its current post-consolidation ISIN, supported by the issuer's corporate-action documentation. HSBC's review uses its issuer-specific statement; banks are not automatically excluded or cleared because of interest income or financial assets.

**Research coverage is independent of evidence clearance.** PASS and REVIEW securities share the same scoring rules and ranking, allowing CSV filters by `gate_status`, sector and score. Unresolved structures (including REIT/property cases) can receive research scores where the configured sector metrics have sufficient coverage; those metrics do not resolve structure-specific accounting limitations. Missing or stale metrics still withhold incomplete overall scores. Known EXCLUDE cases remain unranked. Suggested actions on REVIEW rows require resolving the gate review before considering purchase; account eligibility and affordability are separate checks.

Reprocessing the saved 16 October 2026 live snapshot under this policy ranked **194 securities across 11 HL sectors**: six PASS and 188 REVIEW. These counts describe that snapshot and will change with data availability. This is a wider research comparison, not evidence that the 188 unresolved cases have passed review.

The source reviews were checked on 16 October 2026 and expire on 14 January 2027, or sooner if an identity/classification change triggers review. Price refresh does not renew them. Sources assess a completed tax/reporting year; PASS is not a promise about the current year, past holder-specific PFIC history or future status. The configured policy permits 2025/2026 source years and requires a recent review. Conflicts, expiry, missing sources and future review dates prevent PASS.

[IRS Form 8621 instructions](https://www.irs.gov/instructions/i8621) and [26 USC 1297](https://usc-cdn.house.gov/view.xhtml?edition=prelim&num=0&req=granuleid%3AUSC-prelim-title26-section1297) describe the income/asset tests and relevant banking/insurance treatment. The program validates a screening evidence policy; it does not calculate personal tax or certify legal tax status.

## Scoring policy

`hl-public-v1` is an explicit baseline, implemented in `src/ftse_screener/policy.py`. Relative component weights are **Quality 30, Growth 25, Valuation 20 and Price/Trend 15**, normalized by their sum of 90 to a score out of 100. Explicit sector policies override the baseline.

| Component | Public-data implementation |
|---|---|
| Quality | Closing-equity ROE 25%, operating margin 20%, FCF/net-income conversion 25%, net debt/EBITDA proxy 15%, positive-earnings consistency 15% |
| Growth | Three-year EPS CAGR 35%, revenue CAGR 35%, FCF CAGR 15%, next-year projected EPS growth 15% |
| Valuation | Positive P/E 100%; limited valuation coverage, not a complete historical/sector-multiple valuation |
| Trend | Trailing cumulative price returns over one year 50%, three years 30%, five years 20%; dividends excluded |
| Financial-sector quality | ROE 70% and earnings consistency 30%; excludes industrial cash-flow/leverage metrics |
| Financial-sector growth | EPS CAGR 60% and net-income CAGR 40%; component weights above remain unchanged |

Within a component, normalize each metric to 0–100 between explicit low/high anchors, clamp outliers, and invert lower-is-better metrics. Anchors and submetric weights are published in the policy file; they are a starting research policy, not an optimized or backtested promise of outperformance. Valuation P/E has positive-only treatment. Non-positive CAGR endpoints, missing forecasts and invalid ratios are unavailable rather than favourable bargains. Cross-statement ratios require matching currencies and financial periods. The EBITDA proxy is operating income plus cash-flow depreciation; ROE uses closing equity, explicitly labelled rather than described as average-equity ROE.

The baseline's minimum weighted data coverage is **75% in every investment component**. Annual metrics expire after 450 days; forecast observations after 30 days; P/E and price returns after seven days. Missing metrics reduce coverage. Above the threshold, the available metrics are averaged within their component, with coverage shown. An unavailable component withholds the selection score. No component weight is silently reassigned to another component.

`total_score` = `(Quality × .30 + Growth × .25 + Valuation × .20 + Trend × .15) / .90`.
`rank` sorts descending by this Decimal score, then ISIN for deterministic ties.
Generated CSV and JSON rows are ordered by ascending rank (1 first), with
unranked securities at the end ordered by ISIN.
This preserves the previous independent selection scores and removes the duplicate
`selection_score` and `selection_rank` fields. No ownership, holdings, allocation,
sector target or diversification adjustment is used.

The public adapter does not currently supply FTSE350-index-relative strength, daily 200-day averages or total returns. It uses the explicitly labelled **absolute price-return** submetrics above instead. Returns at or below −90% are withheld for corporate-action/data-quality review, since splits/redenominations can contaminate raw series. No dividends-adjusted claim is made. Other supplied policies can use alternative dated metrics.

## Independent research and accounts

Use the ranking to research new securities or review monthly Direct Debit amounts.
It requires no portfolio information. Legacy holdings and sector-target inputs are
ignored and are omitted from comparison reports. Suggestions use the same wording
for every stock: consider adding or increasing monthly purchases, subject to gate
review. A lower rank is not a sell or reduce instruction.

ISA and Fund and Share Account scenarios remain separate. Optional per-security
contributions estimate affordability without knowing current ownership.

## HL execution and cutoff checks

Each full run verifies the [public HL monthly-investing terms](https://www.hl.co.uk/investment-services/invest-by-direct-debit). The parser currently recognizes the stated minimum per investment, absence of Direct Debit dealing charges, collection day and working-day change rule. If those terms change or cannot be verified, the report marks execution unverified and withholds account affordability estimates; company-data refresh and research can still proceed. A scheduled monthly report cannot guess a deadline when terms/calendar verification fails.

Public account indications combine current membership, the **exact share-class factsheet's** listed account products, tradability and HL's general regular-investment terms. They are labelled `PUBLICLY_INDICATED`; confirm availability in Monthly Savings before submission. Membership by itself is insufficient.

For the configured UK ordinary shares, purchase costs use an explicit **0.5% SDRT estimate**, recorded in the configuration; check actual applicability in HL. The calculation includes configured fees/taxes, rounds whole shares down and total estimated purchase cost upward to pennies. It shows the larger of HL's minimum instruction and the cost of one share, optional estimated shares, and residual contribution. There is no guaranteed execution quantity. Annual platform charges and personal taxes are not modelled.

The upcoming collection date advances to an England/Wales working day. The instruction cutoff subtracts the verified number of working days using the [official GOV.UK holiday calendar](https://www.gov.uk/bank-holidays.json). Because HL's public text does not specify an exact time of day, the implementation conservatively uses **midnight at the start of the calculated cutoff date**, Europe/London. Cutoff-day instructions are blocked. Monthly reporting is five calendar days earlier by default. Holidays outside the official calendar's coverage fail rather than being guessed.

## Local use

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ftse-fetch-hl config/ftse_live.json reports/ftse_current.json \
  --discover-universe --full-metrics --cache-dir reports/hl-cache
.venv/bin/ftse-screener reports/ftse_current.json \
  --as-of YYYY-MM-DD --output reports/ftse-comparison-YYYY-MM-DD
```

Add `--monthly-per-share 100` to the last command for a £100-per-candidate scenario. Supplied JSON input remains supported: financial numbers should be decimal strings, dates ISO, and each stock requires company, ticker, ISIN, share class, sector and security type. `metrics` contain `value`, `date`, `source` and descriptive basis/units. The example fixture documents this format. Missing data, booleans and non-finite financial numbers do not become zero.

## Actions, refresh and artifacts

Manual runs default to real configuration and live refresh. Pushes to the FTSE implementation/configuration trigger an end-to-end live validation. The daily 07:15 UTC scheduled trigger checks Europe/London dates: Mondays produce weekly reports, and the dynamically verified upcoming cutoff minus the configured buffer produces monthly reports. `FTSE_INPUT_JSON` optionally selects a different repository configuration. Non-report days only check current execution terms/calendar; they do not crawl all constituents.

All tests run before fetching. GitHub Actions restores the most recent public-page cache across dates and saves each successful refresh under a new run key. Market pages refresh daily; financial statements and forecasts refresh after seven days. Cached forecasts retain their original observation dates. Old daily pages are removed, and expired financial pages are fetched again; failed downloads do not fall back to expired data. A missing or evicted GitHub cache requires a cold fetch. The first run after this cache upgrade also starts cold. Dated artifacts retain inputs, refreshed data and reports for 30 days. Source failures are shown in the job summary; a failed live fetch does not publish an old report as new. Empty/unusable HL performance responses and empty or rejected constituent-list pages are retried up to three times, evicting the response from the daily cache before retrying. Each advertised constituent page must return links; a rejected page cannot be skipped even if the aggregate count would meet the minimum. A persistent HL rejection is an upstream access failure and cannot be repaired by relaxing the universe count. Persistent failures still stop report generation; the error includes the source URL, response size, table-row count and page title. With `--cache-dir`, the last rejected response is saved as `reports/ftse-fetch-failure.html` (beside the cache directory) and included in the workflow artifact for diagnosis. A retained diagnostic can also describe an earlier attempt that recovered; use the job result to determine success. Annual fundamentals, gate evidence, membership, execution and price freshness are tracked separately.

The Python distribution is **financial-screeners**; independent `gilt_analyser`, `us_treasury_analyser` and `ftse_screener` packages preserve existing commands and separate GBP/USD calculations. Local folder and GitHub repository names remain unchanged. A future US-stock package can be added without moving existing packages.

HL's [website terms, section 8](https://www.hl.co.uk/__data/assets/pdf_file/0010/13718431/Website-terms-of-use-UK-0918.pdf) describe personal-use extracts and restrict commercial use. This integration is for the requested personal research workflow; it does not assume redistribution rights. Keep configurations and reports private as appropriate. No live reports or raw fetched HTML are committed to the repository.

Comparison reports default to dated prefixes: `gilt-comparison-YYYY-MM-DD`,
`us-treasury-comparison-YYYY-MM-DD`, and `ftse-comparison-YYYY-MM-DD`.
Bond dates are settlement dates; FTSE dates are the requested as-of dates.
An explicit `--output` prefix is preserved. Bond columns place months to maturity,
net annualised return and rank immediately after name. FTSE columns place existing
1-, 3- and 5-year price returns and rank and rank movement immediately after ISIN;
these historical returns are not annualised yields or forecasts.

Unrankable rows show `N/A` in the CSV. JSON retains `rank_basis: selection` solely
to validate comparisons with previous reports. Older portfolio-adjusted ranks
are not compared with the current investment-only ranking.

Actions caches the previous successful report separately for each input
configuration and refresh mode. `prior_rank` matches by ISIN only when the previous
report is from an earlier date, has the same illustrative/live mode and uses the
same rank basis. `rank_change` is prior minus current rank: positive means an
improvement. Missing history, new entrants and incompatible comparisons show
`N/A`, never an invented zero. The first run starts a baseline; cache eviction can
reset it. Local runs can use `--previous-report path/to/previous-report.json`.

## Alternative market-data sources

See [replacement-source evaluation](FTSE_DATA_SOURCES.md) for the tested LSE
constituent adapter (`--universe-source lse`), historical-price candidates and
remaining coverage/access requirements. The optional LSE adapter replaces only
membership discovery; HL performance and factsheet access remain dependencies.
