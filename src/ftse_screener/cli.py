"""Supplied JSON inputs; no network access or automated dealing."""
import argparse
import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from .engine import screen


def json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def write_reports(rows, prefix, today, illustrative=False):
    prefix.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(as_of=today.isoformat(), illustrative=illustrative,
                   data_status="SUPPLIED SNAPSHOT; no live refresh performed", rows=rows)
    prefix.with_suffix(".json").write_text(json.dumps(payload, default=json_default, indent=2)+"\n")
    columns = ["company", "ticker", "isin", "share_class", "sector", "security_type", "holding", "holding_value_gbp", "candidate", "universe_reason",
               "gate_status", "gate_reason", "total_score", "rank", "prior_rank", "rank_change", "components", "coverage",
               "sector_weight", "portfolio_basis", "dca_status", "dca_reason", "estimated_shares", "residual_gbp", "report_due",
               "actionable", "gate_evidence", "metrics", "membership", "execution", "price", "drivers"]
    with prefix.with_suffix(".csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(row[k], default=json_default) if isinstance(row.get(k), (dict, list)) else row.get(k) for k in columns})
    lines = [f"# FTSE screening — {today}", "", "ILLUSTRATIVE FIXTURE" if illustrative else "SUPPLIED SNAPSHOT — no live refresh performed", "",
             "Proposals require human review. PASS records a dated review decision, not a permanent PFIC guarantee.", ""]
    groups = [("Ranked PASS candidates", lambda r: r["rank"] is not None),
              ("Existing holdings comparison", lambda r: r.get("holding")),
              ("Unranked PASS / outside universe", lambda r: r["gate_status"] == "PASS" and r["rank"] is None),
              ("REVIEW queue", lambda r: r["gate_status"] == "REVIEW"),
              ("EXCLUDE audit", lambda r: r["gate_status"] == "EXCLUDE")]
    for title, include in groups:
        lines += [f"## {title}", ""]
        selected = sorted((r for r in rows if include(r)), key=lambda r: (r["rank"] or 10**9, r["isin"]))
        for row in selected:
            # Escape user/provider content so it cannot alter the report structure.
            display_score = "withheld" if row["total_score"] is None else str(row["total_score"].quantize(Decimal(".01")))
            summary = f'{row["company"]} ({row["ticker"]}): {row["gate_status"]}; {row["gate_reason"]}; score {display_score}; rank {row["rank"] or "unranked"}; DCA {row["dca_status"]}: {row["dca_reason"]}. ' + "; ".join(row["drivers"])
            if not row["candidate"]:
                summary += "; " + row["universe_reason"]
            lines.append("- " + summary.replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;"))
        if not selected:
            lines.append("None.")
        lines.append("")
    prefix.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Screen supplied FTSE data with auditable evidence gates")
    parser.add_argument("input", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, default=Path("reports/ftse"))
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(), parse_float=Decimal)
        rows = screen(data, args.as_of)
        write_reports(rows, args.output, args.as_of, data.get("illustrative", False))
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
        parser.error(str(error))
    print(f"Wrote {args.output}.csv, .json and .md (supplied snapshot)")


if __name__ == "__main__":
    main()
