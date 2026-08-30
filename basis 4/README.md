# Basis — an audit layer for AI-generated financial work product

**One sentence:** AI agents now produce banker-grade deliverables (briefs, datapacks,
models); Basis is the citation gate that answers the question a client will actually
ask — *how do you know it's right?* — by tracing every number back to the filed source
and stripping what it can't verify.

Built with Claude Code over a weekend. The interesting output isn't the tool — it's
[FAILURES.md](FAILURES.md), the root-cause log of ten specific ways the agents and the
audit itself went wrong while building it.

---

## What it does + who uses it

Two audit targets, one engine:

1. **Diligence briefs.** An LLM drafts a company brief where every quantitative claim
   must carry a source reference (XBRL concept + period) or a derivation spec. A
   deterministic verifier checks each figure against SEC EDGAR data, recomputes derived
   metrics from cited primitives, and strips anything it can't check.
2. **Agent-generated Excel.** Anthropic's public investment-banking plugin generates
   IC-ready datapacks and promises "zero tolerance for errors" — in prose, with no
   enforcement mechanism. Basis audits the generated workbook cell by cell: maps row
   labels to XBRL concepts, verifies inputs against filed values (scale-aware),
   recomputes every derived formula's value, enforces the plugin's own
   formulas-not-hardcodes rule, and flags numeric claims living in narrative text.

User: me — for screening names I follow. Design target: any workflow where an
AI-drafted financial document needs to be trusted by someone who didn't watch it
being made.

## Inputs → outputs

- **In:** SEC EDGAR XBRL company facts (free, no key), cached locally as JSON;
  a drafted brief (`drafts/*.json`, typed claim schema); and/or a generated `.xlsx`.
- **Out:** verdicts per claim/cell — `VERIFIED / MISMATCH / UNSOURCED / RULE6_VIOLATION /
  NARRATIVE_UNAUDITED / UNVERIFIABLE(human)` — plus a grounding-rate metric, an HTML
  report with inline badges and a full audit trail, and machine-readable JSON.

## Headline results (SMCI, FY2021–FY2025)

| Run | Result |
|---|---|
| Brief drafted from model memory (no data access) | **10%** of quantitative claims survived audit — errors were stale (last year's cash as current), inflated ("tripled" for +110%), or plausibly precise and wrong |
| Same brief drafted against the cache | **87.5%** verified; both failures were the gate *refusing* claims it couldn't check, not wrong numbers passing |
| Anthropic IB-plugin datapack (94 formulas, clean recalc) | **128/139 cells verified**; 1 real defect caught — a link to an intentionally-blank cell manufactured a fake "0.0% growth"; 3 narrative bypasses flagged |

## Architecture

```
[live network]                 [anywhere, incl. locked-down env]
EDGAR XBRL API ──► fetch ──► data/cache/*.json ──► verify.py      ──► verdicts ──► render.py ──► HTML report
                   (edgar.py)         │             (claim gate)
                                      └──────────► xlsx_audit.py  ──► verdicts
                                                    (workbook gate)
LLM sits ONLY at the drafting edge — never in the data path (FAILURES.md #2).
```

- `basis/edgar.py` — EDGAR client + cache boundary (`CORE_CONCEPTS` is the versioned
  evidence base; see FAILURES.md #5)
- `basis/verify.py` — claim schema verifier: primitive facts matched to filed values,
  derived metrics recomputed via a small op DSL, split tolerances (0.5% rel on dollars,
  0.4pp abs on percentages — FAILURES.md #7)
- `basis/xlsx_audit.py` — workbook auditor (two-pass openpyxl read, label→concept
  mapping, scale detection, derived recompute, RULE-6 hardcode detection, prose scan)
- `agent_run/` — the agent-under-test: the datapack built by following the plugin
  skill's instructions verbatim
- `reports/` — HTML report + JSON audit trails

## Tooling

Claude Code (build agent + brief drafter), Python 3.11 stdlib + openpyxl, SEC EDGAR
XBRL API, LibreOffice headless for formula recalculation. No framework, no vector DB,
no fine-tuning — the point is that trust came from a deterministic 300-line verifier,
not from a bigger model.

## What I'd build next

Multi-company tag resolver (FAILURES.md #6), average-balance ops in the derivation DSL
(#4), narrative generated *from* verified cells instead of alongside them (#10), and a
Form D module extending the same gate to private-company raise data.
