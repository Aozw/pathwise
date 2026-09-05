# CLAUDE.md

## Project

Pathwise: an agentic career readiness system for NUS students. A LangGraph orchestrator running
on Amazon Bedrock AgentCore Runtime plans which sub-agents to dispatch, gathers candidates from
NUSMods, Devpost and GitHub Search, scores them against the student's ranked skill gaps, and
re-plans when the student logs an outcome such as a rejected hackathon application.

**Read `PLAN.md` before doing anything.** It defines file ownership, the frozen type contract,
the workstreams and the git workflow. If PLAN.md and a conversation disagree, PLAN.md wins.

## Hard rules

Violating any of these breaks someone else's work or the build. If a task appears to require
breaking one, stop and say so rather than working around it.

- **NEVER commit to `main`.** Always create a branch first. Branch protection will reject it
  anyway, so attempting it only wastes time.
- **ONE feature per branch.** If the task grows a second concern mid-way, stop and ask. Do not
  bundle an unrelated fix, cleanup or refactor into the same branch.
- **NEVER edit files outside this workstream's ownership area** (PLAN.md section 4). If a change
  is needed in someone else's file, say which file and why, then stop. Do not edit it to make a
  test pass, and do not create a duplicate to work around it.
- **`src/state.py` and `src/config.py` are frozen** after the contract PR. Do not modify them. If
  a type genuinely does not fit the task, say so and stop; the owner changes it in a dedicated PR.
- **NEVER commit `.env`, credentials, API keys, tokens or AWS config.** If one is already staged,
  stop and flag it.
- **NEVER call Bedrock or any external API from a test.** Tests run in CI without credentials or
  network access. Use the fixtures in `data/fixtures/`.
- **Model ids come from `src/config.py`.** Never write a model id inline, and never construct one
  by string concatenation.
- **Every loop a model can influence needs a hard iteration cap** read from config and held in
  state. The cap ignores the model's own judgement about whether it is finished.
- **Tools return small typed objects, never raw API JSON.** Large payloads fill the context
  window and are re-read on every subsequent turn, which costs money and degrades accuracy.
- **Never embed the module catalogue at runtime.** The index is built offline by a script and
  committed. At most one embedding call per query, for the query text itself.
- **Do not add FAISS, Chroma, pgvector, S3 Vectors or any other vector store dependency.** Brute
  force cosine similarity over six thousand vectors is sub-millisecond and adds no cold-start cost.
  If a task seems to need one, say so and stop.
- **Every external call needs a timeout, one retry, and a fixture fallback** that writes a
  TraceEvent recording that the fallback was used. This is a product feature, not just resilience.

## Architecture facts worth knowing

- The planner node is the only place where a model determines control flow. Everything downstream
  is deterministic on purpose, so that rankings are reproducible and auditable.
- The trace in state is the real execution record and is rendered directly as the user-facing
  decision log. Never write trace entries that describe something the code did not actually do.
- Scoring is split: the model produces gap coverage and role fit only. Time cost, redundancy
  penalty and the weighted sum are computed in Python.
- `RunState.candidates` is an append-only audit log (`operator.add`) of everything any agent
  ever surfaced, across every refine-loop iteration — it never shrinks or gets rewritten.
  Scored, ranked, capped output goes in `RunState.ranked` instead (plain last-write-wins,
  replaced whole on every scoring pass). Read `ranked` for recommendations, `candidates` for
  the full history.
- Eligibility filtering happens before scoring, so no tokens are spent on candidates the student
  cannot take. A semantic shortlist runs immediately after it, ranking the eligible survivors
  against the target gap and keeping the top k, so per-candidate model calls run on tens of options
  rather than hundreds.
- The module embedding index in `data/index/` is precomputed offline and committed. It is a numpy
  array searched by dot product, not a database.

## Style

- Python 3.11+, type hints everywhere, Pydantic for anything crossing a module boundary.
- Pure functions for scoring and eligibility. No I/O inside them, so they stay unit testable.
- Comment why, not what. Judges read this code to assess methodology, so a comment explaining a
  design decision is worth more than one restating the line below it.
- Keep functions short enough to explain out loud in one sentence.

## Git workflow

```bash
git checkout main && git pull
git checkout -b feat/<owner>-<short-description>
# work, commit in small steps
git push -u origin feat/<owner>-<short-description>
gh pr create --fill
# after CI passes and the human has read the diff:
gh pr merge --squash --delete-branch
```

The author merges their own PR once CI is green. There is no reviewer, so never merge on the
human's behalf and never merge without being asked to.

Commit messages: `feat:`, `fix:` or `chore:` followed by what changed, in imperative mood.

## Before finishing a task

1. Run `ruff check` and `pytest` locally and make them pass.
2. Confirm `git diff --stat` touches only files this workstream owns.
3. Confirm no secrets are staged.
4. Write the PR description: what changed, how it was tested, anything left undone.
5. Summarise the diff for the human in plain language before they merge, and call out anything
   you were unsure about. No one else will review this code, so an uncertainty you stay quiet
   about reaches `main`.
