# Session 3 Observations

First end-to-end run of the triage pipeline: Semgrep finding → snippet
extraction → Gemini structured output → Pydantic-validated
`TriageVerdict`. Ran against `results[0]` of `data/semgrep_juiceshop.json`
(the ReDoS finding in `lib/codingChallenges.ts`).

## 1. Verdict on Finding 0 is driven by path bias, not data-flow analysis

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

## 2. Open questions

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

## 3. First prompt-engineering lever to test

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
