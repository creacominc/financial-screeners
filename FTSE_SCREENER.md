# FTSE equity screener

## Steps in brief

1. Install the project with `python -m pip install -e ".[dev]"`.
2. Try `ftse-screener examples/ftse_snapshot.json --as-of 2026-10-16 --output reports/ftse-demo`.
3. For real data, copy `examples/ftse_config.json` to your own configuration. Set the applicable PFIC review year and freshness policy.
4. Run `ftse-fetch-hl your-config.json reports/ftse-current.json --discover-universe` to discover the FTSE350 and fetch public HL factsheets without logging in. A full universe takes several minutes at one request per second. New records default to unresolved classification and REVIEW.
5. Supply reviewed evidence, holdings values, scoring policy, missing metrics and execution context. Re-run `ftse-screener reports/ftse-current.json --as-of YYYY-MM-DD --output reports/ftse-YYYY-MM-DD`.
6. Review CSV, JSON and Markdown reports before manually adjusting HL instructions.

The engine implements the [design handoff](FTSE350_SCREENER_DESIGN.md). It produces auditable screening proposals; it does not change Direct Debits. The demo is fictitious, contains no approved companies and cannot produce actionable recommendations.

## Project organization

The distribution is named `financial-screeners`. Independent packages under `src/` keep UK gilts (`gilt_analyser`), USD Treasuries (`us_treasury_analyser`) and GBP FTSE equities (`ftse_screener`) separate. Existing CLI commands and bond inputs remain supported. A future `us_stock_screener` can be added without moving these packages. Local folder and remote repository names have not been changed; neither is a runtime dependency. Reinstall the editable project after the distribution rename. Bond calculation conventions remain in `AGENTS.md`.

## Public HL data: implemented and remaining

The adapter reads public pages only: FTSE350 pagination, exact share identifiers, sector, indicative buy price and quote timestamp, displayed P/E, operating margin and free cash flow when provided. It parses JSON numbers directly into Decimal. GBX prices convert to GBP only in affordability. Annual financial metrics retain their financial period-end date; fetching again does not make old fundamentals fresh. Each metric retains its source. Prices are indicative, not executable quotes.

Discovery checks that the listing contains 300–400 unique factsheet links, follows pagination, and fails on missing identity/price data instead of silently publishing a partial universe. This is a structural sanity check, not independent verification of FTSE's official constituent list. Without discovery, refresh requires configured `hl_url` values and verifies ISINs. With discovery, holdings absent from the refreshed universe remain separately visible and outside the candidate list; their old metrics are not refreshed automatically. Sector changes trigger REVIEW. Price refresh never renews PFIC evidence or HL execution verification.

HL's [public Direct Debit page](https://www.hl.co.uk/investment-services/invest-by-direct-debit), checked 16 October 2026, describes FTSE350 shares, £25 minimum per investment, no Direct Debit dealing charge, collection on the 7th and investment on the 10th (next working day where necessary), and changes at least seven working days before collection. These are context, not hardcoded engine assumptions. Configure verified terms for your exact account/share class. The application requires an explicit upcoming timezone-aware cutoff; it does not calculate UK bank holidays or infer a cutoff from a fixed date. Cutoff day itself is conservatively blocked because the calculation is date-based.

HL's [website terms, section 8](https://www.hl.co.uk/__data/assets/pdf_file/0010/13718431/Website-terms-of-use-UK-0918.pdf) allow personal-use extracts and restrict commercial use. No right to redistribute HL data is assumed. Keep reports/configuration private and check provider terms for your usage. The adapter does not call undocumented internal APIs or use account credentials.

Full historical total-return series, three-year EPS CAGR, forecasts, relative strength, ROIC and bank/insurer-specific ratios are **not supplied by this adapter**. Supply them from permitted sources with their original dates. The public adapter is not a complete fundamentals provider. The initial design shortlist is not pre-cleared or promoted. Real recommendations require the remaining evidence, data and configuration below.

## Input contract

JSON has `policy`, `stocks`, and optional `illustrative` and `refresh` fields. Financial numbers must be decimal strings (JSON decimals are also parsed as Decimal); percentage metrics such as ROIC use percentage points. Booleans and non-finite numbers are rejected for financial calculations. Each stock requires `company`, `ticker`, `isin`, `share_class`, `sector`, and `security_type`. ISINs must be unique. Accounts are supplied as execution context; use separate runs for different accounts/contribution plans for the same share class.

- `membership`: `ftse350` boolean, `date` (ISO), `source`. Missing/stale membership prevents candidate ranking, while a holding can still receive a clearly separate comparison score.
- `holding`: boolean; `holding_value_gbp`: current position value. All holdings use values if complete; otherwise the entire allocation calculation uses a labelled counts fallback. Include every equity holding, including those outside FTSE350. Do not mix cash, gilts, USD valuations or unconverted foreign equities into this equity-sector denominator. Overall portfolio context can be attached in extra JSON fields; cross-currency asset allocation is not calculated.
- `gate_evidence`: `decision` (`PASS`, `REVIEW`, `EXCLUDE`), `source`, `year`, `date`, `reviewer`, `rationale`, `recheck_date`, optional `conflict`. Dates cannot be future observations; PASS requires the configured applicable year, recent review, a future recheck date and no conflict. Unknown structures, REITs/property structures and unresolved cases require REVIEW; investment trusts, funds, ETFs, VCTs, closed-end funds, SPACs and shells are excluded. PASS requires `security_type: operating_company`, never inferred from a ticker or sector.
- `metrics`: named objects with `value`, `date`, `source` and optional units/basis. Missing values, stale/future dates, empty sources and non-positive positive-only metrics reduce coverage. Define growth intervals and currencies consistently upstream.
- `price`: `value`, `currency` (`GBP` or `GBX`), `date`, `source`.
- `execution`: `eligible` boolean for the exact share class, `account`, `date`, `source`, `contribution_gbp`, `fee_gbp`, `purchase_tax_rate` (fraction, e.g. `0.005`), `minimum_gbp`, and `cutoff` (ISO timestamp with UTC offset). Missing information produces UNVERIFIED, false eligibility INELIGIBLE. Allocate contributions explicitly; the program does not assume a total budget is available independently for every candidate. Include all applicable purchase charges in the configured fee/rate. This simple model does not model tiered/conditional fees or annual platform charges.
- Optional `prior_rank` produces prior minus current rank (positive means improvement). Previous input/evidence snapshots can be retained alongside dated artifacts. Automatic gate-change comparisons and contribution optimization are not implemented.

## Scoring policy

Weights are fixed at Quality 30%, Growth 25%, Valuation 20%, Trend 15%, Diversification 10%. Only PASS cases receive components. For each exact sector, configure four lists in `policy.sector_metrics`: `quality`, `growth`, `valuation`, `trend`. There is deliberately no generic sector fallback. Banks and insurers require reviewed financial-sector metrics (e.g. ROE, capital ratios and P/B where appropriate), rather than inheriting debt/EBITDA or industrial FCF metrics. The engine enforces explicit sector configuration, not economic suitability of the supplied policy.

Each metric specification has `name`, positive `weight`, `low`, `high`, `direction` (`higher`/`lower`), optional `positive_only`. Score = 100 × (value − low)/(high − low), clamped to [0,100], inverted for lower-is-better metrics. Anchors should be calibrated against appropriate sector/history data. This implements explicit anchor normalization rather than unstable percentiles across a tiny shortlist. Outliers saturate at endpoints. Non-positive P/E and PEG should use `positive_only: true`; they are unavailable, never bargains. Missing forecasts are not set to zero.

A component is the weighted average of usable metrics. Coverage = usable metric weight / configured metric weight. `minimum_coverage` must be in (0,1]; the example requires 100% for every component. A total is withheld if any component fails coverage, sector policy is missing or portfolio diversification is unavailable. Partial components and reasons remain visible. No missing component's weight is redistributed across other components.

Diversification = clamp(50 + 50 × (target sector weight − actual sector weight)/target sector weight, 0, 100). Targets in `policy.sector_targets` are explicit fractions in (0,1]. A target-weight sector scores 50, an unrepresented sector 100, a sector at twice target or more 0. Current holdings receive precisely the same rules as new candidates. Missing/zero total equity exposure withholds diversification. The qualitative holdings list in the design is not treated as a verified current portfolio.

Trend metrics must document their benchmark and price-only/total-return basis. The illustrative `relative_strength_12m` represents percentage-point outperformance versus FTSE350 on a **price-only** basis; it is not calculated from the current quote. No total-return claim is made. The fixture anchors are demonstration values, not a calibrated investment policy.

Sort complete current-universe PASS candidates by descending Decimal total, then ISIN. Gate review cases and exclusions have no investment scores/ranks. Actionable flags require a ranked complete candidate plus verified affordable execution context, and are always false for illustrative data. Whole shares round down after configured fees and purchase tax, with total estimated purchase cost rounded upward to pennies; residual is unspent contribution. Blocked instructions leave the full contribution as cash. This is a price estimate, not an execution guarantee.

## PFIC review policy

The software validates documentation and freshness; it does not determine a company's tax status. [IRS Form 8621 instructions](https://www.irs.gov/instructions/i8621) and [26 USC 1297](https://usc-cdn.house.gov/view.xhtml?edition=prelim&num=0&req=granuleid%3AUSC-prelim-title26-section1297), checked 16 October 2026, describe the 75% passive-income and 50% passive-asset tests and relevant active banking/qualifying insurance treatment. These distinctions require company/year-specific evidence and applicable exceptions. No automatic bank exclusion or clearance is encoded. A human review must document relevant treatment, evidence and rationale for the configured year. Recheck on expiry and corporate events. PASS is a policy decision for that evidence period, not a permanent PFIC-free guarantee or personal tax advice.

## Actions and scheduling

`Run FTSE screening` can run manually with the illustrative supplied snapshot, or with a real configuration plus `fetch_hl` enabled. For scheduled operation set repository variable `FTSE_INPUT_JSON` to a real configuration path. The daily 07:15 UTC trigger is interpreted in Europe/London: Mondays produce weekly reports and a configured cutoff minus `cutoff_buffer_days` calendar days produces the monthly review. Explicit cutoff timestamps handle daylight-saving offsets. The buffer is calendar days, not working days. GitHub scheduling can be delayed; use a sufficient buffer.

Scheduled report runs refresh HL universe/public fields; non-report days do not scrape. Without a real configuration the scheduled job fails visibly instead of calling fixture data current. Full pytest runs precede refresh. Dated source snapshots and CSV/JSON/Markdown artifacts are retained for 30 days with unique run IDs. A fetch failure stops report generation and flags the run; old artifacts are not promoted as fresh. Manual supplied-data reports are explicitly labelled snapshots. Freshness thresholds are independent for gate, membership, metrics, price and execution. The monthly report uses the same ranked candidates, holding comparisons and review/exclusion sections; it is not an automatically optimized portfolio or an automatic HL instruction.

## Validation and limitations

Run `.venv/bin/pytest`. Focused tests cover gating, stale/conflicting evidence, weights, normalization, coverage, invalid numeric inputs, membership, sector policy, holdings parity, allocation basis, affordability/cost rounding, deterministic ranking, rank change, report files, timezone-aware scheduling and HL parser failure behavior. Live HTML can change; public-page access does not establish PFIC status or completeness of available financial history.
