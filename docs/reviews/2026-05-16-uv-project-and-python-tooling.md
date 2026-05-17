# Cross-model review — uv-project-and-python-tooling

- **Date:** 2026-05-16
- **Model:** gpt-5.4
- **Target:** uv-project-and-python-tooling

---

## Summary

This change moves the repo from an ad hoc `pip install -r scripts/requirements-harness.txt` setup to a uv-managed Python workspace. It also tightens the closeout pipeline with a required `--prompt`, threads `--slug` into cross-review filenames, and adds a triage gate before approval.

The direction is sensible and mostly consistent with the project principles:

- one install command: `uv sync`
- configuration over code: root `pyproject.toml`, committed `uv.lock`
- better audit trail: prompt number in journal filename, triage gate, explicit ADRs
- onboarding: new `docs/setup/uv-quickstart.md`

I did not find a structural reason to reject the change. The main issues are narrower and fixable.

The most important gaps I see are:

1. **The workspace scaffold is incomplete as committed.**
   `docs/PLAN.md` now claims all listed top-level directories are present, but `api/`, `agents/`, `tools/`, `sdk/`, `frontend/`, and `infra/` are added here while no evidence is shown for how `gitkeep`-only directories behave in the intended workflow. This is not fatal, but it means the “project structure done” claim in `docs/PLAN.md:39-41` is slightly ahead of the actual usable structure.

2. **The closeout pipeline still permits silent slug fallback in the actual script path.**
   In `scripts/close_prompt.py:539`, `slug = args.slug or infer_slug_from_branch(branch_now, default="workflow-harness")`. That means the command doc now strongly recommends `--slug`, but the code still falls back to `"workflow-harness"` if branch inference fails. `docs/DEFERRED.md:42-47` already notes this, but it remains a real audit-trail risk today because the wrong slug affects:
   - cross-review filename
   - journal filename content
   - PR title/body content

3. **The new triage gate is better than before, but its parser contract is still brittle.**
   `scripts/close_prompt.py:343-377` matches any line starting with `"

## Triage

_TODO: human-filled. Disposition each finding above as accept / defer / reject, with reason._
