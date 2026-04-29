# Observations

Running notes on the LLM-assisted SAST triage pipeline. Each session adds
a new section; older sections stay immutable as a record of what we
believed at each point in time.

## Session 3

First end-to-end run of the triage pipeline: Semgrep finding → snippet
extraction → Gemini structured output → Pydantic-validated
`TriageVerdict`. Ran against `results[0]` of `data/semgrep_juiceshop.json`
(the ReDoS finding in `lib/codingChallenges.ts`).

### 1. Verdict on Finding 0 is driven by path bias, not data-flow analysis

Gemini returned **`true_positive` with confidence 0.9** on the
`detect-non-literal-regexp` finding at
`lib/codingChallenges.ts:76`. The reasoning trace, however, exposes the
basis for that verdict:

> *"Given this code is from 'juice-shop', an intentionally vulnerable
> application, it is highly probable that `challengeKey` is
> user-controlled or can be manipulated."*

The model reached its verdict by recognizing **"juice-shop" in the file
path**, not by tracing where `challengeKey` actually comes from. The
snippet provided (lines 73–79 with `context=3`) does not contain any
definition of `challengeKey` — so strictly speaking, the model had no
code-level basis to assert the variable is user-controlled.

In reality, `challengeKey` appears to be sourced from Juice Shop's
internal challenge metadata — hardcoded identifier strings like
`"scoreBoardChallenge"` defined within the project itself, not user
input. If that holds, this finding should be a **false positive** (or at
minimum `needs_review` given the limited context window). The 0.9
confidence on a verdict derived from repo-name priors rather than
evidence in the snippet is the clearest failure mode surfaced so far.

> **Session 4 update:** this behavior did not reproduce on a re-run of
> the same baseline prompt. See §4.1. The Session 3 observation appears
> to have been a sample from a distribution, not a stable property of
> the prompt.

### 2. Open questions

- **(a) Does this bias generalize?** Is path-based priors influencing
  verdicts across all 26 findings, or is it idiosyncratic to this one?
  Need to run the full batch and inspect reasoning traces for similar
  tells ("given this is juice-shop…", "since this is vulnerable code…",
  etc.).
- **(b) Would anonymizing the path change the verdict?** If we strip or
  replace `juice-shop` in the prompt (e.g. to `project/lib/...`), does
  the verdict flip to `needs_review` or `false_positive`? This would
  isolate the contribution of the path string from the contribution of
  the code itself.
- **(c) How does few-shot prompting affect this?** If we add 2–3
  worked examples in the prompt — one `true_positive`, one
  `false_positive`, one `needs_review` — each showing reasoning grounded
  in visible code only, does that suppress the repo-name heuristic?

### 3. First prompt-engineering lever to test

Before anything fancier, try the simplest intervention: **add an
explicit instruction to base the verdict only on visible code, not on
file paths or project names.** Re-run on this same finding and compare.

Concretely, insert a line like:

> *"Base your verdict strictly on the code visible in the snippet. Do
> not infer exploitability from the file path, project name, or
> repository reputation."*

If the verdict flips to `needs_review` or `false_positive` (or even
stays `true_positive` but with cleaner reasoning that references the
`RegExp` construction pattern rather than the repo name), that's a
signal the bias is steerable via the prompt alone and we don't need to
anonymize paths or rewrite the pipeline. If the verdict stays
`true_positive` with the same reasoning pattern, we need stronger
interventions — path anonymization, few-shot examples, or expanded
snippet context that actually shows where `challengeKey` is defined.

## Session 4

Built the first prompt variant (`no_path_bias`) and ran the A/B
experiment planned in Session 3 §3. The result invalidated the
experimental design, not the hypothesis.

### 1. Path-bias experiment: the bias did not reproduce

Ran `triage_finding(results[0], variant="baseline")` and
`triage_finding(results[0], variant="no_path_bias")` back-to-back on
the same finding:

| Variant        | Verdict        | Confidence | Cited "juice-shop" in reasoning? |
|----------------|----------------|------------|----------------------------------|
| `baseline`     | `needs_review` | 0.9        | No                               |
| `no_path_bias` | `needs_review` | 0.8        | No                               |

Both variants converged on `needs_review`, with reasoning that
correctly identified the core problem: the definition of `challengeKey`
is not visible in the snippet, so exploitability cannot be determined
from the code alone. No mention of "juice-shop" in either trace.

**The Session 3 path-bias verdict did not reproduce on the baseline
prompt.** The earlier `true_positive` with path-based reasoning
happened once; on the next call with identical inputs, the model
produced a rigorous `needs_review`. The behavior we flagged as a
failure mode of the prompt was actually a sample from the model's
output distribution.

### 2. Lesson: single-shot A/B comparisons of LLM prompts are unfalsifiable

LLM output has real run-to-run variance. A single call per variant
cannot distinguish:

- a genuine effect of the prompt change, from
- noise in the sampling process, from
- regression to a different mode of the output distribution.

In this experiment, we happened to compare a noisy-baseline sample
(Session 3's `true_positive`) against a same-or-different-prompt sample
(Session 4's `needs_review`) and attributed the shift to the prompt.
The fair comparison is baseline-sample vs. no_path_bias-sample from the
same session — and when we ran that, both variants gave the same label.

To measure prompt effects, we need **N ≥ 5 trials per variant per
finding**, and we compare distributions (verdict mix, mean confidence,
reasoning-trace properties), not individual verdicts.

### 3. Implication for the project: the eval harness must be statistical

The eval harness must:

- Run every `(finding, variant)` pair **N times** (start with N=5, bump
  if variance warrants).
- Report the **verdict distribution** per pair (e.g. "4/5 `needs_review`,
  1/5 `true_positive`"), not a single verdict.
- **Grep reasoning traces** for bias tells — a small list of substrings
  like `"juice-shop"`, `"intentionally vulnerable"`, `"vulnerable
  application"`, `"known vulnerable"`, `"OWASP"` — and report the
  frequency per variant. If `baseline` mentions "juice-shop" in 3/5
  reasoning traces and `no_path_bias` mentions it in 0/5, that is the
  signal we were trying to detect.
- Track mean + stddev of `confidence` per pair, since variance within a
  variant is itself informative.

Without the multi-trial machinery, any prompt-variant comparison we
publish is unfalsifiable in the sense that a single reviewer could
re-run it once and get either the same answer or the opposite.

### 4. Implication for labeling: the metric changes shape, not purpose

Ground-truth labels on the 26 findings are still meaningful and still
necessary. The comparison metric, however, shifts from a boolean to a
rate:

- **Before (implicit metric):** "Did Gemini match the label?" — a
  single boolean per finding, producing a single accuracy number per
  variant.
- **After:** "For this (finding, variant) pair, what fraction of the N
  trials matched the ground-truth label? And how does that fraction
  differ between variants?"

This naturally produces finer-grained, more statistically honest
reporting:

- Per finding: `baseline` matches ground truth 4/5 times; `no_path_bias`
  matches 5/5.
- Aggregated: `no_path_bias` has a higher mean match-rate across all 26
  findings, with variance narrow enough to suggest the difference is
  real and not sampling noise.

Labels also unlock a second axis of measurement: **disagreement cost**.
A variant that gets 5/5 on easy findings but 0/5 on the hard-but-real
vulnerabilities is worse than one that gets 3/5 on both. We'll want to
stratify match-rate by finding difficulty (or by ground-truth label
class) to surface that kind of trade-off.

## Session 5

Built the human-labeled ground-truth set, added a third prompt variant
(`few_shot`) seeded from those labels, and ran a three-way smoke test on
finding 0.

### 1. Ground-truth label set: 8 of 26 findings, missing the false-positive class

After two labeling sessions, `eval/ground_truth.json` contains 8 labels
with the following distribution:

| Verdict          | Count |
|------------------|-------|
| `true_positive`  | 5     |
| `needs_review`   | 3     |
| `false_positive` | 0     |

**The FP gap is the most important problem with the current label set.**
With zero labeled false positives, we cannot measure whether the
pipeline correctly *rejects* spurious findings — only whether it
correctly accepts real ones. A model that returns `true_positive` on
every input would score perfectly on TP recall and look great in the
aggregate metric, while being useless for triage in practice. The
specificity dimension is invisible until at least one FP lands in the
labeled set.

Future labeling sessions should prioritize finding likely-FP candidates.
Promising places to look: the four `express-check-directory-listing`
firings on `server.ts` (some are on auth-gated routes — possibly safe),
the `express-res-sendfile` family with intact extension allowlists, and
the `unsafe-formatstring` INFO-severity finding. Aim for at least 3–5
labeled FPs before considering the eval set balanced enough to draw
specificity conclusions from.

### 2. Few-shot variant added, with a class imbalance baked in

Added `PROMPT_VARIANTS["few_shot"]` to `src/triage_engine.py`. The
template is the baseline prompt with a `BEGIN EXAMPLES` / `END EXAMPLES`
block inserted between the classification instructions and the finding
data. The block contains three worked examples drawn directly from
`eval/ground_truth.json`:

| Example | Verdict          | Source label                   |
|---------|------------------|--------------------------------|
| 1       | `needs_review`   | finding 15 (open-redirect)     |
| 2       | `true_positive`  | finding 3  (hardcoded JWT key) |
| 3       | `true_positive`  | finding 13 (SQL injection)     |

**No `false_positive` example, because no labeled FP exists.** The
prompt is therefore demonstrating two of the three possible verdict
labels. This may bias the model toward TP-or-needs-review and away from
FP — which would be the wrong inductive bias if the rest of the
unlabeled findings contain real false positives. Once the label set
includes at least one good FP, swap one of the two TP examples for it
to balance the demonstrations.

### 3. Three-variant smoke test on finding 0: same verdict, declining confidence

Ran `triage_finding(results[0], variant=v)` for each `v in
["baseline", "no_path_bias", "few_shot"]`:

| Variant        | Verdict        | Confidence |
|----------------|----------------|------------|
| `baseline`     | `needs_review` | 0.90       |
| `no_path_bias` | `needs_review` | 0.70       |
| `few_shot`     | `needs_review` | 0.65       |

All three converged on the verdict that matches the ground-truth label
(`needs_review`, c=0.50). Confidence dropped monotonically as more
constraints were added to the prompt.

**N=1 per variant — could be noise.** A real signal would require at
least 5 trials per variant and a comparison of confidence
distributions, not point estimates. Filed this as the first hypothesis
the eval harness should test:

> *Do constraint-heavy prompts (no_path_bias, few_shot) produce more
> humble (lower-confidence) verdicts on uncertain cases, even when the
> verdict label itself is unchanged?*

If yes, that's a desirable property — overconfidence on uncertain cases
is one of the failure modes a human triager would specifically want the
prompt to suppress. If no, the confidence drop is just noise and the
extra prompt tokens are buying nothing.

### 4. Path-bias failure mode did not reproduce on any variant

None of the three variants exhibited the Session 3 path-bias verdict
("juice-shop is intentionally vulnerable so this must be a true
positive"). The baseline prompt — without any explicit anti-bias
instruction — correctly identified that `challengeKey`'s definition is
not visible in the snippet and escalated to `needs_review` on its own.

This reinforces the Session 4 lesson directly. The Session 3
"observation" of path bias was a single sample from a distribution that
also produces rigorous reasoning. Any future "the model is biased
toward X" claim, including ones we make confidently from looking at one
or two reasoning traces, needs N≥5 trials and a comparison against the
distribution under a control condition before we should treat it as a
real property of the prompt.

## Session 6

First end-to-end run of the statistical eval harness against the labeled
ground-truth set. The headline numbers told one story; the like-for-like
correction told a different and more interesting one.

### 1. First eval run: 9 labels × 3 variants × 5 trials = 130 attempted, 118 used

Ran `scripts/run_eval.py` which executes
:func:`~src.eval_harness.run_evaluation` against the full label set. Of
135 nominal trials (9 × 3 × 5), 15 were skipped due to few-shot
contamination (3 labels × 5 trials × 1 variant) and 2 errored — both
transient Gemini ``503 UNAVAILABLE`` capacity errors on
``finding_index=5`` (the b2bOrder notevil case) under ``no_path_bias``,
trials 2 and 3. The per-trial try/except caught both, the run completed
cleanly, and 118 trials produced usable verdicts. Full per-trial JSON is
at ``eval/results_20260429-003519.json`` (gitignored;
``eval/results_*.json`` was added to ``.gitignore`` before this run).

The harness handled the failure mode gracefully, which is exactly what
it was designed to do — but a small ``tenacity``-style retry layer on
``ServerError``/503 would recover transient failures without writing
``error`` rows. Worth adding before the next scale-up.

### 2. Original headline: a clean ranking that turned out to be misleading

Aggregated over all succeeded trials:

| Variant        | n_succeeded | Match rate | Avg confidence | Avg latency |
|----------------|-------------|------------|----------------|-------------|
| `baseline`     | 45          | 44.4%      | 0.912          | 8.10s       |
| `no_path_bias` | 43          | 51.2%      | 0.911          | 7.67s       |
| `few_shot`     | 30          | 60.0%      | 0.820          | 8.39s       |

The ranking ``few_shot > no_path_bias > baseline`` matches what any
prompt-engineering practitioner would predict, and the gaps look real
(7–9 points between adjacent variants).

**But the variants were measured on different label subsets.**
``few_shot`` evaluated 6 of 9 labels (3 contaminated by appearing as
worked examples in its own prompt); ``baseline`` and ``no_path_bias``
evaluated all 9. Apples to oranges.

### 3. Like-for-like correction: the "few_shot wins" story collapses

Recomputed match-rate over the 6 non-contaminated labels only
(excluding ``finding_index`` ∈ ``{3, 13, 15}``):

| Variant        | All-labels rate | Non-contaminated rate (n=30 each)¹ |
|----------------|-----------------|------------------------------------|
| `baseline`     | 44.4%           | **46.7%**                          |
| `no_path_bias` | 51.2%           | **60.7%** (n=28²)                  |
| `few_shot`     | 60.0%           | **60.0%**                          |

¹ ``baseline`` and ``few_shot`` succeeded on all 30 non-contaminated
trials; ``no_path_bias`` had 28 of 30 due to the 2 errored 503s above.

² Both errored trials were on a non-contaminated label
(``finding_index=5``), so they fall inside the like-for-like denominator.

The corrected picture:

- ``few_shot`` and ``no_path_bias`` are **statistically tied** at ~60%.
- ``baseline`` lags both by ~14 points — that gap survived the
  correction, so it is not a label-mix artifact. Either constraint
  (worked examples *or* anti-bias instruction) appears to help; both
  appear to help comparably.
- The original 9-point ``few_shot`` advantage was an apples-to-oranges
  artifact of the contamination-skip mechanism.

**The interesting finding is the cost dimension.** ``no_path_bias`` adds
one sentence to the baseline prompt (~30 tokens). ``few_shot`` adds
three full worked examples (~600 tokens). They produce equivalent
match-rate on this label set. Cost-effectiveness analysis decisively
favors ``no_path_bias`` until/unless we see a label class where
``few_shot``'s extra structure earns its keep.

### 4. The confidence-vs-accuracy hypothesis got partial support

The Session 5 §5.3 hypothesis was: *do constraint-heavy prompts produce
more humble (lower-confidence) verdicts on uncertain cases, even when
the verdict label is unchanged?*

What the run actually showed:

- ``few_shot``: confidence 0.820, match-rate 60.0% — **humbler and at
  least as accurate**. Matches the hypothesis cleanly.
- ``no_path_bias``: confidence 0.911 (essentially identical to
  ``baseline``'s 0.912), match-rate 60.7% — **same confidence as
  baseline, but more accurate**. Does not match the "more constraints →
  lower confidence" story.

So the hypothesis was directionally right for one variant and wrong for
the other. Updated reading: **the type of constraint matters**.

- Worked examples (few_shot) demonstrate a *style* of reasoning that
  includes the move "I do not have enough context — escalate to
  ``needs_review``". This propagates through the model as both
  better-calibrated reasoning and lower confidence.
- An explicit instruction (no_path_bias) prunes one specific
  failure mode (path-name priors) without changing the model's
  baseline confidence calibration. It tightens accuracy without
  affecting how sure the model feels.

If this generalizes, the prompt-engineering implication is that
"humility-via-constraint" is not a free side effect of adding any
constraint — it requires demonstrating humility in the prompt, not just
forbidding a specific bias.

### 5. Floor-effect caveat for the writeup

Of the 9 ground-truth labels, 3 are ``needs_review``. A null model that
returns ``needs_review`` on every input would score 3/9 = **33.3%**
match-rate by default — meaning the bottom of our match-rate scale is
not zero. All three variants clear this floor:

- ``baseline``: 46.7% (+13.4 over floor)
- ``no_path_bias``: 60.7% (+27.4 over floor)
- ``few_shot``: 60.0% (+26.7 over floor)

So the variants are doing real work — but the absolute match-rates are
inflated by the share of ``needs_review`` cases in the label set, which
are the easiest verdicts to land. Any reported number should also
include the always-``needs_review`` baseline so readers can see how
much of the headline rate is non-trivial.

A more honest aggregate metric would either be (a) match-rate
stratified by ground-truth verdict class, or (b) match-rate excluding
the trivially-easy class. We can compute either from the existing
trials JSON without re-running.

### 6. Known gaps before any external claim

| Gap | Why it matters | Cheapest fix |
|---|---|---|
| **No labeled FPs (0/9)** | Cannot measure specificity. A "always say true_positive" model would score well on TP recall and look great in the aggregate. | Label 3–5 likely-FP candidates from the unlabeled set (see §5.1 for candidate list). |
| **N=5 trials per pair** | Cannot make statistical claims about variant differences. The ~14-point ``baseline`` gap *looks* real, but we have no significance test. | Run N=10 or N=20 on the most interesting (variant, label) pairs. Cost: linear in N. |
| **Single model (Gemini 2.5-flash only)** | Cannot distinguish "this prompt change helps" from "this prompt change helps Gemini specifically". | Wire up Claude Haiku (or any second model with structured output). The pipeline is model-agnostic above the SDK boundary. |
| **No retry layer on transient errors** | Two 503s cost us 2 of 45 trials in this run. At larger N, retries matter. | Wrap the API call in a tenacity exponential-backoff retry on ``ServerError``/503. |
| **Few-shot examples are 2 TP + 1 needs_review** | The few_shot prompt demonstrates only two of three verdict labels. May implicitly bias toward those classes. | Once a labeled FP exists, swap one TP example for it. |
