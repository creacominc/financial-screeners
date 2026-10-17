"""Supplied JSON inputs; no network access or automated dealing."""
import argparse
import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote, urlparse

from .engine import screen, fresh, number


def json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def write_reports(rows, prefix, today, illustrative=False, metadata=None):
    rows = sorted(rows, key=lambda row: (row["rank"] is None,
                                         row["rank"] if row["rank"] is not None else 0,
                                         row["isin"]))
    prefix.parent.mkdir(parents=True, exist_ok=True)
    metadata = metadata or {}
    refresh = metadata.get("refresh", {})
    data_status = ("REAL HL DATA SNAPSHOT assembled at " + refresh["fetched_at_utc"]) if refresh.get("full_metrics") else "SUPPLIED SNAPSHOT; no live refresh performed"
    if refresh.get('hl_page_cache'):
        cache = refresh['hl_page_cache']
        data_status += f"; {cache['downloaded_pages']} HL pages downloaded, {cache['cached_pages']} reused from cache (market pages: {cache['cache_utc_date']} UTC; financial pages: up to 7 days old); original provider and forecast observation dates retained"
    payload = dict(as_of=today.isoformat(), illustrative=illustrative,
                   data_status=data_status, refresh=refresh, execution_error=metadata.get("execution_error"), rows=rows)
    prefix.with_suffix(".json").write_text(json.dumps(payload, default=json_default, indent=2)+"\n")
    columns = ["company", "ticker", "isin", "share_class", "sector", "security_type", "candidate", "universe_reason",
               "gate_status", "gate_reason", "score_status", "suggested_action", "quality_score", "growth_score", "valuation_score", "trend_score", "pe", "eps_cagr_3y", "revenue_cagr_3y", "price_return_1y", "price_return_3y", "price_return_5y", "price_gbp", "price_date", "total_score", "rank", "prior_rank", "rank_change", "components", "coverage",
               "dca_status", "dca_reason", "estimated_shares", "residual_gbp", "report_due",
               "actionable", "industry", "account_estimates", "data_warnings", "gate_evidence", "metrics", "membership", "execution", "price", "drivers"]
    leading = ["company", "ticker", "isin", "price_return_1y", "price_return_3y", "price_return_5y", "rank", "prior_rank", "rank_change", "total_score"]
    columns = leading + [column for column in columns if column not in leading]
    with prefix.with_suffix(".csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for original in rows:
            row = dict(original)
            for name in ('quality','growth','valuation','trend'):
                row[name+'_score'] = row['components'].get(name)
            for name in ('pe','eps_cagr_3y','revenue_cagr_3y','price_return_1y','price_return_3y','price_return_5y'):
                row[name] = row.get('metrics',{}).get(name,{}).get('value')
            price = row.get('price',{})
            row['price_date'] = price.get('date')
            row['price_gbp'] = (Decimal(price['value']) / (100 if price['currency']=='GBX' else 1)) if price.get('value') and price.get('currency') in ('GBP','GBX') else None
            for key in ("rank", "prior_rank", "rank_change"):
                if row.get(key) is None:
                    row[key] = "N/A"
            writer.writerow({k: json.dumps(row[k], default=json_default) if isinstance(row.get(k), (dict, list)) else row.get(k) for k in columns})
    lines = [f"# FTSE comparison — {today}", "", "ILLUSTRATIVE FIXTURE" if illustrative else data_status, "",
             "Proposals require human review. PASS records a dated review decision, not a permanent PFIC guarantee.", ""]
    def cell(value):
        return str(value if value is not None else '—').replace('|','/').replace('\n',' ').replace('<','&lt;').replace('>','&gt;')
    def company_link(row):
        name = cell(row['company'])
        url = row.get('hl_url', '')
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.netloc != 'www.hl.co.uk':
            return name
        for character in ('\\', '[', ']'):
            name = name.replace(character, '\\' + character)
        return f"[{name}]({quote(url, safe=':/?=&%#')})"
    passed = [r for r in rows if r['gate_status']=='PASS']
    selected = sorted((r for r in rows if r['rank'] is not None),key=lambda r:r['rank'])
    lines += [f"Universe: **{len(rows)}** securities; evidence PASS: **{len(passed)}**; scored selection candidates: **{len(selected)}**; REVIEW: **{sum(r['gate_status']=='REVIEW' for r in rows)}**; EXCLUDE: **{sum(r['gate_status']=='EXCLUDE' for r in rows)}**.", "",
              "Ranking uses Quality 30, Growth 25, Valuation 20 and Price/Trend 15, normalized to 100. Scores are independent of ownership and current investments.", "",
              "Research ranking includes PASS and REVIEW cases with sufficient data. Filter gate_status in the CSV to restrict the universe. REVIEW scores do not establish security/PFIC clearance; EXCLUDE cases remain unscored. Missing data or unsuitable sector policies can still prevent ranking.", "",
              "## Stock research ranking (PASS and REVIEW)", "",
              "| Rank | Company | Sector | Gate status | Indicative GBP buy | Score /100 | Quality | Growth | Valuation | Trend | Next action |",
              "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for row in selected[:25]:
        price=row.get('price',{})
        p=(Decimal(price['value'])/(100 if price.get('currency')=='GBX' else 1)) if price.get('value') and price.get('currency') in ('GBP','GBX') else None
        values=[row['rank'],company_link(row),row['sector'],row['gate_status'],p,row['total_score']]+[row['components'].get(k) for k in ('quality','growth','valuation','trend')]+[row.get('suggested_action')]
        lines.append('| '+' | '.join(cell(v.quantize(Decimal('.01')) if isinstance(v,Decimal) else v) for v in values)+' |')
    if not selected:
        lines += ['','No candidate currently meets the membership and data requirements. See the review queue and data gaps below.']
    lines += ['', '## Account checks and optional affordability scenarios', '',
              'Account indications combine the exact factsheet’s account products with current public HL monthly-investing terms. Verify the share class in HL Monthly Savings before submission. A per-share scenario is not a proposed total portfolio budget.', '']
    for row in selected[:25]:
        for account in row.get('account_estimates',[]):
            lines.append('- '+cell(f"{row['ticker']} — {account['account']}: {account['eligibility']}; {account['proposed_action']}; minimum estimated contribution for one share: £{account.get('minimum_for_one_share_gbp','unverified')}; {account['dca_status']}; estimated shares {account.get('estimated_shares') if account.get('estimated_shares') is not None else '—'}; residual £{account.get('residual_gbp') if account.get('residual_gbp') is not None else '—'}; instruction cutoff {account['cutoff']}"))
    if not any(r.get('account_estimates') for r in selected):
        lines.append('No verified account scenarios supplied.')
    if metadata.get('execution_error'):
        lines += ['', 'HL execution checks unavailable: '+cell(metadata['execution_error'])+'. Stock research remains available; no verified account affordability estimates are supplied.']
    if refresh.get('financial_data_gaps'):
        lines += ['',f"Financial-data gaps: {len(refresh['financial_data_gaps'])}. Affected fields are withheld; details are retained in JSON."]
    lines.append('')
    groups = [('PASS evidence and scoring details', lambda r: r["gate_status"] == "PASS"),
              ("REVIEW queue", lambda r: r["gate_status"] == "REVIEW"),
              ("EXCLUDE audit", lambda r: r["gate_status"] == "EXCLUDE")]
    for title, include in groups:
        lines += [f"## {title}", ""]
        selected = sorted((r for r in rows if include(r)), key=lambda r: (r["rank"] or 10**9, r["isin"]))
        for row in selected:
            # Escape user/provider content so it cannot alter the report structure.
            display_score = "withheld" if row["total_score"] is None else str(row["total_score"].quantize(Decimal(".01")))
            summary = f'{row["company"]} ({row["ticker"]}): {row["gate_status"]}; {row["gate_reason"]}; score {display_score}; rank {row["rank"] or "unranked"}; DCA {row["dca_status"]}: {row["dca_reason"]}. ' + "; ".join(row["drivers"])
            summary += f'; indicative quote {row.get("price",{}).get("value")} {row.get("price",{}).get("currency")} dated {row.get("price",{}).get("date")}'
            if row.get("gate_evidence",{}).get("source"):
                summary += "; evidence: " + row["gate_evidence"]["source"]
            if not row["candidate"]:
                summary += "; " + row["universe_reason"]
            lines.append("- " + summary.replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;"))
        if not selected:
            lines.append("None.")
        lines.append("")
    prefix.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")



def analyse(data, as_of):
    rows = screen(data, as_of)
    terms = data.get('hl_monthly_terms')
    if terms and fresh(terms,as_of,data['policy']['execution_max_days']) and data.get('hl_cutoff'):
        from .execution import account_scenarios
        for row in rows:
            row['account_estimates'] = account_scenarios(row,data,as_of,terms,data['hl_cutoff'])
    return rows


def apply_previous_ranks(rows, previous, as_of, illustrative):
    """Compare only earlier reports with the same ranking basis and data mode."""
    compatible = (date.fromisoformat(previous["as_of"]) < as_of
                  and previous.get("illustrative", False) == illustrative)
    prior = {r["isin"]: r for r in previous["rows"]} if compatible else {}
    for row in rows:
        old = prior.get(row["isin"], {})
        rank = old.get("rank") if old.get("rank_basis") == row["rank_basis"] else None
        if rank is not None and (type(rank) is not int or rank < 1):
            raise ValueError("Invalid previous rank")
        row["prior_rank"] = rank
        row["rank_change"] = rank - row["rank"] if rank is not None and row["rank"] is not None else None


def main():
    parser = argparse.ArgumentParser(description="Screen supplied FTSE data with auditable evidence gates")
    parser.add_argument("input", type=Path)
    parser.add_argument("--monthly-per-share", help="optional GBP affordability scenario per share, not total monthly budget")
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--previous-report", type=Path, help="previous FTSE JSON report for rank movement")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if args.output is None:
        args.output = Path(f"reports/ftse-comparison-{args.as_of.isoformat()}")
    try:
        data = json.loads(args.input.read_text(), parse_float=Decimal)
        if args.monthly_per_share:
            value = number(args.monthly_per_share)
            if value <= 0:
                raise ValueError("Monthly per-share scenario must be positive")
            data["monthly_per_share_gbp"] = str(value)
        rows = analyse(data, args.as_of)
        if args.previous_report:
            previous = json.loads(args.previous_report.read_text(), parse_float=Decimal)
            apply_previous_ranks(rows, previous, args.as_of, data.get("illustrative", False))
        write_reports(rows, args.output, args.as_of, data.get("illustrative", False), data)
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
        parser.error(str(error))
    print(f"Wrote {args.output}.csv, .json and .md (see report data status)")


if __name__ == "__main__":
    main()
