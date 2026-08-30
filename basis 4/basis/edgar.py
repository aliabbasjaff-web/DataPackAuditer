"""EDGAR data layer for Basis -- ticker-driven.

Two modes:
  - live:   hits data.sec.gov directly (open network, e.g. your laptop).
  - cache:  reads a local JSON snapshot (works anywhere, incl. locked-down
            environments -- see FAILURES.md #1 for why this boundary exists).

Ticker -> CIK resolution uses SEC's public company_tickers.json.

Tag resolution: "revenue" is not one XBRL tag (FAILURES.md #6, #11). Each
logical metric has an ordered list of candidate us-gaap tags; the fetcher
tries them in order and records which one won in meta.resolved, so the
audit trail shows exactly which tag every number came from.
"""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import date
from pathlib import Path

UA = "basis-diligence-tool/0.2 (personal research project)"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"

# Logical metric -> candidate tags, tried in order. A tag enters this table
# only with a period-alignment story; the winner is recorded per company.
LOGICAL_TAGS: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "inventory": ["InventoryNet"],
    "ocf": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "rnd": ["ResearchAndDevelopmentExpense"],
    "ar": ["AccountsReceivableNetCurrent"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
}


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def resolve_ticker(ticker: str) -> tuple[str, str]:
    """Return (cik10, company title) for a ticker. Live network required."""
    data = _get_json(TICKERS_URL)
    t = ticker.upper()
    for row in data.values():
        if row["ticker"] == t:
            return str(row["cik_str"]).zfill(10), row["title"]
    raise SystemExit(f"Ticker {t!r} not found in SEC's registry.")


def annual_series(raw: dict) -> dict[str, int]:
    """{period_end: value} from 10-K facts only; restated periods resolve to
    the most recently filed value (restatements are corrections)."""
    out: dict[str, tuple[str, int]] = {}
    for unit_entries in raw.get("units", {}).values():
        for e in unit_entries:
            if e.get("form") != "10-K":
                continue
            end, filed, val = e.get("end"), e.get("filed", ""), e.get("val")
            if end is None or val is None:
                continue
            # keep annual-length durations only (instant facts have no start)
            start = e.get("start")
            if start is not None:
                span = (date.fromisoformat(end) - date.fromisoformat(start)).days
                if not 300 <= span <= 400:
                    continue
            if end not in out or filed > out[end][0]:
                out[end] = (filed, val)
    return {end: v for end, (_, v) in sorted(out.items())}


def build_cache(ticker: str, out_path: Path, years: int = 7) -> dict:
    """Live mode: resolve ticker, resolve tags, fetch, snapshot."""
    cik, title = resolve_ticker(ticker)
    facts: dict[str, dict] = {}
    resolved: dict[str, str] = {}
    misses: list[str] = []
    for logical, candidates in LOGICAL_TAGS.items():
        series: dict[str, int] = {}
        winner = None
        for tag in candidates:
            try:
                raw = _get_json(CONCEPT_URL.format(cik=cik, tag=tag))
            except Exception:
                continue
            s = annual_series(raw)
            time.sleep(0.15)  # SEC limit is 10 req/s; stay well under
            if len(s) >= 3:   # a tag "wins" only with real annual coverage
                series, winner = s, tag
                break
        if winner is None:
            misses.append(logical)
            continue
        concept = f"us-gaap:{winner}"
        facts[concept] = dict(sorted(series.items())[-years:])
        resolved[logical] = concept

    # fiscal calendar comes from the data, never assumed (FAILURES.md #13)
    all_ends = sorted({e for s in facts.values() for e in s})
    fiscal_periods = {f"FY{e[:4]}": e for e in all_ends}

    snapshot = {
        "meta": {
            "entity": title, "ticker": ticker.upper(), "cik": cik,
            "source": "SEC EDGAR XBRL companyconcept API (data.sec.gov)",
            "retrieved": date.today().isoformat(),
            "resolved": resolved,
            "fiscal_periods": fiscal_periods,
            "unresolved_metrics": misses,
        },
        "facts": facts,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, indent=2))
    return snapshot


def load_cache(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--ticker", required=True)
    p.add_argument("--out", default=None)
    args = p.parse_args()
    out = Path(args.out or f"data/cache/{args.ticker.lower()}.json")
    snap = build_cache(args.ticker, out)
    print(f"wrote {out}: {len(snap['facts'])} concepts, "
          f"periods {min(snap['meta']['fiscal_periods'])}..{max(snap['meta']['fiscal_periods'])}, "
          f"unresolved: {snap['meta']['unresolved_metrics'] or 'none'}")
