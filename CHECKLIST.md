# Pathwise — Task Workflow and Completion Gates

Read alongside `PLAN.md`. That file explains why. This one tracks where you are.

**How to use the "done when" pointers.** Every one is something another person could verify on
their own machine. "It works on mine" is not a completion signal. If a criterion cannot be
checked by someone else, the step is not finished, it is only claimed.

**Owner note.** Samuel is off code for the rest of the build and owns the written deliverables
(Steps 17 and 18, started early rather than left to Monday). Alvin has absorbed all of W2 on top of
W1, so his steps are a sequential queue, not parallel work.

**Three hard gates.** Steps 3, 9 and 15 block everything downstream. Nothing past them proceeds
until they pass.

---

## Phase 0 — Foundation (Saturday morning, sequential, blocks all work)

### Step 1 — Repo created and scaffolded
**Owner:** Alvin · **Blocks:** everyone

- [ ] `gh repo create pathwise --private --clone` done
- [ ] Full directory tree from PLAN.md 2.2 committed to `main`
- [ ] `.gitignore` in place with `.env`, `.venv/`, `data/cache/`, `data/runs/`
- [ ] Aaron, Samuel and Stevson added as collaborators with write access
- [ ] `PLAN.md`, `CLAUDE.md` and `README.md` committed

**Done when:** all three teammates have run `gh repo clone <you>/pathwise` successfully and can
see `CLAUDE.md` in their local root. Confirm in the group chat, one message each. Not "I sent the
invite" — three confirmations.

---

### Step 2 — Branch protection and CI live
**Owner:** Alvin · **Blocks:** every PR

- [ ] Branch protection rule on `main`: PR required, approvals 0, force pushes off, deletions off,
      include administrators ticked
- [ ] `.github/workflows/ci.yml` runs `ruff check` and `pytest` on pull requests
- [ ] CI has run at least once, so the job appears in the status-checks list
- [ ] Required status check added to the protection rule

**Done when:** you try `git push origin main` directly and GitHub rejects it. Actually attempt
this. A protection rule you have not tested is a protection rule you have not configured.
Also: a PR with a deliberate lint error shows a red check.

---

### Step 3 — HARD GATE: state contract and fixtures merged
**Owner:** Alvin · **Blocks:** W1.2 onward, all of W2, W3, W4

- [ ] `src/state.py` defines `StudentProfile`, `Dimension`, `Gap`, `Candidate`,
      `ScoreComponents`, `TraceEvent`, `PendingAction`, `RunMetrics`, `RunState`
- [ ] `src/config.py` holds model id, region, weights, `MAX_REFINE_ITERATIONS = 3`, threshold
- [ ] `data/fixtures/` contains sample transcript, resume, NUSMods, Devpost, GitHub responses
- [ ] Merged to `main`

**Done when:** each of the other three has pulled `main`, run
`python -c "from src.state import Candidate, RunState; print('ok')"`, and confirmed the types
cover what their workstream needs. **Ask them explicitly before merging, not after.** After this
merges, `state.py` is frozen and changing it costs three people their morning.

---

## Phase 1 — Parallel start (Saturday, after Step 3)

### Step 4 — Devpost endpoint verified
**Owner:** Alvin · **Blocks:** W2.3, the diagram, one slide

- [ ] Actual HTTP call made to the Devpost hackathon endpoint
- [ ] Response inspected, fields identified that map onto `Candidate`
- [ ] Result reported in the group chat within the hour

**Done when:** you can paste real returned JSON into the chat. If it fails, say so immediately
and switch to the fixture fallback in PLAN.md section 10, then tell Alvin so the diagram and
wireframe labels change. Do not spend two hours trying to make a dead endpoint work.

---

### Step 5 — Entrypoint runs locally
**Owner:** Aaron

- [ ] `src/entrypoint.py` with the `@app.entrypoint` handler
- [ ] Returns a stub payload, no real logic

**Done when:** `curl -X POST localhost:8080/invocations -d '{"prompt":"test"}'` returns 200 with
the stub JSON, from a teammate's machine after a fresh clone and `pip install -r requirements.txt`.

---

### Step 6 — Transcript parser working
**Owner:** Stevson

- [ ] Bedrock call with Pydantic schema producing a valid `StudentProfile`
- [ ] Runs against `data/fixtures/`

**Done when:** parsing the fixture transcript returns a `StudentProfile` that validates, with the
right module count and unit total. Run it three times; if the output shape varies between runs,
the schema is not constraining the model and the step is not done.

---

### Step 7 — Graph skeleton merged
**Owner:** Alvin

- [ ] All nodes exist as stubs returning fixture values
- [ ] Edges wired, conditional fan-out present, refine loop with counter
- [ ] Compiles and runs end to end

**Done when:** invoking the graph returns a populated `RunState` with a non-empty `trace`, and
`graph.get_graph().draw_ascii()` shows the structure you intended. Nothing is real yet and that
is fine; the point is Aaron now has something deployable.

---

## Phase 2 — Deployment spike (Saturday midday, Aaron and Alvin paired)

Do these in order. Do not skip ahead when one is slow.

### Step 8 — AWS access confirmed
**Owner:** Aaron + Alvin

- [ ] Bedrock model access for Claude Haiku 4.5 confirmed in your chosen region
- [ ] `aws configure` working for both of you
- [ ] Billing alarm set at 5 USD

**Done when:** a one-line `boto3` Bedrock call returns a completion from both machines. If the
Singapore region lacks what you need, switch to us-west-2 or us-east-1 now and record the choice
in `config.py`. Everything downstream depends on this, so do not proceed on assumption.

---

### Step 9 — HARD GATE: stub agent reachable from a browser (18:00 Saturday)
**Owner:** Aaron + Alvin · **Blocks:** the entire deployment path

- [ ] Stub agent deployed to AgentCore Runtime
- [ ] Lambda Function URL forwarding requests with the IAM role
- [ ] Static page on S3 calling the Function URL
- [ ] CORS resolved

**Done when:** you open the S3 URL in a browser on a phone, on mobile data rather than your own
wifi, click a button, and see the stub response render. No terminal involved.

**If this fails at 18:00, stop and switch.** Go to the Lambda container fallback in PLAN.md
section 10. Do not carry the problem into Sunday. This deadline exists because nobody on the team
has deployed on AWS before and optimism is not a mitigation.

---

## Phase 3 — Features (Saturday evening through Sunday, four in parallel)

### Step 10 — Planner node
**Owner:** Alvin · This is the project's core claim

- [ ] Bedrock call with structured output returning `{dispatch, skip, rationale}`
- [ ] Conditional edges read `dispatch`
- [ ] Every skip writes a `TraceEvent` with its reason

**Done when:** two different student profiles produce two different dispatch sets, and at least
one sub-agent is skipped with a rationale you would be willing to read aloud to a judge. If the
planner dispatches everything every time, you have a fan-out, not a decision, and the step is not
done.

---

### Step 11a — Module embedding index (W2.1b) — CUT
**Owner:** unassigned

**Skip this step.** With W2 reassigned to Alvin there is no capacity for it. The Module Agent
passes eligible candidates straight to scoring with a fixed cap. If Step 15 passes early on Sunday
and Alvin has room, reinstate it; otherwise remove the shortlist box from the architecture diagram
before submission so the deck matches what you built.

The criteria below apply only if it is reinstated.

- [ ] ~6000 NUSMods module descriptions embedded once, offline, by a script in the repo
- [ ] Result committed as a numpy array in `data/index/`
- [ ] `src/tools/retrieval.py` exposes `shortlist(gap_text, eligible_ids, k)`
- [ ] No FAISS, Chroma, pgvector or S3 Vectors anywhere in `requirements.txt`

**Done when:** querying the index with "distributed systems" returns modules a human would agree
are about distributed systems, and querying with a gap the catalogue does not cover returns
nothing convincing rather than confident nonsense. Check ten queries by eye. Separately, confirm
the index loads in under a second from a cold process, since it sits on the AgentCore cold path.

**Cut this first** if W2.0 or W2.2 runs long. It is a token saving and a slide point, not
structure.

---

### Step 11 — Tools returning typed candidates
**Owner:** Alvin (reassigned from Samuel)

**Watch the load here.** Alvin now owns Steps 3, 4, 7, 10, 11, 12 and half of 9. If Step 11 has not
started by Saturday evening, hand W2.3 and W2.4 to Stevson before Sunday rather than after.

- [ ] NUSMods cached to `data/cache/`, trimmed subset in fixtures
- [ ] `is_eligible(module, completed_modules)` as a pure function
- [ ] Devpost and GitHub tools returning `Candidate` objects
- [ ] Each tool has timeout, one retry, fixture fallback writing a trace entry
- [ ] Module Agent caps candidates at a fixed number before returning (shortlist is cut)

**Done when:** `pytest` passes with no network access at all. Disconnect wifi and run it. Each
tool returns small typed objects, never raw JSON. Separately, kill the network mid-run and confirm
the fallback fires and appears in the trace, because that path is in your demo.

Also: the trace records candidate counts before and after the shortlist. Read those two numbers on
a real run. If the shortlist is not cutting hundreds down to tens, it is not earning its place and
the token argument on your slide is not true.

---

### Step 12 — Scoring composition
**Owner:** Alvin

- [ ] Time cost lookup, redundancy penalty as set logic, weighted sum
- [ ] Pure functions, no I/O
- [ ] Unit tested

**Done when:** a candidate covering a gap the student already has evidence for scores measurably
lower than an equivalent candidate covering an open gap. Show the two numbers side by side. The
redundancy penalty is what separates this from a chatbot, so prove it fires.

---

### Step 13 — Profile assessment and metrics
**Owner:** Stevson

- [ ] Resume parser producing skills and evidence held (shape agreed with Alvin)
- [ ] Readiness assessment across five dimensions with ranked gaps
- [ ] `RunMetrics` written to `data/runs/{run_id}.json` each run

**Done when:** one full run leaves a JSON file containing tool calls attempted and succeeded,
schema validations passed and failed, iteration count and token usage. Open the file and read it.
These numbers go on a slide, so they must be real.

---

### Step 14 — Frontend wired to the deployed agent
**Owner:** Aaron

- [ ] `Preview_V3.html` stripped into `web/`, Design runtime removed, styling intact
- [ ] Onboard, run and approve calling the real endpoint
- [ ] Decision log rendered from `state.trace`
- [ ] One-command deploy script in `infra/`

**Done when:** the log panel shows entries that change between two different runs. If the log
looks identical regardless of input, it is still hardcoded. Also: redeploying takes one command,
timed. If it takes five steps, people stop redeploying and the demo drifts from `main`.

---

## Phase 4 — Integration

### Step 15 — HARD GATE: the setback path works end to end (Sunday afternoon)
**Owner:** everyone · **Blocks:** the video, which blocks the submission

- [ ] Log an outcome ("not shortlisted")
- [ ] Planner re-plans and dispatches differently
- [ ] Ranking changes
- [ ] Trace shows the skip with its reason
- [ ] Approval gate holds an action until approved

**Done when:** someone who did not build it runs the full three-act flow on the deployed URL,
start to finish, without you touching the keyboard or explaining what to click. Watch them. Every
place they hesitate is a place a judge will hesitate.

**This is the demo.** If it works, everything else is polish. If it does not, drop features until
it does. Cut the Project Agent before you cut this.

---

## Phase 5 — Deliverables

### Step 16 — Video recorded (Sunday night, not Monday)
**Owner:** Alvin, with the team

- [ ] Recorded against the deployed URL
- [ ] Under 5 minutes
- [ ] Shows all three acts, including a skip and the approval gate

**Done when:** the file is exported and playable, and someone outside the team watches it and can
say what the product does. Sunday night. If it is good you finish a day early; if it is not,
Monday is the buffer you will need.

---

### Step 17 — Problem statement written
**Owner:** Samuel

- [ ] POV format, one person at one moment
- [ ] A cited figure with a date
- [ ] No technology words anywhere in it
- [ ] Justifies why Year 2 rather than final year

**Done when:** it survives being read against slide 8 of the training deck, which uses "students
need help with career planning" as a negative example. If yours could be mistaken for that
sentence, rewrite it.

---

### Step 18 — Deck, README, submission
**Owner:** Samuel, with numbers from Stevson

- [ ] Deck at 10 slides maximum, including the testing and evaluation numbers from Step 13
- [ ] Architecture diagram updated to match what you actually built
- [ ] README explaining how to run it
- [ ] Project files under 5GB, one submission only

**Done when:** submitted, with time left to check the confirmation. Not "uploading now" at the
deadline.

---

## Running checks, all phases

Verify these at each phase boundary, not once at the end:

- [ ] `main` is green and deployable
- [ ] The deployed version matches `main` (redeploy after every significant merge)
- [ ] AWS billing console checked, under 5 USD
- [ ] No `.env` or credentials in any commit
- [ ] Every merged PR touched only its owner's files
