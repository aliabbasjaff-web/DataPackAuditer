"""Render the verification results as a single-file HTML report.

The report is the demo artifact: the grounded brief with inline
verification badges, the ungrounded draft shown as the 'before', and the
full audit trail in an appendix. No external assets, opens anywhere.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

BADGE = {
    "VERIFIED": ("&#10003; verified", "#0d7a3f", "#e7f5ec"),
    "MISMATCH": ("&#10007; mismatch", "#b3261e", "#fdeceb"),
    "UNSOURCED": ("&#9888; unsourced", "#8a5a00", "#fdf3e0"),
    "UNVERIFIABLE": ("&#9998; human review", "#5b5b66", "#efeff2"),
}

CSS = """
:root { --ink:#1c1c22; --muted:#5b5b66; --line:#e4e4ea; --bg:#fafafa; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.6 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
.wrap { max-width:880px; margin:0 auto; padding:48px 24px 96px; }
h1 { font-size:26px; margin:0 0 4px; }
h2 { font-size:19px; margin:40px 0 12px; border-bottom:1px solid var(--line); padding-bottom:6px; }
.sub { color:var(--muted); margin-bottom:28px; }
.scoreband { display:flex; gap:16px; margin:24px 0; flex-wrap:wrap; }
.score { flex:1 1 180px; border:1px solid var(--line); background:#fff; border-radius:10px; padding:16px 18px; }
.score .n { font-size:30px; font-weight:700; }
.score .l { color:var(--muted); font-size:13px; }
.claim { background:#fff; border:1px solid var(--line); border-left-width:4px;
  border-radius:8px; padding:12px 16px; margin:10px 0; }
.badge { display:inline-block; font-size:11.5px; font-weight:600; padding:2px 9px;
  border-radius:99px; margin-left:8px; vertical-align:middle; white-space:nowrap; }
.detail { color:var(--muted); font-size:12.5px; margin-top:6px; font-family:ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
.note { background:#fff; border:1px solid var(--line); border-radius:10px; padding:16px 18px; color:var(--muted); font-size:13.5px; }
table { width:100%; border-collapse:collapse; background:#fff; font-size:13px; }
th, td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
th { color:var(--muted); font-weight:600; }
.mono { font-family:ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size:12px; }
.overflow { overflow-x:auto; }
"""


def _badge(verdict: str) -> str:
    label, fg, bg = BADGE[verdict]
    return f'<span class="badge" style="color:{fg};background:{bg}">{label}</span>'


def _claims_html(results: list[dict], strip_failed: bool) -> str:
    out = []
    for r in results:
        v = r["verdict"]
        if strip_failed and v in ("MISMATCH", "UNSOURCED"):
            continue
        _, fg, _ = BADGE[v]
        out.append(
            f'<div class="claim" style="border-left-color:{fg}">'
            f'{html.escape(r["text"])}{_badge(v)}'
            f'<div class="detail">{html.escape(r["detail"])}</div></div>'
        )
    return "\n".join(out)


def _score(label: str, value: str, sub: str) -> str:
    return (f'<div class="score"><div class="n">{value}</div>'
            f'<div class="l">{label}<br>{sub}</div></div>')


def render(ungrounded: dict | None, grounded: dict, out_path: Path) -> None:
    g_t = grounded["tally"]
    if ungrounded:
        ug_t = ungrounded["tally"]
        before_scores = (
            _score("supplied draft", f"{ungrounded['grounding_rate']:.0%}",
                   "of quantitative claims verified &mdash; e.g. model memory only")
            + _score("mismatches caught", str(ug_t.get("MISMATCH", 0)),
                     "figures that cited a source but did not match it"))
        before_section = f"""
<h2>Before: the supplied draft (e.g. drafted from model memory)</h2>
<p class="note">Same company, but drafted without the source data in front of the model.
Ungrounded errors are rarely random noise: they tend to be <b>stale</b> (last year's true
figures presented as current), <b>rounded past the tolerance</b>, or <b>narratively
inflated</b>.</p>
{_claims_html(ungrounded["results"], strip_failed=False)}"""
        trail = ungrounded["results"] + grounded["results"]
    else:
        before_scores, before_section = "", ""
        trail = grounded["results"]
    body = f"""
<div class="wrap">
<h1>Basis &mdash; grounded diligence brief</h1>
<div class="sub">{html.escape(grounded["company"])} &middot; generated {html.escape(str(grounded.get("as_of","")))} &middot;
source: SEC EDGAR XBRL, 10-K filings &middot; every figure below is machine-audited against the filed value</div>

<div class="scoreband">
{_score("grounded brief", f"{grounded['grounding_rate']:.0%}", "of quantitative claims verified against filings")}
{before_scores}
{_score("claims stripped", str(g_t.get("UNSOURCED", 0)), "grounded-brief claims the gate could not recompute")}
</div>

<h2>The brief (grounded &amp; audited)</h2>
{_claims_html(grounded["results"], strip_failed=False)}
{before_section}

<h2>Audit trail</h2>
<div class="overflow"><table>
<tr><th>id</th><th>verdict</th><th>detail</th></tr>
{"".join(f'<tr><td class="mono">{r["id"]}</td><td>{_badge(r["verdict"])}</td><td class="mono">{html.escape(r["detail"])}</td></tr>' for r in trail)}
</table></div>

<h2>Method</h2>
<p class="note">Facts come from SEC EDGAR's XBRL companyconcept API and are cached locally
(<span class="mono">data/cache/smci.json</span>). A claim is a typed JSON object: primitive facts
carry a concept + period source ref; derived metrics carry a derivation spec the verifier
recomputes from cited primitives. Tolerances: 0.5% relative on dollar figures, 0.4pp absolute
on percentages. Qualitative claims are labeled for human review &mdash; the gate neither blesses
nor strips what it cannot check. Restated periods resolve to the most recent filing.</p>
</div>
"""
    doc = (f"<!doctype html><html><head><meta charset='utf-8'>"
           f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>Basis &mdash; SMCI diligence brief</title><style>{CSS}</style></head>"
           f"<body>{body}</body></html>")
    out_path.write_text(doc)


XLSX_BADGE = dict(BADGE)
XLSX_BADGE.update({
    "RULE6_VIOLATION": ("&#9888; rule 6: hardcode", "#8a5a00", "#fdf3e0"),
    "NARRATIVE_UNAUDITED": ("&#9998; prose &mdash; human review", "#5b5b66", "#efeff2"),
    "NOT_EVALUATED": ("&#9711; not evaluated", "#5b5b66", "#efeff2"),
})


def _xbadge(verdict: str) -> str:
    label, fg, bg = XLSX_BADGE.get(verdict, (verdict, "#5b5b66", "#efeff2"))
    return f'<span class="badge" style="color:{fg};background:{bg}">{label}</span>'


def render_datapack_audit(audit: dict, company: str, out_path: Path,
                          workbook_name: str = "", recalc_note: str = "") -> None:
    """Single-page report for the Excel datapack audit."""
    t = audit["tally"]
    s = audit["stats"]
    verified = t.get("VERIFIED", 0)
    findings = [f for f in audit["findings"] if f["verdict"] != "VERIFIED"]
    hard = [f for f in findings if f["verdict"] in ("MISMATCH", "RULE6_VIOLATION", "UNSOURCED")]
    soft = [f for f in findings if f["verdict"] not in ("MISMATCH", "RULE6_VIOLATION", "UNSOURCED")]

    def rows(fs):
        return "".join(
            f'<tr><td class="mono">{html.escape(f["sheet"])}!{html.escape(f["cell"])}</td>'
            f'<td>{_xbadge(f["verdict"])}</td>'
            f'<td>{html.escape(f.get("label",""))}</td>'
            f'<td class="mono">{html.escape(f["detail"])}</td></tr>' for f in fs)

    body = f"""
<div class="wrap">
<h1>Basis &mdash; datapack audit</h1>
<div class="sub">{html.escape(company)} &middot; workbook: {html.escape(workbook_name)} &middot;
generated per the Anthropic IB-plugin conventions, then audited cell-by-cell against SEC EDGAR XBRL</div>

<div class="scoreband">
{_score("cells audited", str(s["cells_audited"]), f"{s['inputs']} inputs &middot; {s['formulas']} formulas")}
{_score("verified", str(verified), "matched a filed value, or recomputed correctly")}
{_score("hard findings", str(len(hard)), "mismatches, rule violations, unsourced hardcodes")}
{_score("flagged for humans", str(len(soft)), "prose numbers &amp; unevaluated cells")}
</div>

<h2>Findings</h2>
{("<p class='note'>No hard findings and nothing flagged &mdash; every audited cell traced or recomputed.</p>"
  if not findings else "")}
<div class="overflow"><table>
<tr><th>cell</th><th>verdict</th><th>row label</th><th>detail</th></tr>
{rows(hard)}{rows(soft)}
</table></div>

<h2>What was checked</h2>
<p class="note">1) Every hardcoded input was mapped from its row label to an XBRL concept and compared,
scale-aware, to the value the company filed (tolerance 0.5% relative / small rounding allowance).
2) Every recognizable derived formula (margins, growth, DSO/DIO, plugs, totals) was independently
recomputed from the filed values and compared to the spreadsheet's result &mdash; a well-formed formula
proves nothing; only recompute-and-compare does. 3) The plugin's own "formulas, never hardcodes"
rule was enforced on calculation rows. 4) Numbers appearing inside prose were flagged for human
review: text bypasses cell-level audit. {html.escape(recalc_note)}</p>
</div>
"""
    doc = (f"<!doctype html><html><head><meta charset='utf-8'>"
           f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>Basis &mdash; datapack audit</title><style>{CSS}</style></head>"
           f"<body>{body}</body></html>")
    Path(out_path).write_text(doc)


if __name__ == "__main__":
    ug = json.loads(Path(sys.argv[1]).read_text())
    g = json.loads(Path(sys.argv[2]).read_text())
    out = Path(sys.argv[3] if len(sys.argv) > 3 else "reports/report.html")
    render(ug, g, out)
    print(f"wrote {out}")
