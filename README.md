# TriageGPT

LLM-assisted triage of SAST findings. A Streamlit app that classifies Semgrep
results as true/false positive with structured reasoning, evaluated against
ground-truth labels from OWASP Juice Shop.

**Status:** Week 4 — planning phase. See [project_plan.md](./project_plan.md)
for the full project plan.

## Stack (planned)

- **Scanner:** Semgrep
- **Test corpus:** OWASP Juice Shop
- **App:** Streamlit
- **Models:** Gemini 2.5 Flash (primary), Claude Haiku 4.5 (comparison)

## Roadmap

- [x] Week 4: Project plan
- [ ] Week 6: Working triage tab + initial eval harness
- [ ] Week 8: Full app, model comparison, final evaluation, live demo
