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
