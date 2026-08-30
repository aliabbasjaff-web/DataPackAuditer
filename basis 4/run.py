#!/usr/bin/env python3
"""Basis -- one command, any ticker: generate the datapack, then audit it.

    python3 run.py --ticker NVDA            fetch EDGAR -> build Excel datapack
                                            (per the IB-plugin conventions)
                                            -> recalc -> audit -> HTML report
    python3 run.py --ticker SMCI --offline  use the existing cache, no network
    python3 run.py --ticker SMCI --memo     also run the memo track (grounded
                                            brief generated + verified)

Outputs land in reports/:  <ticker>_datapack_audit.html (the page to open),
plus machine-readable verdict JSONs. The generated workbook lands in
datapacks/<TICKER>_DataPack.xlsx.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from basis import edgar, brief, verify, render, datapack, xlsx_audit


def recalc(xlsx: Path) -> str:
    """Recalculate formulas via bundled LibreOffice script. Returns a note."""
    if shutil.which("soffice") is None:
        return ("LibreOffice not found: formula values were not computed. "
                "Open the workbook in Excel and hit save, then re-run with --offline "
                "to get full formula verification (or install LibreOffice).")
    r = subprocess.run([sys.executable, "scripts/recalc.py", str(xlsx)],
                       capture_output=True, text=True)
    try:
        j = json.loads(r.stdout.strip())
        if j.get("status") == "success":
            return f"Recalculated {j.get('total_formulas', '?')} formulas, 0 errors."
        return f"Recalc reported: {j}"
    except Exception:
        return f"Recalc output unparseable: {r.stdout[-200:]} {r.stderr[-200:]}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--memo", action="store_true", help="also run the memo (brief) track")
    ap.add_argument("--draft", default=None, help="with --memo: verify this extra draft too")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    t = args.ticker.lower()
    cache_path = Path(f"data/cache/{t}.json")

    # [1] the answer key
    if cache_path.exists() and args.offline:
        print(f"[1/4] using cached snapshot {cache_path}")
    elif args.offline:
        raise SystemExit(f"--offline set but no cache at {cache_path}.")
    else:
        print(f"[1/4] fetching {args.ticker.upper()} from SEC EDGAR...")
        try:
            edgar.build_cache(args.ticker, cache_path)
        except Exception as e:
            if cache_path.exists():
                print(f"      fetch failed ({e}); using existing cache")
            else:
                raise SystemExit(
                    f"Fetch failed and no cache exists: {e}\n"
                    f"On a restricted network? That's FAILURES.md #1 -- fetch from an open "
                    f"network and bring the snapshot over.")
    cache = edgar.load_cache(cache_path)
    meta = cache["meta"]
    print(f"      {meta['entity']} | {len(cache['facts'])} concepts | "
          f"{min(meta['fiscal_periods'])}..{max(meta['fiscal_periods'])}"
          + (f" | data gaps: {meta['unresolved_metrics']}" if meta.get("unresolved_metrics") else ""))

    # [2] the agent-under-test: build the datapack
    print("[2/4] building the Excel datapack (IB-plugin conventions)...")
    xlsx = Path(f"datapacks/{args.ticker.upper()}_DataPack.xlsx")
    datapack.build_datapack(cache_path, xlsx)

    # [3] recalc + audit
    print("[3/4] recalculating and auditing every cell...")
    note = recalc(xlsx)
    print(f"      {note}")
    audit = xlsx_audit.audit(str(cache_path), str(xlsx))
    reports = Path("reports"); reports.mkdir(exist_ok=True)
    (reports / f"{t}_datapack_verdicts.json").write_text(json.dumps(audit, indent=2))

    # [4] report
    print("[4/4] rendering report...")
    out_html = reports / f"{t}_datapack_audit.html"
    render.render_datapack_audit(audit, f"{meta['entity']} ({meta.get('ticker','?')})",
                                 out_html, workbook_name=xlsx.name, recalc_note=note)

    print()
    print(f"  audit: {audit['tally']} over {audit['stats']['cells_audited']} cells")
    for f in audit["findings"]:
        if f["verdict"] not in ("VERIFIED",):
            print(f"    !! {f['sheet']}!{f['cell']} {f['verdict']}: {f['detail'][:110]}")
    print(f"\n  workbook: {xlsx}")
    print(f"  report:   {out_html}")

    if args.memo:
        gpath = Path(f"drafts/{t}_grounded_auto.json"); gpath.parent.mkdir(exist_ok=True)
        gpath.write_text(json.dumps(brief.generate_grounded_brief(cache), indent=2))
        g = verify.verify_draft(str(cache_path), str(gpath))
        u = verify.verify_draft(str(cache_path), args.draft) if args.draft else None
        memo_html = reports / f"{t}_memo_report.html"
        render.render(u, g, memo_html)
        print(f"  memo track: grounded {g['grounding_rate']:.0%}"
              + (f" | supplied draft {u['grounding_rate']:.0%}" if u else "")
              + f" -> {memo_html}")

    if not args.no_open:
        webbrowser.open(out_html.resolve().as_uri())


if __name__ == "__main__":
    main()
