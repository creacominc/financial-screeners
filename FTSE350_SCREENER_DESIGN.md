> Policy update, 17 October 2026: use a single investment score and rank, with no portfolio inputs or diversification adjustments. Quality, Growth, Valuation and Trend retain relative weights 30:25:20:15, normalized to 100. This supersedes the previous portfolio design.

> Policy update, 16 October 2026: at the user’s request, research rankings now include both PASS and unresolved REVIEW cases with sufficient financial data. Gate status and reasons remain visible for spreadsheet filtering; REVIEW is never silently promoted to PASS or marked actionable. EXCLUDE cases remain unscored. This supersedes the PASS-only scoring/ranking requirements below; other requirements continue to apply.

# FTSE 350 Stock Screener — Design Handoff

Design captured: 16 October 2026\
Purpose: preserve the agreed design for implementation in Codex / VS Code. This is a design document, not a completed screener, live eligibility check, PFIC determination, or recommendation to buy the research shortlist.

## Implementation and execution

- Build the screening and reporting engine in **Python**, running on **GitHub Actions**.
- Prefer this over HL or Barchart screening because it supports explicit exclusions, repeatable weighted scoring, evidence, and explainable results.
- Use **Hargreaves Lansdown (HL)** for execution through regular monthly Direct Debit investing and gradual pound-cost averaging (DCA).
- Treat Barchart as an optional comparison or data source, not the primary engine.
- Keep this work separate from the existing gilt calculations. This handoff does not authorize changes to existing source files or introduce scraping. Confirm data access, licensing and permitted use before implementing integrations.

## Mandatory security and PFIC gate — before scoring

The concern described as avoiding “passive income investments” is specifically avoidance of potential **US Passive Foreign Investment Companies (PFICs)**; dividend-paying operating businesses are not automatically excluded merely for paying dividends.

FTSE 350 membership and HL regular-investing eligibility do **not** establish PFIC suitability. Apply a hard security-type and PFIC-risk gate before any investment score. A high score must never override the gate.

### Security exclusions

Explicitly exclude:

- Investment trusts.
- ETFs and other funds.
- VCTs.
- Closed-end funds.
- SPACs and cash shells.

Conservatively flag or exclude REITs and property-investment structures. Use EXCLUDE where the structure clearly falls outside the permitted universe; use REVIEW where classification or evidence is unresolved. Neither may enter an actionable purchase list.

### PFIC review

- Ordinary operating companies can still require PFIC review. A company label, exchange listing or sector alone is insufficient evidence of suitability.
- The PFIC framework includes passive-income and passive-asset tests, assessed for the relevant tax year. Verify current authoritative rules, relevant exceptions and company evidence during implementation rather than treating this document as tax advice.
- Banks and insurers require nuanced treatment: do not automatically classify them as PFICs simply because they hold financial assets or receive interest, and do not automatically clear them. Relevant business activity, exceptions and available evidence need review.
- Store evidence sources, applicable year, review date, rationale and any expiry/recheck date. Do not describe PASS as a permanent guarantee of PFIC-free status.
- Missing, conflicting or stale evidence must not silently become a pass. A documented review decision is needed to resolve uncertainty.

### Gate statuses

| Status | Meaning | Scoring / action |
|---|---|---|
| **PASS** | Permitted security type and sufficient documented evidence for the configured review policy | Eligible for scoring; purchase eligibility checked separately |
| **REVIEW** | Classification, PFIC evidence or applicable treatment unresolved | Show with reasons in a review queue; withhold investment ranking and purchase action |
| **EXCLUDE** | Prohibited security type or unacceptable PFIC risk under the policy | Exclude before scoring; retain in the audit output with reasons |

## Scoring survivors

Score all current FTSE 350 candidates by the same investment rules, independently of ownership.

| Component | Weight | Suggested submetrics |
|---|---:|---|
| Quality | **30/90** | ROIC / ROE; operating margin; free cash flow (FCF) conversion; debt / EBITDA; earnings consistency |
| Growth | **25/90** | Three-year EPS CAGR; forecast EPS growth; revenue CAGR; FCF growth |
| Valuation | **20/90** | Sector-relative and historical P/E; FCF yield; EV / EBITDA and PEG where appropriate |
| Price / Trend | **15/90** | Twelve-month relative strength; three- and five-year returns; position relative to the 200-day moving average |
| **Total** | **Normalized to 100** | Weighted sum divided by .90 |

Implementation details to settle explicitly:

- Normalize submetrics to comparable component scores, preferably using suitable sector peers. Define outlier treatment and metric direction.
- Define the relative-strength benchmark and whether long-period returns include dividends; label price-only data clearly.
- Use sector-appropriate metrics. Debt / EBITDA, FCF and EV / EBITDA may be unsuitable for banks and insurers; document substitutions and keep component weights consistent.
- Handle negative earnings, invalid PEGs and missing forecasts explicitly. Never treat unavailable data as zero valuation or silently award a favourable score.
- Publish data coverage and freshness. Withhold or clearly mark incomplete scores according to a documented minimum-coverage policy.

## Initial research shortlist

Primary research candidates: **RELX, Sage, AstraZeneca, London Stock Exchange Group (LSEG), Experian and Next**.

Secondary research candidates: **Bunzl and Compass Group**.

These are research starting points, not pre-approved buys. Each must pass the same security/PFIC gate, current FTSE 350 check, scoring, affordability and HL eligibility checks as every other candidate.

## DCA and HL execution suitability

Keep execution suitability separate from investment score:

- Check current HL monthly regular-investment eligibility for the exact security / share class and account type; FTSE membership alone is insufficient.
- Verify current HL dealing charges, minimum instruction, Direct Debit schedule and instruction-change cutoff. Do not hardcode previously quoted terms as permanent facts.
- Model whole-share affordability using the proposed monthly contribution and a recent price. Show estimated shares purchasable and residual cash; explain when the instruction cannot buy even one share.
- Account for applicable purchase costs in affordability. An estimate based on a recent price is not a guaranteed execution quantity.
- Show a DCA suitability status and reason, including ineligibility, insufficient monthly contribution, or unverified execution information.
- Generate proposed changes for human review. This design does not include automatic trading or automatic changes to HL instructions.

## Suggested outputs

Produce machine-readable CSV / JSON plus a readable Markdown report. Suggested columns:

| Group | Columns |
|---|---|
| Identity | Company, ticker, ISIN, share class, sector, security type, current FTSE 350 membership |
| Gate | PASS / REVIEW / EXCLUDE, exclusion or review reason, evidence links, applicable year, reviewed date, recheck date |
| Scores | Quality, Growth, Valuation, Price / Trend, weighted total, rank, prior rank / rank change |
| Evidence | Key underlying metrics, metric dates, source links, coverage / confidence, stale-data flags |
| DCA | Recent share price and date, proposed monthly contribution, estimated whole shares, residual cash, HL monthly eligibility and checked date, DCA status / reason |
| Explanation | Why it ranked here, main strengths, risks / weak metrics, next review or action |

Separate ranked PASS and REVIEW candidates and EXCLUDE audit cases. Do not give excluded securities misleading investment scores. Provide concise reason text for every status and score driver, for example: “Strong cash conversion and consistent earnings; valuation above sector history; monthly allocation currently buys one whole share.” Generate explanations from actual data rather than generic templates that imply unsupported conclusions.

## Refresh and reporting schedule

- **Weekly:** refresh prices, trend metrics and rankings; refresh fundamentals when new data becomes available. Record source dates and explain material ranking changes.
- **Monthly:** produce an actionable report sufficiently before HL's verified Direct Debit instruction-change cutoff, allowing time for review and submission. Schedule relative to the actual cutoff with a configurable buffer rather than assuming a fixed date.
- The monthly report should highlight eligible affordable candidates, optional per-security contribution scenarios, gate changes and unresolved reviews.
- Recheck membership, HL eligibility and PFIC/security evidence on an explicit cadence and when material corporate events occur. A weekly price refresh alone does not refresh these checks.
- Configure GitHub Actions scheduling with explicit timezone handling; retain dated reports and flag failed or incomplete refreshes instead of presenting stale results as current.

## Suggested implementation sequence

1. Confirm optional per-security contribution scenarios, account types and permitted data sources.
2. Define the security/PFIC evidence policy and implement auditable PASS / REVIEW / EXCLUDE decisions.
3. Build a current constituent universe and normalize identifiers, sectors and data dates.
4. Implement sector-aware scoring and apply it consistently to all candidates.
5. Add HL eligibility, whole-share affordability and explanatory reports.
6. Add weekly refresh and monthly reporting schedules, with dated artifacts and failure visibility.
7. Validate gates, missing-data behaviour, score weights, sector-specific treatment, affordability and report scheduling with focused automated tests before relying on outputs.

Open decisions include data provider / licensing, detailed PFIC review evidence, submetric weights and normalization, and the verified HL cutoff and reporting buffer. Preserve these as explicit configuration or documented policy rather than hidden assumptions.
