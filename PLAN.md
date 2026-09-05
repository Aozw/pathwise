# Pathwise — Build Plan

Agentic career readiness system for the IGNITE Agentic AI Hackathon 2026.
Submission: Monday 7 September, end of day. Team of four.

**This file is the source of truth.** If this document and a conversation disagree, this
document wins until someone changes it in a PR.

---

## 0. How to use this document

Every team member works with their own Claude Code account on the same repo.

Before starting any task, paste this into Claude Code:

> Read PLAN.md and CLAUDE.md in the repo root. I am working on <workstream ID>.
> Confirm which files I own and which I must not touch, then start on <task ID>.

Claude Code must never begin work without reading both files first. Four agents working on one
repo without shared rules produces four incompatible codebases and a merge conflict you cannot
resolve on Sunday night.

---

## 1. Ground rules — non-negotiable

These apply to humans and to Claude Code equally.

1. **`main` is always deployable.** If `main` is broken, everything stops until it is fixed.
2. **One branch, one feature.** A branch that does two things gets closed and split. If Claude
   Code proposes an unrelated improvement mid-task, say no and note it for later.
3. **No direct commits to `main`.** Ever. Branch protection enforces this; do not ask for an
   exception.
4. **Every change lands via pull request** with passing CI. You merge your own PR once the
   checks are green; no waiting for anyone.
5. **Never touch files you do not own.** See the ownership map in section 4. If you need a
   change in someone else's area, open a GitHub issue and tag them. Do not edit it yourself, and
   do not let Claude Code edit it "to make the tests pass".
6. **Never commit secrets.** No `.env`, no AWS keys, no tokens. `.gitignore` covers this from
   commit one. If a key ever reaches a commit it must be rotated, not just deleted.
7. **Small PRs.** If a diff is over roughly 400 lines, it should have been two PRs.
8. **Pull before you branch.** `git checkout main && git pull` every single time.

### Branch naming

```
feat/<owner>-<short-description>     new capability
fix/<owner>-<short-description>      bug fix
chore/<owner>-<short-description>    config, deps, docs, CI
```

Examples: `feat/samuel-nusmods-tool`, `fix/stevson-parser-null-grade`, `chore/aaron-ci-pipeline`

### Commit messages

```
<type>: <what changed, imperative mood>

feat: add prerequisite eligibility filter
fix: handle modules with no listed prerequisites
chore: cache NUSMods module list to data/
```

### The loop, every time

```bash
git checkout main
git pull
git checkout -b feat/<owner>-<thing>
# ... work, commit in small steps ...
git push -u origin feat/<owner>-<thing>
gh pr create --fill
# ... read your own diff in the PR view, wait for CI green, then:
gh pr merge --squash --delete-branch
git checkout main && git pull
```

Delete the branch after merge. Stale branches cause people to work from old code.

---

## 2. Repo setup — Alvin, once, before anyone else starts

About twenty minutes, and it blocks everything, so do it first.

### 2.1 Create the repo

```bash
gh repo create pathwise --private --clone
cd pathwise
```

Add Aaron, Samuel and Stevson as collaborators with write access.

### 2.2 Scaffold

Create this structure and commit it directly to `main` as the initial commit. This is the only
direct commit to `main` that will ever happen.

```
pathwise/
├── PLAN.md
├── CLAUDE.md
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── .github/workflows/ci.yml
├── src/
│   ├── config.py           shared constants
│   ├── state.py            shared types — FROZEN after the contract PR
│   ├── graph.py            graph wiring
│   ├── entrypoint.py       @app.entrypoint handler
│   ├── scoring.py
│   ├── agents/
│   │   ├── profile.py
│   │   ├── planner.py
│   │   ├── module.py
│   │   ├── event.py
│   │   └── project.py
│   └── tools/
│       ├── nusmods.py
│       ├── devpost.py
│       ├── github.py
│       └── retrieval.py     semantic shortlist over the module index
├── web/                    static frontend
├── infra/                  deploy scripts, IAM notes
├── data/                   caches, fixtures, run metrics
│   └── index/              precomputed module embeddings (committed)
└── tests/
```

`.gitignore` must include at minimum:

```
.env
.venv/
__pycache__/
data/cache/
data/runs/
data/profiles/
*.pyc
.aws/
```

### 2.3 Branch protection

Your GitHub Education benefits include GitHub Pro, so branch protection works on a private
personal repo. Settings → Branches → Add rule for `main`:

- Require a pull request before merging
- Required approvals: **0**
- Require status checks to pass (add the CI job once it has run once)
- Do not allow force pushes
- Do not allow deletions
- Include administrators — tick this, so the rule applies to you too

GitHub does not let an author approve their own pull request, so "everyone self-approves" is
achieved by setting required approvals to zero. Branch protection still does the work that
matters: nothing reaches `main` except through a PR, and nothing merges unless CI is green.

Because no second person reads the diff before it lands, two things replace the review:

- **Self-review the diff in the GitHub UI before merging.** Not the local diff, the PR view. Read
  it as if someone else wrote it. Four Claude Code agents producing plausible code that nobody
  read is how a repo becomes unexplainable, and the rubric checks whether you can defend your
  design choices out loud.
- **Post a one-line summary in the group chat when you merge.** "Merged W2.2, prerequisite
  parser, `is_eligible` is now available." Thirty seconds, and it stops two people building on
  assumptions about code they have not seen.

### 2.4 CI

`.github/workflows/ci.yml` runs on every PR: install dependencies, `ruff check`, `pytest`.
Nothing else. CI that takes more than two minutes gets ignored.

CI never calls Bedrock or any external API. Tests run against fixtures in `data/fixtures/`.

---

## 3. The contract — what must land before parallel work begins

**This is the most important section in the document.**

Four people cannot build against types that do not exist yet. If everyone starts at once, each
Claude Code agent invents its own `Candidate` shape and nothing merges.

So exactly one PR lands first, from Alvin, before anyone else opens a branch.

**PR #1 — `feat/alvin-state-contract`**

Contains only `src/state.py` and `src/config.py`. No logic, no graph, no tools.

`src/state.py` defines every type that crosses a module boundary:

- `StudentProfile` — parsed transcript and resume output
- `Dimension`, `Gap` — readiness assessment output
- `Candidate` — anything a sub-agent can return, whatever the source
- `ScoreComponents` — gap coverage, role fit, time cost, redundancy penalty, weighted total
- `TraceEvent` — one entry in the decision log, with a `kind` field
- `PendingAction` — an action awaiting approval
- `RunMetrics` — tool calls attempted and succeeded, schema validations passed and failed,
  iterations, tokens
- `RunState` — the graph state, with reducers on `candidates` and `trace`

`src/config.py` holds constants only: model id, region, dimension weights, score weights,
`MAX_REFINE_ITERATIONS = 3`, score threshold, source names. Model ids are read from here and
never constructed inline anywhere in the codebase.

Once PR #1 merges, **`state.py` is frozen.** Changing it later breaks three people's work at
once. If a change is genuinely needed, open an issue, agree it in the group chat, and Alvin makes
it in a dedicated PR that everyone rebases onto immediately.

**Amendment, 5 September, agreed in chat before merging:** `RunState` gained one field,
`ranked: list[Candidate]`, plain last-write-wins (no reducer). `candidates` (`operator.add`)
cannot be rewritten by the scorer without appending duplicate entries every time score runs,
including every refine-loop iteration, so it stays a pure append-only log of everything any
agent ever surfaced. `ranked` is the scored, capped, sorted output the real W1.4 scorer
produces — fully replaced on every scoring pass — and is what the UI and the act node should
read for actual recommendations. Nothing else in the contract changed. See the `RunState`
docstring in `src/state.py` for the full reasoning.

**These two files are the one exception to self-merging.** Since nothing else is gated by a
reviewer, a silent change to `state.py` or `config.py` can break three workstreams before anyone
notices. Announce it in the group chat and get a yes from at least one other person before
merging. This is a social rule, not a GitHub setting, so it only holds if you all honour it.

Alongside PR #1, Alvin commits `data/fixtures/`: one sample transcript, one sample resume, a
sample NUSMods response, a sample Devpost response, a sample GitHub response. They are made up
and that is fine. Everyone builds against them, so nobody is ever blocked waiting for someone
else's component to start working.

---

## 4. Ownership map

Nobody edits outside their row without an issue and the owner's agreement.

| Owner | Workstream | Files owned |
|---|---|---|
| Alvin | W1 — state, graph, orchestrator | `src/state.py`, `src/config.py`, `src/graph.py`, `src/agents/planner.py`, `src/scoring.py` |
| Alvin | W2 — data sources (reassigned) | `src/tools/*`, `data/index/*`, `src/agents/module.py`, `src/agents/event.py`, `src/agents/project.py` |
| Stevson | W3 — profile ingestion and evaluation | `src/agents/profile.py`, `tests/*`, `data/fixtures/*` |
| Aaron | W4 — frontend, entrypoint, deploy | `web/*`, `infra/*`, `src/entrypoint.py`, `.github/workflows/*` |

Samuel is off code for the rest of the build and owns the written deliverables instead. Alvin
absorbs all of W2 on top of W1.

**What this changes in practice.** Alvin now owns most of `src/`, so the do-not-touch rule matters
less for him and more for everyone else: Stevson and Aaron must still stay in their own areas.
W1 and W2 are no longer parallel, they are sequential through one person, so the ordering in
section 5 is now a queue rather than two independent tracks. Assume less gets built, and cut from
the bottom of the W2 list rather than starting everything and finishing nothing.

---

## 5. Workstreams

Tasks are ordered. Do them in order. Each is one branch and one PR.

### W1 — Alvin: state, graph, orchestrator

- **W1.1** State contract and config. See section 3. Blocks everyone, so it is first.
- **W1.2** Graph skeleton. All nodes exist as stubs returning hardcoded values from fixtures.
  Wire the edges, the conditional fan-out, and the refine loop with its counter. Merge this
  early even though nothing is real, because it gives Aaron something to deploy end to end.
- **W1.3** Planner node. One Bedrock call with a structured output schema returning
  `{dispatch, skip, rationale}`. Conditional edges read `dispatch`. Every skip writes a
  `TraceEvent` with its reason. **This node is the project's core claim — build it carefully.**
- **W1.4** Scoring composition in `scoring.py`: time cost lookup, redundancy penalty as set logic
  over evidence already held, weighted sum. Pure functions, no I/O, fully unit tested.
- **W1.5** Refine loop with the hard cap from config, and the approval interrupt before the act
  node.
- **W1.6** S3 state snapshot: read at run start, write at run end.

### W2 — Alvin: data sources

**Reassigned from Samuel, who has no Claude Code capacity this week.** Alvin now owns both the
critical path and every data source, which is more than one person can carry in three days. Two
things follow, and they are not optional.

**W2.1b is cut by default.** Not "cut if behind". Cut. The Module Agent passes eligible candidates
straight to scoring with a fixed cap. Revisit only if Step 15 passes early. Leave the shortlist box
in the diagram only if you build it; if you do not, remove it before submission rather than
presenting architecture you did not ship.

**Samuel is off code entirely** and owns W5, the written deliverables, below. He can still review
diffs, which costs him nothing.

- **W2.0** **Do this before anything else today.** Verify the Devpost hackathon endpoint returns
  data for a search query. If it does not, say so in the group chat within the hour, because it
  changes the architecture and the diagram. Do not build around an endpoint you have not called.
- **W2.1** NUSMods: fetch the module list and module info once, cache to `data/cache/`, commit a
  trimmed subset to `data/fixtures/`. Never fetch this per run; it is large and static.
- **W2.1b** Module embedding index. Embed the ~6000 NUSMods module descriptions once, offline, with
  Titan, and commit the result as a numpy array in `data/index/`. Roughly 24MB, well inside GitHub
  limits, and it loads instantly at cold start. `src/tools/retrieval.py` exposes
  `shortlist(gap_text, eligible_ids, k) -> list[str]` doing cosine similarity by dot product.
  **No FAISS, no Chroma, no vector database, no S3 Vectors.** At six thousand documents brute force
  is sub-millisecond, and every one of those dependencies is a cold-start risk on AgentCore for no
  benefit. Exactly one embedding call at runtime, for the query. This task is standalone and
  produces a committed artifact, so it carries no integration risk; do it while you are still in the
  catalogue code from W2.1.
- **W2.2** Prerequisite parser. NUSMods prerequisite trees are nested and irregular. Write
  `is_eligible(module, completed_modules) -> bool` as a pure function with unit tests. This is
  one of only two places that can produce a real accuracy number for the slides, so it matters
  more than it looks.
- **W2.3** Devpost tool returning small typed `Candidate` objects. Never put raw API JSON into
  state; it fills the context window and you pay for it on every subsequent turn.
- **W2.4** GitHub Search tool, same shape.
- **W2.5** The three sub-agent nodes: call the tool, map to `Candidate`, write a `TraceEvent`. The
  Module Agent additionally calls `shortlist()` after the eligibility filter and before returning,
  so scoring runs on tens of candidates rather than hundreds. This is roughly ten lines inside a
  node you are writing anyway. Record the before and after counts in the trace, because that
  reduction is the token argument on your slide.
  with counts (found, above threshold). Every tool call gets a timeout, one retry, and a fallback
  to the fixture, and the fallback writes a trace entry saying so. That fallback path is the
  demo's handled-failure moment, so it is a feature, not a safety net.

### W5 — Samuel: written deliverables

Runs in parallel with everything and needs no repo access beyond reading it.

- **W5.1** Problem statement in POV format. See Step 17 in `CHECKLIST.md` for the bar it has to
  clear. Start here; it determines what the demo has to prove, so it should not wait for Monday.
- **W5.2** README: what the system does, how to run it, how to deploy it.
- **W5.3** Deck, 10 slides maximum. Leave the testing and evaluation numbers as placeholders until
  Stevson's W3.5 produces them.
- **W5.4** Video script and shot list, so Sunday night's recording is one take rather than five.

### W3 — Stevson: profile ingestion and evaluation

- **W3.1** Transcript parser. Bedrock call with a Pydantic schema producing `StudentProfile`.
  Works entirely against fixtures, so it needs nothing from anyone else. Start here.
- **W3.2** Resume parser producing extracted skills and evidence already held. The evidence list
  feeds the redundancy penalty, so agree its exact shape with Alvin before writing it.
- **W3.3** Readiness assessment: map skills onto the five dimensions, compute weighted scores,
  rank the priority gaps.
- **W3.4** Metrics collection. Wrap tool and model calls to record attempts, successes, schema
  validation outcomes, iterations and token usage into `RunMetrics`, written to
  `data/runs/{run_id}.json` at the end of each run.
- **W3.5** Evaluation set: eight to ten constructed student profiles with known correct answers
  for eligibility. Report prerequisite accuracy, schema validation pass rate, tool-call success
  rate. **This is the testing slide.** The rubric requires testing and evaluation in the deck,
  and this is the only workstream that produces those numbers.

### W4 — Aaron: frontend, entrypoint, deploy

- **W4.1** `src/entrypoint.py` with the `@app.entrypoint` handler, runnable locally, responding
  to `POST localhost:8080` with a stub payload. Merge within the first two hours.
- **W4.2** **Deploy spike, paired with Alvin, today.** See section 6 for the go/no-go.
- **W4.3** Strip `Preview_V3.html` down into `web/`: plain HTML, CSS and JS, Design runtime
  removed, mock state replaced by `fetch` calls. Keep the styling exactly as it is; it is the
  presentation score.
- **W4.4** Wire three real calls: onboard, run, approve. Fix CORS on the first one, not the last.
- **W4.5** Render the decision log from `state.trace` rather than hardcoded entries. The trace
  being the real execution record is the whole point.
- **W4.6** Deploy script in `infra/`: build, push, update, in one command. If redeploying takes
  more than one command, people stop doing it and the deployed version drifts from `main`.

---

## 6. Schedule

### Saturday 5 September

| Time | What |
|---|---|
| Now | Alvin: repo, scaffold, branch protection, CI. Nobody else starts until this is pushed. |
| +30m | Alvin: PR #1, state contract plus fixtures. Everyone reviews it immediately. |
| Morning | Alvin: W2.0, verify Devpost. Stevson: W3.1 against fixtures. Aaron: W4.1 entrypoint. Samuel: W5.1. |
| Midday | **Deploy spike begins.** Aaron and Alvin paired, on one machine, working it together. |
| **18:00** | **Deployment go/no-go. Hard checkpoint.** |
| Evening | W1.2 graph skeleton merged. The deploy question is settled either way. |

**The 18:00 go/no-go.** Nobody on this team has deployed on AWS before, so the risk is real and
the mitigation is a deadline rather than optimism. By 18:00 you need a stub agent reachable from
a browser through the deployed path. If you have it, continue on AgentCore Runtime. If you do
not, switch to the fallback in section 10 and do not spend Sunday debugging IAM.

Spike order, and do not skip ahead:

1. Confirm Bedrock model access for Claude Haiku 4.5 in your chosen region. If Singapore does
   not have what you need, use us-west-2 or us-east-1. Everything downstream depends on this, so
   it is step one.
2. `aws configure` working locally for both of you.
3. Deploy the stub agent. The AgentCore starter toolkit CLI handles the container build, ECR push
   and IAM role creation for you, which is exactly why it is the right path for a team new to
   AWS. Follow the current AWS documentation for the exact commands rather than anything
   remembered or copied from a blog post, because these tools change quickly.
4. Lambda Function URL in front of it, holding the IAM role and forwarding the request.
5. Static page on S3 that calls the Function URL and renders the response. Fix CORS here.
6. Set a billing alarm at 5 USD. Not later. Now.

### Sunday 6 September

Features, all four workstreams in parallel, merging continuously. Redeploy after every
significant merge so `main` and the deployed version never diverge by much.

By late afternoon the setback path must work end to end: log an outcome, planner re-plans,
sub-agents dispatch differently, ranking changes, trace shows the skip. That is the demo. Nothing
else matters as much.

**Record the video Sunday night**, against the deployed URL. Not Monday. If the recording is good
you are finished a day early. If it is not, Monday is the buffer you will need.

### Monday 7 September

Slides, problem statement, README, re-record if needed, submit. Treat Monday as reserve rather
than build time. Something will break, and this is where you absorb it.

---

## 7. Working with Claude Code

`CLAUDE.md` sits beside this file in the repo root. Claude Code reads it automatically at the
start of every session, so the rules apply without anyone remembering to restate them. Commit it
in the initial scaffold and do not let anyone weaken it mid-build.

### Prompting practice

Give Claude Code one task from section 5 at a time, by ID. "Implement W2.2, the prerequisite
parser" works. "Build the module agent" invites it to touch four files across two workstreams.

When it proposes refactoring shared code, decline and open an issue. A refactor that improves the
code and breaks three teammates is a net loss on a three-day build.

Review the diff before committing, and again in the PR view before merging. Since nobody else is
reading it, you are the only check on what reaches `main`. Ask Claude Code to explain any part of
its own diff you cannot follow, and do not merge code you could not defend to a judge.

---

## 8. Definition of done

A PR is ready when all of these are true:

- [ ] Branch contains exactly one feature
- [ ] `ruff check` and `pytest` pass locally, CI green
- [ ] Diff touches only files this workstream owns
- [ ] No secrets, no `.env`, no credentials
- [ ] New logic testable without network access has a test
- [ ] PR description says what changed, how it was tested, what is left
- [ ] You have read the diff in the GitHub PR view, not just locally
- [ ] Merged, and a one-line note posted in the group chat

---

## 9. Cost guardrails

The AWS budget is 20 USD and the account shuts down if it is exceeded. Token spend is the
dominant line; AgentCore Runtime, Lambda and S3 at demo volume are close to nothing.

- Billing alarm at 5 USD, set Saturday.
- Develop against fixtures. Only call Bedrock when testing the model path itself.
- Cache the NUSMods catalogue once. Never fetch it per run.
- No scheduled jobs, no always-on compute, nothing that runs while you sleep.
- Do not use AgentCore Memory or Gateway. Your own S3 object does the same job for free.
- Haiku 4.5 everywhere. Only consider Sonnet for transcript parsing, and try Haiku first.
- Check the billing console before ending Sunday. Do not discover a problem on Monday morning.

---

## 10. Fallbacks

Decide these in advance so nobody is improvising at midnight.

**If AgentCore Runtime does not work by Saturday 18:00.** Package the LangGraph app as a Lambda
container image behind a Function URL. Same frontend, same S3 state, one fewer unfamiliar
service. You will already have built most of the pieces during the spike.

**If deployment fails entirely.** Run locally, record the video locally, and put the deployment
architecture on slide 9 as roadmap. A working local demo scores; a broken deployment does not.

**If Devpost does not work.** Serve hackathons from a committed fixture of real Singapore events,
badged as prototype data in the interface, and relabel the diagram. You lose one live source and
keep two, which is enough to demonstrate the fan-out.

**The module index (W2.1b) is already cut** under the W2 reassignment. The Module Agent passes
eligible candidates straight to scoring, capped at a fixed number by a cheap heuristic. You lose a
token saving and one slide point, nothing structural.

**If Alvin is the bottleneck by Saturday evening, and he will be.** Move W2.3 and W2.4, the Devpost
and GitHub tools, to Stevson. They are self-contained functions against fixtures with no dependency
on W1, which makes them the cleanest thing to hand over. Trade away W3.5, the evaluation set, only
as a last resort, because it is the testing slide and nothing else produces those numbers.

**If you are behind on Saturday night.** Cut the Project Agent. Two sub-agents plus a documented
skip still demonstrates orchestration. Do not cut the planner node to save time; it is the only
thing that makes this project agentic rather than a rules engine with an LLM attached.
