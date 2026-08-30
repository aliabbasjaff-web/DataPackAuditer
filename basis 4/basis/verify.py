"""The citation gate.

Every quantitative claim in a drafted brief must either:
  (a) cite a cached XBRL fact (concept + period) that matches its value, or
  (b) be a derived metric the verifier can recompute from cited primitives.

Anything else is UNSOURCED and gets stripped from the rendered brief.
Anything that cites a source but doesn't match it is a MISMATCH -- worse
than unsourced, because it *looks* grounded.

Claim JSON schema (drafts/*.json):
{
  "company": "...", "as_of": "...",
  "claims": [
    {
      "id": "c01",
      "text": "human-readable sentence containing the figure(s)",
      "kind": "fact" | "derived" | "qualitative",
      # kind=fact:
      "figure": {"value": 21972042000, "concept": "us-gaap:...",
                 "period_end": "2025-06-30", "unit": "USD"},
      # kind=derived:
      "derivation": {"op": "yoy_growth" | "margin" | "ratio" | "delta",
                     "numerator":   {"concept": "...", "period_end": "..."},
                     "denominator": {"concept": "...", "period_end": "..."},
                     "stated_value": 0.466,  # what the draft asserted
                     "unit": "pct" | "x" | "USD"}
    }, ...
  ]
}

Verdicts: VERIFIED | MISMATCH | UNSOURCED | UNVERIFIABLE (qualitative --
needs a human or a filing-text check; the gate neither blesses nor strips
these, it labels them).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Tolerances. Chosen deliberately, and worth defending out loud:
# - REL_TOL 0.5% for dollar figures: allows "$22.0B" prose rounding of
#   21,972,042,000 but catches a stale or fabricated number.
# - PCT_TOL 0.4pp absolute for percentages: "~14% gross margin" vs 13.75%
#   passes; 9.6% vs 11.1% fails. Relative tolerance is wrong for small
#   percentages (0.5% of an 11% margin is 0.06pp -- nothing would pass).
REL_TOL = 0.005
PCT_TOL = 0.004


def _lookup(cache: dict, concept: str, period_end: str):
    series = cache["facts"].get(concept)
    if series is None:
        return None, f"concept {concept} not in cache"
    if period_end not in series:
        have = ", ".join(sorted(series)[-3:])
        return None, f"period {period_end} not in cache for {concept} (latest: {have})"
    return series[period_end], None


def _close(stated: float, actual: float, unit: str) -> bool:
    if unit in ("pct",):
        return abs(stated - actual) <= PCT_TOL
    if actual == 0:
        return stated == 0
    return abs(stated - actual) / abs(actual) <= REL_TOL


def _recompute(cache: dict, d: dict):
    num, err = _lookup(cache, d["numerator"]["concept"], d["numerator"]["period_end"])
    if err:
        return None, err
    den, err = _lookup(cache, d["denominator"]["concept"], d["denominator"]["period_end"])
    if err:
        return None, err
    op = d["op"]
    if op == "yoy_growth":
        if den == 0:
            return None, "division by zero"
        return num / den - 1.0, None
    if op == "margin" or op == "ratio":
        if den == 0:
            return None, "division by zero"
        return num / den, None
    if op == "delta":
        return num - den, None
    return None, f"unknown op {op}"


def verify_claim(cache: dict, claim: dict) -> dict:
    kind = claim.get("kind")
    out = {"id": claim["id"], "text": claim["text"], "kind": kind}

    if kind == "qualitative":
        out["verdict"] = "UNVERIFIABLE"
        out["detail"] = "qualitative claim -- outside the gate; flag for human review"
        return out

    if kind == "fact":
        fig = claim.get("figure")
        if not fig or "concept" not in fig:
            out["verdict"] = "UNSOURCED"
            out["detail"] = "no source reference attached to figure"
            return out
        actual, err = _lookup(cache, fig["concept"], fig["period_end"])
        if err:
            out["verdict"] = "UNSOURCED"
            out["detail"] = err
            return out
        if _close(fig["value"], actual, fig.get("unit", "USD")):
            out["verdict"] = "VERIFIED"
            out["detail"] = f"matches {fig['concept']} @ {fig['period_end']} = {actual:,}"
        else:
            delta = (fig["value"] - actual) / actual if actual else float("inf")
            out["verdict"] = "MISMATCH"
            out["detail"] = (
                f"stated {fig['value']:,} vs filed {actual:,} "
                f"({delta:+.1%} off) for {fig['concept']} @ {fig['period_end']}"
            )
        return out

    if kind == "derived":
        d = claim.get("derivation")
        if not d:
            out["verdict"] = "UNSOURCED"
            out["detail"] = "derived claim with no derivation spec"
            return out
        actual, err = _recompute(cache, d)
        if err:
            out["verdict"] = "UNSOURCED"
            out["detail"] = f"cannot recompute: {err}"
            return out
        stated = d["stated_value"]
        unit = d.get("unit", "pct")
        if _close(stated, actual, unit):
            out["verdict"] = "VERIFIED"
            out["detail"] = f"recomputed {actual:,.4f} ~= stated {stated:,.4f} [{d['op']}]"
        else:
            out["verdict"] = "MISMATCH"
            out["detail"] = f"stated {stated:,.4f} but recomputes to {actual:,.4f} [{d['op']}]"
        out["recomputed"] = actual
        return out

    out["verdict"] = "UNSOURCED"
    out["detail"] = f"unknown claim kind {kind!r}"
    return out


def verify_draft(cache_path: str, draft_path: str) -> dict:
    cache = json.loads(Path(cache_path).read_text())
    draft = json.loads(Path(draft_path).read_text())
    results = [verify_claim(cache, c) for c in draft["claims"]]
    tally: dict[str, int] = {}
    for r in results:
        tally[r["verdict"]] = tally.get(r["verdict"], 0) + 1
    quantitative = [r for r in results if r["kind"] != "qualitative"]
    passed = sum(1 for r in quantitative if r["verdict"] == "VERIFIED")
    return {
        "draft": draft_path,
        "company": draft.get("company"),
        "tally": tally,
        "grounding_rate": round(passed / len(quantitative), 3) if quantitative else None,
        "results": results,
    }


if __name__ == "__main__":
    report = verify_draft(sys.argv[1], sys.argv[2])
    print(json.dumps(report, indent=2))
