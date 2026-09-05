// Pathwise frontend — W4.3. Ported by hand from Preview V3.html (a Claude Design canvas
// export) into plain HTML/CSS/JS: no build step, no React, no design-tool runtime.
// One state object + one render() that rebuilds #app's innerHTML from a template string,
// same pattern the original prototype used, just without its `{{binding}}`/`sc-if` layer.

const TOG_IDS = ['buildai','hacknus','fintech','cs3230','cs3223','proj1','proj2','i1','i2','i3','i4','r1','r2','r3','s1','s2','s3','s4'];

const CLOUD = 'Closes your critical gap: Cloud & deployment';
const ACTS = {
  saveBuildai: { t: 'shortlist', what: 'Save BuildAI Hackathon — Backend Track to your shortlist',
    data: 'Uses: your name, major, 6 extracted skills', dest: 'Writes to: your Pathwise shortlist (profile state)',
    why: CLOUD, done: 'Saved BuildAI Hackathon — Backend Track to your shortlist.' },
  draftBuildai: { t: 'draftApp', draft: true, what: 'Draft an application for BuildAI Hackathon — Backend Track',
    data: 'Uses: your name, major, 6 extracted skills, 2 project links', dest: 'Submits to: eventbrite.com registration form',
    why: CLOUD, done: 'Drafted an application for BuildAI Hackathon — Backend Track. Waiting for you to check and submit it.' },
  saveHacknus: { t: 'shortlist', what: 'Save HackNUS Systems Track to your shortlist',
    data: 'Uses: your name, major, 6 extracted skills', dest: 'Writes to: your Pathwise shortlist (profile state)',
    why: 'Closes your third gap: Systems & networks', done: 'Saved HackNUS Systems Track to your shortlist.' },
  draftHacknus: { t: 'draftApp', draft: true, what: 'Draft an application for HackNUS Systems Track',
    data: 'Uses: your name, major, 6 extracted skills, 2 project links', dest: 'Submits to: NUS Computing Club registration form',
    why: 'Closes your third gap: Systems & networks', done: 'Drafted an application for HackNUS Systems Track. Waiting for you to check and submit it.' },
  saveFintech: { t: 'shortlist', what: 'Save Fintech Sprint 2026 to your shortlist',
    data: 'Uses: your name, major, 6 extracted skills', dest: 'Writes to: your Pathwise shortlist (profile state)',
    why: 'Closes no priority gap — saved on your instruction, not on the agent\'s ranking', done: 'Saved Fintech Sprint 2026 to your shortlist.' },
  draftFintech: { t: 'draftApp', draft: true, what: 'Draft an application for Fintech Sprint 2026',
    data: 'Uses: your name, major, 6 extracted skills, 2 project links', dest: 'Submits to: eventbrite.com registration form',
    why: 'Closes no priority gap — the agent ranks this 61%', done: 'Drafted an application for Fintech Sprint 2026. Waiting for you to check and submit it.' },
  addCs3230: { t: 'studyPlan', what: 'Add CS3230 — Design and Analysis of Algorithms to your Y3 study plan',
    data: 'Uses: your parsed transcript, 3 in-progress modules, NUSMods offering data',
    dest: 'Writes to: your Pathwise study plan (nothing is sent to NUS)',
    why: 'Closes your second-tier gap: Data structures & algorithms', done: 'Added CS3230 to your study plan for Y3 Sem 1.' },
  addCs3223: { t: 'studyPlan', what: 'Add CS3223 — Database Systems Implementation to your Y3 study plan',
    data: 'Uses: your parsed transcript, 3 in-progress modules, NUSMods offering data',
    dest: 'Writes to: your Pathwise study plan (nothing is sent to NUS)',
    why: 'Closes your second gap: Databases & data infrastructure', done: 'Added CS3223 to your study plan for Y3 Sem 2.' },
  dismissCodesprint: { t: 'dismiss', what: 'Dismiss the recommendation CodeSprint Open 2026',
    data: 'Uses: your logged outcomes and the redundancy scores of your other items',
    dest: 'Writes to: your recommendation filters (the event stays searchable)',
    why: 'Duplicates evidence two items already in your plan produce', done: 'Dismissed CodeSprint Open 2026. It will not be recommended again unless your evidence changes.' },
  saveShopee: { t: 'shortlist', what: 'Save Infrastructure Intern, Shopee to your shortlist',
    data: 'Uses: your name, major, 6 extracted skills', dest: 'Writes to: your Pathwise shortlist (profile state)',
    why: CLOUD, done: 'Saved Infrastructure Intern, Shopee to your shortlist.' },
  draftIntern: { t: 'draftApp', draft: true, what: 'Draft an application for this internship',
    data: 'Uses: your name, major, 6 extracted skills, 2 project links, 18 completed modules',
    dest: 'Submits to: the employer\'s own application form',
    why: CLOUD, done: 'Drafted an internship application. Waiting for you to check and submit it.' },
};

const SEED_PENDING = [
  { id: 'p1', kind: 'draft', act: 'draftHacknus', title: 'Draft application — HackNUS Systems Track', meta: 'closes Oct 26' },
  { id: 'p2', kind: 'save', act: 'saveShopee', title: 'Save to shortlist — Infrastructure Intern, Shopee', meta: 'Closes: Cloud & deployment' },
];
const AUTO_DEFAULT = { shortlist: true, studyPlan: false, draftApp: false };

let state = {
  screen: 'onboarding', step: 1, setback: false, showReasoning: true,
  logOpen: false, logItem: 'BuildAI Hackathon — Backend Track', logOutcome: 'Not shortlisted',
  filter: 'All', sc: {},
  approvalOpen: false, approvalKey: null, approvalPending: null,
  autoApprove: { ...AUTO_DEFAULT }, pending: SEED_PENDING.slice(),
  settingsOpen: false, traceOpen: false, trace2Open: false,
  done: [], seq: 0, seedUndone: false, refreshed: false,
};

function setState(patch) {
  const p = typeof patch === 'function' ? patch(state) : patch;
  state = { ...state, ...p };
  render();
}

function request(key, pid) {
  const a = ACTS[key];
  if (!a) return;
  if (state.autoApprove[a.t]) { commit(key, true, pid); return; }
  setState({ approvalOpen: true, approvalKey: key, approvalPending: pid || null });
}

function commit(key, auto, pid) {
  const a = ACTS[key];
  setState(p => ({
    approvalOpen: false, approvalKey: null, approvalPending: null,
    pending: pid ? p.pending.filter(x => x.id !== pid) : p.pending,
    seq: p.seq + 1,
    done: [{ id: 'a' + (p.seq + 1), text: a.done, auto: !!auto }, ...p.done],
  }));
  // TODO(W4.4): POST the approved action to the backend's approve endpoint here.
}

function computeVals() {
  const s = state.screen, st = state, back = st.setback;
  const sc = {};
  TOG_IDS.forEach(id => { sc[id] = !!st.sc[id]; });
  const accent = 'var(--color-accent-700)', muted = 'var(--color-neutral-600)';
  const ap = ACTS[st.approvalKey] || {};
  const aa = st.autoApprove;
  const swBg = on => (on ? 'var(--color-accent-500)' : 'var(--color-neutral-400)');
  const swPos = on => (on ? 'flex-end' : 'flex-start');
  const g = back ? [84, 68, 43, 35, 26] : [84, 71, 48, 35, 26];
  const weights = [30, 30, 20, 10, 10];
  const readiness = Math.round(g.reduce((a, v, i) => a + v * weights[i] / 100, 0));
  return {
    isOnboarding: s === 'onboarding', isApp: s !== 'onboarding',
    isDashboard: s === 'dashboard', notDashboard: s !== 'dashboard',
    isStudy: s === 'study', notStudy: s !== 'study',
    isHackathons: s === 'hackathons', notHackathons: s !== 'hackathons',
    isInternships: s === 'internships', notInternships: s !== 'internships',
    isStep1: st.step === 1, isStep2: st.step === 2, isStep3: st.step === 3,
    step1Color: st.step === 1 ? accent : muted,
    step2Color: st.step === 2 ? accent : muted,
    step3Color: st.step === 3 ? accent : muted,
    setback: back, isOnTrack: !back,
    readiness,
    readinessSum: `${g[0]}×30 + ${g[1]}×30 + ${g[2]}×20 + ${g[3]}×10 + ${g[4]}×10, all over 100, gives ${readiness}%.`,
    g1: g[0], g2: g[1], g3: g[2], g4: g[3], g5: g[4],
    hackOutcome: back ? '1 not shortlisted' : '1 pending',
    hacknusPen: back ? '−9' : '−4',
    hacknusPenNote: back
      ? 'Penalty rose from −4 to −9 once a hackathon application was logged as a completed attempt — the second one adds less new evidence.'
      : 'Low penalty while you have no hackathon result on record. It rises once an attempt is logged.',
    showReasoning: st.showReasoning,
    logItem: st.logItem, logOutcome: st.logOutcome,
    filterAll: st.filter === 'All', filterActivity: st.filter === 'Activity', filterConv: st.filter === 'Conversation',
    showActivity: st.filter !== 'Conversation',
    showConv: st.filter !== 'Activity',
    showChanged: back && st.filter !== 'Conversation',
    sc,
    approvalOpen: st.approvalOpen && !!ACTS[st.approvalKey],
    apWhat: ap.what || '', apData: ap.data || '', apDest: ap.dest || '', apWhy: ap.why || '', apDraft: !!ap.draft,
    hasPending: st.pending.length > 0, pendingCount: st.pending.length,
    pendingItems: st.pending.map(it => ({
      id: it.id, act: it.act, title: it.title, meta: it.meta,
      isReview: it.kind === 'draft', isApprove: it.kind !== 'draft',
    })),
    hasActions: st.done.length > 0 && st.filter !== 'Conversation',
    actionRunLabel: back ? 'Run 4' : 'Run 3',
    doneItems: st.done.map((d, i) => ({ id: d.id, text: d.text, step: st.done.length - i, auto: d.auto, manual: !d.auto })),
    settingsOpen: st.settingsOpen,
    sw1bg: swBg(aa.shortlist), sw1pos: swPos(aa.shortlist),
    sw2bg: swBg(aa.studyPlan), sw2pos: swPos(aa.studyPlan),
    sw3bg: swBg(aa.draftApp), sw3pos: swPos(aa.draftApp),
    traceOpen: st.traceOpen, traceLabel: st.traceOpen ? 'Hide trace' : 'Show trace',
    trace2Open: st.trace2Open, trace2Label: st.trace2Open ? 'Hide trace' : 'Show trace',
    seedLive: !st.seedUndone && st.filter !== 'Conversation',
    seedUndone: st.seedUndone && st.filter !== 'Conversation',
    refreshed: st.refreshed,
  };
}

// — handlers, called from inline onclick/onchange in the rendered markup —
function toggleSc(id) { setState(p => ({ sc: { ...p.sc, [id]: !p.sc[id] } })); }
function ask(key) { request(key, null); }
function cancelApproval() { setState({ approvalOpen: false, approvalKey: null, approvalPending: null }); }
function approveOnce() { commit(state.approvalKey, false, state.approvalPending); }
function approveAuto() {
  const t = (ACTS[state.approvalKey] || {}).t;
  setState(p => ({ autoApprove: { ...p.autoApprove, [t]: true } }));
  commit(state.approvalKey, false, state.approvalPending);
}
function reviewOrApprovePending(act, id) { request(act, id); }
function rejectPending(id) { setState(p => ({ pending: p.pending.filter(x => x.id !== id) })); }
function undoDone(id) { setState(p => ({ done: p.done.filter(x => x.id !== id) })); }
function openSettings() { setState({ settingsOpen: true }); }
function closeSettings() { setState({ settingsOpen: false }); }
function toggleAuto(type) { setState(p => ({ autoApprove: { ...p.autoApprove, [type]: !p.autoApprove[type] } })); }
function toggleTrace() { setState(p => ({ traceOpen: !p.traceOpen })); }
function toggleTrace2() { setState(p => ({ trace2Open: !p.trace2Open })); }
function undoSeed() { setState({ seedUndone: true }); }
function refreshSources() { setState({ refreshed: true }); }
function goDashboard() { setState({ screen: 'dashboard' }); } // TODO(W4.4): POST /invocations to onboard, then goDashboard
function goDash() { setState({ screen: 'dashboard' }); }
function goStudy() { setState({ screen: 'study' }); }
function goHack() { setState({ screen: 'hackathons' }); }
function goIntern() { setState({ screen: 'internships' }); }
function goOnboarding() { setState({ screen: 'onboarding', step: 1 }); }
function goStep(n) { setState({ step: n }); }
function openLog() { setState({ logOpen: true }); }
function closeLog() { setState({ logOpen: false }); }
function setLogItem(v) { setState({ logItem: v }); }
function setLogOutcome(v) { setState({ logOutcome: v }); }
function confirmLog() { setState(p => ({ logOpen: false, setback: p.logOutcome === 'Not shortlisted' })); }
function resetDemo() {
  setState({
    setback: false, logOpen: false, logOutcome: 'Not shortlisted', sc: {},
    approvalOpen: false, approvalKey: null, approvalPending: null, settingsOpen: false,
    autoApprove: { ...AUTO_DEFAULT }, pending: SEED_PENDING.slice(),
    traceOpen: false, trace2Open: false, done: [], seq: 0, seedUndone: false, refreshed: false,
  });
}
function toggleReasoning() { setState(p => ({ showReasoning: !p.showReasoning })); }
function filterSet(f) { setState({ filter: f }); }

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
const ICON_REFRESH = '<path d="M3 12a9 9 0 0 1 15-6.7L21 8"></path><path d="M21 3v5h-5"></path><path d="M21 12a9 9 0 0 1-15 6.7L3 16"></path><path d="M3 21v-5h5"></path>';
const ICON_ARROW = '<path d="M5 12h14"></path><path d="m12 5 7 7-7 7"></path>';
const ICON_UPLOAD = '<path d="M12 13v8"></path><path d="m8 17 4-4 4 4"></path><path d="M20.4 14.5A5 5 0 0 0 18 5h-1.3A8 8 0 1 0 4 12.7"></path>';
const ICON_RESUME = '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"></path><path d="M14 2v5h6"></path><path d="M9 13h6"></path><path d="M9 17h4"></path>';
const ICON_INFO = '<circle cx="12" cy="12" r="10"></circle><path d="M12 16v-4"></path><path d="M12 8h.01"></path>';
const ICON_CHECK = '<path d="M21.801 10A10 10 0 1 1 17 3.335"></path><path d="m9 11 3 3L22 4"></path>';
const ICON_PAW = '<path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.4 5.4 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.6.9-.9 1.9-1 3V22"></path><path d="M9 18c-4.51 2-5-2-7-2"></path>';

// — decomposition-toggle card fragment, reused by every ranked candidate across screens —
function decomp(id, v, gap, role, time, pen, note) {
  return v.sc[id] ? `<div class="decomp"><div class="decomp-grid">
    <div><div class="decomp-k">Gap coverage</div><div class="decomp-v">${gap}</div></div>
    <div><div class="decomp-k">Role fit</div><div class="decomp-v">${role}</div></div>
    <div><div class="decomp-k">Time cost</div><div class="decomp-v">${time}</div></div>
    <div><div class="decomp-k">Redundancy penalty</div><div class="decomp-v">${pen}</div></div>
    </div><p class="decomp-note">${note}</p></div>` : '';
}
function whybtn(id) { return `<button type="button" class="whybtn" style="margin-top:8px" onclick="toggleSc('${id}')">Why this score?</button>`; }

function renderOnboarding(v) {
  const step1 = `
    <span style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--color-accent-700)">Step 1 of 3</span>
    <h1 style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:34px;margin:8px 0 10px">Upload your transcript and resume</h1>
    <p style="font-size:15px;max-width:62ch;color:var(--color-neutral-700);margin:0 0 30px">Your documents are parsed into a structured profile — completed modules, units, grades and skills — which becomes the state your agent plans against. Nothing is planned until this profile exists.</p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:22px">
      <div class="card" style="padding:26px 22px;border-style:dashed;text-align:center">
        ${icon(ICON_UPLOAD, 26, 'margin-bottom:10px').replace('stroke="currentColor"', 'stroke="var(--color-accent-700)"').replace('stroke-width="2"','stroke-width="1.6"')}
        <div class="card-title" style="font-size:15.5px;margin-bottom:4px">Academic transcript</div>
        <p class="card-body" style="font-size:12.5px;margin:0 0 12px">Drop your unofficial transcript here, or browse</p>
        <div style="font-size:11px;color:var(--color-neutral-600);margin-bottom:14px">PDF · max 10 MB</div>
        <button type="button" class="btn btn-secondary" style="font-size:12.5px">Choose file</button>
      </div>
      <div class="card" style="padding:26px 22px;border-style:dashed;text-align:center">
        ${icon(ICON_RESUME, 26, 'margin-bottom:10px').replace('stroke="currentColor"', 'stroke="var(--color-accent-700)"').replace('stroke-width="2"','stroke-width="1.6"')}
        <div class="card-title" style="font-size:15.5px;margin-bottom:4px">Resume</div>
        <p class="card-body" style="font-size:12.5px;margin:0 0 12px">Drop your latest resume here, or browse</p>
        <div style="font-size:11px;color:var(--color-neutral-600);margin-bottom:14px">PDF or DOCX · max 10 MB</div>
        <button type="button" class="btn btn-secondary" style="font-size:12.5px">Choose file</button>
      </div>
    </div>
    <div class="card" style="padding:16px 18px;margin-bottom:26px">
      <div style="display:flex;gap:10px;align-items:flex-start">
        ${icon(ICON_INFO, 16, 'flex:none;margin-top:2px').replace('stroke="currentColor"', 'stroke="var(--color-neutral-600)"').replace('stroke-width="2"','stroke-width="1.8"')}
        <div>
          <div style="font-size:13px;margin-bottom:3px">Why upload instead of connecting your account?</div>
          <p style="margin:0;font-size:12.5px;color:var(--color-neutral-700);line-height:1.55">NUS EduRec has no student-accessible API, so there is no sanctioned way to read your record automatically. Parsing an uploaded transcript keeps the profile accurate and under your control — and it is what lets the agent check real prerequisites rather than guess.</p>
        </div>
      </div>
    </div>
    <div style="display:flex;justify-content:flex-end;gap:12px">
      <button type="button" class="btn btn-primary" onclick="goStep(2)">Parse documents${icon(ICON_ARROW, 14)}</button>
    </div>`;
  const step2 = `
    <span style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--color-accent-700)">Step 2 of 3</span>
    <h1 style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:34px;margin:8px 0 10px">Review what we found</h1>
    <p style="font-size:15px;max-width:62ch;color:var(--color-neutral-700);margin:0 0 30px">We parsed your transcript and resume into a structured profile. Confirm it — every recommendation is derived from these fields.</p>
    <div style="display:grid;grid-template-columns:290px 1fr;gap:28px">
      <div class="card" style="padding:20px">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><div class="card-kicker">Documents</div><span class="tag tag-neutral" style="font-size:10px">Prototype data</span></div>
        <div style="display:flex;flex-direction:column;gap:12px;margin-top:14px">
          <div style="display:flex;align-items:center;gap:10px">${icon(ICON_CHECK, 17).replace('stroke="currentColor"', 'stroke="var(--color-accent-700)"')}<div><div style="font-size:13.5px">transcript_2026.pdf</div><div style="font-size:11.5px;color:var(--color-neutral-600)">Parsed · 18 modules found</div></div></div>
          <div style="display:flex;align-items:center;gap:10px">${icon(ICON_CHECK, 17).replace('stroke="currentColor"', 'stroke="var(--color-accent-700)"')}<div><div style="font-size:13.5px">resume_weiling.pdf</div><div style="font-size:11.5px;color:var(--color-neutral-600)">Parsed · 6 skills extracted</div></div></div>
        </div>
        <div class="hr" style="margin:18px 0"></div>
        <button type="button" class="btn btn-ghost btn-block" style="font-size:12.5px" onclick="goStep(1)">Upload another file</button>
        <p style="margin:12px 0 0;font-size:11px;color:var(--color-neutral-600);line-height:1.5">Module codes are validated against the NUSMods catalogue on parse.</p>
      </div>
      <div class="card" style="padding:24px">
        <div class="card-kicker">Auto-filled profile</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px">
          <div class="field"><label>Full name</label><input class="input" value="Wei Ling Tan"></div>
          <div class="field"><label>Matriculation year</label><input class="input" value="2025"></div>
          <div class="field"><label>Major</label><input class="input" value="Computer Science"></div>
          <div class="field"><label>Units completed</label><input class="input" value="72 / 160"></div>
        </div>
        <div style="margin-top:18px">
          <label style="font-size:12.5px;color:var(--color-neutral-700);display:block;margin-bottom:8px">Completed modules (18)</label>
          <div style="display:flex;flex-wrap:wrap;gap:6px"><span class="tag tag-outline">CS1101S</span><span class="tag tag-outline">CS1231S</span><span class="tag tag-outline">CS2030S</span><span class="tag tag-outline">CS2040S</span><span class="tag tag-outline">CS2100</span><span class="tag tag-outline">MA1521</span><span class="tag tag-neutral">+12 more</span></div>
        </div>
        <div style="margin-top:18px">
          <label style="font-size:12.5px;color:var(--color-neutral-700);display:block;margin-bottom:8px">In progress (3)</label>
          <div style="display:flex;flex-wrap:wrap;gap:6px"><span class="tag tag-outline">CS2103T</span><span class="tag tag-outline">CS2105</span><span class="tag tag-outline">MA2001</span></div>
        </div>
        <div style="margin-top:18px">
          <label style="font-size:12.5px;color:var(--color-neutral-700);display:block;margin-bottom:8px">Skills extracted from resume</label>
          <div style="display:flex;flex-wrap:wrap;gap:6px"><span class="tag tag-accent">Python</span><span class="tag tag-accent">Java</span><span class="tag tag-accent">SQL</span><span class="tag tag-accent">React</span><span class="tag tag-accent">Data Structures</span><span class="tag tag-accent">Git</span></div>
        </div>
      </div>
    </div>
    <div style="display:flex;justify-content:flex-end;gap:12px;margin-top:28px">
      <button type="button" class="btn btn-ghost" onclick="goStep(1)">Back</button>
      <button type="button" class="btn btn-primary" onclick="goStep(3)">Looks right${icon(ICON_ARROW, 14)}</button>
    </div>`;
  const step3 = `
    <span style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--color-accent-700)">Step 3 of 3</span>
    <h1 style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:34px;margin:8px 0 10px">Set your goal</h1>
    <p style="font-size:15px;max-width:62ch;color:var(--color-neutral-700);margin:0 0 30px">Your goal sets the weights the agent scores everything against. Change it later and the whole plan re-ranks.</p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
      <div class="card" style="padding:24px">
        <div class="card-kicker">Career goal</div>
        <div class="field" style="margin-top:14px"><label>Target role</label><input class="input" value="Software Engineer — Backend / Infrastructure"></div>
        <div style="margin-top:16px">
          <label style="font-size:12.5px;color:var(--color-neutral-700);display:block;margin-bottom:8px">Target timeline</label>
          <div style="display:flex;flex-wrap:wrap;gap:6px"><span class="tag tag-accent">Internship by Y3 summer</span><span class="tag tag-outline">Full-time by Y4</span></div>
        </div>
        <div class="field" style="margin-top:16px"><label>Anything the agent should know?</label><input class="input" placeholder="e.g. prefer online hackathons during term"></div>
      </div>
      <div class="card" style="padding:24px">
        <div class="card-kicker">What your agent will do</div>
        <div style="display:flex;flex-direction:column;gap:12px;margin-top:14px">
          <div style="display:flex;gap:9px;align-items:flex-start"><span style="color:var(--color-accent-700);font-size:13px;line-height:1.5">1</span><p style="margin:0;font-size:13px;line-height:1.55">Score you on five readiness dimensions weighted to a backend target, and keep that state between sessions.</p></div>
          <div style="display:flex;gap:9px;align-items:flex-start"><span style="color:var(--color-accent-700);font-size:13px;line-height:1.5">2</span><p style="margin:0;font-size:13px;line-height:1.55">Search NUSMods, Eventbrite and GitHub, and rank results by the gap each one closes — not by keyword similarity.</p></div>
          <div style="display:flex;gap:9px;align-items:flex-start"><span style="color:var(--color-accent-700);font-size:13px;line-height:1.5">3</span><p style="margin:0;font-size:13px;line-height:1.55">Re-plan when you log an outcome, so a rejection changes the roadmap instead of ending it.</p></div>
        </div>
        <div class="hr" style="margin:18px 0"></div>
        <p style="margin:0;font-size:11.5px;color:var(--color-neutral-600);line-height:1.55">Prerequisite checks run against your parsed transcript, so recommended modules are ones you can actually take.</p>
      </div>
    </div>
    <div style="display:flex;justify-content:flex-end;gap:12px;margin-top:28px">
      <button type="button" class="btn btn-ghost" onclick="goStep(2)">Back</button>
      <button type="button" class="btn btn-primary" onclick="goDashboard()">Build my plan${icon(ICON_ARROW, 14)}</button>
    </div>`;
  return `<div style="width:100%;height:100%;overflow:auto">
    <div style="max-width:920px;margin:0 auto;padding:56px 32px 80px">
      <div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:30px">
        <div style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:22px;letter-spacing:.02em">Pathwise</div>
        <a onclick="goDashboard()" style="font-size:13px;cursor:pointer">Skip to dashboard →</a>
      </div>
      <div style="display:flex;gap:22px;align-items:center;margin-bottom:26px;flex-wrap:wrap">
        <button type="button" class="stepdot" onclick="goStep(1)" style="color:${v.step1Color}"><span style="width:20px;height:20px;border-radius:50%;border:1px solid ${v.step1Color};display:inline-flex;align-items:center;justify-content:center;font-size:11px">1</span>Upload documents</button>
        <span style="width:26px;height:1px;background:var(--color-divider)"></span>
        <button type="button" class="stepdot" onclick="goStep(2)" style="color:${v.step2Color}"><span style="width:20px;height:20px;border-radius:50%;border:1px solid ${v.step2Color};display:inline-flex;align-items:center;justify-content:center;font-size:11px">2</span>Review parsed profile</button>
        <span style="width:26px;height:1px;background:var(--color-divider)"></span>
        <button type="button" class="stepdot" onclick="goStep(3)" style="color:${v.step3Color}"><span style="width:20px;height:20px;border-radius:50%;border:1px solid ${v.step3Color};display:inline-flex;align-items:center;justify-content:center;font-size:11px">3</span>Set your goal</button>
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
  return `<div style="width:216px;flex:none;border-right:1px solid var(--color-divider);display:flex;flex-direction:column;padding:22px 14px;box-sizing:border-box">
    <div style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:20px;letter-spacing:.02em;padding:0 8px;margin-bottom:26px">Pathwise</div>
    ${navItem('Dashboard', 'dashboard', ICON_DASH, state.screen, 'goDash')}
    ${navItem('Study Plan', 'study', ICON_STUDY, state.screen, 'goStudy')}
    ${navItem('Hackathons', 'hackathons', ICON_HACK, state.screen, 'goHack')}
    ${navItem('Internships', 'internships', ICON_INTERN, state.screen, 'goIntern')}
    <div style="flex:1"></div>
    <div class="hr" style="margin:12px 0"></div>
    <div class="navitem" onclick="goOnboarding()" style="color:var(--color-neutral-600);font-size:12.5px">↺ View onboarding</div>
    <div style="display:flex;align-items:center;gap:10px;padding:12px 8px 4px">
      <div style="width:30px;height:30px;border-radius:50%;border:1px solid var(--color-divider);display:flex;align-items:center;justify-content:center;font-family:var(--font-heading);font-size:14px;color:var(--color-accent-700)">WL</div>
      <div style="flex:1;min-width:0"><div style="font-size:12.5px">Wei Ling Tan</div><div style="font-size:11px;color:var(--color-neutral-600)">Y2 · Computer Science</div></div>
      <button type="button" class="btn btn-ghost btn-icon" aria-label="Automation settings" style="flex:none;padding:6px" onclick="openSettings()">${icon(ICON_GEAR, 15, undefined).replace('stroke-width="2"','stroke-width="1.8"')}</button>
    </div>
  </div>`;
}

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

function renderDashboard(v) {
  const logPanel = v.logOpen ? `<div class="card elev-sm" style="padding:20px;margin-bottom:20px">
    <div class="card-kicker">Log an outcome</div>
    <p class="card-body" style="font-size:12.5px;margin:6px 0 16px">Recording a result updates your profile state. The agent re-scores and re-plans from the new state.</p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div class="field"><label>Item</label>
        <select class="input" onchange="setLogItem(this.value)">
          ${['BuildAI Hackathon — Backend Track','HackNUS Systems Track','CS2105 — Intro to Computer Networks','Distributed key-value store project'].map(o => `<option ${o === state.logItem ? 'selected' : ''}>${o}</option>`).join('')}
        </select>
      </div>
      <div class="field"><label>Outcome</label>
        <select class="input" onchange="setLogOutcome(this.value)">
          ${['Accepted','Not shortlisted','Completed','Withdrew'].map(o => `<option ${o === state.logOutcome ? 'selected' : ''}>${o}</option>`).join('')}
        </select>
      </div>
    </div>
    <div class="field" style="margin-top:14px"><label>Note (optional)</label><input class="input" placeholder="e.g. no feedback given"></div>
    <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:18px">
      <button type="button" class="btn btn-ghost" onclick="closeLog()">Cancel</button>
      <button type="button" class="btn btn-primary" onclick="confirmLog()">Record outcome</button>
    </div>
  </div>` : '';

  const setbackBanner = v.setback ? `<div class="card elev-sm" style="padding:18px;margin-bottom:20px;border-color:var(--color-accent-500)">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px">
      <div>
        <span class="tag tag-accent" style="margin-bottom:8px;display:inline-block">Plan adjusted</span>
        <div class="card-title" style="font-size:16px;margin-bottom:4px">Outcome recorded: not shortlisted for BuildAI — here's the pivot</div>
        <p class="card-body" style="margin:0">Readiness moved 62% → 60% because the provisional hackathon evidence is gone. HackNUS Systems Track and the distributed KV store project moved up; Y3 internship applications now start a semester earlier.</p>
      </div>
      <button type="button" class="btn btn-secondary" style="white-space:nowrap" onclick="goStudy()">Review new plan</button>
    </div>
  </div>` : '';

  const pendingCard = v.hasPending ? `<div class="card elev-sm" style="padding:18px 20px;margin-bottom:20px">
    <div style="display:flex;align-items:center;gap:9px;margin-bottom:4px">
      <span class="kindtag" style="background:var(--color-accent-100);color:var(--color-accent-700)">Pending approval</span>
      <span style="font-size:11.5px;color:var(--color-neutral-600)">· ${v.pendingCount} items</span>
    </div>
    ${v.pendingItems.map(it => `<div style="display:flex;align-items:center;gap:16px;justify-content:space-between;padding:11px 0;border-bottom:1px solid var(--color-divider)">
      <div style="min-width:0"><div style="font-size:13.5px">${it.title}</div><div style="font-size:11.5px;color:var(--color-neutral-600);margin-top:2px">${it.meta}</div></div>
      <div style="display:flex;gap:8px;flex:none">
        ${it.isReview ? `<button type="button" class="btn btn-secondary" style="font-size:12px;padding:5px 13px" onclick="reviewOrApprovePending('${it.act}','${it.id}')">Review</button>` : ''}
        ${it.isApprove ? `<button type="button" class="btn btn-secondary" style="font-size:12px;padding:5px 13px" onclick="reviewOrApprovePending('${it.act}','${it.id}')">Approve</button>` : ''}
        <button type="button" class="btn btn-ghost" style="font-size:12px;padding:5px 13px" onclick="rejectPending('${it.id}')">Reject</button>
      </div>
    </div>`).join('')}
    <p style="margin:12px 0 0;font-size:11.5px;color:var(--color-neutral-600);line-height:1.55">The agent prepared these and is waiting. Nothing is sent until you approve.</p>
  </div>` : '';

  const onTrackList = `<div style="display:flex;flex-direction:column;gap:14px">
    ${rankedCard(1, '<span class="tag tag-accent">96% match</span><span class="tag tag-outline">Closes: Cloud &amp; deployment</span><span class="tag tag-neutral">Event Agent · Eventbrite</span>',
      'Apply: BuildAI Hackathon — Backend Track', '', 'Backend-track prizes with a required deployment step — the only item in your list that produces cloud &amp; deployment evidence before Y3.',
      decomp('r1', v, 88, 94, 42, '−6', 'Components are scored 0–100 from your profile state and blended with your role weights; the redundancy penalty subtracts directly. Low penalty here because you hold no deployment evidence yet.'),
      'r1', `<button type="button" class="btn btn-secondary" style="flex:none;white-space:nowrap" onclick="goHack()">View details</button>`)}
    ${rankedCard(2, '<span class="tag tag-accent">93% match</span><span class="tag tag-outline">Closes: Cloud &amp; deployment</span><span class="tag tag-neutral">Project Agent · GitHub Search</span>',
      'Ship: distributed key-value store', 'pingcap/talent-plan · Rust · 10.4k ★ · updated 6 days ago', 'A staged reference curriculum you can deploy and write up. Produces the deployment artefact your saved roles ask for.',
      decomp('r2', v, 91, 90, 66, '−5', 'Highest gap coverage in your list, offset by the largest time cost — a multi-week build. Ranked below BuildAI only because the hackathon has a hard deadline.'),
      'r2', `<button type="button" class="btn btn-ghost" style="flex:none;white-space:nowrap">See repo</button>`)}
    ${rankedCard(3, '<span class="tag tag-accent">89% match</span><span class="tag tag-outline">Closes: Data structures &amp; algorithms</span><span class="tag tag-neutral">Module Agent · NUSMods</span>',
      'Take CS3230 next semester', '4 units · Offered Sem 1 &amp; 2 · Prereq: CS2040S ✓ met, CS1231S ✓ met', 'Required by 3 of 4 backend role profiles you’ve saved. No clash with your current plan.',
      decomp('r3', v, 76, 92, 48, '−3', 'Strong role fit but it closes your second-tier gap, not your critical one — which is why a deployment item outranks it.'),
      'r3', `<button type="button" class="btn btn-ghost" style="flex:none;white-space:nowrap" onclick="ask('addCs3230')">Add to study plan</button>`)}
  </div>`;

  const setbackList = `<div style="display:flex;flex-direction:column;gap:14px">
    ${rankedCard(1, '<span class="tag tag-accent">93% match</span><span class="tag tag-outline">Closes: Cloud &amp; deployment</span><span class="tag tag-neutral">Project Agent · GitHub Search</span><span class="tag tag-accent" style="font-size:10px">Moved up</span>',
      'Ship: distributed key-value store', 'pingcap/talent-plan · Rust · 10.4k ★ · updated 6 days ago', 'Now your only route to deployment evidence this year. A shipped, deployed project is evidence you fully control — no shortlist required.',
      decomp('s1', v, 91, 90, 66, '−5', 'Unchanged since the BuildAI outcome — but now top-ranked, because the item above it disappeared rather than because this one improved.'),
      's1', `<button type="button" class="btn btn-secondary" style="flex:none;white-space:nowrap">See repo</button>`)}
    ${rankedCard(2, '<span class="tag tag-accent">88% match</span><span class="tag tag-outline">Closes: Systems &amp; networks</span><span class="tag tag-neutral">Event Agent · organiser page</span><span class="tag tag-accent" style="font-size:10px">Moved up</span>',
      'Apply: HackNUS Systems Track', 'Nov 2–3 · NUS School of Computing, COM3 · Free · registration closes Oct 26', 'Rolling admissions, still open, smaller field than BuildAI. Systems track lines up with CS2105 in progress.',
      decomp('s2', v, 79, 89, 38, v.hacknusPen, v.hacknusPenNote),
      's2', `<button type="button" class="btn btn-secondary" style="flex:none;white-space:nowrap" onclick="goHack()">View details</button>`)}
    ${rankedCard(3, '<span class="tag tag-accent">89% match</span><span class="tag tag-outline">Closes: Data structures &amp; algorithms</span><span class="tag tag-neutral">Module Agent · NUSMods</span>',
      'Take CS3230 next semester', '4 units · Offered Sem 1 &amp; 2 · Prereq: CS2040S ✓ met, CS1231S ✓ met', 'Unaffected by the outcome. Still required by 3 of 4 saved role profiles.',
      decomp('s3', v, 76, 92, 48, '−3', 'A module outcome doesn’t move when a hackathon outcome is logged — the components are scored independently.'),
      's3', `<button type="button" class="btn btn-ghost" style="flex:none;white-space:nowrap" onclick="ask('addCs3230')">Add to study plan</button>`)}
    ${rankedCard(4, '<span class="tag tag-outline">34% match</span><span class="tag tag-outline">Closes: Systems &amp; networks (duplicate)</span><span class="tag tag-neutral">Event Agent · Eventbrite</span><span class="tag tag-neutral" style="font-size:10px">Deprioritised</span>',
      'CodeSprint Open 2026', 'Nov 8–9 · Suntec Convention Centre · Free · registration closes Nov 1', 'You already have hackathon applications in flight; a shipped deployed project adds evidence you don’t have yet.',
      decomp('s4', v, 38, 55, 61, '−74', 'The penalty is doing the work here. On skills alone this would rank mid-list; it is pushed to the bottom because it duplicates evidence two other items already produce.'),
      's4', `<button type="button" class="btn btn-ghost" style="flex:none;white-space:nowrap" onclick="ask('dismissCodesprint')">Dismiss recommendation</button>`, true)}
  </div>`;

  return `<div style="max-width:1080px;margin:0 auto;padding:44px 40px 60px">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:26px;flex-wrap:wrap">
      <div style="min-width:0">
        <h1 style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:30px;margin:0 0 6px">Welcome back, Wei Ling</h1>
        <p style="font-size:14px;color:var(--color-neutral-700);margin:0">Goal: <strong style="font-weight:600">Software Engineer — Backend / Infrastructure</strong></p>
      </div>
      <button type="button" class="btn btn-secondary" style="flex:none;white-space:nowrap" onclick="openLog()">${icon('<path d="M12 5v14"></path><path d="M5 12h14"></path>', 14)}Log an outcome</button>
    </div>
    ${logPanel}
    ${setbackBanner}
    ${pendingCard}
    <div class="card" style="padding:22px;margin-bottom:18px">
      <div class="card-kicker">Career readiness</div>
      <div style="display:flex;align-items:baseline;gap:10px;margin:6px 0 14px">
        <span style="font-family:var(--font-heading);font-weight:400;font-size:44px;font-variant-numeric:tabular-nums">${v.readiness}%</span>
        <span style="font-size:12.5px;color:var(--color-neutral-600)">weighted sum of the five dimensions below, against the Backend / Infrastructure target</span>
      </div>
      <div style="height:6px;border-radius:3px;background:var(--color-neutral-200);overflow:hidden;margin-bottom:20px"><div style="height:100%;background:var(--color-accent-500);width:${v.readiness}%"></div></div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px">
        <div><div style="font-size:11px;color:var(--color-neutral-600);text-transform:uppercase;letter-spacing:.06em">Modules</div><div style="font-size:18px;font-variant-numeric:tabular-nums">18 / 40</div><div style="font-size:11px;color:var(--color-neutral-600)">3 in progress</div></div>
        <div><div style="font-size:11px;color:var(--color-neutral-600);text-transform:uppercase;letter-spacing:.06em">Hackathons</div><div style="font-size:18px;font-variant-numeric:tabular-nums">2 applied</div><div style="font-size:11px;color:var(--color-neutral-600)">${v.hackOutcome}</div></div>
        <div><div style="font-size:11px;color:var(--color-neutral-600);text-transform:uppercase;letter-spacing:.06em">Internships</div><div style="font-size:18px;font-variant-numeric:tabular-nums">0 applied</div><div style="font-size:11px;color:var(--color-neutral-600)">Y3 target</div></div>
        <div><div style="font-size:11px;color:var(--color-neutral-600);text-transform:uppercase;letter-spacing:.06em">Projects</div><div style="font-size:18px;font-variant-numeric:tabular-nums">1 shipped</div><div style="font-size:11px;color:var(--color-neutral-600)">1 in progress</div></div>
      </div>
    </div>
    <div class="card" style="padding:22px;margin-bottom:18px">
      <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:16px">
        <div class="card-kicker">Skill gap analysis</div>
        <span style="font-size:11px;color:var(--color-neutral-600)">Derived from parsed transcript + NUSMods module outcomes</span>
      </div>
      <div style="display:grid;grid-template-columns:1.25fr 1fr;gap:28px">
        <div>
          <div class="barrow" style="color:var(--color-neutral-600);font-size:10px;text-transform:uppercase;letter-spacing:.07em;margin-bottom:8px"><span>Dimension</span><span></span><span style="text-align:right">Score</span><span style="text-align:right">Weight</span></div>
          <div style="display:flex;flex-direction:column;gap:11px">
            <div class="barrow"><span>Programming fundamentals</span><span class="bartrack"><span style="display:block;height:100%;background:var(--color-accent-500);width:${v.g1}%"></span></span><span style="text-align:right;font-variant-numeric:tabular-nums">${v.g1}%</span><span style="text-align:right;color:var(--color-neutral-600);font-size:11px">×30</span></div>
            <div class="barrow"><span>Data structures &amp; algorithms</span><span class="bartrack"><span style="display:block;height:100%;background:var(--color-accent-500);width:${v.g2}%"></span></span><span style="text-align:right;font-variant-numeric:tabular-nums">${v.g2}%</span><span style="text-align:right;color:var(--color-neutral-600);font-size:11px">×30</span></div>
            <div class="barrow"><span>Systems &amp; networks</span><span class="bartrack"><span style="display:block;height:100%;background:var(--color-accent-500);width:${v.g3}%"></span></span><span style="text-align:right;font-variant-numeric:tabular-nums">${v.g3}%</span><span style="text-align:right;color:var(--color-neutral-600);font-size:11px">×20</span></div>
            <div class="barrow"><span>Databases &amp; data infrastructure</span><span class="bartrack"><span style="display:block;height:100%;background:var(--color-accent-500);width:${v.g4}%"></span></span><span style="text-align:right;font-variant-numeric:tabular-nums">${v.g4}%</span><span style="text-align:right;color:var(--color-neutral-600);font-size:11px">×10</span></div>
            <div class="barrow"><span>Cloud &amp; deployment</span><span class="bartrack"><span style="display:block;height:100%;background:var(--color-accent-500);width:${v.g5}%"></span></span><span style="text-align:right;font-variant-numeric:tabular-nums">${v.g5}%</span><span style="text-align:right;color:var(--color-neutral-600);font-size:11px">×10</span></div>
          </div>
          <p style="margin:14px 0 0;font-size:11.5px;color:var(--color-neutral-600);line-height:1.55">Weights are set by your target role. ${v.readinessSum}</p>
        </div>
        <div>
          <div style="font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--color-neutral-600);margin-bottom:12px">Priority gaps</div>
          <div style="display:flex;flex-direction:column;gap:12px">
            <div style="display:flex;gap:10px;align-items:flex-start"><span style="font-family:var(--font-heading);font-size:15px;color:var(--color-accent-700);line-height:1.3">1</span><div><div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap"><span style="font-size:13px">Cloud &amp; deployment</span><span class="tag tag-accent" style="font-size:10px">Critical</span></div><p style="margin:3px 0 0;font-size:12px;color:var(--color-neutral-700);line-height:1.5">Weakest area, and required by every backend role you've saved.</p></div></div>
            <div style="display:flex;gap:10px;align-items:flex-start"><span style="font-family:var(--font-heading);font-size:15px;color:var(--color-accent-700);line-height:1.3">2</span><div><div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap"><span style="font-size:13px">Databases &amp; data infrastructure</span><span class="tag tag-outline" style="font-size:10px">High</span></div><p style="margin:3px 0 0;font-size:12px;color:var(--color-neutral-700);line-height:1.5">Needed to convert coursework into production-relevant evidence.</p></div></div>
            <div style="display:flex;gap:10px;align-items:flex-start"><span style="font-family:var(--font-heading);font-size:15px;color:var(--color-accent-700);line-height:1.3">3</span><div><div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap"><span style="font-size:13px">Systems &amp; networks</span><span class="tag tag-neutral" style="font-size:10px">Medium</span></div><p style="margin:3px 0 0;font-size:12px;color:var(--color-neutral-700);line-height:1.5">CS2105 in progress will partially close this.</p></div></div>
          </div>
        </div>
      </div>
    </div>
    <div class="card" style="padding:22px;margin-bottom:32px">
      <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px">
        <div class="card-kicker">Your roadmap</div>
        <span style="font-size:11px;color:var(--color-neutral-600)">Y2 Sem 1 · today</span>
      </div>
      <div style="position:relative;margin-top:22px">
        <div style="position:absolute;left:0;right:0;top:5px;height:1px;background:var(--color-divider)"></div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:22px;position:relative">
          <div>
            <div style="width:9px;height:9px;border-radius:50%;background:var(--color-neutral-400);margin-bottom:12px"></div>
            <div style="display:flex;align-items:center;gap:7px;margin-bottom:8px"><span style="font-size:12px;font-weight:600">Y1</span><span class="tag tag-neutral" style="font-size:9.5px">Completed</span></div>
            <p class="rmitem" style="color:var(--color-neutral-700)">CS1101S, CS1231S foundations</p>
            <p class="rmitem" style="color:var(--color-neutral-700)">First hackathon attempt</p>
          </div>
          <div>
            <div style="width:11px;height:11px;border-radius:50%;background:var(--color-accent-500);margin:-1px 0 11px"></div>
            <div style="display:flex;align-items:center;gap:7px;margin-bottom:8px"><span style="font-size:12px;font-weight:600;color:var(--color-accent-700)">Y2 · now</span><span class="tag tag-accent" style="font-size:9.5px">In progress</span></div>
            <p class="rmitem">CS2103T, CS2105, MA2001</p>
            <p class="rmitem">BuildAI application</p>
            <p class="rmitem">Distributed KV store project started</p>
          </div>
          <div>
            <div style="width:9px;height:9px;border-radius:50%;border:1px solid var(--color-neutral-400);background:var(--color-bg);margin-bottom:12px"></div>
            <div style="display:flex;align-items:center;gap:7px;margin-bottom:8px"><span style="font-size:12px;font-weight:600;color:var(--color-neutral-600)">Y3</span><span class="tag tag-outline" style="font-size:9.5px">Agent-planned</span></div>
            <p class="rmitem" style="color:var(--color-neutral-600)">CS3230, CS3223</p>
            ${v.isOnTrack ? '<p class="rmitem" style="color:var(--color-neutral-600)">Summer internship applications</p>' : '<p class="rmitem" style="color:var(--color-accent-700)">Internship applications from Nov — one semester earlier <span class="tag tag-accent" style="font-size:9px">Changed</span></p>'}
            <p class="rmitem" style="color:var(--color-neutral-600)">One deployed production project</p>
          </div>
          <div>
            <div style="width:9px;height:9px;border-radius:50%;border:1px solid var(--color-neutral-400);background:var(--color-bg);margin-bottom:12px"></div>
            <div style="display:flex;align-items:center;gap:7px;margin-bottom:8px"><span style="font-size:12px;font-weight:600;color:var(--color-neutral-600)">Y4</span><span class="tag tag-outline" style="font-size:9.5px">Agent-planned</span></div>
            <p class="rmitem" style="color:var(--color-neutral-600)">Systems electives</p>
            <p class="rmitem" style="color:var(--color-neutral-600)">Final year project</p>
            <p class="rmitem" style="color:var(--color-neutral-600)">Full-time conversion</p>
          </div>
        </div>
      </div>
      <p class="note" style="font-size:11.5px;color:var(--color-neutral-600);margin:20px 0 0">Items after today are planned by your agent and change when your profile changes.</p>
    </div>
    <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:6px">${icon(ICON_SPARK, 16).replace('stroke="currentColor"', 'stroke="var(--color-accent-700)"')}<h2 style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:19px;margin:0">Ranked by your Career Agent</h2></div>
    <p style="font-size:12px;color:var(--color-neutral-600);margin:0 0 16px">Every item traces to a priority gap. Anything that closes no gap is not listed.</p>
    ${v.isOnTrack ? onTrackList : setbackList}
    <div style="margin-top:36px;padding-top:14px;border-top:1px solid var(--color-divider);display:flex;justify-content:space-between;align-items:center;gap:12px">
      <span style="font-size:11px;color:var(--color-neutral-600)">Sources: NUSMods API · Eventbrite API · GitHub Search API. Panels fed by other sources are badged.</span>
      <a onclick="resetDemo()" style="font-size:11px;color:var(--color-neutral-600);cursor:pointer">Reset demo state</a>
    </div>
  </div>`;
}

function renderHackathons(v) {
  const reason = t => v.showReasoning ? `<p class="card-body" style="margin:8px 0 0">${t}</p>` : '';
  return `<div style="max-width:1080px;margin:0 auto;padding:44px 40px 80px">
    <h1 style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:28px;margin:0 0 6px">Hackathons</h1>
    <p style="font-size:13.5px;color:var(--color-neutral-600);margin:0 0 6px">Ranked by the gap each event closes, not by keyword similarity</p>
    <p style="font-size:12px;color:var(--color-neutral-600);margin:0 0 24px">Sources: Eventbrite API (live) · organiser pages (prototype)</p>
    <div style="display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap;align-items:center">
      <input class="input" placeholder="Search hackathons" style="max-width:260px">
      <span class="tag tag-outline">Track: Backend / infra</span><span class="tag tag-outline">Singapore</span>
      <div style="flex:1"></div>
      <button type="button" class="btn btn-ghost" onclick="toggleReasoning()" style="font-size:12.5px">Toggle match reasoning</button>
    </div>
    <div style="display:flex;flex-direction:column;gap:14px">
      <div class="card" style="padding:18px 20px"><div style="display:flex;justify-content:space-between;align-items:flex-start;gap:20px;flex-wrap:wrap;row-gap:14px">
        <div style="flex:1 1 260px;min-width:0">
          <div style="display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin-bottom:6px"><span class="tag tag-accent">96% match</span><span class="tag tag-outline">Closes: Cloud &amp; deployment</span><span class="tag tag-neutral">Event Agent · Eventbrite · live</span></div>
          <div class="card-title" style="font-size:16px">BuildAI Hackathon — Backend Track</div>
          <div class="card-meta" style="margin:4px 0 0">Oct 18–19 · JTC Launchpad @ one-north · AWS Activate Singapore · Free · registration closes Oct 10</div>
          ${reason('Required deployment step makes this the only near-term item that produces cloud &amp; deployment evidence. Matches 4 of your 6 extracted skills.')}
          ${whybtn('buildai')}
          ${decomp('buildai', v, 88, 94, 42, '−6', 'Gap coverage is measured against your critical gap; the penalty is near zero because you hold no deployment evidence yet.')}
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;margin-left:auto"><button type="button" class="btn btn-ghost" onclick="ask('saveBuildai')">Save to shortlist</button><button type="button" class="btn btn-primary" onclick="ask('draftBuildai')">Draft application</button></div>
      </div></div>
      <div class="card" style="padding:18px 20px"><div style="display:flex;justify-content:space-between;align-items:flex-start;gap:20px;flex-wrap:wrap;row-gap:14px">
        <div style="flex:1 1 260px;min-width:0">
          <div style="display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin-bottom:6px"><span class="tag tag-accent">88% match</span><span class="tag tag-outline">Closes: Systems &amp; networks</span><span class="tag tag-neutral">Event Agent · organiser page · cached</span><span class="tag tag-neutral" style="font-size:10px">Prototype data</span></div>
          <div class="card-title" style="font-size:16px">HackNUS Systems Track</div>
          <div class="card-meta" style="margin:4px 0 0">Nov 2–3 · NUS School of Computing, COM3 · NUS Computing Club · Free · registration closes Oct 26</div>
          <div style="display:flex;gap:9px;align-items:flex-start;margin:10px 0 0;padding:10px 12px;border:1px solid var(--color-divider);border-radius:var(--radius-md);background:var(--color-neutral-100)">
            ${icon(ICON_INFO, 14, 'flex:none;margin-top:2px').replace('stroke="currentColor"', 'stroke="var(--color-neutral-600)"').replace('stroke-width="2"','stroke-width="1.9"')}
            <p style="margin:0;font-size:11.5px;line-height:1.55;color:var(--color-neutral-700)">We couldn't reach the NUS Computing Club page just now, so these details are from our last successful check. Registration dates may have moved — confirm on the organiser's page before applying.</p>
          </div>
          ${reason('Rolling admissions still open. Smaller applicant pool than BuildAI, similar skill fit, lowest time cost in this list.')}
          ${whybtn('hacknus')}
          ${decomp('hacknus', v, 79, 89, 38, v.hacknusPen, v.hacknusPenNote)}
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;margin-left:auto"><button type="button" class="btn btn-ghost" onclick="ask('saveHacknus')">Save to shortlist</button><button type="button" class="btn btn-primary" onclick="ask('draftHacknus')">Draft application</button></div>
      </div></div>
      <div class="card" style="padding:18px 20px"><div style="display:flex;justify-content:space-between;align-items:flex-start;gap:20px;flex-wrap:wrap;row-gap:14px">
        <div style="flex:1 1 260px;min-width:0">
          <div style="display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin-bottom:6px"><span class="tag tag-outline">61% match</span><span class="tag tag-outline">Closes: Programming fundamentals</span><span class="tag tag-neutral">Event Agent · Eventbrite · live</span></div>
          <div class="card-title" style="font-size:16px">Fintech Sprint 2026</div>
          <div class="card-meta" style="margin:4px 0 0">Nov 21–22 · Marina Bay Financial Centre Tower 3 · DBS Innovation · Paid · registration closes Nov 12</div>
          ${reason('Kept visible but not recommended — fintech-domain focus closes your strongest dimension, not a priority gap.')}
          ${whybtn('fintech')}
          ${decomp('fintech', v, 41, 52, 44, '−12', 'Low gap coverage because it strengthens programming fundamentals, already at 84%. This is why it does not appear on your dashboard.')}
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;margin-left:auto"><button type="button" class="btn btn-ghost" onclick="ask('saveFintech')">Save to shortlist</button><button type="button" class="btn btn-secondary" onclick="ask('draftFintech')">Draft application</button></div>
      </div></div>
    </div>
  </div>`;
}

function internRow(role, company, closes, match, matchOutline, id, deadline, v, gap, roleFit, time, pen, note) {
  return `<tr>
    <td>${role}</td><td>${company}</td><td><span class="tag tag-outline" style="font-size:10px">${closes}</span></td>
    <td><span class="tag ${matchOutline ? 'tag-outline' : 'tag-accent'}">${match}</span><br><button type="button" class="whybtn" style="margin-top:4px" onclick="toggleSc('${id}')">Why?</button></td>
    <td class="text-muted">${deadline}</td>
    <td><button type="button" class="btn btn-secondary" style="font-size:12px;padding:5px 12px" onclick="ask('draftIntern')">Draft application</button></td>
  </tr>${v.sc[id] ? `<tr><td colspan="6" style="padding-top:0"><div class="decomp" style="margin-top:0"><div class="decomp-grid">
    <div><div class="decomp-k">Gap coverage</div><div class="decomp-v">${gap}</div></div>
    <div><div class="decomp-k">Role fit</div><div class="decomp-v">${roleFit}</div></div>
    <div><div class="decomp-k">Time cost</div><div class="decomp-v">${time}</div></div>
    <div><div class="decomp-k">Redundancy penalty</div><div class="decomp-v">${pen}</div></div>
    </div><p class="decomp-note">${note}</p></div></td></tr>` : ''}`;
}

function renderInternships(v) {
  return `<div style="max-width:1080px;margin:0 auto;padding:44px 40px 80px">
    <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:6px"><h1 style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:28px;margin:0">Internships</h1><span class="tag tag-neutral" style="font-size:10px">Prototype data</span></div>
    <p style="font-size:13.5px;color:var(--color-neutral-600);margin:0 0 24px;max-width:78ch">Illustrative listings · live sourcing planned via employer career pages and aggregator feeds (Phase 2)</p>
    <div style="display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap">
      <input class="input" placeholder="Search internships" style="max-width:260px">
      <span class="tag tag-outline">Industry: Software</span><span class="tag tag-outline">Duration: 3–6 mo</span><span class="tag tag-outline">Singapore</span>
    </div>
    <table class="table">
      <thead><tr><th>Role</th><th>Company</th><th>Closes</th><th>Match</th><th>Deadline</th><th></th></tr></thead>
      <tbody>
        ${internRow('Backend Engineering Intern', 'Grab', 'Cloud &amp; deployment', '92%', false, 'i1', 'Sep 30', v, 87, 95, 70, '−4', 'Highest role fit of the four — a named backend team with infrastructure exposure, closing your critical gap directly.')}
        ${internRow('Infrastructure Intern', 'Shopee', 'Cloud &amp; deployment', '87%', false, 'i2', 'Oct 5', v, 89, 88, 72, '−9', 'Marginally higher gap coverage than Grab, but a higher penalty: it overlaps heavily with the deployment project already in your plan.')}
        ${internRow('Software Engineer Intern', 'DBS Bank', 'Databases', '74%', true, 'i3', 'Oct 12', v, 64, 71, 68, '−7', 'General SWE scope, so role fit against a backend / infrastructure target is moderate. Closes your second-tier gap rather than the critical one.')}
        ${internRow('Data Engineering Intern', 'Sea Group', 'Databases', '68%', true, 'i4', 'Oct 20', v, 61, 64, 69, '−6', 'Data-pipeline work is adjacent to your target, not on it. Ranked last because both components that matter most score lowest here.')}
      </tbody>
    </table>
    <p class="note" style="font-size:12px;color:var(--color-neutral-600);margin-top:14px;max-width:80ch">Internship sourcing is Phase 2. The ranking logic is source-agnostic, so listings plug into the same scoring function as modules and hackathons once a feed is connected.</p>
  </div>`;
}

function renderStudy(v) {
  return `<div style="max-width:1080px;margin:0 auto;padding:44px 40px 80px">
    <div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:6px;flex-wrap:wrap"><h1 style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:28px;margin:0">Study Plan</h1><span style="font-size:12px;color:var(--color-neutral-600)">NUSMods API · AY2026/27 · synced today</span></div>
    <p style="font-size:13.5px;color:var(--color-neutral-600);margin:0 0 20px">B.Comp Computer Science · 72 / 160 units</p>
    <div style="height:6px;border-radius:3px;background:var(--color-neutral-200);overflow:hidden;margin-bottom:32px"><div style="height:100%;width:45%;background:var(--color-accent-500)"></div></div>
    <div style="font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--color-neutral-600);margin-bottom:10px">This semester · 3 in progress</div>
    <table class="table" style="margin-bottom:32px">
      <thead><tr><th>Module</th><th>Title</th><th>Units</th><th>Offered</th><th>Status</th></tr></thead>
      <tbody>
        <tr><td>CS2103T</td><td>Software Engineering</td><td>4</td><td class="text-muted">Sem 1 &amp; 2</td><td><span class="tag tag-neutral">In progress</span></td></tr>
        <tr><td>CS2105</td><td>Introduction to Computer Networks</td><td>4</td><td class="text-muted">Sem 1 &amp; 2</td><td><span class="tag tag-neutral">In progress</span></td></tr>
        <tr><td>MA2001</td><td>Linear Algebra I</td><td>4</td><td class="text-muted">Sem 1 &amp; 2</td><td><span class="tag tag-neutral">In progress</span></td></tr>
      </tbody>
    </table>
    <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:6px">${icon(ICON_SPARK, 16).replace('stroke="currentColor"', 'stroke="var(--color-accent-700)"')}<h2 style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:18px;margin:0">Recommended next, based on your goal</h2></div>
    <p style="font-size:12px;color:var(--color-neutral-600);margin:0 0 16px">Prerequisites checked against your parsed transcript. Only modules you can actually take are shown.</p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:36px">
      <div class="card" style="padding:18px">
        <div style="display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin-bottom:6px"><span class="tag tag-accent">89% match</span><span class="tag tag-outline">Closes: Data structures &amp; algorithms</span><span class="tag tag-neutral">Module Agent · NUSMods</span></div>
        <div class="card-title" style="font-size:15.5px">CS3230 — Design and Analysis of Algorithms</div>
        <div class="card-meta" style="margin:4px 0 0">4 units · Offered Sem 1 &amp; 2 · Prereq: CS2040S ✓ met, CS1231S ✓ met</div>
        <p class="card-body" style="font-size:13px;margin:8px 0 0">Required by 3 of 4 backend role profiles you've saved. No clash with your current plan.</p>
        ${whybtn('cs3230')}
        ${v.sc['cs3230'] ? `<div class="decomp"><div class="decomp-grid" style="grid-template-columns:1fr 1fr">
          <div><div class="decomp-k">Gap coverage</div><div class="decomp-v">76</div></div><div><div class="decomp-k">Role fit</div><div class="decomp-v">92</div></div>
          <div><div class="decomp-k">Time cost</div><div class="decomp-v">48</div></div><div><div class="decomp-k">Redundancy penalty</div><div class="decomp-v">−3</div></div>
          </div><p class="decomp-note">Ranked above CS3223 because it is required by more of your saved role profiles and is offered in both semesters, so it carries less scheduling risk.</p></div>` : ''}
        <button type="button" class="btn btn-ghost" style="margin-top:10px;font-size:12.5px" onclick="ask('addCs3230')">Add to study plan</button>
      </div>
      <div class="card" style="padding:18px">
        <div style="display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin-bottom:6px"><span class="tag tag-accent">84% match</span><span class="tag tag-outline">Closes: Databases &amp; data infrastructure</span><span class="tag tag-neutral">Module Agent · NUSMods</span></div>
        <div class="card-title" style="font-size:15.5px">CS3223 — Database Systems Implementation</div>
        <div class="card-meta" style="margin:4px 0 0">4 units · Offered Sem 2 · Prereq: CS2030S ✓ met, CS2040S ✓ met</div>
        <p class="card-body" style="font-size:13px;margin:8px 0 0">Closes your second-priority gap and pairs directly with the distributed KV store project.</p>
        ${whybtn('cs3223')}
        ${v.sc['cs3223'] ? `<div class="decomp"><div class="decomp-grid" style="grid-template-columns:1fr 1fr">
          <div><div class="decomp-k">Gap coverage</div><div class="decomp-v">81</div></div><div><div class="decomp-k">Role fit</div><div class="decomp-v">86</div></div>
          <div><div class="decomp-k">Time cost</div><div class="decomp-v">52</div></div><div><div class="decomp-k">Redundancy penalty</div><div class="decomp-v">−5</div></div>
          </div><p class="decomp-note">Higher gap coverage than CS3230 but lower role fit, and Sem 2 only — the scheduling constraint is what puts it second.</p></div>` : ''}
        <button type="button" class="btn btn-ghost" style="margin-top:10px;font-size:12.5px" onclick="ask('addCs3223')">Add to study plan</button>
      </div>
    </div>
    <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:6px">${icon(ICON_PAW, 16).replace('stroke="currentColor"', 'stroke="var(--color-accent-700)"')}<h2 style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:18px;margin:0">Project targets from GitHub Search</h2></div>
    <p style="font-size:12px;color:var(--color-neutral-600);margin:0 0 16px">40 repositories matched; 2 ranked above threshold. Ranked on gap coverage, not stars.</p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div class="card" style="padding:18px">
        <div style="display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin-bottom:6px"><span class="tag tag-accent">93% match</span><span class="tag tag-outline">Closes: Cloud &amp; deployment</span><span class="tag tag-neutral">Project Agent · GitHub Search</span></div>
        <div class="card-title" style="font-size:15.5px">Ship: distributed key-value store</div>
        <div class="card-meta" style="margin:4px 0 0">pingcap/talent-plan · Rust · 10.4k ★ · updated 6 days ago</div>
        <p class="card-body" style="font-size:13px;margin:8px 0 0">Staged reference curriculum you can deploy and write up — produces the deployment artefact your saved roles ask for.</p>
        ${whybtn('proj1')}
        ${v.sc['proj1'] ? `<div class="decomp"><div class="decomp-grid" style="grid-template-columns:1fr 1fr">
          <div><div class="decomp-k">Gap coverage</div><div class="decomp-v">91</div></div><div><div class="decomp-k">Role fit</div><div class="decomp-v">90</div></div>
          <div><div class="decomp-k">Time cost</div><div class="decomp-v">66</div></div><div><div class="decomp-k">Redundancy penalty</div><div class="decomp-v">−5</div></div>
          </div><p class="decomp-note">Highest gap coverage available to you, offset by the largest time cost in your plan.</p></div>` : ''}
        <button type="button" class="btn btn-ghost" style="margin-top:10px;font-size:12.5px">See repo</button>
      </div>
      <div class="card" style="padding:18px">
        <div style="display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin-bottom:6px"><span class="tag tag-accent">81% match</span><span class="tag tag-outline">Closes: Systems &amp; networks</span><span class="tag tag-neutral">Project Agent · GitHub Search</span></div>
        <div class="card-title" style="font-size:15.5px">Build: container runtime from scratch</div>
        <div class="card-meta" style="margin:4px 0 0">p8952/bocker · Shell · 12.1k ★ · updated 3 weeks ago</div>
        <p class="card-body" style="font-size:13px;margin:8px 0 0">Smaller scope than the KV store and directly reinforces CS2105 material you are covering now.</p>
        ${whybtn('proj2')}
        ${v.sc['proj2'] ? `<div class="decomp"><div class="decomp-grid" style="grid-template-columns:1fr 1fr">
          <div><div class="decomp-k">Gap coverage</div><div class="decomp-v">72</div></div><div><div class="decomp-k">Role fit</div><div class="decomp-v">84</div></div>
          <div><div class="decomp-k">Time cost</div><div class="decomp-v">39</div></div><div><div class="decomp-k">Redundancy penalty</div><div class="decomp-v">−11</div></div>
          </div><p class="decomp-note">Lowest time cost of the two, but penalised: CS2105 already generates systems &amp; networks evidence this semester.</p></div>` : ''}
        <button type="button" class="btn btn-ghost" style="margin-top:10px;font-size:12.5px">See repo</button>
      </div>
    </div>
  </div>`;
}

function filterBtn(label, key, v) {
  const active = state.filter === key;
  return `<button type="button" class="scenario-opt" style="border:1px solid ${active ? 'var(--color-accent-500)' : 'var(--color-divider)'};border-radius:var(--radius-md);${active ? 'background:var(--color-accent-100);color:var(--color-accent-700);' : ''}padding:4px 11px;font-size:11.5px" onclick="filterSet('${key}')">${label}</button>`;
}

function renderDecisionLog(v) {
  const doneRun = v.hasActions ? `<div style="display:flex;flex-direction:column;gap:16px">
    <div style="padding-bottom:9px;border-bottom:1px solid var(--color-divider)">
      <div style="font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--color-neutral-600);margin-bottom:3px">${v.actionRunLabel}</div>
      <div style="font-size:11px;color:var(--color-neutral-700);line-height:1.45">triggered by: you — approved an action</div>
    </div>
    ${v.doneItems.map(d => `<div style="display:grid;grid-template-columns:15px 1fr;gap:9px">
      <span class="stepno">${d.step}</span>
      <div>
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:5px">
          <span class="kindtag" style="border:1px solid var(--color-accent-500);color:var(--color-accent-700)">Action</span>
          ${d.auto ? '<span class="tag tag-neutral" style="font-size:9.5px">Auto-approved</span>' : '<span class="tag tag-neutral" style="font-size:9.5px">You approved</span>'}
        </div>
        <p style="margin:0;font-size:12.5px;line-height:1.55">${d.text}</p>
        <a onclick="undoDone('${d.id}')" style="font-size:11px;cursor:pointer;display:inline-block;margin-top:5px">Undo</a>
      </div>
    </div>`).join('')}
  </div>` : '';

  const run3 = v.showChanged ? `<div style="display:flex;flex-direction:column;gap:16px">
    <div style="padding-bottom:9px;border-bottom:1px solid var(--color-divider)">
      <div style="font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--color-neutral-600);margin-bottom:3px">Run 3</div>
      <div style="font-size:11px;color:var(--color-neutral-700);line-height:1.45">triggered by: outcome logged (BuildAI — not shortlisted)</div>
    </div>
    <div style="display:grid;grid-template-columns:15px 1fr;gap:9px"><span class="stepno">1</span><div>
      <div style="margin-bottom:5px"><span class="kindtag" style="border:1px solid var(--color-divider);color:var(--color-neutral-700)">Observed</span></div>
      <p style="margin:0;font-size:12.5px;line-height:1.55">Outcome logged for BuildAI: not shortlisted. Provisional hackathon evidence dropped from your profile state.</p>
    </div></div>
    <div style="display:grid;grid-template-columns:15px 1fr;gap:9px"><span class="stepno">2</span><div>
      <div style="margin-bottom:5px"><span class="kindtag" style="border:1px solid var(--color-accent-500);color:var(--color-accent-700)">Planned</span></div>
      <p style="margin:0;font-size:12.5px;line-height:1.55">Re-planned after outcome. Dispatched 2 of 3 sub-agents.</p>
      <button type="button" class="whybtn" style="margin-top:6px" onclick="toggleTrace()">${v.traceLabel}</button>
      ${v.traceOpen ? `<div class="tracebox">
        <div><div class="tracehd">Career Agent · plan</div><p class="tracenote">Critical gap is Cloud &amp; deployment. Hackathon outcome changed evidence held, not module eligibility. Dispatching Event Agent and Project Agent.</p></div>
        <div class="arow"><span style="font-size:11px;color:var(--color-accent-700);line-height:1.5">→</span><div><div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline"><span class="aname">Event Agent</span><span class="ameta" style="text-align:right;flex:none">4 results<br>2 above threshold</span></div><div class="ameta">Eventbrite + organiser pages</div></div></div>
        <div class="arow"><span style="font-size:11px;color:var(--color-accent-700);line-height:1.5">→</span><div><div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline"><span class="aname">Project Agent</span><span class="ameta" style="text-align:right;flex:none">40 repos<br>2 above threshold</span></div><div class="ameta">GitHub Search</div></div></div>
        <div style="border:1px dashed var(--color-divider);border-radius:var(--radius-md);padding:9px 10px;background:var(--color-neutral-100)"><div class="arow"><span style="font-size:11px;color:var(--color-neutral-600);line-height:1.5">⊘</span><div><div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline"><span class="aname" style="color:var(--color-neutral-700)">Module Agent</span><span class="ameta" style="flex:none">skipped</span></div><p class="tracenote" style="color:var(--color-neutral-600)">A hackathon outcome does not change prerequisite eligibility or module scores. Reusing cached component scores from run 1.</p></div></div></div>
        <div><div class="tracehd">Career Agent · merge</div><p class="tracenote">9 candidates → prerequisite filter → 6 → redundancy pass → 4 ranked.</p></div>
        <div><div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline"><span class="tracehd">Career Agent · refine</span><span class="ameta" style="flex:none">iteration 2 of 3 (cap)</span></div><p class="tracenote">Pass 1: 4 candidates, 2 closing the same gap.</p><p class="tracenote">Pass 2: redundancy penalty applied, ranking stable. Exiting before cap.</p></div>
        <p style="margin:9px 0 0;font-size:10.5px;color:var(--color-neutral-600);line-height:1.5">Every planning loop has a hard iteration cap held in state, so a run cannot circle indefinitely.</p>
      </div>` : ''}
    </div></div>
    <div style="display:grid;grid-template-columns:15px 1fr;gap:9px"><span class="stepno">3</span><div>
      <div style="margin-bottom:5px"><span class="kindtag" style="border:1px solid var(--color-accent-500);color:var(--color-accent-700)">Decided</span></div>
      <p style="margin:0;font-size:12.5px;line-height:1.55">Ranked the distributed KV store above HackNUS: same critical gap, higher coverage, and it needs nobody's shortlist.</p>
    </div></div>
    <div style="display:grid;grid-template-columns:15px 1fr;gap:9px"><span class="stepno">4</span><div>
      <div style="margin-bottom:5px"><span class="kindtag" style="background:var(--color-accent-100);color:var(--color-accent-700)">Changed</span></div>
      <p style="margin:0;font-size:12.5px;line-height:1.55">Readiness 62% → 60%. HackNUS and the KV store project moved up; Y3 internship applications now start a semester earlier.</p>
    </div></div>
  </div>` : '';

  const run2 = `<div style="display:flex;flex-direction:column;gap:16px">
    <div style="padding-bottom:9px;border-bottom:1px solid var(--color-divider)">
      <div style="font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--color-neutral-600);margin-bottom:3px">Run 2</div>
      <div style="font-size:11px;color:var(--color-neutral-700);line-height:1.45">triggered by: you — “Show hackathons better suited to my skills”</div>
    </div>
    ${v.showConv ? `<div style="display:grid;grid-template-columns:15px 1fr;gap:9px"><span class="stepno">1</span>
      <div style="align-self:start;max-width:100%;background:var(--color-accent-100);border-radius:var(--radius-md);padding:9px 12px">
        <div style="font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--color-accent-700);margin-bottom:3px">You</div>
        <p style="margin:0;font-size:12.5px;line-height:1.5">Show hackathons better suited to my skills.</p>
      </div></div>` : ''}
    ${v.showActivity ? `<div style="display:flex;flex-direction:column;gap:16px">
      <div style="display:grid;grid-template-columns:15px 1fr;gap:9px"><span class="stepno">2</span><div>
        <div style="margin-bottom:5px"><span class="kindtag" style="border:1px solid var(--color-accent-500);color:var(--color-accent-700)">Planned</span></div>
        <p style="margin:0;font-size:12.5px;line-height:1.55">Dispatched Event Agent and Project Agent. Module Agent skipped. One organiser fetch failed twice and fell back to cache.</p>
        <button type="button" class="whybtn" style="margin-top:6px" onclick="toggleTrace2()">${v.trace2Label}</button>
        ${v.trace2Open ? `<div class="tracebox">
          <div><div class="tracehd">Career Agent · plan</div><p class="tracenote">Instruction is scoped to events and evidence. Dispatching Event Agent and Project Agent; module eligibility is unaffected.</p></div>
          <div class="arow"><span style="font-size:11px;color:var(--color-accent-700);line-height:1.5">→</span><div><div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline"><span class="aname">Event Agent</span><span class="ameta" style="text-align:right;flex:none">6 events<br>4 backend track</span></div><div class="ameta">Eventbrite search · Singapore</div></div></div>
          <div style="border:1px dashed var(--color-divider);border-radius:var(--radius-md);padding:9px 10px"><div class="arow"><span style="font-size:11px;color:var(--color-accent-700);line-height:1.5">→</span><div><div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline"><span class="aname">Event Agent</span><span class="ameta" style="flex:none">recovered</span></div><div class="ameta">organiser page fetch</div><p class="tracenote" style="margin-top:5px">Attempt 1: timeout after 8s — nus computing club events page</p><p class="tracenote">Attempt 2: timeout after 8s</p><p class="tracenote">Fell back to cached listing from 2 runs ago.</p></div></div></div>
          <div class="arow"><span style="font-size:11px;color:var(--color-accent-700);line-height:1.5">→</span><div><div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline"><span class="aname">Project Agent</span><span class="ameta" style="text-align:right;flex:none">40 repos<br>2 above threshold</span></div><div class="ameta">GitHub Search</div></div></div>
          <div style="border:1px dashed var(--color-divider);border-radius:var(--radius-md);padding:9px 10px;background:var(--color-neutral-100)"><div class="arow"><span style="font-size:11px;color:var(--color-neutral-600);line-height:1.5">⊘</span><div><div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline"><span class="aname" style="color:var(--color-neutral-700)">Module Agent</span><span class="ameta" style="flex:none">skipped</span></div><p class="tracenote" style="color:var(--color-neutral-600)">The instruction concerned events, not coursework. Module scores and eligibility reused from run 1.</p></div></div></div>
          <div><div class="tracehd">Career Agent · merge</div><p class="tracenote">7 candidates → prerequisite filter → 5 → redundancy pass → 3 ranked.</p></div>
        </div>` : ''}
      </div></div>
      <div style="display:grid;grid-template-columns:15px 1fr;gap:9px"><span class="stepno">3</span><div>
        <div style="margin-bottom:5px"><span class="kindtag" style="border:1px solid var(--color-accent-500);color:var(--color-accent-700)">Decided</span></div>
        <p style="margin:0;font-size:12.5px;line-height:1.55">Deprioritised Fintech Sprint 2026: redundancy penalty 12, role fit 52. Kept visible in search, off the dashboard.</p>
      </div></div>
    </div>` : ''}
    ${v.showConv ? `<div style="display:grid;grid-template-columns:15px 1fr;gap:9px"><span class="stepno">4</span><div>
      <div style="margin-bottom:5px"><span class="kindtag" style="border:1px solid var(--color-accent-500);color:var(--color-accent-700)">Agent</span></div>
      <p style="margin:0;font-size:12.5px;line-height:1.55">Filtered to backend and infrastructure tracks. Re-ranked 3 results. HackNUS details are from cache — I couldn't reach the organiser page.</p>
    </div></div>` : ''}
    ${v.seedLive ? `<div style="display:grid;grid-template-columns:15px 1fr;gap:9px"><span class="stepno">5</span><div>
      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:5px"><span class="kindtag" style="border:1px solid var(--color-accent-500);color:var(--color-accent-700)">Action</span><span class="tag tag-neutral" style="font-size:9.5px">Auto-approved</span></div>
      <p style="margin:0;font-size:12.5px;line-height:1.55">Saved BuildAI Hackathon to your shortlist.</p>
      <a onclick="undoSeed()" style="font-size:11px;cursor:pointer;display:inline-block;margin-top:5px">Undo</a>
    </div></div>` : ''}
    ${v.seedUndone ? `<div style="display:grid;grid-template-columns:15px 1fr;gap:9px"><span class="stepno">5</span><div>
      <div style="margin-bottom:5px"><span class="kindtag" style="border:1px solid var(--color-divider);color:var(--color-neutral-700)">Action</span></div>
      <p style="margin:0;font-size:12.5px;line-height:1.55;color:var(--color-neutral-600)">Undone: BuildAI Hackathon removed from your shortlist. Auto-approve for saving to shortlist is still on.</p>
    </div></div>` : ''}
  </div>`;

  const run1 = v.showActivity ? `<div style="display:flex;flex-direction:column;gap:16px">
    <div style="padding-bottom:9px;border-bottom:1px solid var(--color-divider)">
      <div style="font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--color-neutral-600);margin-bottom:3px">Run 1</div>
      <div style="font-size:11px;color:var(--color-neutral-700);line-height:1.45">triggered by: onboarding complete</div>
    </div>
    <div style="display:grid;grid-template-columns:15px 1fr;gap:9px"><span class="stepno">1</span><div><div style="margin-bottom:5px"><span class="kindtag" style="border:1px solid var(--color-divider);color:var(--color-neutral-700)">Observed</span></div><p style="margin:0;font-size:12.5px;line-height:1.55">Profile Agent parsed your transcript: 18 modules complete, 3 in progress, 72 of 160 units. Resume: 6 skills extracted.</p></div></div>
    <div style="display:grid;grid-template-columns:15px 1fr;gap:9px"><span class="stepno">2</span><div><div style="margin-bottom:5px"><span class="kindtag" style="border:1px solid var(--color-divider);color:var(--color-neutral-700)">Observed</span></div><p style="margin:0;font-size:12.5px;line-height:1.55">CS2105 in progress with a graded component posted — systems &amp; networks scored 48%.</p></div></div>
    <div style="display:grid;grid-template-columns:15px 1fr;gap:9px"><span class="stepno">3</span><div><div style="margin-bottom:5px"><span class="kindtag" style="border:1px solid var(--color-accent-500);color:var(--color-accent-700)">Decided</span></div><p style="margin:0;font-size:12.5px;line-height:1.55">Module Agent prerequisite check against transcript: CS3230 eligible, CS3223 eligible, CS4231 blocked (CS3230 not met).</p></div></div>
    <div style="display:grid;grid-template-columns:15px 1fr;gap:9px"><span class="stepno">4</span><div><div style="margin-bottom:5px"><span class="kindtag" style="border:1px solid var(--color-divider);color:var(--color-neutral-700)">Observed</span></div><p style="margin:0;font-size:12.5px;line-height:1.55">Project Agent · GitHub Search: 40 repositories matching “distributed key-value store”, 2 ranked above threshold.</p></div></div>
    <div style="display:grid;grid-template-columns:15px 1fr;gap:9px"><span class="stepno">5</span><div><div style="margin-bottom:5px"><span class="kindtag" style="border:1px solid var(--color-accent-500);color:var(--color-accent-700)">Decided</span></div><p style="margin:0;font-size:12.5px;line-height:1.55">Ranked CS3230 above CS3223 for next semester: required by 3 of 4 saved role profiles, prerequisites met.</p></div></div>
  </div>` : '';

  return `<div style="width:326px;flex:none;border-left:1px solid var(--color-divider);display:flex;flex-direction:column;box-sizing:border-box">
    <div style="padding:18px 20px 14px;border-bottom:1px solid var(--color-divider)">
      <div style="display:flex;align-items:center;gap:9px;margin-bottom:12px">${icon(ICON_SPARK, 16).replace('stroke="currentColor"', 'stroke="var(--color-accent-700)"')}<div><div style="font-family:var(--font-heading);font-weight:var(--font-heading-weight);font-size:15px">Career Agent</div><div style="font-size:11px;color:var(--color-neutral-600)">Decision log · accepts instructions</div></div></div>
      <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px">
        <button type="button" class="btn btn-secondary" style="font-size:11.5px;padding:5px 11px" onclick="refreshSources()">${icon(ICON_REFRESH, 12)}Refresh sources</button>
        ${v.refreshed ? '<span style="font-size:10.5px;color:var(--color-neutral-600);line-height:1.4;text-align:right">Re-checked · no new results above threshold</span>' : ''}
      </div>
      <p style="margin:0 0 11px;font-size:11px;color:var(--color-neutral-600);line-height:1.5">The agent runs when you ask it to, or when your profile changes.</p>
      <div style="display:flex;gap:6px">${filterBtn('All', 'All', v)}${filterBtn('Activity', 'Activity', v)}${filterBtn('Conversation', 'Conversation', v)}</div>
    </div>
    <div style="flex:1;overflow:auto;padding:16px 18px;display:flex;flex-direction:column;gap:16px">
      ${doneRun}${run3}${run2}${run1}
    </div>
    <div style="padding:14px 16px;border-top:1px solid var(--color-divider);display:flex;gap:8px">
      <input class="input" placeholder="Ask the agent to adjust your plan" style="flex:1;font-size:12.5px">
      <button type="button" class="btn btn-primary btn-icon" aria-label="Send">${icon(ICON_ARROW, 14)}</button>
    </div>
  </div>`;
}

function renderApprovalDialog(v) {
  if (!v.approvalOpen) return '';
  return `<div class="dialog-backdrop">
    <div class="dialog" style="width:min(540px,100%)">
      <div class="dialog-title">Approve this action</div>
      <div style="display:flex;flex-direction:column;gap:11px">
        <div style="display:grid;grid-template-columns:62px 1fr;gap:12px;align-items:baseline"><span style="font-size:10px;letter-spacing:.09em;text-transform:uppercase;color:var(--color-neutral-600)">What</span><span style="font-size:13.5px;line-height:1.5">${v.apWhat}</span></div>
        <div style="display:grid;grid-template-columns:62px 1fr;gap:12px;align-items:baseline"><span style="font-size:10px;letter-spacing:.09em;text-transform:uppercase;color:var(--color-neutral-600)">Data</span><span style="font-size:13px;line-height:1.5;color:var(--color-neutral-700)">${v.apData}</span></div>
        <div style="display:grid;grid-template-columns:62px 1fr;gap:12px;align-items:baseline"><span style="font-size:10px;letter-spacing:.09em;text-transform:uppercase;color:var(--color-neutral-600)">Where</span><span style="font-size:13px;line-height:1.5;color:var(--color-neutral-700)">${v.apDest}</span></div>
        <div style="display:grid;grid-template-columns:62px 1fr;gap:12px;align-items:baseline"><span style="font-size:10px;letter-spacing:.09em;text-transform:uppercase;color:var(--color-neutral-600)">Why</span><span style="font-size:13px;line-height:1.5;color:var(--color-accent-700)">${v.apWhy}</span></div>
      </div>
      ${v.apDraft ? '<p style="margin:0;font-size:12px;line-height:1.55;color:var(--color-neutral-700);border-left:2px solid var(--color-accent-500);padding-left:11px">The agent prepares the draft and leaves it for you to check. Submitting is a separate action you take yourself — nothing is sent until you do.</p>' : ''}
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
  const row = (label, bg, pos, fn) => `<div style="display:flex;align-items:center;justify-content:space-between;gap:16px;padding:13px 0;border-top:1px solid var(--color-divider)">
    <div><div style="font-size:13.5px">${label}</div><div style="font-size:11.5px;color:var(--color-neutral-600)">auto-approve</div></div>
    <button type="button" class="swpill" aria-label="Auto-approve ${label.toLowerCase()}" style="background:${bg};justify-content:${pos}" onclick="${fn}"><span style="width:14px;height:14px;border-radius:50%;background:var(--color-surface)"></span></button>
  </div>`;
  return `<div class="dialog-backdrop">
    <div class="dialog" style="width:min(520px,100%)">
      <div class="dialog-title">Automation</div>
      <p class="dialog-body" style="margin:0">Choose which actions your agent may take without asking. Everything else waits for your approval.</p>
      <div style="display:flex;flex-direction:column">
        ${row('Save to shortlist', v.sw1bg, v.sw1pos, "toggleAuto('shortlist')")}
        ${row('Add to study plan', v.sw2bg, v.sw2pos, "toggleAuto('studyPlan')")}
        ${row('Draft application', v.sw3bg, v.sw3pos, "toggleAuto('draftApp')")}
        <div style="display:flex;align-items:center;justify-content:space-between;gap:16px;padding:13px 0;border-top:1px solid var(--color-divider);opacity:.5">
          <div><div style="font-size:13.5px">Submit application</div><div style="font-size:11.5px;color:var(--color-neutral-600)">always requires approval</div></div>
          <button type="button" class="swpill" disabled aria-label="Submitting always requires approval" style="background:var(--color-neutral-400);justify-content:flex-start;cursor:not-allowed"><span style="width:14px;height:14px;border-radius:50%;background:var(--color-surface)"></span></button>
        </div>
      </div>
      <p style="margin:0;font-size:11.5px;color:var(--color-neutral-600);line-height:1.55">Submission is never automated. Auto-approved actions still appear in your decision log and can be undone.</p>
      <div class="dialog-actions"><button type="button" class="btn btn-primary" onclick="closeSettings()">Done</button></div>
    </div>
  </div>`;
}

function render() {
  const v = computeVals();
  const root = document.getElementById('app');
  if (v.isOnboarding) {
    root.innerHTML = renderOnboarding(v);
    return;
  }
  const screenBody = v.isDashboard ? renderDashboard(v)
    : v.isHackathons ? renderHackathons(v)
    : v.isInternships ? renderInternships(v)
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
