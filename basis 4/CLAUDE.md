# Basis — instructions for Claude Code

This repo is a citation gate for AI-generated financial documents: it audits every
number in an AI-drafted brief (or generated Excel) against SEC EDGAR filings.
README.md explains the project; FAILURES.md is the root-cause log and a first-class
deliverable.

## House rules (do not break these)

1. The verifier stays deterministic. Never add an LLM to verify.py or xlsx_audit.py.
2. You (the LLM) work only at the edges: drafting briefs, explaining results.
   Never transport or transform source data yourself — code does that.
3. Fail closed: anything unverifiable is stripped or flagged, never trusted.
4. Every failure or surprise gets logged in FAILURES.md (symptom → root cause →
   fix → generalization) before it gets fixed.
5. The user is not technical. Explain what you're doing in plain terms as you go.

## The commands

Audit any company (fetch -> build Excel datapack -> audit -> HTML report):

    python3 run.py --ticker NVDA

Offline from an existing snapshot:

    python3 run.py --ticker SMCI --offline

Add the memo track (grounded brief generated + verified; optional 'before' draft):

    python3 run.py --ticker SMCI --offline --memo --draft drafts/smci_ungrounded.json

Formula verification needs computed values: run.py uses LibreOffice via
scripts/recalc.py if installed; otherwise open the workbook in Excel, save,
and re-run with --offline.

## When the user says "audit <TICKER>" (the main flow)

Run `python3 run.py --ticker <TICKER>`, then open reports/<ticker>_datapack_audit.html
and summarize: cells verified, each finding and why, and anything in
meta.unresolved_metrics (metrics whose XBRL tags didn't resolve for this company —
candidates may need to be added to LOGICAL_TAGS in basis/edgar.py; that is the
evidence base widening, do it deliberately and note it).

## When the user says "run the memory experiment for <TICKER>"

1. Make sure the cache exists (run.py fetches it).
2. WITHOUT reading the cache file, write drafts/<ticker>_ungrounded.json from your
   own prior knowledge of the company: ~10-12 claims in the schema
   (see drafts/smci_ungrounded.json for the shape), with the source refs the claims
   intend to cite. Be honest — state what you actually believe, don't hedge.
3. Run: python3 run.py --ticker <TICKER> --offline --draft drafts/<ticker>_ungrounded.json
4. Report both grounding rates, classify your own errors (stale / inflated /
   plausible-precision), and append the pattern to FAILURES.md.

## Repo map

- run.py — orchestrator (fetch → grounded brief → verify → render)
- basis/edgar.py — EDGAR client: ticker→CIK, tag resolver (LOGICAL_TAGS), cache snapshots
- basis/brief.py — generates the grounded, machine-checkable brief from a cache
- basis/verify.py — the citation gate (claims: fact / derived / qualitative)
- basis/xlsx_audit.py — audits generated Excel workbooks cell-by-cell
- basis/render.py — single-file HTML report
- drafts/ — claim sets; data/cache/ — EDGAR snapshots; reports/ — outputs
- agent_run/ — the datapack built by Anthropic's IB-plugin skill, used as audit target
