// Pathwise frontend — W4.3 stripped the design-tool runtime out, W4.4 wires it to the
// real backend. One state object + one render() that rebuilds #app's innerHTML from a
// template string; no build step, no framework.
//
// Everything under state.backend is exactly what src/entrypoint.py returned from the
// last onboard/run/approve call — this file does not invent scores, gaps or trace
// entries. The one deliberate exception is the Internships screen: no Internship Agent
// or data source was ever built (W2 only ever covered NUSMods, Devpost and GitHub), so
// it stays the illustrative placeholder it always was, labelled as such.

// Set at upload time by infra's deploy script — not hardcoded in source control. See
// infra/spike_test/index.html, which established this same placeholder convention.
const ENDPOINT = "__ENDPOINT__";

async function sha256Hex(text) {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, "0")).join("");
}

// CloudFront's OAC signs the request to the Lambda Function URL, but Lambda doesn't
// support unsigned payloads for POST — the client supplies this hash itself. No AWS
// credentials involved, just a hash of our own body. See infra/lambda_handler.py.
async function callBackend(action, extra) {
  const body = JSON.stringify({ action, run_id: state.runId, ...extra });
  const bodyHash = await sha256Hex(body);
  let res;
  try {
    res = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "content-type": "application/json", "x-amz-content-sha256": bodyHash },
      body,
    });
  } catch (err) {
    throw new Error(`could not reach the backend: ${err}`);
  }
  let parsed;
  try {
    parsed = JSON.parse(await res.text());
  } catch {
    throw new Error(`backend returned a non-JSON response (HTTP ${res.status})`);
  }
  if (!res.ok || parsed.status === "error") {
    throw new Error(parsed.message || `backend returned HTTP ${res.status}`);
  }
  return parsed;
}

const AUTO_DEFAULT = { addToRoadmap: false };

let state = {
  screen: 'onboarding', step: 1,
  runId: null, backend: null, approvedIds: [],
  loading: false, error: null,
  logOpen: false, logCandidateId: '', logOutcome: 'not_shortlisted',
  sc: {}, settingsOpen: false,
  approvalOpen: false, approvalActionId: null, autoApprove: { ...AUTO_DEFAULT },
};

function setState(patch) {
  const p = typeof patch === 'function' ? patch(state) : patch;
  state = { ...state, ...p };
  render();
}

// — data helpers: everything below reads state.backend, never invents a number —

function pctOf(x) { return Math.round((x || 0) * 100); }

function candidateById(id) {
  return (state.backend?.ranked || []).find(c => c.id === id);
}

function pendingActionFor(candidateId) {
  return (state.backend?.pending || []).find(a => a.candidate_id === candidateId);
}

// A candidate's PendingAction disappears from backend.pending the moment it's
// approved, so "was this already approved" can't be answered from the current
// response alone. Remember every action id this run has ever proposed, keyed by
// candidate id, so a later response (which no longer lists it as pending) can still
// be matched against state.approvedIds.
let actionIdByCandidate = {};
function rememberActionIds(pending) {
  for (const a of pending || []) actionIdByCandidate[a.candidate_id] = a.id;
}

const SOURCE_LABEL = {
  nusmods: 'Module Agent · NUSMods',
  devpost: 'Event Agent · Devpost',
  github: 'Project Agent · GitHub Search',
  fixture: 'Fixture data (live source unavailable)',
};

// — handlers, called from inline onclick/onchange in the rendered markup —

async function startPlan() {
  setState({ loading: true, error: null });
  try {
    const res = await callBackend('onboard', {});
    rememberActionIds(res.pending);
    setState({ loading: false, runId: res.run_id, backend: res, screen: 'dashboard' });
  } catch (err) {
    setState({ loading: false, error: String(err.message || err) });
  }
}

function toggleSc(id) { setState(p => ({ sc: { ...p.sc, [id]: !p.sc[id] } })); }

function ask(actionId) {
  if (state.autoApprove.addToRoadmap) { approve([actionId], true); return; }
  setState({ approvalOpen: true, approvalActionId: actionId });
}
function cancelApproval() { setState({ approvalOpen: false, approvalActionId: null }); }
async function approveOnce() { return approve([state.approvalActionId], false); }
async function approveAuto() {
  setState(p => ({ autoApprove: { ...p.autoApprove, addToRoadmap: true } }));
  return approve([state.approvalActionId], false);
}

async function approve(actionIds, auto) {
  setState({ approvalOpen: false, approvalActionId: null, loading: true, error: null });
  try {
    const res = await callBackend('approve', { approved: actionIds });
    rememberActionIds(res.pending);
    setState(p => ({
      loading: false, backend: res,
      approvedIds: [...p.approvedIds, ...(res.approved || [])],
    }));
  } catch (err) {
    setState({ loading: false, error: String(err.message || err) });
  }
}

function toggleAutoApprove() {
  setState(p => ({ autoApprove: { addToRoadmap: !p.autoApprove.addToRoadmap } }));
}
function openSettings() { setState({ settingsOpen: true }); }
function closeSettings() { setState({ settingsOpen: false }); }

function openLog() {
  const first = (state.backend?.ranked || [])[0];
  setState({ logOpen: true, logCandidateId: first ? first.id : '', logOutcome: 'not_shortlisted' });
}
function closeLog() { setState({ logOpen: false }); }
function setLogCandidate(v) { setState({ logCandidateId: v }); }
function setLogOutcome(v) { setState({ logOutcome: v }); }

async function confirmLog() {
  setState({ logOpen: false, loading: true, error: null });
  try {
    const res = await callBackend('run', {
      outcome: { candidate_id: state.logCandidateId, result: state.logOutcome },
    });
    rememberActionIds(res.pending);
    setState({ loading: false, backend: res });
  } catch (err) {
    setState({ loading: false, error: String(err.message || err) });
  }
}

function goDash() { setState({ screen: 'dashboard' }); }
function goStudy() { setState({ screen: 'study' }); }
function goHack() { setState({ screen: 'hackathons' }); }
function goIntern() { setState({ screen: 'internships' }); }
function goOnboarding() { setState({ screen: 'onboarding', step: 1 }); }
function goStep(n) { setState({ step: n }); }

function resetDemo() {
  actionIdByCandidate = {};
  setState({
    screen: 'onboarding', step: 1, runId: null, backend: null, approvedIds: [],
    loading: false, error: null, logOpen: false, sc: {}, settingsOpen: false,
    approvalOpen: false, approvalActionId: null, autoApprove: { ...AUTO_DEFAULT },
  });
}

// — icons —
function icon(paths, size, extra) {
  return `<svg width="${size || 16}" height="${size || 16}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"${extra ? ` style="${extra}"` : ''}>${paths}</svg>`;
}
const ICON_DASH = '<rect x="3" y="3" width="7" height="9"></rect><rect x="14" y="3" width="7" height="5"></rect><rect x="14" y="12" width="7" height="9"></rect><rect x="3" y="16" width="7" height="5"></rect>';
const ICON_STUDY = '<path d="M12 7v14"></path><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"></path>';
const ICON_HACK = '<path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"></path><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"></path><path d="M4 22h16"></path><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"></path><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"></path><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"></path>';
const ICON_INTERN = '<rect width="20" height="14" x="2" y="6" rx="2"></rect><path d="M16 20V6a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v14"></path><path d="M2 12h20"></path>';
const ICON_GEAR = '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"></path><circle cx="12" cy="12" r="3"></circle>';
const ICON_SPARK = '<path d="m12 3-1.9 5.8a2 2 0 0 1-1.287 1.288L3 12l5.8 1.9a2 2 0 0 1 1.288 1.287L12 21l1.9-5.8a2 2 0 0 1 1.287-1.288L21 12l-5.8-1.9a2 2 0 0 1-1.288-1.287z"></path>';
const ICON_ARROW = '<path d="M5 12h14"></path><path d="m12 5 7 7-7 7"></path>';
const ICON_UPLOAD = '<path d="M12 13v8"></path><path d="m8 17 4-4 4 4"></path><path d="M20.4 14.5A5 5 0 0 0 18 5h-1.3A8 8 0 1 0 4 12.7"></path>';
const ICON_RESUME = '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"></path><path d="M14 2v5h6"></path><path d="M9 13h6"></path><path d="M9 17h4"></path>';
const ICON_INFO = '<circle cx="12" cy="12" r="10"></circle><path d="M12 16v-4"></path><path d="M12 8h.01"></path>';
const ICON_CHECK = '<path d="M21.801 10A10 10 0 1 1 17 3.335"></path><path d="m9 11 3 3L22 4"></path>';

// — shared card fragments —

function decomp(id, v, breakdown) {
  if (!v.sc[id] || !breakdown) return '';
  return `<div class="decomp"><div class="decomp-grid">
    <div><div class="decomp-k">Gap coverage</div><div class="decomp-v">${pctOf(breakdown.gap_coverage)}</div></div>
    <div><div class="decomp-k">Role fit</div><div class="decomp-v">${pctOf(breakdown.role_fit)}</div></div>
    <div><div class="decomp-k">Time cost</div><div class="decomp-v">${pctOf(breakdown.time_cost)}</div></div>
    <div><div class="decomp-k">Redundancy penalty</div><div class="decomp-v">−${pctOf(breakdown.redundancy_penalty)}</div></div>
    </div><p class="decomp-note">${breakdown.rationale || ''}</p></div>`;
}
function whybtn(id) { return `<button type="button" class="whybtn" style="margin-top:8px" onclick="toggleSc('${id}')">Why this score?</button>`; }

function rankedCard(rank, tags, title, meta, body, decompHtml, whyId, action, opacity) {
  return `<div class="card" style="padding:18px 20px${opacity ? ';opacity:.72' : ''}">
    <div style="display:flex;gap:16px;align-items:flex-start">
      <span style="font-family:var(--font-heading);font-size:20px;color:var(--color-neutral-400);line-height:1.1;flex:none">${rank}</span>
      <div style="flex:1;min-width:0">
        <div style="display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin-bottom:6px">${tags}</div>
        <div class="card-title" style="font-size:16px">${title}</div>
        ${meta ? `<div class="card-meta" style="margin:4px 0 0">${meta}</div>` : ''}
        <p class="card-body" style="font-size:13px;margin:6px 0 0">${body}</p>
        ${whybtn(whyId)}
        ${decompHtml}
      </div>
      ${action}
    </div>
  </div>`;
}

// One candidate -> one rankedCard, reused by Dashboard, Hackathons and Study. `rank`
// is the 1-based position in whatever list the caller passed (the full ranked list on
// the dashboard, a kind-filtered subset elsewhere).
function candidateCard(v, candidate, rank) {
  const pct = candidate.score == null ? null : pctOf(candidate.score);
  const closes = candidate.closes_gaps.length
    ? `<span class="tag tag-outline">Closes: ${candidate.closes_gaps.join(', ')}</span>` : '';
  const tags = `${pct == null ? '' : `<span class="tag tag-accent">${pct}% match</span>`}${closes}<span class="tag tag-neutral">${SOURCE_LABEL[candidate.source] || candidate.source}</span>`;
  const meta = [
    candidate.units != null ? `${candidate.units} units` : '',
    candidate.deadline ? `Deadline: ${candidate.deadline}` : '',
    candidate.url ? `<a href="${candidate.url}" target="_blank" rel="noopener">${candidate.url}</a>` : '',
  ].filter(Boolean).join(' · ');
  const pending = pendingActionFor(candidate.id);
  const knownActionId = actionIdByCandidate[candidate.id];
  const alreadyApproved = !!knownActionId && state.approvedIds.includes(knownActionId);
  let action = '';
  if (pending && !alreadyApproved) {
    action = `<button type="button" class="btn btn-secondary" style="flex:none;white-space:nowrap" onclick="ask('${pending.id}')">Add to roadmap</button>`;
  } else if (alreadyApproved) {
    action = `<span class="tag tag-neutral" style="flex:none">Added</span>`;
  }
  return rankedCard(
    rank, tags, candidate.title, meta, candidate.description,
    decomp(candidate.id, v, candidate.score_breakdown), candidate.id, action,
  );
}

function renderOnboarding(v) {
  const step1 = `
    <span style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--color-accent-700)">Step 1 of 3</span>
    <h1 style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:34px;margin:8px 0 10px">Upload your transcript and resume</h1>
    <p style="font-size:15px;max-width:62ch;color:var(--color-neutral-700);margin:0 0 30px">Your documents are parsed into a structured profile — completed modules, units, grades and skills — which becomes the state your agent plans against. Nothing is planned until this profile exists.</p>
    <div class="card" style="padding:16px 18px;margin-bottom:26px">
      <div style="display:flex;gap:10px;align-items:flex-start">
        ${icon(ICON_INFO, 16, 'flex:none;margin-top:2px').replace('stroke="currentColor"', 'stroke="var(--color-neutral-600)"').replace('stroke-width="2"','stroke-width="1.8"')}
        <div>
          <div style="font-size:13px;margin-bottom:3px">This demo plans against one fixture student</div>
          <p style="margin:0;font-size:12.5px;color:var(--color-neutral-700);line-height:1.55">Accepting your own transcript upload needs a change to the frozen state contract that hasn't landed yet, so every run plans against the committed sample transcript and resume (Tan Wei Ling, Y2 Computer Science) rather than a file you drop here. Everything past this screen — the profile, the readiness scores, the ranked plan — is real output from that fixture, produced by the same Bedrock calls a real upload would go through.</p>
        </div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:26px">
      <div class="card" style="padding:26px 22px;border-style:dashed;text-align:center;opacity:.6">
        ${icon(ICON_UPLOAD, 26, 'margin-bottom:10px').replace('stroke="currentColor"', 'stroke="var(--color-accent-700)"').replace('stroke-width="2"','stroke-width="1.6"')}
        <div class="card-title" style="font-size:15.5px;margin-bottom:4px">Academic transcript</div>
        <p class="card-body" style="font-size:12.5px;margin:0 0 12px">transcript.txt (fixture)</p>
      </div>
      <div class="card" style="padding:26px 22px;border-style:dashed;text-align:center;opacity:.6">
        ${icon(ICON_RESUME, 26, 'margin-bottom:10px').replace('stroke="currentColor"', 'stroke="var(--color-accent-700)"').replace('stroke-width="2"','stroke-width="1.6"')}
        <div class="card-title" style="font-size:15.5px;margin-bottom:4px">Resume</div>
        <p class="card-body" style="font-size:12.5px;margin:0 0 12px">resume.txt (fixture)</p>
      </div>
    </div>
    <div style="display:flex;justify-content:flex-end;gap:12px">
      <button type="button" class="btn btn-primary" onclick="goStep(2)">Continue${icon(ICON_ARROW, 14)}</button>
    </div>`;
  const step2 = `
    <span style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--color-accent-700)">Step 2 of 3</span>
    <h1 style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:34px;margin:8px 0 10px">Review what we found</h1>
    <p style="font-size:15px;max-width:62ch;color:var(--color-neutral-700);margin:0 0 30px">Parsed from the fixture transcript and resume named on the previous step — this is the exact profile your agent plans against, not a preview of a real upload.</p>
    <div style="display:grid;grid-template-columns:290px 1fr;gap:20px;margin-bottom:26px">
      <div class="card" style="padding:20px">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><div class="card-kicker">Documents</div><span class="tag tag-neutral" style="font-size:10px">Fixture data</span></div>
        <div style="display:flex;flex-direction:column;gap:12px;margin-top:14px">
          <div style="display:flex;align-items:center;gap:10px">
            ${icon(ICON_CHECK, 17).replace('stroke="currentColor"', 'stroke="var(--color-accent-700)"')}
            <div><div style="font-size:13.5px">transcript.txt (fixture)</div><div style="font-size:11.5px;color:var(--color-neutral-600)">Parsed · 18 modules found</div></div>
          </div>
          <div style="display:flex;align-items:center;gap:10px">
            ${icon(ICON_CHECK, 17).replace('stroke="currentColor"', 'stroke="var(--color-accent-700)"')}
            <div><div style="font-size:13.5px">resume.txt (fixture)</div><div style="font-size:11.5px;color:var(--color-neutral-600)">Parsed · 12 skills extracted</div></div>
          </div>
        </div>
        <div class="hr" style="margin:18px 0"></div>
        <button type="button" class="btn btn-ghost btn-block" style="font-size:12.5px" onclick="goStep(1)">Upload another file</button>
        <p style="margin:12px 0 0;font-size:11px;color:var(--color-neutral-600);line-height:1.5">Module codes are validated against the NUSMods catalogue on parse.</p>
      </div>
      <div class="card" style="padding:24px">
        <div class="card-kicker">Auto-filled profile</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px">
          <div class="field"><label>Full name</label><input class="input" value="Tan Wei Ling" disabled></div>
          <div class="field"><label>Year</label><input class="input" value="Year 2" disabled></div>
          <div class="field"><label>Major</label><input class="input" value="Computer Science" disabled></div>
          <div class="field"><label>Units completed</label><input class="input" value="72 / 160" disabled></div>
        </div>
        <div style="margin-top:18px">
          <label style="font-size:12.5px;color:var(--color-neutral-700);display:block;margin-bottom:8px">Completed modules (18)</label>
          <div style="display:flex;flex-wrap:wrap;gap:6px">
            <span class="tag tag-outline">CS1101S</span><span class="tag tag-outline">CS1231S</span><span class="tag tag-outline">MA1521</span><span class="tag tag-outline">GEA1000</span><span class="tag tag-outline">CS2030S</span><span class="tag tag-outline">CS2040S</span><span class="tag tag-neutral">+12 more</span>
          </div>
        </div>
        <div style="margin-top:18px">
          <label style="font-size:12.5px;color:var(--color-neutral-700);display:block;margin-bottom:8px">Skills extracted from resume</label>
          <div style="display:flex;flex-wrap:wrap;gap:6px">
            <span class="tag tag-accent">Java</span><span class="tag tag-accent">Python</span><span class="tag tag-accent">JavaScript</span><span class="tag tag-accent">SQL</span><span class="tag tag-accent">Flask</span><span class="tag tag-accent">Spring Boot</span><span class="tag tag-accent">React</span><span class="tag tag-accent">Flutter</span><span class="tag tag-accent">Git</span><span class="tag tag-accent">Docker</span><span class="tag tag-accent">pytest</span><span class="tag tag-accent">Postman</span>
          </div>
        </div>
      </div>
    </div>
    <div style="display:flex;justify-content:flex-end;gap:12px">
      <button type="button" class="btn btn-ghost" onclick="goStep(1)">Back</button>
      <button type="button" class="btn btn-primary" onclick="goStep(3)">Looks right${icon(ICON_ARROW, 14)}</button>
    </div>`;
  const step3 = `
    <span style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--color-accent-700)">Step 3 of 3</span>
    <h1 style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:34px;margin:8px 0 10px">Build your plan</h1>
    <p style="font-size:15px;max-width:62ch;color:var(--color-neutral-700);margin:0 0 30px">This calls the deployed agent for real: it parses the fixture profile, assesses readiness across five dimensions, dispatches the Module/Event/Project agents, scores every candidate against your priority gaps, and pauses for your approval before anything is added to your roadmap.</p>
    ${v.error ? `<div class="card" style="padding:14px 16px;margin-bottom:20px;border-color:var(--color-accent-500)"><p style="margin:0;font-size:13px;color:var(--color-accent-700)">${v.error}</p></div>` : ''}
    <div style="display:flex;justify-content:flex-end;gap:12px">
      <button type="button" class="btn btn-ghost" onclick="goStep(2)">Back</button>
      <button type="button" class="btn btn-primary" ${v.loading ? 'disabled' : ''} onclick="startPlan()">${v.loading ? 'Running the agent…' : 'Build my plan'}${v.loading ? '' : icon(ICON_ARROW, 14)}</button>
    </div>`;
  return `<div style="width:100%;height:100%;overflow:auto">
    <div style="max-width:920px;margin:0 auto;padding:56px 32px 80px">
      <div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:30px">
        <div style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:22px;letter-spacing:.02em">Pathwise</div>
      </div>
      <div style="display:flex;gap:22px;align-items:center;margin-bottom:26px;flex-wrap:wrap">
        <button type="button" class="stepdot" onclick="goStep(1)" style="color:${v.step1Color}"><span style="width:20px;height:20px;border-radius:50%;border:1px solid ${v.step1Color};display:inline-flex;align-items:center;justify-content:center;font-size:11px">1</span>Documents</button>
        <span style="width:26px;height:1px;background:var(--color-divider)"></span>
        <button type="button" class="stepdot" onclick="goStep(2)" style="color:${v.step2Color}"><span style="width:20px;height:20px;border-radius:50%;border:1px solid ${v.step2Color};display:inline-flex;align-items:center;justify-content:center;font-size:11px">2</span>Review</button>
        <span style="width:26px;height:1px;background:var(--color-divider)"></span>
        <button type="button" class="stepdot" onclick="goStep(3)" style="color:${v.step3Color}"><span style="width:20px;height:20px;border-radius:50%;border:1px solid ${v.step3Color};display:inline-flex;align-items:center;justify-content:center;font-size:11px">3</span>Build plan</button>
      </div>
      <div>${v.isStep1 ? step1 : v.isStep2 ? step2 : step3}</div>
    </div>
  </div>`;
}

function navItem(label, screenKey, iconPaths, current, goFn) {
  const active = current === screenKey;
  return `<div class="navitem" ${active ? '' : `onclick="${goFn}()"`} style="${active ? 'background:var(--color-accent-100);color:var(--color-accent-700)' : 'color:var(--color-text)'}">${icon(iconPaths)}${label}</div>`;
}

function renderSidebar(v) {
  const profile = v.profile;
  const initials = profile ? profile.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase() : '?';
  return `<div style="width:216px;flex:none;border-right:1px solid var(--color-divider);display:flex;flex-direction:column;padding:22px 14px;box-sizing:border-box">
    <div style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:20px;letter-spacing:.02em;padding:0 8px;margin-bottom:26px">Pathwise</div>
    ${navItem('Dashboard', 'dashboard', ICON_DASH, state.screen, 'goDash')}
    ${navItem('Study Plan', 'study', ICON_STUDY, state.screen, 'goStudy')}
    ${navItem('Hackathons', 'hackathons', ICON_HACK, state.screen, 'goHack')}
    ${navItem('Internships', 'internships', ICON_INTERN, state.screen, 'goIntern')}
    <div style="flex:1"></div>
    <div class="hr" style="margin:12px 0"></div>
    <div class="navitem" onclick="goOnboarding()" style="color:var(--color-neutral-600);font-size:12.5px">↺ New run</div>
    <div style="display:flex;align-items:center;gap:10px;padding:12px 8px 4px">
      <div style="width:30px;height:30px;border-radius:50%;border:1px solid var(--color-divider);display:flex;align-items:center;justify-content:center;font-family:var(--font-heading);font-size:14px;color:var(--color-accent-700)">${initials}</div>
      <div style="flex:1;min-width:0"><div style="font-size:12.5px">${profile ? profile.name : 'Unknown'}</div><div style="font-size:11px;color:var(--color-neutral-600)">${profile ? `Y${profile.year} · ${profile.major}` : ''}</div></div>
      <button type="button" class="btn btn-ghost btn-icon" aria-label="Automation settings" style="flex:none;padding:6px" onclick="openSettings()">${icon(ICON_GEAR, 15, undefined).replace('stroke-width="2"','stroke-width="1.8"')}</button>
    </div>
  </div>`;
}

function renderDashboard(v) {
  const b = v.backend;
  const logPanel = state.logOpen ? `<div class="card elev-sm" style="padding:20px;margin-bottom:20px">
    <div class="card-kicker">Log an outcome</div>
    <p class="card-body" style="font-size:12.5px;margin:6px 0 16px">Recording a result adds an Outcome to your profile state. The agent's refine loop re-plans from it, up to its hard iteration cap.</p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div class="field"><label>Item</label>
        <select class="input" onchange="setLogCandidate(this.value)">
          ${(b.ranked || []).map(c => `<option value="${c.id}" ${c.id === state.logCandidateId ? 'selected' : ''}>${c.title}</option>`).join('')}
        </select>
      </div>
      <div class="field"><label>Outcome</label>
        <select class="input" onchange="setLogOutcome(this.value)">
          ${[['accepted','Accepted'],['not_shortlisted','Not shortlisted'],['withdrew','Withdrew']].map(([val,label]) => `<option value="${val}" ${val === state.logOutcome ? 'selected' : ''}>${label}</option>`).join('')}
        </select>
      </div>
    </div>
    <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:18px">
      <button type="button" class="btn btn-ghost" onclick="closeLog()">Cancel</button>
      <button type="button" class="btn btn-primary" onclick="confirmLog()">Record outcome</button>
    </div>
  </div>` : '';

  const pendingCard = v.hasPending ? `<div class="card elev-sm" style="padding:18px 20px;margin-bottom:20px">
    <div style="display:flex;align-items:center;gap:9px;margin-bottom:4px">
      <span class="kindtag" style="background:var(--color-accent-100);color:var(--color-accent-700)">Pending approval</span>
      <span style="font-size:11.5px;color:var(--color-neutral-600)">· ${v.pending.length} items</span>
    </div>
    ${v.pending.map(a => `<div style="display:flex;align-items:center;gap:16px;justify-content:space-between;padding:11px 0;border-bottom:1px solid var(--color-divider)">
      <div style="min-width:0"><div style="font-size:13.5px">${a.label}</div></div>
      <div style="display:flex;gap:8px;flex:none">
        <button type="button" class="btn btn-secondary" style="font-size:12px;padding:5px 13px" onclick="ask('${a.id}')">Approve</button>
      </div>
    </div>`).join('')}
    <p style="margin:12px 0 0;font-size:11.5px;color:var(--color-neutral-600);line-height:1.55">The agent proposed these after ranking and is waiting. Nothing is added to your roadmap until you approve.</p>
  </div>` : '';

  const readinessDims = (b.readiness?.dimensions || []);
  const readinessPct = Math.round(readinessDims.reduce((sum, d) => sum + d.score * d.weight, 0) * 100);
  const readinessSum = readinessDims.map(d => `${pctOf(d.score)}×${Math.round(d.weight * 100)}`).join(' + ');
  const gaps = b.readiness?.gaps || [];
  const gapTagFor = i => i === 0 ? 'tag-accent' : i === 1 ? 'tag-outline' : 'tag-neutral';
  const gapLabelFor = i => i === 0 ? 'Critical' : i === 1 ? 'High' : 'Medium';

  const ranked = b.ranked || [];

  return `<div style="max-width:1080px;margin:0 auto;padding:44px 40px 60px">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:26px;flex-wrap:wrap">
      <div style="min-width:0">
        <h1 style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:30px;margin:0 0 6px">Welcome back, ${v.profile ? v.profile.name.split(' ')[0] : ''}</h1>
        <p style="font-size:14px;color:var(--color-neutral-700);margin:0">Goal: <strong style="font-weight:600">${v.profile ? v.profile.target_role.replace(/_/g, ' ') : ''}</strong></p>
      </div>
      <button type="button" class="btn btn-secondary" style="flex:none;white-space:nowrap" onclick="openLog()">${icon('<path d="M12 5v14"></path><path d="M5 12h14"></path>', 14)}Log an outcome</button>
    </div>
    ${v.error ? `<div class="card" style="padding:14px 16px;margin-bottom:20px;border-color:var(--color-accent-500)"><p style="margin:0;font-size:13px;color:var(--color-accent-700)">${v.error}</p></div>` : ''}
    ${logPanel}
    ${pendingCard}
    <div class="card" style="padding:22px;margin-bottom:18px">
      <div class="card-kicker">Career readiness</div>
      <div style="display:flex;align-items:baseline;gap:10px;margin:6px 0 14px">
        <span style="font-family:var(--font-heading);font-weight:400;font-size:44px;font-variant-numeric:tabular-nums">${readinessPct}%</span>
        <span style="font-size:12.5px;color:var(--color-neutral-600)">weighted sum of the five dimensions below, against your target role</span>
      </div>
      <div style="height:6px;border-radius:3px;background:var(--color-neutral-200);overflow:hidden;margin-bottom:20px"><div style="height:100%;background:var(--color-accent-500);width:${readinessPct}%"></div></div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px">
        <div><div style="font-size:11px;color:var(--color-neutral-600);text-transform:uppercase;letter-spacing:.06em">Modules ranked</div><div style="font-size:18px;font-variant-numeric:tabular-nums">${ranked.filter(c => c.kind === 'module').length}</div></div>
        <div><div style="font-size:11px;color:var(--color-neutral-600);text-transform:uppercase;letter-spacing:.06em">Hackathons ranked</div><div style="font-size:18px;font-variant-numeric:tabular-nums">${ranked.filter(c => c.kind === 'hackathon').length}</div></div>
        <div><div style="font-size:11px;color:var(--color-neutral-600);text-transform:uppercase;letter-spacing:.06em">Projects ranked</div><div style="font-size:18px;font-variant-numeric:tabular-nums">${ranked.filter(c => c.kind === 'project').length}</div></div>
      </div>
    </div>
    <div class="card" style="padding:22px;margin-bottom:18px">
      <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:16px">
        <div class="card-kicker">Skill gap analysis</div>
        <span style="font-size:11px;color:var(--color-neutral-600)">From the readiness assessment on this run</span>
      </div>
      <div style="display:grid;grid-template-columns:1.25fr 1fr;gap:28px">
        <div>
          <div class="barrow" style="color:var(--color-neutral-600);font-size:10px;text-transform:uppercase;letter-spacing:.07em;margin-bottom:8px"><span>Dimension</span><span></span><span style="text-align:right">Score</span><span style="text-align:right">Weight</span></div>
          <div style="display:flex;flex-direction:column;gap:11px">
            ${readinessDims.map(d => `<div class="barrow"><span style="text-transform:capitalize">${d.dimension}</span><span class="bartrack"><span style="display:block;height:100%;background:var(--color-accent-500);width:${pctOf(d.score)}%"></span></span><span style="text-align:right;font-variant-numeric:tabular-nums">${pctOf(d.score)}%</span><span style="text-align:right;color:var(--color-neutral-600);font-size:11px">×${Math.round(d.weight * 100)}</span></div>`).join('')}
          </div>
          <p style="margin:14px 0 0;font-size:11.5px;color:var(--color-neutral-600);line-height:1.55">Weights are set by your target role. ${readinessSum}, all over 100, gives ${readinessPct}%.</p>
        </div>
        <div>
          <div style="font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--color-neutral-600);margin-bottom:12px">Priority gaps</div>
          <div style="display:flex;flex-direction:column;gap:12px">
            ${gaps.map((g, i) => `<div style="display:flex;gap:10px;align-items:flex-start"><span style="font-family:var(--font-heading);font-size:15px;color:var(--color-accent-700);line-height:1.3">${g.priority}</span><div><div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap"><span style="font-size:13px">${g.label}</span><span class="tag ${gapTagFor(i)}" style="font-size:10px">${gapLabelFor(i)}</span></div><p style="margin:3px 0 0;font-size:12px;color:var(--color-neutral-700);line-height:1.5">Current ${pctOf(g.current)}% against a target of ${pctOf(g.target)}%.</p></div></div>`).join('') || '<p style="margin:0;font-size:12.5px;color:var(--color-neutral-600)">No gaps below target — every dimension already meets its weighted target.</p>'}
          </div>
        </div>
      </div>
    </div>
    <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:6px">${icon(ICON_SPARK, 16).replace('stroke="currentColor"', 'stroke="var(--color-accent-700)"')}<h2 style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:19px;margin:0">Ranked by your Career Agent</h2></div>
    <p style="font-size:12px;color:var(--color-neutral-600);margin:0 0 16px">Every item traces to a priority gap. Anything that scored below threshold is not listed.</p>
    <div style="display:flex;flex-direction:column;gap:14px">
      ${ranked.length ? ranked.map((c, i) => candidateCard(v, c, i + 1)).join('') : '<p style="font-size:13px;color:var(--color-neutral-600)">No candidates scored above the ranking threshold on this run.</p>'}
    </div>
    <div style="margin-top:36px;padding-top:14px;border-top:1px solid var(--color-divider);display:flex;justify-content:space-between;align-items:center;gap:12px">
      <span style="font-size:11px;color:var(--color-neutral-600)">Sources: NUSMods API · Devpost API · GitHub Search API, or their fixture fallback when a live call fails.</span>
      <a onclick="resetDemo()" style="font-size:11px;color:var(--color-neutral-600);cursor:pointer">Start a new run</a>
    </div>
  </div>`;
}

function candidateScreen(v, kind, title, subtitle) {
  const items = (v.backend.ranked || []).filter(c => c.kind === kind);
  return `<div style="max-width:1080px;margin:0 auto;padding:44px 40px 80px">
    <h1 style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:28px;margin:0 0 6px">${title}</h1>
    <p style="font-size:13.5px;color:var(--color-neutral-600);margin:0 0 24px">${subtitle}</p>
    ${v.error ? `<div class="card" style="padding:14px 16px;margin-bottom:20px;border-color:var(--color-accent-500)"><p style="margin:0;font-size:13px;color:var(--color-accent-700)">${v.error}</p></div>` : ''}
    <div style="display:flex;flex-direction:column;gap:14px">
      ${items.length ? items.map((c, i) => candidateCard(v, c, i + 1)).join('') : `<p style="font-size:13px;color:var(--color-neutral-600)">No ${kind} candidates scored above threshold on this run.</p>`}
    </div>
  </div>`;
}

function renderHackathons(v) {
  return candidateScreen(v, 'hackathon', 'Hackathons', 'Ranked by the gap each event closes, sourced from Devpost with a fixture fallback');
}

function renderStudy(v) {
  const modules = candidateScreen(v, 'module', 'Study Plan', 'Ranked by the gap each module closes, prerequisites checked against the parsed transcript');
  const projects = (v.backend.ranked || []).filter(c => c.kind === 'project');
  return modules.replace('</div>', `
    <div style="display:flex;align-items:baseline;gap:10px;margin:32px 0 6px">${icon(ICON_SPARK, 16).replace('stroke="currentColor"', 'stroke="var(--color-accent-700)"')}<h2 style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:18px;margin:0">Project targets from GitHub Search</h2></div>
    <div style="display:flex;flex-direction:column;gap:14px">
      ${projects.length ? projects.map((c, i) => candidateCard(v, c, i + 1)).join('') : '<p style="font-size:13px;color:var(--color-neutral-600)">No project candidates scored above threshold on this run.</p>'}
    </div>
  </div>`);
}

function renderInternships() {
  // No Internship Agent or data source exists in the backend - W2 only ever built
  // Module (NUSMods), Event (Devpost) and Project (GitHub) agents. This stays
  // illustrative rather than pretending there's a fourth source behind it.
  return `<div style="max-width:1080px;margin:0 auto;padding:44px 40px 80px">
    <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:6px"><h1 style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:28px;margin:0">Internships</h1><span class="tag tag-neutral" style="font-size:10px">Prototype data</span></div>
    <p style="font-size:13.5px;color:var(--color-neutral-600);margin:0 0 24px;max-width:78ch">Illustrative listings only — no Internship Agent or data source is wired up. The Module, Event and Project agents share one scoring path, so a real feed would plug into the same ranking logic without a redesign.</p>
    <table class="table">
      <thead><tr><th>Role</th><th>Company</th><th>Closes</th><th>Deadline</th></tr></thead>
      <tbody>
        <tr><td>Backend Engineering Intern</td><td>Grab</td><td><span class="tag tag-outline" style="font-size:10px">Cloud &amp; deployment</span></td><td class="text-muted">Sep 30</td></tr>
        <tr><td>Infrastructure Intern</td><td>Shopee</td><td><span class="tag tag-outline" style="font-size:10px">Cloud &amp; deployment</span></td><td class="text-muted">Oct 5</td></tr>
        <tr><td>Software Engineer Intern</td><td>DBS Bank</td><td><span class="tag tag-outline" style="font-size:10px">Databases</span></td><td class="text-muted">Oct 12</td></tr>
      </tbody>
    </table>
    <p class="note" style="font-size:12px;color:var(--color-neutral-600);margin-top:14px;max-width:80ch">Internship sourcing is Phase 2.</p>
  </div>`;
}

const TRACE_KIND_STYLE = {
  observed: 'border:1px solid var(--color-divider);color:var(--color-neutral-700)',
  planned: 'border:1px solid var(--color-accent-500);color:var(--color-accent-700)',
  decided: 'border:1px solid var(--color-accent-500);color:var(--color-accent-700)',
  changed: 'background:var(--color-accent-100);color:var(--color-accent-700)',
  action: 'border:1px solid var(--color-accent-500);color:var(--color-accent-700)',
  user: 'border:1px solid var(--color-divider);color:var(--color-neutral-700)',
};

function traceRow(t, i) {
  return `<div style="display:grid;grid-template-columns:15px 1fr;gap:9px">
    <span class="stepno">${i + 1}</span>
    <div>
      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:5px">
        <span class="kindtag" style="${TRACE_KIND_STYLE[t.kind] || TRACE_KIND_STYLE.observed}">${t.kind}</span>
        <span style="font-size:11px;color:var(--color-neutral-600)">${t.agent}</span>
      </div>
      <p style="margin:0;font-size:12.5px;line-height:1.55">${t.message}</p>
      ${t.detail ? `<p class="tracenote" style="margin-top:4px">${t.detail}</p>` : ''}
    </div>
  </div>`;
}

function renderDecisionLog(v) {
  const trace = v.backend ? (v.backend.trace || []) : [];
  return `<div style="width:326px;flex:none;border-left:1px solid var(--color-divider);display:flex;flex-direction:column;box-sizing:border-box">
    <div style="padding:18px 20px 14px;border-bottom:1px solid var(--color-divider)">
      <div style="display:flex;align-items:center;gap:9px;margin-bottom:4px">${icon(ICON_SPARK, 16).replace('stroke="currentColor"', 'stroke="var(--color-accent-700)"')}<div><div style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:15px">Career Agent</div><div style="font-size:11px;color:var(--color-neutral-600)">Decision log — every entry below is state.trace from the real run</div></div></div>
    </div>
    <div style="flex:1;overflow:auto;padding:16px 18px;display:flex;flex-direction:column;gap:16px">
      ${trace.length ? trace.map((t, i) => traceRow(t, i)).join('') : '<p style="font-size:12.5px;color:var(--color-neutral-600)">No run yet.</p>'}
    </div>
  </div>`;
}

function renderApprovalDialog(v) {
  if (!v.approvalOpen) return '';
  const action = (v.backend?.pending || []).find(a => a.id === state.approvalActionId);
  const candidate = action ? candidateById(action.candidate_id) : null;
  const why = candidate && candidate.closes_gaps.length
    ? `Closes: ${candidate.closes_gaps.join(', ')}` : 'Ranked above the scoring threshold for your priority gaps';
  return `<div class="dialog-backdrop">
    <div class="dialog" style="width:min(540px,100%)">
      <div class="dialog-title">Approve this action</div>
      <div style="display:flex;flex-direction:column;gap:11px">
        <div style="display:grid;grid-template-columns:62px 1fr;gap:12px;align-items:baseline"><span style="font-size:10px;letter-spacing:.09em;text-transform:uppercase;color:var(--color-neutral-600)">What</span><span style="font-size:13.5px;line-height:1.5">${action ? action.label : ''}</span></div>
        <div style="display:grid;grid-template-columns:62px 1fr;gap:12px;align-items:baseline"><span style="font-size:10px;letter-spacing:.09em;text-transform:uppercase;color:var(--color-neutral-600)">Where</span><span style="font-size:13px;line-height:1.5;color:var(--color-neutral-700)">Writes to your Pathwise roadmap for this run</span></div>
        <div style="display:grid;grid-template-columns:62px 1fr;gap:12px;align-items:baseline"><span style="font-size:10px;letter-spacing:.09em;text-transform:uppercase;color:var(--color-neutral-600)">Why</span><span style="font-size:13px;line-height:1.5;color:var(--color-accent-700)">${why}</span></div>
      </div>
      <div class="dialog-actions" style="flex-wrap:wrap">
        <button type="button" class="btn btn-ghost" onclick="cancelApproval()">Cancel</button>
        <button type="button" class="btn btn-secondary" onclick="approveOnce()">Approve once</button>
        <button type="button" class="btn btn-primary" onclick="approveAuto()">Approve and auto-approve this type</button>
      </div>
    </div>
  </div>`;
}

function renderSettingsDialog(v) {
  if (!v.settingsOpen) return '';
  const on = v.autoApprove.addToRoadmap;
  return `<div class="dialog-backdrop">
    <div class="dialog" style="width:min(520px,100%)">
      <div class="dialog-title">Automation</div>
      <p class="dialog-body" style="margin:0">Every real action this agent can propose is "add to roadmap" — there is no draft or submit-application capability behind this demo yet.</p>
      <div style="display:flex;flex-direction:column">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:16px;padding:13px 0;border-top:1px solid var(--color-divider)">
          <div><div style="font-size:13.5px">Add to roadmap</div><div style="font-size:11.5px;color:var(--color-neutral-600)">auto-approve</div></div>
          <button type="button" class="swpill" aria-label="Auto-approve add to roadmap" style="background:${on ? 'var(--color-accent-500)' : 'var(--color-neutral-400)'};justify-content:${on ? 'flex-end' : 'flex-start'}" onclick="toggleAutoApprove()"><span style="width:14px;height:14px;border-radius:50%;background:var(--color-surface)"></span></button>
        </div>
      </div>
      <p style="margin:0;font-size:11.5px;color:var(--color-neutral-600);line-height:1.55">Auto-approved actions still appear in your decision log.</p>
      <div class="dialog-actions"><button type="button" class="btn btn-primary" onclick="closeSettings()">Done</button></div>
    </div>
  </div>`;
}

function computeVals() {
  const s = state;
  const b = s.backend || {};
  return {
    isStep1: s.step === 1, isStep2: s.step === 2, isStep3: s.step === 3,
    step1Color: s.step === 1 ? 'var(--color-accent-700)' : 'var(--color-neutral-600)',
    step2Color: s.step === 2 ? 'var(--color-accent-700)' : 'var(--color-neutral-600)',
    step3Color: s.step === 3 ? 'var(--color-accent-700)' : 'var(--color-neutral-600)',
    loading: s.loading, error: s.error,
    backend: b, profile: b.profile || null,
    hasPending: !!b.awaiting_approval && (b.pending || []).some(a => !s.approvedIds.includes(a.id)),
    pending: (b.pending || []).filter(a => !s.approvedIds.includes(a.id)),
    approvalOpen: s.approvalOpen && !!(b.pending || []).find(a => a.id === s.approvalActionId),
    settingsOpen: s.settingsOpen,
    autoApprove: s.autoApprove,
    sc: s.sc,
  };
}

function render() {
  const v = computeVals();
  const root = document.getElementById('app');
  if (state.screen === 'onboarding') {
    root.innerHTML = renderOnboarding(v);
    return;
  }
  const screenBody = state.screen === 'dashboard' ? renderDashboard(v)
    : state.screen === 'hackathons' ? renderHackathons(v)
    : state.screen === 'internships' ? renderInternships(v)
    : renderStudy(v);
  root.innerHTML = `<div style="display:flex;height:100%;width:100%">
    ${renderSidebar(v)}
    <div style="flex:1;overflow:auto">${screenBody}</div>
    ${renderDecisionLog(v)}
    ${renderApprovalDialog(v)}
    ${renderSettingsDialog(v)}
  </div>`;
}

render();
