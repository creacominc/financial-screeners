"""Pure Decimal screening. Evidence decisions require an identified reviewer and dated sources."""
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
from zoneinfo import ZoneInfo

D = Decimal
WEIGHTS = {"quality": D(".30"), "growth": D(".25"), "valuation": D(".20"),
           "trend": D(".15"), "diversification": D(".10")}
PROHIBITED = {"investment_trust", "etf", "fund", "vct", "closed_end_fund", "spac", "cash_shell"}


def number(value):
    if value is None or isinstance(value, (float, bool)):
        raise ValueError("financial inputs must be decimal strings or integers")
    result = D(value)
    if not result.is_finite():
        raise ValueError("non-finite number")
    return result


def fresh(record, today, max_days):
    try:
        return bool(record["source"]) and 0 <= (today - date.fromisoformat(record["date"])).days <= max_days
    except (KeyError, ValueError, TypeError):
        return False


def gate(stock, policy, today):
    kind = stock.get("security_type")
    evidence = stock.get("gate_evidence", {})
    if kind in PROHIBITED or evidence.get("decision") == "EXCLUDE":
        return "EXCLUDE", evidence.get("rationale") or "Prohibited security type"
    if kind != "operating_company":
        return "REVIEW", "Unresolved security structure (including property structures)"
    valid = (evidence.get("decision") == "PASS" and evidence.get("rationale")
             and evidence.get("reviewer") and evidence.get("year") in policy.get("review_years", [policy["review_year"]])
             and fresh(evidence, today, policy["gate_max_days"])
             and not evidence.get("conflict", False))
    try:
        valid = valid and today < date.fromisoformat(evidence["recheck_date"])
    except (KeyError, ValueError):
        valid = False
    if not valid:
        return "REVIEW", "Missing, conflicting, stale or unresolved security/PFIC evidence"
    return "PASS", evidence["rationale"]


def component(stock, specs, today, max_days):
    total = weight = covered = D(0)
    drivers = []
    for spec in specs:
        w = number(spec["weight"])
        if w <= 0:
            raise ValueError("metric weight must be positive")
        weight += w
        metric = stock.get("metrics", {}).get(spec["name"], {})
        low, high = number(spec["low"]), number(spec["high"])
        if high <= low or spec["direction"] not in ("higher", "lower"):
            raise ValueError("invalid normalization anchors or direction")
        if not fresh(metric, today, spec.get("max_days", max_days)) or metric.get("value") is None:
            drivers.append(f'{spec["name"]}: unavailable/stale')
            continue
        value = number(metric["value"])
        if spec.get("positive_only") and value <= 0:
            drivers.append(f'{spec["name"]}: non-positive; withheld')
            continue
        score = max(D(0), min(D(100), (value - low) / (high - low) * 100))
        if spec["direction"] == "lower":
            score = 100 - score
        total += score * w
        covered += w
        drivers.append(f'{spec["name"]}={value}: {score.quantize(D(".01"))}/100')
    if weight == 0:
        raise ValueError("empty component policy")
    return (total / covered if covered else None), covered / weight, drivers


def affordability(stock, policy, today):
    info = stock.get("execution", {})
    if not fresh(info, today, policy["execution_max_days"]) or not info.get("account"):
        return dict(dca_status="UNVERIFIED", dca_reason="HL eligibility, costs or account unverified")
    if info.get("eligible") is False:
        return dict(dca_status="INELIGIBLE", dca_reason="Not eligible for supplied HL account/share class")
    price = stock.get("price", {})
    required = ("fee_gbp", "purchase_tax_rate", "minimum_gbp", "contribution_gbp", "cutoff")
    if info.get("eligible") is not True or any(k not in info for k in required) or price.get("value") is None or not fresh(price, today, policy["price_max_days"]):
        return dict(dca_status="UNVERIFIED", dca_reason="Missing/stale price, costs, contribution or cutoff")
    p = number(price["value"])
    if price.get("currency") == "GBX":
        p /= 100
    elif price.get("currency") != "GBP":
        return dict(dca_status="UNVERIFIED", dca_reason="Price must explicitly use GBP or GBX")
    budget, fee, rate, minimum = (
        number(info["contribution_gbp"]), number(info["fee_gbp"]),
        number(info["purchase_tax_rate"]), number(info["minimum_gbp"]))
    if p <= 0 or min(budget, fee, rate, minimum) < 0:
        raise ValueError("invalid price or execution costs")
    cutoff = datetime.fromisoformat(info["cutoff"])
    if cutoff.tzinfo is None:
        raise ValueError("cutoff must include a UTC offset")
    shares = max(D(0), ((budget-fee)/(p*(1+rate))).to_integral_value(rounding=ROUND_FLOOR))
    # Purchase costs rounded upwards to pennies to avoid overstating affordability.
    cost = lambda n: (n*p*(1+rate)+fee).quantize(D(".01"), rounding=ROUND_CEILING)
    while shares and cost(shares) > budget:
        shares -= 1
    ready = shares > 0 and budget >= minimum and today < cutoff.astimezone(ZoneInfo("Europe/London")).date()
    if not ready:
        shares = D(0)
    return dict(dca_status="ESTIMATE" if ready else "BLOCKED",
                dca_reason="Whole-share estimate; human instruction review required" if ready else "Below minimum, unaffordable or cutoff passed",
                estimated_shares=shares, residual_gbp=budget-cost(shares) if shares else budget,
                report_due=(cutoff.astimezone(ZoneInfo("Europe/London"))-timedelta(days=policy["cutoff_buffer_days"])).isoformat())


def screen(data, today):
    policy = data["policy"]
    for field in ("gate_max_days", "membership_max_days", "metric_max_days", "execution_max_days", "price_max_days", "cutoff_buffer_days"):
        if not isinstance(policy[field], int) or policy[field] < 0:
            raise ValueError(f"invalid policy: {field}")
    minimum = number(policy["minimum_coverage"])
    if not 0 < minimum <= 1:
        raise ValueError("minimum_coverage must be in (0, 1]")
    stocks = data["stocks"]
    seen = set()
    sectors = {}
    holdings = [s for s in stocks if s.get("holding")]
    values_available = all("holding_value_gbp" in s for s in holdings)
    for s in holdings:
        value = number(s["holding_value_gbp"]) if values_available else D(1)
        if value < 0:
            raise ValueError("negative holding value")
        sectors[s["sector"]] = sectors.get(s["sector"], D(0)) + value
    total = sum(sectors.values(), D(0)) if not data.get("unresolved_holdings") else D(0)
    rows = []
    for stock in stocks:
        for key in ("isin", "ticker", "company", "share_class", "sector"):
            if not stock.get(key):
                raise ValueError(f"missing {key}")
        if stock["isin"] in seen:
            raise ValueError("duplicate ISIN")
        seen.add(stock["isin"])
        status, reason = gate(stock, policy, today)
        membership = stock.get("membership", {})
        candidate = membership.get("ftse350") is True and fresh(membership, today, policy["membership_max_days"])
        row = dict(stock, gate_status=status, gate_reason=reason, candidate=candidate,
                   total_score=None, rank=None, rank_change=None, selection_score=None, selection_rank=None, score_status="WITHHELD", components={}, coverage={}, drivers=[],
                   sector_weight=sectors.get(stock["sector"], D(0))/total if total else None,
                   portfolio_basis="values" if values_available else "holding counts fallback",
                   universe_reason="Current supplied FTSE350 membership" if candidate else "Outside/unverified/stale FTSE350 membership; purchase ranking withheld",
                   actionable=False)
        row.update(affordability(stock, policy, today))
        if status != "EXCLUDE":
            sector_policy = policy["sector_metrics"].get(stock["sector"])
            if sector_policy:
                for name in ("quality", "growth", "valuation", "trend"):
                    score, coverage, drivers = component(stock, sector_policy[name], today, policy["metric_max_days"])
                    row["components"][name] = score
                    row["coverage"][name] = coverage
                    row["drivers"].extend(drivers)
                if all(v >= minimum for v in row["coverage"].values()) and all(row["components"].get(k) is not None for k in ("quality", "growth", "valuation", "trend")):
                    row["selection_score"] = sum((row["components"][k] * WEIGHTS[k] for k in ("quality", "growth", "valuation", "trend")), D(0)) / D(".90")
                    row["score_status"] = "SELECTION_ONLY: 90% investment components normalized to 100; portfolio diversification not assessed"
                target = policy["sector_targets"].get(stock["sector"])
                if total and target is not None:
                    target = number(target)
                    if not 0 < target <= 1:
                        raise ValueError("sector targets must be in (0, 1]")
                    row["components"]["diversification"] = max(D(0), min(D(100), D(50)+(target-row["sector_weight"])/target*50))
                    row["drivers"].append(f'Sector exposure {row["sector_weight"]*100}% versus target {target*100}%; diversification {row["components"]["diversification"]}/100')
                else:
                    row["components"]["diversification"] = None
                if all(v >= minimum for v in row["coverage"].values()) and all(v is not None for v in row["components"].values()):
                    row["total_score"] = sum((row["components"][k]*w for k,w in WEIGHTS.items()), D(0))
                    row["score_status"] = "COMPLETE: includes portfolio diversification"
            if row["total_score"] is None:
                row["drivers"].append("Portfolio total withheld: missing portfolio context; investment selection score available" if row["selection_score"] is not None else "Score withheld: missing sector policy, portfolio context or minimum coverage")
        if status == "REVIEW":
            row["score_status"] += "; RESEARCH ONLY: unresolved security/PFIC evidence"
        rows.append(row)
    ranked = sorted((r for r in rows if r["candidate"] and r["total_score"] is not None), key=lambda r: (-r["total_score"], r["isin"]))
    for rank, row in enumerate(ranked, 1):
        row["rank"] = rank
        if row.get("prior_rank") is not None:
            row["rank_change"] = int(row["prior_rank"]) - rank
        row["actionable"] = row["gate_status"] == "PASS" and row["dca_status"] == "ESTIMATE" and not data.get("illustrative", False)
    selection = sorted((r for r in rows if r["candidate"] and r["selection_score"] is not None), key=lambda r: (-r["selection_score"], r["isin"]))
    for rank, row in enumerate(selection, 1):
        row["selection_rank"] = rank
        row["suggested_action"] = ("Resolve gate review before considering purchase" if row["gate_status"] == "REVIEW" else "Consider increasing monthly purchase" if row.get("holding") else ("Consider adding to monthly purchases" if row.get("holding") is False or data.get("holdings_complete") else "Check ownership, then consider adding or increasing monthly purchase"))
    return rows
