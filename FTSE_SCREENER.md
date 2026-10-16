# FTSE 350 screener

## Steps in brief

1. In GitHub, open **Actions → Run FTSE screening → Run workflow** on `main`.
2. Keep **Configuration path** as `config/ftse_live.json` and **Refresh HL public data** enabled. These are the defaults; they fetch real data without an HL login.
3. Optionally enter a **GBP amount per share** to see whole-share affordability in both your Stocks and Shares ISA and Fund and Share Account. This amount is a scenario for each candidate separately, not a total budget or automatic allocation.
4. When the run finishes, read the stock-selection shortlist in its Summary and download the `ftse-reports-…` artifact for CSV, JSON, Markdown and input snapshots. The first complete fetch takes several minutes; public pages are cached within the UTC date to speed up repeat runs.
5. Use the shortlist to consider adding a monthly purchase or increasing an existing one, after checking ownership and the exact share class in HL Monthly Savings. The program never changes instructions or submits orders.

Start a **new run** after a code update. GitHub's “Re-run jobs” uses the original run's commit. The explicit demo input remains `examples/ftse_snapshot.json`; it always produces labelled fictitious data, even if refresh is checked. It is no longer the default.

## What the live run produces

The public HL FTSE350 listing supplies the universe and exact identifiers. Every constituent gets an audit record with real indicative prices where available, source links, metric dates, classifications, evidence status and reasons. Discovery follows pagination and checks 300–400 unique factsheet links; this is a structural check rather than independent verification against FTSE's licensed official constituent file.

The adapter follows each factsheet's **actual financial-statements link**. Legacy SEDOL URLs cannot reliably be extended with a tab suffix. It reads five annual income statements, cash flows and balance sheets where available, projected EPS, and HL's public constituent performance table. JSON numbers are parsed into Decimal; all financial formulas and rankings remain Decimal. GBP and GBX are explicit, including GBX-to-GBP conversion for purchase estimates. No broker credentials or undocumented service-layer APIs are used.

Annual metrics keep their **period-end dates**. Refreshing a page does not renew old fundamentals. Quotes retain the provider's timestamp; forecast data retains the observation date and forecast year. Missing/null financial fields do not become zero. A financial-page gap is retained with ticker, URL and error; affected metrics and insufficiently covered scores are withheld. A failed universe/price-page fetch fails the run rather than publishing a silently truncated universe. No fixture fallback occurs on a live run.

The live report separates:

- **Stock-selection shortlist:** only current-universe PASS cases with sufficient financial data; investment components normalized to 100. This can run without a supplied portfolio.
- **Portfolio-adjusted ranking:** includes the 10% diversification component only when holdings and sector targets are available. Missing portfolio information never earns diversification points.
- **Account checks:** separate public eligibility indications and optional affordability scenarios for ISA and Fund and Share Account.
- **PASS detail, holdings comparisons, REVIEW queue and EXCLUDE audit:** evidence and underlying metrics remain visible. Excluded and unresolved securities receive no investment scores.

The first full validation on 16 October 2026 processed **351 securities** and found **three financial-statement gaps**. Counts are recalculated each run; these are validation results, not hardcoded expected outcomes.

## Evidence gate and the current coverage limit

The design's security/PFIC gate remains mandatory **before scoring**. Investment trusts, ETFs/funds, VCTs, closed-end funds, SPACs and cash shells are prohibited. Property/REIT structures and unknown classifications remain REVIEW unless explicitly resolved. A company name, ticker, sector or HL membership never clears the gate.

`config/ftse_live.json` includes four dated, identified **source reviews** under `issuer-statement-v1`: AstraZeneca, Unilever, Diageo and HSBC. Each has a primary annual-report source, applicable year, rationale, reviewer, review date and recheck date. These are Codex source reviews of explicit issuer assessments, not an invented human signoff or independent tax opinion. Unilever uses its current post-consolidation ISIN, supported by the issuer's corporate-action documentation. HSBC's review uses its issuer-specific statement; banks are not automatically excluded or cleared because of interest income or financial assets.

**This is presently a ranking of the documented eligible subset, not a claim to have found the best four businesses in the entire FTSE350.** Other operating companies, including unresolved names in the original design shortlist, remain visible in REVIEW. Their lack of a score does not mean they are inferior investments. Broader buy rankings require company/year-specific reviews to be added to `security_reviews`; no rule silently promotes missing evidence to PASS. The full universe's raw data is still available for research.

The source reviews were checked on 16 October 2026 and expire on 14 January 2027, or sooner if an identity/classification change triggers review. Price refresh does not renew them. Sources assess a completed tax/reporting year; PASS is not a promise about the current year, past holder-specific PFIC history or future status. The configured policy permits 2025/2026 source years and requires a recent review. Conflicts, expiry, missing sources and future review dates prevent PASS.

[IRS Form 8621 instructions](https://www.irs.gov/instructions/i8621) and [26 USC 1297](https://usc-cdn.house.gov/view.xhtml?edition=prelim&num=0&req=granuleid%3AUSC-prelim-title26-section1297) describe the income/asset tests and relevant banking/insurance treatment. The program validates a screening evidence policy; it does not calculate personal tax or certify legal tax status.

## Scoring policy

`hl-public-v1` is an explicit baseline, implemented in `src/ftse_screener/policy.py`. Component weights remain **Quality 30%, Growth 25%, Valuation 20%, Price/Trend 15%, Diversification 10%**. Explicit sector policies override the baseline.

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

Selection score = `(Quality × .30 + Growth × .25 + Valuation × .20 + Trend × .15) / .90`. It is labelled **selection only**, not the full five-component portfolio score. Sort descending by Decimal score, then ISIN for deterministic ties. Complete portfolio totals retain the separate original `rank`; `selection_rank` is the independent stock-selection rank.

The public adapter does not currently supply FTSE350-index-relative strength, daily 200-day averages or total returns. It uses the explicitly labelled **absolute price-return** submetrics above instead. Returns at or below −90% are withheld for corporate-action/data-quality review, since splits/redenominations can contaminate raw series. No dividends-adjusted claim is made. Other supplied policies can use alternative dated metrics.

## Holdings and accounts

You can run stock selection without entering private holdings. Ownership is then unknown, and suggestions say to check ownership and add or increase as appropriate. Lower rank alone is never a sell/reduce instruction.

To personalize, add `holdings` to your private configuration. Each position has `isin`, `account` (`Stocks and Shares ISA` or `Fund and Share Account`), `value_gbp`, and optionally your current contribution. Both accounts may hold the same ISIN: values aggregate for the equity-sector exposure, while proposals retain account context. Set `holdings_complete: true` only when the list is complete. Add reviewable stock records for holdings outside the fetched universe; unresolved holdings are shown separately and withhold portfolio diversification.

Use GBP-converted position values consistently; no unconfigured FX conversion is performed. Gilts/cash can be attached as separate context but are not included in the equity-sector denominator. Explicit supplied stock `holding_value_gbp` values are supported, with a labelled all-holdings-counts fallback when some values are absent.

Set `policy.sector_targets` to fractions in (0,1]. Diversification = `clamp(50 + 50 × (target − actual sector weight) / target, 0, 100)`. Both existing and new holdings use the same scoring rules. No current allocation is inferred from the qualitative holdings list in the design.

## HL execution and cutoff checks

Each full run verifies the [public HL monthly-investing terms](https://www.hl.co.uk/investment-services/invest-by-direct-debit). The parser currently recognizes the stated minimum per investment, absence of Direct Debit dealing charges, collection day and working-day change rule. If those terms change or cannot be verified, execution verification fails visibly instead of silently retaining old terms.

Public account indications combine current membership, the **exact share-class factsheet's** listed account products, tradability and HL's general regular-investment terms. They are labelled `PUBLICLY_INDICATED`; confirm availability in Monthly Savings before submission. Membership by itself is insufficient.

For the four configured UK ordinary shares, purchase costs use an explicit **0.5% SDRT estimate**, recorded in the configuration; check actual applicability in HL. The calculation includes configured fees/taxes, rounds whole shares down and total estimated purchase cost upward to pennies. It shows the larger of HL's minimum instruction and the cost of one share, optional estimated shares, and residual contribution. There is no guaranteed execution quantity. Annual platform charges and personal taxes are not modelled.

The upcoming collection date advances to an England/Wales working day. The instruction cutoff subtracts the verified number of working days using the [official GOV.UK holiday calendar](https://www.gov.uk/bank-holidays.json). Because HL's public text does not specify an exact time of day, the implementation conservatively uses **midnight at the start of the calculated cutoff date**, Europe/London. Cutoff-day instructions are blocked. Monthly reporting is five calendar days earlier by default. Holidays outside the official calendar's coverage fail rather than being guessed.

## Local use

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ftse-fetch-hl config/ftse_live.json reports/ftse_current.json \
  --discover-universe --full-metrics --cache-dir reports/hl-cache
.venv/bin/ftse-screener reports/ftse_current.json \
  --as-of YYYY-MM-DD --output reports/ftse-YYYY-MM-DD
```

Add `--monthly-per-share 100` to the last command for a £100-per-candidate scenario. Supplied JSON input remains supported: financial numbers should be decimal strings, dates ISO, and each stock requires company, ticker, ISIN, share class, sector and security type. `metrics` contain `value`, `date`, `source` and descriptive basis/units. The example fixture documents this format. Missing data, booleans and non-finite financial numbers do not become zero.

## Actions, refresh and artifacts

Manual runs default to real configuration and live refresh. Pushes to the FTSE implementation/configuration trigger an end-to-end live validation. The daily 07:15 UTC scheduled trigger checks Europe/London dates: Mondays produce weekly reports, and the dynamically verified upcoming cutoff minus the configured buffer produces monthly reports. `FTSE_INPUT_JSON` optionally selects a different repository configuration. Non-report days only check current execution terms/calendar; they do not crawl all constituents.

All tests run before fetching. Same-UTC-date public HTML can be cached across runs; previous-day pages are not relabelled as current. Dated artifacts retain inputs, refreshed data and reports for 30 days. Source failures are shown in the job summary; a failed live fetch does not publish an old report as new. Annual fundamentals, gate evidence, membership, execution and price freshness are tracked separately.

The Python distribution is **financial-screeners**; independent `gilt_analyser`, `us_treasury_analyser` and `ftse_screener` packages preserve existing commands and separate GBP/USD calculations. Local folder and GitHub repository names remain unchanged. A future US-stock package can be added without moving existing packages.

HL's [website terms, section 8](https://www.hl.co.uk/__data/assets/pdf_file/0010/13718431/Website-terms-of-use-UK-0918.pdf) describe personal-use extracts and restrict commercial use. This integration is for the requested personal research workflow; it does not assume redistribution rights. Keep portfolio configurations and reports private as appropriate. No live reports or raw fetched HTML are committed to the repository.
