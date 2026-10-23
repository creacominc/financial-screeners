# FTSE replacement-source evaluation

Evaluated on 22 October 2026. These are local retrieval results, not GitHub
Actions availability guarantees. The default workflow has not been switched.

| Data | Candidate | Result |
| --- | --- | --- |
| FTSE 350 membership | London Stock Exchange | Retrieved 351 records with 351 distinct ISINs and SEDOLs; no missing ISIN, ticker or SEDOL |
| Price history excluding dividends | EODHD split-adjusted API | Public AAPL demo returned daily split-adjusted OHLC; full London coverage and account entitlement remain unverified |
| Free price history | Yahoo Finance chart endpoint | Public AZN.L request returned `Edge: Too Many Requests`; not adopted |
| Free price history | Stooq historical CSV | Public azn.uk request returned browser verification HTML; not adopted |

## LSE constituent source

The [LSE constituent page](https://www.londonstockexchange.com/en/indices/ftse-350/constituents)
loads an All tab whose public table configuration identifies this data URL:

`https://apidata.londonstockexchange.com/instrument-summaries/v1?indexCode=NMX`

This is a public website endpoint, not a documented or contracted vendor API.
It can change. The adapter requires a successful response, 300–400 rows, usable
ISIN/SEDOL/ticker/name fields, and unique identities. It does not infer prices,
HL account eligibility, security classification or PFIC clearance from membership.
The numeric range is a sanity check, not independent proof of index completeness.

To use LSE membership while retaining the existing HL factsheet, fundamental and
performance adapters:

```bash
ftse-fetch-hl reports/ftse_input.json reports/ftse_refreshed.json \
  --discover-universe --universe-source lse --full-metrics \
  --cache-dir reports/hl-cache
```

SEDOLs form public HL factsheet URLs. Every fetched HL factsheet must match the
LSE ISIN before membership is accepted. Membership provenance names LSE. Existing
review evidence retains its dates. An identity mismatch stops the refresh.
LSE is fetched afresh; the HL cache does not cache this separate source.
**This option replaces constituent discovery only.** HL performance and individual
factsheet requests may still be rejected, so this is not a complete replacement
for the failing workflow. The default remains HL until the remaining source is
chosen and validated.

## EODHD evaluation

EODHD is a commercial financial-data provider offering authenticated download
APIs. Its [technical API](https://eodhd.com/financial-apis/technical-indicators-api)
provides `function=splitadjusted`, which adjusts price history for splits but
excludes dividends. The public demo successfully returned AAPL closes including
125.01 on 27 August 2020, before Apple's 4-for-1 split. This confirms the response
format, not FTSE coverage.

Its ordinary [end-of-day API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)
returns raw `close` and split-and-dividend-adjusted `adjusted_close`. Neither can
silently substitute for split-adjusted, dividend-excluding price returns.

An appropriate account must permit London stocks, five years of history and the
split-adjusted endpoint. Provider symbols must be matched by ISIN, with ambiguous
or missing identities withheld; appending an exchange suffix to every HL ticker
is not sufficient verification. Full-universe coverage, freshness and sample
return comparisons must be tested before adoption. An API key would belong in
GitHub Actions Secrets, never repository files or a public chat. No subscription
has been purchased, no key is configured, and no paid provider is enabled.

The provider's advertised free allowance (20 calls/day and one year of history)
does not satisfy a full FTSE 350 refresh with 1-, 3- and 5-year returns. Confirm
current plan entitlements and permitted report publication before buying; public
workflow artifacts and Release CSVs need to be considered when choosing a plan.
