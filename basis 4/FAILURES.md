# FAILURES.md — root-cause log

Every failure hit while building Basis, with the root cause underneath the symptom.
This log is a first-class artifact of the project: the tool's design *is* the list of
things that went wrong, addressed one at a time.

---

## 1. The environment blocked the data source before a single line of pipeline code ran

**Symptom.** The plan assumed `data.sec.gov` was reachable. First HTTP call failed:
`Tunnel connection failed: 403 Forbidden` — the build environment's egress proxy
allowlists specific hosts (package registries, GitHub API) and SEC EDGAR wasn't on it.
Neither was any market-data provider I probed.

**Root cause.** Not a bug — a policy. Sandboxed/enterprise environments run
deny-by-default egress. The agent's "plan" was written for the open internet; the
environment it actually ran in looked like a bank's network.

**Fix.** Split the pipeline at a cache boundary: a fetch layer that runs wherever the
network allows it, writing a JSON snapshot; and a verify/render layer that only ever
reads the snapshot. The pipeline became runnable offline, in CI, and inside a locked
network — which is a better architecture than the original plan, not a workaround.

**Generalization.** The first question for any enterprise agent deployment is not
"what can the model do" but "what can the process reach." Egress policy, not model
capability, was the binding constraint within the first ten minutes.

---

## 2. An LLM in the data path silently fabricated a filing record

**Symptom.** To get SMCI's filing history I fetched the EDGAR submissions index through
an LLM-based extraction step (the only fetch path available, see #1). The output listed
a 10-K filed **2024-02-29**. SMCI's FY2024 10-K was famously *late* — filed 2025-02-25
after an NT 10-K and the auditor's resignation. The extraction also dropped the NT 10-K
entirely. The fabricated record was formatted perfectly: right shape, right fields,
plausible date.

**Root cause.** Any lossy model-mediated hop compresses; under compression, models
interpolate. A summarizing model asked to transcribe structured data will sometimes
produce records that *pattern-match* the data instead of records that are *in* the data.
It fails silently — no error, no confidence drop, no formatting tell.

**Fix.** Ejected the submissions data from the trusted path entirely. The cache only
holds values from the XBRL concept endpoints, where each fact could be cross-checked
across multiple fetches (each 10-K restates two prior years, so most values appear
2–3 times — the redundancy is a free consistency check, and it agreed everywhere).
Filing-history claims were demoted to `qualitative` — labeled for human review, never
auto-verified.

**Generalization.** "Model reads data, model writes data" is an architecture smell.
Models belong at the *ends* of a data pipeline (drafting, explaining), never in the
*middle* of it (transport, transformation). If a model must sit in the middle, you need
redundancy to check it against.

---

## 3. The ungrounded draft was wrong in a *structured* way — 8 of 10 quantitative claims failed

**Symptom.** As a baseline, the model drafted the SMCI brief from prior knowledge with no
data access, while still being required to state which fact it was asserting. Grounding
rate: **10%**. But the errors weren't noise; they had a taxonomy:

- **Staleness (worst class):** "cash of ~$1.7B" and "net income ~$1.15B" are FY2024's
  real values asserted as FY2025's. Off by −67% and +10% respectively. A stale number is
  more dangerous than a random one because it *was* true — it survives a smell test.
- **Narrative inflation:** "revenue roughly tripled in FY2024." Actual: +110%. The story
  ("explosive growth") was right; the model rounded the story up, not the number.
- **Plausible-precision misses:** R&D "~$500M" (actual $637M). Sounds specific, isn't.

**Root cause.** Training-data cutoff plus the model's preference for fluent, confident
prose. The model doesn't distinguish "I know this" from "this was true when I last saw it."

**Fix.** The citation gate. Same model, same instructions, drafting *against the cache*
with mandatory source refs: grounding rate went to **87.5%**, and the two failures were
the gate refusing claims it couldn't check (see #4, #5) — not wrong numbers passing.

**Generalization.** Retrieval isn't an accuracy nicety; it flips the failure mode from
"wrong and confident" to "right or refused." For financial workflows only the second is
shippable.

---

## 4. The verifier's derivation language couldn't express a metric the analyst actually wanted

**Symptom.** The grounded draft claimed "DSO improved to ~37 days." The verifier returned
`cannot recompute: unknown op dso`. DSO = AR / revenue × 365 — my derivation spec only
had `yoy_growth | margin | ratio | delta`, all binary ops with no scalar multiply.

**Root cause.** A schema-expressiveness ceiling. The claim schema is a tiny DSL, and any
DSL draws a line: inside it, claims are machine-checkable; outside it, they're not. I hit
the line on day one with one of the most common metrics in credit analysis. (Anything
needing an *average* balance — ROIC, inventory turns done properly — is further outside.)

**Fix (deliberate non-fix for v1).** The gate *strips the claim* rather than trusting it.
That's the right default: the system's promise is "nothing unchecked gets through," not
"everything true gets through." v2 adds a `scale` factor to `ratio` (one line) — but the
interesting decision was choosing which side of the line to fail on.

**Generalization.** Verification coverage is a product decision disguised as a technical
one. Every op added to the DSL widens what the brief can say; every op is also new
surface for verifier bugs — and a wrong verifier is worse than no verifier, because it
launders errors as "verified."

---

## 5. Cache scope silently constrains what the brief can say

**Symptom.** The grounded draft claimed FY2025 FCF of ~$1.1B (OCF minus capex). The gate
rejected it: `PaymentsToAcquirePropertyPlantAndEquipment not in cache`. I'd chosen 9 core
concepts; capex wasn't one of them.

**Root cause.** Scope decisions made at fetch time bind at draft time. The drafting agent
"knew" what FCF was and reached for a concept the pipeline never ingested. Nothing was
wrong — but the brief can only speak from its evidence base, and nobody had written down
what the evidence base *was*.

**Fix.** Made the concept list an explicit, versioned artifact (`CORE_CONCEPTS` in
`edgar.py`) with a comment stating the rule: a concept enters the list only with a
period-alignment rule in the verifier. The drafting prompt now includes the list, so the
agent drafts to the evidence that exists.

**Generalization.** This is the client conversation in miniature: "why doesn't the
report mention X?" — "because X isn't in the approved data yet, and here's the one-line
change plus review that adds it." Being able to answer that precisely is the difference
between a tool a bank can adopt and a demo.

---

## 6. XBRL concept aliasing: "revenue" isn't one tag

**Symptom.** First attempt at pulling revenue used `us-gaap:Revenues`. Sparse/empty for
SMCI's recent years — the actual data lives under
`us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` (post-ASC 606 tag).
Different companies use different tags; some switch tags across years.

**Root cause.** XBRL is a vocabulary, not a schema. GAAP taxonomy offers multiple
concepts for near-identical economics; filers choose. Cross-company comparability —
the whole point of a comps tool — requires a mapping layer that picks the right tag per
company per year, which is exactly the kind of judgment-heavy glue code no one budgets for.

**Fix (v1).** Pinned the correct tag for SMCI and documented the limitation. v2 needs a
resolver: try an ordered list of candidate tags per logical metric, take the one with
recent coverage, and *record which tag was used* in the audit trail — silent tag choice
would undermine the audit.

**Generalization.** "The data is structured" ≠ "the data is uniform." Enterprise data
always has this shape: standardized container, heterogeneous semantics. Budget for the
mapping layer.

---

## 7. Tolerance design decides who gets to round

**Symptom.** Two ungrounded claims sat right at the tolerance boundary: "$14.9B revenue"
(−0.6% off) and "$2.5B cash burn" (+0.6% off) — both MISMATCH at the 0.5% relative
tolerance, both arguably fine as prose rounding. Meanwhile percentage claims needed a
different rule entirely: 0.5% *relative* on an 11.1% margin is 0.06pp — "~11%" would fail.

**Root cause.** One tolerance can't serve two jobs: catching wrong numbers and permitting
human rounding. And relative tolerance is the wrong shape for percentages (error scales
with the metric, not with meaning).

**Fix.** Split the rule: 0.5% relative for dollar figures, 0.4pp absolute for
percentages. Documented both in the report's method note, because an audit rule nobody
can see isn't an audit rule. The boundary cases stay MISMATCH — the draft should say
"$14.99B" if it means $14,989,251,000; precision costs nothing when the number is piped
in rather than remembered.

**Generalization.** Every eval has a tolerance question and it's never technical — it's
"what error can this workflow absorb." A pitch deck absorbs 0.6%; a covenant calc absorbs
zero. The tolerance should be a per-use-case config, not a constant.

---

## 8. The audit harness's v1 flagged its own citations and silently skipped all 94 formulas

**Symptom.** Auditor v1 on the agent-built datapack: 65 VERIFIED, zero MISMATCH, 15
NARRATIVE flags — 11 of which were the workbook's *own source citations* (accession
numbers parsed as "unaudited numeric claims"). Worse: all 94 formula cells produced no
finding at all, which read as a pass.

**Root cause.** Two distinct bugs. (a) Precision failure: the narrative scanner matched
any digit-string; filing IDs and dates aren't claims. (b) Coverage failure: v1 only
verified cells it could map to a *primitive* concept; derived formula cells fell through
every branch. **"No finding" is not "verified" — an audit's silence must be
distinguishable from its approval.**

**Fix.** v2 added a derived-metric recompute table (margins, growth, DSO/DIO, opex
plugs recomputed from cache and compared to the recalculated formula values) and
restricted the narrative scanner to money/percent/bps/multiple patterns, skipping
citation-shaped text. Result: 128/139 cells verified, 3 legitimate narrative flags, 1
real defect found.

**Generalization.** Checkers need checking. An eval that overflags gets ignored; an
eval that underflags launders errors. Both failure modes were present in the same
50-line scanner on day one.

---

## 9. Excel coerced "n/a" into a fake 0.0% — and the audit caught a real workbook defect

**Symptom.** Audit v2's one hard finding: Executive Summary cell B9, "Revenue growth %
FY2021", shows 0.0%. The Historical Financials tab deliberately leaves FY2021 growth
blank (no FY2020 column to compute from) — but the exec summary *links* to that blank
cell, and Excel evaluates a reference to an empty cell as numeric zero. A deliberate
"n/a" became a confident, wrong "0.0% growth" one tab away.

**Root cause.** Semantic loss at a representation boundary: "not applicable" has no
value type in a spreadsheet cell reference. The agent followed the rules (formulas, not
hardcodes; links, not copies) and the rules manufactured the error.

**Fix.** The datapack should carry `="n/a"` or IF-guards on link rows whose source can
legitimately be blank. More importantly, the auditor now knows to try recomputing every
derived cell — this bug was invisible to formula inspection (the formula is "correct")
and to recalc (no error value); only recompute-and-compare caught it.

**Generalization.** Following the style guide perfectly and being right are different
properties. This is the class of error a human reviewer misses too — the cell looks
clean, formats correctly, and is wrong.

---

## 10. Prose is an audit bypass

**Symptom.** Three legitimate residual flags: the exec summary's narrative bullets
assert "46.6%", "$5.2B", "270bps", "~6x" as text inside sentences. Cell-level auditing
never touches them; if the underlying data were restated, the cells would update and the
prose would silently go stale.

**Root cause.** Generated documents mix two representations of the same fact — a
formula-driven cell and a hand-written (or model-written) sentence — with no link
between them.

**Fix (v1: flag, don't fix).** The auditor extracts money/percent claims from prose and
labels them NARRATIVE_UNAUDITED for human review. The real fix is upstream: generate
narrative from the verified cells (templated: "grew {growth_cell} in FY2025"), so prose
inherits verification instead of restating it.

**Generalization.** Every agent-generated deliverable has this seam — tables that are
checkable and narrative that isn't — and IC memos are read for the narrative. Where the
words come from is a bigger trust question than where the numbers come from.

---

## 11. Tag aliasing struck again the moment the evidence base widened

**Symptom.** Adding pre-tax income for the DCF discussion: the standard-looking tag
`IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`
returned a hard 404 for SMCI. The data lives under the *other* long pretax tag
(`...MinorityInterestAndIncomeLossFromEquityMethodInvestments`).

**Root cause.** Same as #6 — XBRL is a vocabulary, not a schema — but now observed on a
second metric, which upgrades it from anecdote to pattern.

**Fix.** Built the resolver the roadmap promised: `LOGICAL_TAGS` in edgar.py maps each
logical metric to an ordered candidate-tag list; the fetcher tries them in order,
requires real annual coverage before a tag "wins," and records the winner per company in
`meta.resolved` so the audit trail shows exactly which tag every number came from.
Unresolvable metrics land in `meta.unresolved_metrics` and the brief generator marks
them as explicit data gaps instead of silently omitting them.

---

## 12. The claim the gate stripped turned out to be WRONG — fail-closed vindicated

**Symptom.** In the first grounded draft, the gate stripped "FY2025 FCF of ~$1.1B"
because capex wasn't in the evidence base (#5). When capex was later added, the pipeline
could finally compute it: OCF $1,659.5M − capex $127.2M = **$1,532M**. The stripped
claim wasn't just unverifiable — it was off by ~28%.

**Root cause.** The $1.1B came from model memory (an implicit capex guess several times
too large). Exactly the failure class from #3, hiding inside an otherwise-grounded draft.

**Fix.** None needed — this is the system working. But it upgraded the argument for
strip-over-flag from principled to empirical: the one claim the gate refused is the one
that was wrong.

**Generalization.** "Unverifiable" and "wrong" are correlated in practice, because both
come from the same place: the model reaching past its evidence.

---

## 13. The auditor hardcoded the demo company's fiscal calendar

**Symptom.** Generalizing the pipeline to any ticker exposed a landmine in the Excel
auditor: it translated a "FY2024" column header to period end 2024-06-30 — June 30
hardcoded, because SMCI's fiscal year ends June 30. Run against a December filer
(most companies) or NVIDIA (late January), it would have looked up the wrong periods
and produced confident false MISMATCHes.

**Root cause.** The classic demo trap: an assumption true of the test company got baked
in as if it were true of the world, and nothing failed while the world was one company.

**Fix.** The cache now carries `fiscal_periods` (FY label → actual period end, derived
from the filing data itself), and the auditor reads the calendar from there. The
fiscal calendar is data, not an assumption.

**Generalization.** A false MISMATCH is the worst failure an audit tool can have — it
erodes the trust the tool exists to create. Generalizing revealed it before a user did;
this is why "works on the demo" and "works" are different claims.

---

## 14. The auditor's first generic run flagged its own blind spot: label mapping and sign conventions

**Symptom.** Making the datapack builder ticker-generic and re-auditing, five capex cells
came back UNSOURCED: "hardcoded -127.2 under unmapped label 'Less: Capex'". Two separate
gaps at once: the label map had no entry for capex, and the sheet presents capex as a
negative ("Less: Capex") while EDGAR files it as a positive outflow — so even with a
mapping, the raw comparison would have failed on sign.

**Root cause.** Financial-statement presentation conventions (contra-signs, "Less:"
rows) are domain knowledge the auditor has to be taught explicitly. The label→concept
map is the judgment layer, and every new row style is a potential silent gap — safely
surfaced here as UNSOURCED (fail-closed), not as a wrong pass.

**Fix.** Added the capex mapping and a sign-flip rule for "Less:"-prefixed labels. Note
the failure direction: the gap produced false ALARMS, not false passes — annoying, but
the safe side of wrong. Verified count went 123→128 with zero code changes to the data.

**Generalization.** Every audit gap showed up as noise, not as silence, because the
default is UNSOURCED. Designing which direction your checker fails in is a choice you
make once, early, and it decides whether coverage gaps are visible or invisible forever.
