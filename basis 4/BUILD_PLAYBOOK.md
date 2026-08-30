# Build Basis yourself in Claude Code — the step-by-step playbook

*Keep this open next to your Terminal. Every prompt below is ready to copy-paste. Total
time: ~2–3 hours, and you can stop after any phase. Do this on your personal Mac, never
a UBS device or network.*

**The one rule that makes this work:** you give Claude Code the *spec* — what to build,
what "correct" means, what the rules are. It writes the code. Never paste code at it.
The prompts below are specs, and by typing them you are literally practicing the skill
Mercor is hiring for: translating requirements into something an engineer (here, an AI
one) can build. When something breaks — and something will — that's not a problem,
that's material: tell Claude Code to add it to FAILURES.md.

**Why rebuild from scratch when a finished version exists?** So the story is first-hand.
You have my reference version (`~/Downloads/basis`) if you ever get stuck — but build in
a fresh folder and resist peeking. Your build will fail in *different* places than mine
did, and those failures will be yours to tell.

---

## Phase 0 — Open Claude Code in a fresh folder (5 min)

Open Terminal (Cmd+Space → "terminal" → Enter) and paste these three lines, one at a
time, pressing Enter after each:

```
mkdir -p ~/basis-build
cd ~/basis-build
claude
```

`mkdir` makes an empty folder; `cd` moves you into it; `claude` starts Claude Code.
First time only: pick a theme (arrows + Enter), log in via the browser with your Claude
account, and answer **yes** to "trust this folder."

**What the permission prompts mean:** Claude Code asks before it runs any command or
edits any file. Read what it wants to do, press Enter (or `y`) to allow. Don't turn on
auto-accept tonight — watching each action is the point. If it ever runs away in a
direction you don't like, press **Escape** to interrupt and just tell it, in plain
English, what you want instead.

---

## Phase 1 — The project brief (5 min)

Paste this as your first message. It sets the mission so every later step has context:

```
I'm building a project called Basis. The idea: AI can now draft financial documents
that look perfect but contain wrong numbers. Basis is a "citation gate" — a verifier
that takes an AI-drafted diligence brief on a public company and checks every number
in it against what the company actually filed with the SEC, using EDGAR's free XBRL
API. Verified claims keep a citation; wrong ones get flagged; untraceable ones get
stripped rather than trusted.

Important design rules I want you to follow throughout:
1. The verifier must be plain deterministic Python — no AI does the checking, ever.
2. The AI (you) is only allowed at the drafting edge, never in the data path.
3. When we can't verify something, we fail closed: strip it, don't trust it.
4. Keep everything simple — Python standard library where possible, no frameworks.
5. Maintain a FAILURES.md file: every time something breaks or surprises us, log it
   as symptom → root cause → fix → what it generalizes to. That log is a first-class
   deliverable.

Our test company is Super Micro Computer (SMCI), CIK 1375365 — I know the name from
my banking work, its fiscal year ends June 30 which makes period alignment a real
test, and its 2024 was literally a market trust crisis (delayed 10-K, auditor
resignation), so it fits a "can you trust the numbers" tool.

Don't write any code yet. First: set up the folder structure you'd suggest, create an
empty FAILURES.md with a short header, and explain your plan back to me in plain,
non-technical terms so I can approve it. I've never coded before, so throughout this
project explain what you're doing as we go.
```

Read its plan. If it makes sense, say "go ahead." You're the reviewer now.

## Phase 2 — The fetcher: get the answer key (20 min)

```
Step 1: the data layer. Build a Python script that pulls annual financial data for
SMCI from SEC EDGAR's XBRL companyconcept API (data.sec.gov, free, no key — but it
requires a User-Agent header identifying the requester; use my email).

Pull these 10 concepts: revenue (careful — modern filers use the ASC-606 tag
RevenueFromContractWithCustomerExcludingAssessedTax, not plain Revenues; check which
one actually has data), GrossProfit, OperatingIncomeLoss, NetIncomeLoss, InventoryNet,
NetCashProvidedByUsedInOperatingActivities, CashAndCashEquivalentsAtCarryingValue,
ResearchAndDevelopmentExpense, AccountsReceivableNetCurrent, and
PaymentsToAcquirePropertyPlantAndEquipment (capex).

Keep only values from 10-K filings. The same year appears in multiple filings because
each 10-K restates two prior years — keep the value from the most recently filed one,
since restatements are corrections. Save everything to data/cache/smci.json as
{concept: {period_end_date: value}}, fiscal years 2019 through 2025. Stay well under
SEC's 10 requests/second limit.

Then run it, show me SMCI's revenue by year in a simple table, and tell me what
revenue was in fiscal 2025. I'll sanity-check it against what I know.
```

Sanity check when it shows you the table: FY2025 revenue should be ~$21.97B, FY2024
~$14.99B. If yes, say so — you just verified the answer key like a banker would.

**If the fetch fails** (network hiccup, weird error): perfect. Tell it: *"Log this in
FAILURES.md with the root cause, then work around it."* (For reference: when I built
this in a cloud sandbox, the network *blocked* sec.gov entirely — that's my Failure #1.
Your home network will likely just work, which is itself worth noting: same code,
different environment, different outcome. That contrast is an interview answer.)

## Phase 3 — The claim schema and the verifier (30 min)

```
Now the core: the citation gate. Two parts.

Part A — a claim format. A drafted brief is a JSON file containing claims, and every
quantitative claim must be machine-checkable. Three kinds:
- "fact": a number plus a source reference (which concept, which period). Example:
  revenue of 21972042000 citing the revenue concept at period 2025-06-30.
- "derived": a computed metric plus a recipe for recomputing it: operations
  yoy_growth, margin, ratio, and delta, each naming the concepts and periods to
  compute from, plus the stated value.
- "qualitative": text with no checkable number (e.g. "the auditor resigned") —
  these get labeled for human review, neither verified nor stripped.

Part B — verify.py, plain deterministic Python. For each claim: facts are looked up
in the cache and compared to the filed value; derived claims are recomputed from the
cache and compared. Verdicts: VERIFIED, MISMATCH (cites a source but contradicts
it — the worst kind, because it looks grounded), UNSOURCED (can't be checked — gets
stripped), UNVERIFIABLE (qualitative).

Tolerances — this matters, use exactly these: dollar amounts pass within 0.5%
RELATIVE (so "$22.0B" passes as rounding of 21,972,042,000, but a stale number
fails). Percentages pass within 0.4 percentage points ABSOLUTE (relative tolerance
on a small margin would be absurdly tight — 0.5% of an 11% margin is 0.06pp and
nothing human-written would ever pass). The output should include a "grounding
rate": the share of quantitative claims that came back VERIFIED.

Build it, then create a tiny 3-claim test file with one obviously right claim, one
obviously wrong one, and one citing a concept we never fetched — run it and show me
the verifier catches all three correctly. Explain the output to me line by line.
```

That little 3-claim test is you *testing the checker* — remember this moment; it's your
answer to "how do you know the auditor is right?"

## Phase 4 — The experiment: memory vs data (30 min)

This is the demo's heart. Two drafts, same format, different information.

```
Now the experiment. Create drafts/smci_ungrounded.json: WITHOUT looking at our cache
or doing any lookups — using only what you already believe you know about Super
Micro — write a diligence brief as ~12 claims in our schema covering fiscal 2024 and
2025: revenue, growth, gross margin, net income, cash, inventory, operating cash
flow, R&D, plus one or two qualitative claims about the auditor situation. Attach
the source references the claims INTEND to cite. Be honest — write what you'd
confidently say from memory, don't hedge the numbers.

Then run the verifier on it and show me the grounding rate and every verdict. Then
tell me honestly: which of your confident claims were wrong, and is there a pattern
in HOW they were wrong (stale? inflated? plausible-but-off)? Add the pattern to
FAILURES.md.
```

Then:

```
Now drafts/smci_grounded.json: the same brief, but this time build every claim from
the actual cache values, with correct source references and derived-claim recipes.
Include at least one claim you EXPECT the gate to strip — try days sales outstanding
(AR/revenue × 365) and see whether our four derivation operations can even express
it. Run the verifier, show me both grounding rates side by side, and explain what
the difference proves in one paragraph a non-engineer would understand.
```

Watch what your numbers come out to. Mine were 10% vs 87.5% — yours will differ, and
whatever they are, they're *yours*. If DSO gets stripped: that's the
schema-expressiveness finding (my Failure #4). If it added a `dso` op on its own
initiative and the claim passed: also interesting — ask it what ELSE the DSL still
can't express (average-balance metrics like ROIC), and log that instead.

## Phase 5 — The report (20 min)

```
Build render.py: a single self-contained HTML report (no external files) showing:
a scoreband at the top comparing the two grounding rates; the grounded brief with a
colored verdict badge on every claim (green verified with its citation, red
mismatch, amber stripped, gray human-review); the ungrounded draft below it as the
"before"; a full audit-trail table; and a short methodology note that discloses our
tolerances — an audit rule nobody can see isn't an audit rule. Clean and readable,
like something I'd hand a client. Then open it in my browser so I can see it.
```

Click around it. Ask for tweaks in plain English ("make the badges bigger," "put the
grounding rates in the header"). Iterating on a live artifact by conversation is the
"how I use AI" answer, demonstrated.

## Phase 6 — Close the loop (15 min)

```
Three closing tasks:
1. Review FAILURES.md — make sure every failure we hit tonight is in there with a
   root cause, and add anything you noticed that I didn't.
2. Write a README.md: one paragraph on what Basis is and why trust is the product,
   the two grounding rates, inputs → outputs, tooling, and what I'd build next
   (multi-company tag mapping, average-balance ops, auditing generated Excel).
3. Then quiz me: ask me the five hardest questions an engineer would ask about this
   project in an interview, one at a time, and critique my answers honestly.
```

That quiz is your dress rehearsal. Do it out loud.

---

## If you have a second session in you (optional, Monday)

The reference repo (`~/Downloads/basis`) has a piece you didn't rebuild: the Excel
auditor that checks a workbook generated by Anthropic's investment-banking agent
(`basis/xlsx_audit.py` + `agent_run/`). Copy those into your build and tell Claude
Code: *"I'm adopting this module from an earlier prototype — read it, explain how it
works, run it on the workbook in agent_run, then walk me through the one real defect
it caught in the Executive Summary."* Adopting and understanding someone else's code
is also a real skill — just be straight in the interview about which parts you built
fresh and which you adopted and extended.

## Ground rules for the whole session

- **Stuck or confused → say so to Claude Code in plain English.** "I don't understand
  what just happened, explain it simply" is a completely legitimate prompt.
- **Something broke → celebrate, log it, then fix it.** The failure log is the project.
- **Never paste in code from anywhere.** Specs in, code out.
- **You can't break anything.** Worst case: `rm -rf ~/basis-build` deletes the folder
  and you start over, 2 hours older and wiser. The reference repo still exists.
- **Quit Claude Code** with `/exit` (or Ctrl+C twice). Your work is saved on disk —
  running `claude` again in the same folder picks up where the files left off, and
  `claude --continue` also restores the conversation.
