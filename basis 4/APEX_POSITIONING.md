# How Mercor's APEX work changes your positioning (and doesn't change your build)

*Read alongside DEFENSE.md. Sources: the APEX-v1-extended paper (arXiv 2509.25721) and
the APEX-Agents IB analyst leaderboard.*

---

## 1. What APEX actually is, in plain terms

Mercor recruited 137 professionals (7+ years average experience — bankers, lawyers,
consultants, doctors) and had them write realistic work tasks with **rubrics**: checklists
of binary pass/fail criteria, which the paper explicitly calls "analogous to unit tests
for code." Example IB criterion: *"calculates Net IRR for LPs as 29.79% (acceptable
range 29.49%–30.09%)."* A single LM judge (Gemini 2.5 Flash) grades each model's answer
against each criterion; scores are the mean share of criteria met over 8 runs.

Two benchmarks matter to you:
- **APEX-v1-extended** (the paper): 100 held-out single-turn cases per job. Headline:
  GPT-5 (High) tops the board at **67.0%** overall — and **investment banking is the
  worst-scoring of all four jobs**: the best model (Gemini 3 Pro) meets only **63.0%**
  of expert criteria, versus 77.9% in law.
- **APEX-Agents** (the leaderboard you linked): 160 multi-step IB tasks (merger model
  edits, sensitivity analyses) written by GS/JPM-caliber bankers. Top agent score:
  **~53%**. Agents fail nearly half of real multi-step banking tasks.

They also **open-sourced** 25 IB cases (apex-v1-devset, on Hugging Face, CC-BY) plus the
grading harness (GitHub).

## 2. The instinct to check — and the answer

Your instinct ("they've already done eval work like this") is exactly right to check and
the answer is good news: **APEX and Basis are not the same thing. They're the two halves
of one problem, and Mercor has published only one half.**

| | APEX | Basis |
|---|---|---|
| Question it answers | *How capable is this model at banking work?* | *Is THIS document right?* |
| When it runs | Offline, on a fixed benchmark, before deployment | At runtime, on every real output, in production |
| Where ground truth comes from | **Experts write it into the rubric** ("IRR is 29.79%") — expensive, scales by hiring | **Machine-derived from structured sources** (EDGAR XBRL) — free, scales by coverage |
| Who grades | An LM judge (Gemini Flash) applying expert criteria | Deterministic code recomputing from source |
| What it can't do | Can't tell you if today's specific memo for a specific client is right | Can't check judgment calls — only claims traceable to structured data |

The one-line version for the interview: **"APEX is the bar exam; Basis is the compliance
check on each memo. A bank deploying agents needs both — the benchmark to pick the
model, the gate to ship its output."**

And the bridge insight — this is the most senior thing you can say Tuesday: *the
expensive part of APEX is expert-authored ground truth. For the subset of claims that
trace to structured filings, ground truth can be generated programmatically — my gate is
effectively a machine-written rubric. The frontier for Mercor Enterprise is knowing
which criteria belong to which side of that line: automate the groundable ones, spend
scarce expert hours only where judgment is genuinely required.*

## 3. Their published numbers are now YOUR opening stat

Use their own results to motivate your project — it shows you read their work and it
makes your premise unarguable:

> "Your APEX papers show IB is the hardest domain you measure — the best frontier model
> meets 63% of expert criteria single-turn, and your agents leaderboard tops out around
> 53% on multi-step banking tasks. That gap is precisely why I built a runtime gate: if
> agents fail a third to a half of expert criteria, the deployment question isn't 'which
> model' — it's 'what catches the failures on the way to the client.'"

## 4. Validations you can cite (your independent findings match their design)

- **Tolerances.** Their criteria carry acceptable ranges (29.49%–30.09% ≈ ±1%). You
  independently hit the same design problem (Failure #7) and went further: split rules
  for dollars vs percentages, and the point that tolerance is per-use-case.
- **Binary criteria / typed claims.** Their rubric criteria are "unit tests for
  responses"; your claim schema is the same idea with the ground-truth half automated.
- **Judge reliability.** They moved from a judge *panel* to a single LM judge for
  transparency and speed. You can speak to the tradeoff from experience: your Failure #2
  (LLM in the data path fabricating a record) and #8 (your own checker over- and
  under-flagging) are the two failure modes any LM-judge pipeline has to manage. Your
  deterministic gate sidesteps judge reliability entirely for numeric claims — which is
  also its limitation for everything else.

## 5. What to change (positioning), what not to change (the build)

**Change the pitch, not the code.** The build is done and correct. Adjust three things:

1. **Open with their numbers** (section 3 above), then your 90-second story.
2. **Rename the framing** of your claim schema when talking to them: "machine-generated
   rubric" / "each claim is a unit-test criterion whose expected value comes from EDGAR
   instead of an expert." Speaking their language costs nothing and lands hard.
3. **Update the Mercor-fit answer** (DEFENSE.md Q10): you're no longer saying "this is
   like what you do" — you're saying "this is the *runtime complement* to what you
   published, and here's the line between machine-groundable and expert-authored
   criteria."

**Optional (only if time after the capex exercise):** pull 2–3 IB cases from
apex-v1-devset on Hugging Face, look at their rubrics, and classify each criterion:
could a deterministic checker verify this (numeric, source-traceable) or does it need
expert/LM judgment? Even done on paper for one task, that classification IS the bridge
insight made concrete — and mentioning "I went through your open-sourced devset" is a
strong signal. Do NOT attempt to run their full harness before Tuesday; it's scope you
don't need.

## 6. One probe question this adds — be ready

**"Why not just use an LM judge like we do?"**
"Your judge works because experts already wrote the expected answer into the criterion —
the judge only has to compare. My gate generates the expected value from the filings, so
for numeric claims I don't need a judge at all, and determinism buys perfect
repeatability and immunity to fluent-but-wrong responses. Where there's no structured
source — judgment calls, qualitative criteria — a judge applying expert rubrics is the
right tool, which is exactly the part of the stack Mercor's expert network supplies. The
interesting engineering question is routing: which criteria go to which grader."
