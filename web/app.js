(() => {
  "use strict";

  const state = {
    data: null,
    route: "home",
    params: [],
    filter: "all",
    galleryFilter: "All",
    conversation: [],
    conversationId: "judge-demo",
    busy: false,
    lastAnswer: null,
    apiOnline: false,
    runtime: null,
  };

  const main = document.querySelector("#main");
  const modal = document.querySelector("#modal");
  const modalContent = document.querySelector("#modal-content");
  const toast = document.querySelector("#toast");

  const icon = (name, className = "") =>
    `<svg class="${className}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;

  const escapeHtml = (value = "") => String(value).replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[character]));

  const formatDate = (value) => new Intl.DateTimeFormat("en", {
    month: "short", day: "numeric", year: "numeric",
  }).format(new Date(value));

  const percent = (value) => `${Math.round(value * 100)}%`;

  async function loadData() {
    try {
      const response = await fetch("/api/v1/bootstrap", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`API ${response.status}`);
      state.data = await response.json();
      state.apiOnline = true;
      const health = await fetch("/health", { headers: { Accept: "application/json" } });
      if (health.ok) state.runtime = await health.json();
    } catch (_error) {
      const response = await fetch("/fixtures/demo.json");
      if (!response.ok) throw new Error("The bundled demo fixture could not be loaded.");
      state.data = await response.json();
      state.apiOnline = false;
      state.runtime = { mode: "demo", live_models: false, model: "gemini-3.7-flash", triage_model: "gemini-3.5-flash-lite", embedding_model: "gemini-embedding-2" };
      const persisted = readLocalCorrections();
      state.data.memory.corrections = persisted;
    }
    document.querySelector("#sync-label").textContent = `Synced ${state.data.summary.last_sync}`;
    document.querySelector("#nav-subject-count").textContent = state.data.subjects.length;
    const runtimeLabel = document.querySelector("#runtime-label");
    const runtimePill = document.querySelector("#runtime-pill");
    if (runtimeLabel) runtimeLabel.textContent = state.runtime?.live_models ? "Gemini live" : "Sample world";
    runtimePill?.classList.toggle("live", Boolean(state.runtime?.live_models));
    route();
  }

  function readLocalCorrections() {
    try { return JSON.parse(localStorage.getItem("realitydiff-corrections") || "[]"); }
    catch (_error) { return []; }
  }

  function writeLocalCorrection(correction) {
    const current = readLocalCorrections();
    current.push(correction);
    localStorage.setItem("realitydiff-corrections", JSON.stringify(current));
    state.data.memory.corrections = current;
  }

  function route() {
    if (!state.data) return;
    const raw = location.hash.replace(/^#\/?/, "") || "home";
    const [name, ...params] = raw.split("/").filter(Boolean);
    state.route = name;
    state.params = params;
    document.querySelectorAll("[data-route]").forEach((item) => {
      const target = item.dataset.route;
      const active = target === name || (name === "subject" && target === "reality") || (name === "use-case" && target === "use-cases");
      item.classList.toggle("active", active);
      if (active) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });

    const renderers = {
      home: renderHome,
      gallery: renderGallery,
      reality: renderReality,
      subject: () => renderSubject(params[0]),
      "use-cases": renderUseCases,
      "use-case": () => renderUseCase(params[0]),
      timeline: renderTimeline,
      ask: renderAsk,
      sources: renderSources,
      memory: renderMemory,
    };
    (renderers[name] || renderNotFound)();
    window.scrollTo({ top: 0, behavior: "instant" });
    main.focus({ preventScroll: true });
  }

  function renderHome() {
    const d = state.data;
    const office = subject("home-office");
    const latest = office.changes[office.changes.length - 2];
    main.innerHTML = `
      <div class="page">
        <section class="home-hero">
          <div class="hero-copy">
            <p class="eyebrow">Your world · reconstructed</p>
            <h1 class="page-title">Photos remember moments.<br>Reality Diff remembers <em>state.</em></h1>
            <p class="page-intro">Ask what changed, when it changed, and what the original photographs actually prove.</p>
            <div class="hero-actions">
              <a class="primary-button violet" href="/#ask">${icon("ask")} Ask your world</a>
              <a class="secondary-button" href="/#reality">Explore realities ${icon("arrow")}</a>
            </div>
          </div>
          <div class="hero-visual">
            <img src="${office.cover}" alt="A home office with a light ergonomic chair, an ultrawide monitor and a plant">
            <div class="hero-change"><small>Change detected</small><strong>${latest.title}</strong></div>
            <span class="hero-date">${latest.when}</span>
          </div>
        </section>

        <section class="stats-strip" aria-label="World summary">
          ${stat(d.summary.photos_indexed, "photos indexed")}
          ${stat(d.summary.subjects, "recurring realities")}
          ${stat(d.summary.changes, "supported changes")}
          ${stat(d.summary.history_months, "months of history")}
        </section>

        <div class="section-head"><h2>Your recent photos</h2><a href="/#gallery">Open gallery →</a></div>
        <section class="photo-preview-grid">${galleryPhotos().slice(0, 7).map((item, index) => galleryTile(item, index, true)).join("")}</section>

        <div class="section-head"><h2>Reality, organised</h2><a href="/#reality">See the whole world →</a></div>
        <section class="subject-grid">${d.subjects.map(subjectCard).join("")}</section>

        <div class="section-head"><h2>Recent changes</h2><a href="/#timeline">Open timeline →</a></div>
        <section class="change-list">
          ${changeCard(office, office.changes[1])}
          ${changeCard(subject("white-rental-car"), subject("white-rental-car").changes[1])}
          ${changeCard(subject("blue-bike-project"), subject("blue-bike-project").changes[4])}
        </section>

        <section class="ask-banner">
          <div><h2>What do you want to remember?</h2><p>Answers are bounded by photo evidence. Missing views stay missing.</p></div>
          <a class="primary-button" href="/#ask">Ask Reality Diff ${icon("arrow")}</a>
        </section>
      </div>`;
  }

  function galleryPhotos() {
    const subjectKinds = Object.fromEntries(state.data.subjects.map((item) => [item.id, item.kind]));
    const evidence = state.data.assets.map((item) => ({
      id: `evidence-${item.id}`,
      image: item.image,
      captured_at: item.captured_at,
      title: item.label,
      category: ({ space: "Places", vehicle: "Things", project: "Projects", plant: "Plants" })[subjectKinds[item.subject_id]] || "Everyday",
      location: subject(item.subject_id)?.name || "Evidence sequence",
      source: item.source,
      origin: "Synthetic evidence fixture",
      evidence_id: item.id,
      status: "analyzed",
      analysis: { description: item.observation, embedding_dimensions: 768, pipeline: { execution: "fixture", reasoning_model: state.data.meta.model } },
    }));
    return [...(state.data.gallery || []), ...evidence]
      .sort((left, right) => new Date(right.captured_at) - new Date(left.captured_at));
  }

  function renderGallery() {
    const all = galleryPhotos();
    const categories = ["All", ...new Set(all.map((item) => item.category))];
    const photos = state.galleryFilter === "All" ? all : all.filter((item) => item.category === state.galleryFilter);
    const grouped = Object.groupBy ? Object.groupBy(photos, (item) => monthKey(item.captured_at)) : photos.reduce((result, item) => {
      const key = monthKey(item.captured_at);
      (result[key] ||= []).push(item);
      return result;
    }, {});
    main.innerHTML = `<div class="page gallery-page">
      <header class="page-head gallery-head"><div><p class="eyebrow">Your connected library</p><h1 class="page-title">Photos</h1><p class="page-intro">Moments stay familiar. Gemini quietly connects the ones that describe the same physical world.</p></div><div class="page-actions"><button class="secondary-button" data-action="add-photos">${icon("plus")} Add photos</button></div></header>
      <div class="gallery-toolbar"><div class="filter-row" role="group" aria-label="Filter gallery">${categories.map((name) => `<button class="filter-chip ${state.galleryFilter === name ? "active" : ""}" data-gallery-filter="${escapeHtml(name)}">${escapeHtml(name)}</button>`).join("")}</div><span>${photos.length} photos</span></div>
      ${Object.entries(grouped).map(([month, values]) => `<section class="gallery-month"><header><h2>${escapeHtml(month)}</h2><span>${values.length} photos</span></header><div class="gallery-grid">${values.map((item, index) => galleryTile(item, index)).join("")}</div></section>`).join("")}
      ${photos.length ? "" : `<div class="empty-gallery">${icon("gallery")}<h2>No photos in this view</h2><p>Try another category or add a few photos from your library.</p></div>`}
    </div>`;
  }

  function monthKey(value) {
    return new Intl.DateTimeFormat("en", { month: "long", year: "numeric" }).format(new Date(value));
  }

  function galleryTile(item, index, compact = false) {
    const status = item.status === "queued" ? `<span class="photo-ai-state">Queued</span>` : item.status === "analysis_failed" ? `<span class="photo-ai-state error">Retry</span>` : "";
    return `<button class="gallery-tile ${compact ? "compact-tile" : ""} shape-${index % 7}" data-gallery-item="${escapeHtml(item.id)}" aria-label="Open ${escapeHtml(item.title)}"><img src="${item.image}" alt="${escapeHtml(item.title)}" loading="${compact ? "eager" : "lazy"}">${status}<span class="gallery-overlay"><strong>${escapeHtml(item.title)}</strong><small>${formatDate(item.captured_at)}</small></span></button>`;
  }

  function stat(value, label) {
    return `<div class="stat"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`;
  }

  function subjectCard(item) {
    return `<article class="subject-card" role="link" tabindex="0" data-go="subject/${item.id}" aria-label="Open ${escapeHtml(item.name)}">
      <div class="subject-photo"><img src="${item.cover}" alt="" loading="lazy"><span class="photo-count">${item.photo_count} photos</span></div>
      <div class="subject-body">
        <div class="subject-top"><h3>${escapeHtml(item.name)}</h3><span class="confidence-ring" style="--score:${percent(item.confidence)}"><span>${Math.round(item.confidence * 100)}</span></span></div>
        <p>${escapeHtml(item.summary)}</p>
        <div class="subject-meta"><span>${escapeHtml(item.duration)}</span><span>${item.changes.length} changes</span></div>
      </div>
    </article>`;
  }

  function changeCard(item, change) {
    const unverifiable = change.type === "UNVERIFIABLE";
    return `<article class="change-card" role="link" tabindex="0" data-go="subject/${item.id}">
      <span class="change-type"><i style="background:${unverifiable ? "var(--amber)" : "var(--violet)"}"></i>${escapeHtml(change.type.replaceAll("_", " "))}</span>
      <h3>${escapeHtml(change.title)}</h3><p>${escapeHtml(item.name)} · ${escapeHtml(change.when)}</p>
    </article>`;
  }

  function renderReality() {
    const filters = ["all", "space", "vehicle", "project", "plant"];
    const subjects = state.filter === "all" ? state.data.subjects : state.data.subjects.filter((item) => item.kind === state.filter);
    main.innerHTML = `<div class="page">
      <header class="page-head"><div><p class="eyebrow">Semantic world</p><h1 class="page-title">Your realities</h1><p class="page-intro">Recurring places, objects and projects discovered across ordinary photos—not manually created albums.</p></div><div class="page-actions"><button class="secondary-button" data-action="add-photos">${icon("plus")} Index new photos</button></div></header>
      <div class="filter-row" role="group" aria-label="Filter realities">${filters.map((name) => `<button class="filter-chip ${state.filter === name ? "active" : ""}" data-filter="${name}">${name === "all" ? "All realities" : `${name[0].toUpperCase()}${name.slice(1)}s`}</button>`).join("")}</div>
      <section class="subject-grid">${subjects.map(subjectCard).join("")}</section>
      <div class="honesty-callout">${icon("shield")}<div><strong>Discovery, not surveillance.</strong><br>Only photos you connect are indexed. Screenshots and near-duplicates are filtered before semantic analysis, and every imported photo can be removed.</div></div>
    </div>`;
  }

  function renderSubject(id) {
    const item = subject(id);
    if (!item) return renderNotFound();
    const isCar = item.id === "white-rental-car";
    main.innerHTML = `<div class="page">
      <a class="back-link" href="/#reality">${icon("arrow")} All realities</a>
      <section class="detail-hero"><img src="${item.cover}" alt=""><div class="detail-hero-copy"><p class="eyebrow">${escapeHtml(item.kind)} · ${Math.round(item.confidence * 100)}% identity confidence</p><h1>${escapeHtml(item.name)}</h1><p>${escapeHtml(item.summary)}</p><div class="detail-meta"><span>${item.photo_count} photos</span><span>${escapeHtml(item.range)}</span><span>${item.changes.length} supported changes</span></div></div></section>
      <div class="detail-grid">
        <section class="panel"><header class="panel-head"><h2>${item.kind === "project" ? "Project stages" : "Change history"}</h2><span>Evidence-linked</span></header><div class="panel-body"><div class="timeline-list">${item.changes.map((change) => timelineEvent(item, change)).join("")}</div></div></section>
        <div>
          <section class="panel"><header class="panel-head"><h3>Latest known state</h3></header><div class="panel-body"><div class="state-chips">${item.latest_state.map((value) => `<span class="state-chip">${escapeHtml(value)}</span>`).join("")}</div></div></section>
          <section class="panel" style="margin-top:18px"><header class="panel-head"><h3>Evidence coverage</h3><span>${percent(item.coverage.score)}</span></header><div class="panel-body"><div class="coverage-meter"><span style="width:${percent(item.coverage.score)}"></span></div><p class="coverage-copy">${escapeHtml(item.coverage.note)}</p>${isCar ? viewCoverage(item.coverage.views) : ""}</div></section>
          <section class="panel" style="margin-top:18px"><div class="panel-body"><p class="eyebrow">Ask this reality</p><button class="primary-button violet" style="width:100%" data-ask-subject="${item.id}">${icon("ask")} Ask about ${escapeHtml(item.name)}</button></div></section>
        </div>
      </div>
    </div>`;
  }

  function timelineEvent(item, change) {
    return `<article class="timeline-event ${change.type === "UNVERIFIABLE" ? "unverifiable" : ""}"><i></i><div><h3>${escapeHtml(change.title)}</h3><p>${escapeHtml(change.when)} · ${Math.round(change.confidence * 100)}% confidence</p></div><button data-evidence="${change.evidence.join(",")}" data-change-title="${escapeHtml(change.title)}">View evidence</button></article>`;
  }

  function viewCoverage(views) {
    return `<div class="view-grid"><b>View</b><b>Pickup</b><b>Return</b>${views.map((view) => `<span>${escapeHtml(view.name)}</span><strong class="${view.pickup ? "yes" : "no"}">${view.pickup ? "✓" : "—"}</strong><strong class="${view.return ? "yes" : "no"}">${view.return ? "✓" : "—"}</strong>`).join("")}</div>`;
  }

  function renderUseCases() {
    main.innerHTML = `<div class="page"><header class="page-head"><div><p class="eyebrow">Use cases</p><h1 class="page-title">Useful views over the same world</h1><p class="page-intro">Reality Diff proposes cases from photo history. You can also start one deliberately; both paths use the same evidence model.</p></div></header><section class="usecase-grid">${state.data.use_cases.map(useCaseCard).join("")}</section></div>`;
  }

  function useCaseCard(item) {
    return `<article class="usecase-card ${item.accent}" role="link" tabindex="0" data-go="use-case/${item.id}"><div class="usecase-icon">${item.name.split(" ").map((word) => word[0]).join("").slice(0,2)}</div><small>${escapeHtml(item.eyebrow)}</small><h3>${escapeHtml(item.name)}</h3><p>${escapeHtml(item.description)}</p><div class="usecase-found"><span>${escapeHtml(item.found)}</span>${icon("arrow")}</div></article>`;
  }

  function renderUseCase(id) {
    const useCase = state.data.use_cases.find((item) => item.id === id);
    if (!useCase) return renderNotFound();
    if (useCase.subject_id) return renderSubject(useCase.subject_id);
    main.innerHTML = `<div class="page"><a class="back-link" href="/#use-cases">${icon("arrow")} All use cases</a><header class="page-head"><div><p class="eyebrow">${escapeHtml(useCase.eyebrow)}</p><h1 class="page-title">${escapeHtml(useCase.name)}</h1><p class="page-intro">${escapeHtml(useCase.description)}</p></div></header><section class="panel"><div class="panel-body" style="padding:40px;text-align:center"><div class="usecase-icon" style="margin:0 auto">${icon("camera")}</div><h2>Build this record from your photos</h2><p class="page-intro" style="margin:8px auto 22px">Search the connected world automatically or add a deliberate set of photos.</p><div class="hero-actions" style="justify-content:center"><button class="primary-button violet" data-action="find-photos">${icon("spark")} Find from my photos</button><button class="secondary-button" data-action="add-photos">${icon("plus")} Add photos</button></div></div></section></div>`;
  }

  function renderTimeline() {
    const events = state.data.subjects.flatMap((item) => item.changes.map((change) => ({ item, change })));
    main.innerHTML = `<div class="page"><header class="page-head"><div><p class="eyebrow">Across realities</p><h1 class="page-title">Timeline</h1><p class="page-intro">Meaningful changes reconstructed from observations. The date shown is exact only when the photographs support it.</p></div></header><section class="panel"><div class="panel-body"><div class="timeline-list">${events.map(({ item, change }) => `<article class="timeline-event ${change.type === "UNVERIFIABLE" ? "unverifiable" : ""}"><i></i><div><h3>${escapeHtml(change.title)}</h3><p>${escapeHtml(item.name)} · ${escapeHtml(change.when)}</p></div><button data-go="subject/${item.id}">Open</button></article>`).join("")}</div></div></section></div>`;
  }

  function renderAsk() {
    if (!state.conversation.length) {
      state.conversation = [{ role: "agent", answer: {
        status: "answered", title: "What do you want to know?",
        text: "I can reason across your connected photos, explain the evidence behind an answer, or tell you when the necessary view is missing.",
        confidence_label: "not_applicable", evidence: [], choices: [], steps: [],
      }}];
    }
    main.innerHTML = `<div class="page"><header class="page-head"><div><p class="eyebrow">Collaborative partner</p><h1 class="page-title">Ask your physical history</h1><p class="page-intro">Every factual answer can be opened back to its source photographs.</p></div></header><div class="ask-page"><section class="chat-card"><header class="chat-head"><span class="agent-avatar">${icon("spark")}</span><div><strong>Reality Diff</strong><small>Evidence-first temporal agent</small></div><span class="chat-status"><i></i>${state.apiOnline ? "Shared API" : "Offline fixture"}</span></header><div class="messages" id="messages">${state.conversation.map(messageHtml).join("")}</div><form class="chat-form" id="chat-form"><textarea id="question" name="question" rows="1" maxlength="500" placeholder="Ask when something changed…" aria-label="Ask a question"></textarea><button type="submit" aria-label="Send question" ${state.busy ? "disabled" : ""}>${state.busy ? "…" : icon("arrow")}</button></form></section><aside class="quick-panel"><section class="quick-card"><h2>Try a real question</h2><div class="prompt-list">${quickPrompts().map((prompt) => `<button class="prompt-button" data-prompt="${escapeHtml(prompt)}"><span>${escapeHtml(prompt)}</span>${icon("chevron")}</button>`).join("")}</div></section><section class="quick-card"><h2>Memory in use</h2><div class="memory-mini">${memorySummary()}</div><a class="ghost-button" style="width:100%;margin-top:10px" href="/#memory">Inspect memory ${icon("arrow")}</a></section></aside></div></div>`;
    requestAnimationFrame(() => { const messages = document.querySelector("#messages"); if (messages) messages.scrollTop = messages.scrollHeight; });
  }

  function quickPrompts() {
    return [
      "When did I replace my chair?",
      "Was this scratch already there?",
      "Was the rear-right scratch already there at pickup?",
      "Show me how the bike restoration evolved.",
    ];
  }

  function memorySummary() {
    const aliases = state.data.memory.aliases.slice(0, 2);
    const corrections = state.data.memory.corrections.slice(-1);
    return [...aliases.map((item) => `${item.term} means ${item.means}`), ...corrections.map((item) => item.statement)]
      .map((text) => `<div>${icon("check")}<span>${escapeHtml(text)}</span></div>`).join("") || `<div>${icon("check")}<span>Corrections you make here carry into later questions.</span></div>`;
  }

  function messageHtml(message) {
    if (message.role === "user") return `<article class="message user"><div class="message-bubble">${escapeHtml(message.text)}</div><div class="message-meta">You · now</div></article>`;
    const answer = message.answer;
    const confidence = answer.confidence_label && answer.confidence_label !== "not_applicable" ? `<span class="confidence-badge ${answer.confidence_label === "low" ? "low" : ""}">${answer.confidence_label} confidence${answer.confidence ? ` · ${Math.round(answer.confidence * 100)}%` : ""}</span>` : "";
    const evidence = (answer.evidence || []).length ? `<div class="evidence-row">${answer.evidence.map((item) => `<button class="evidence-mini" data-asset="${item.asset_id}"><img src="${item.image}" alt=""><span>${escapeHtml(item.label)} · ${formatDate(item.captured_at)}</span></button>`).join("")}</div>` : "";
    const choices = (answer.choices || []).length ? `<div class="choice-row">${answer.choices.map((choice) => `<button class="choice-button" data-choice="${escapeHtml(choice)}">${escapeHtml(choice)}</button>`).join("")}</div>` : "";
    const coverage = answer.coverage_note ? `<div class="answer-coverage"><strong>Coverage:</strong> ${escapeHtml(answer.coverage_note)}</div>` : "";
    const actions = (answer.steps || []).length ? `<div class="answer-actions"><button data-why="${answer.answer_id || "welcome"}">${icon("eye")} Why this answer?</button><button data-action="correct-answer">Correct this</button></div>` : "";
    return `<article class="message agent"><div class="message-bubble"><h3>${escapeHtml(answer.title)}</h3><div>${escapeHtml(answer.text)}</div>${coverage}${evidence}${choices}${actions}${answer.follow_up ? `<p style="margin:10px 0 0;color:var(--muted);font-size:11px">${escapeHtml(answer.follow_up)}</p>` : ""}</div><div class="message-meta">Reality Diff · now ${confidence}</div></article>`;
  }

  async function askQuestion(question) {
    const cleaned = question.trim();
    if (!cleaned || state.busy) return;
    state.conversation.push({ role: "user", text: cleaned });
    state.busy = true;
    renderAsk();
    let answer;
    if (state.apiOnline) {
      try {
        const response = await fetch("/api/v1/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: cleaned, conversation_id: state.conversationId }) });
        if (!response.ok) throw new Error(`API ${response.status}`);
        answer = await response.json();
      } catch (_error) {
        state.apiOnline = false;
        answer = localAnswer(cleaned);
      }
    } else answer = localAnswer(cleaned);
    state.lastAnswer = answer;
    state.conversation.push({ role: "agent", answer });
    state.busy = false;
    renderAsk();
  }

  function localAnswer(question) {
    const q = question.toLowerCase();
    const evidence = (...ids) => ids.map((id) => asset(id)).filter(Boolean);
    const steps = (detail, status = "complete") => [
      { name: "Understand", status: "complete", detail: "Resolved the question to a subject and physical entity." },
      { name: "Retrieve", status, detail },
      { name: "Verify", status: "complete", detail: "Checked temporal order, region coverage and contradictory evidence." },
      { name: "Answer", status, detail: status === "complete" ? "Returned the narrowest supported claim." : "Stopped before an unsupported claim." },
    ];
    const base = { answer_id: `local_${Date.now()}`, subject_id: null, evidence: [], coverage_note: null, follow_up: null, choices: [], steps: [] };
    if (q.includes("chair")) return { ...base, status: "answered", title: "Your chair changed between June 4 and June 11", text: "The dark mesh chair is last clearly visible on June 4. The sand-coloured ergonomic chair first appears on June 11. There is no clear workspace photo between those dates, so I can narrow the replacement to that seven-day window, not a single day.", confidence: .96, confidence_label: "high", subject_id: "home-office", evidence: evidence("office-jun-04", "office-jun-11"), coverage_note: "No usable home-office photo was captured from June 5–10.", follow_up: "Want me to show the monitor and plant changes from the same week?", steps: steps("Compared 42 home-office observations.") };
    if (/scratch|scuff|mark|damage/.test(q) && !/front|rear|left|right|bumper/.test(q)) return { ...base, status: "clarification_required", title: "Which mark do you mean?", text: "I found two different marks on the white rental car. Their evidence is not equivalent, so choosing for you could produce the wrong claim.", confidence: 0, confidence_label: "not_applicable", subject_id: "white-rental-car", evidence: evidence("car-return-front-left", "car-return-rear-right"), choices: ["Front-left bumper scuff", "Rear-right bumper scratch"], steps: steps("Two candidate entities matched; paused before resolving ambiguity.", "needs_input") };
    if (/scratch|scuff|mark|damage/.test(q) && /rear/.test(q) && /right/.test(q)) return { ...base, status: "uncertain", title: "I can’t determine whether the rear-right scratch was already there", text: "The scratch is visible in a return photo, but none of the pickup photographs clearly shows the rear-right bumper. Absence from an unseen region is not evidence that the mark was new.", confidence: .18, confidence_label: "low", subject_id: "white-rental-car", evidence: evidence("car-return-rear-right"), coverage_note: "Pickup coverage gap: rear-right bumper and quarter panel.", follow_up: "If you have another pickup photo or video, add it and I’ll re-check this region.", steps: steps("Rear-right pickup region was never visible.", "refused") };
    if (/scratch|scuff|mark|damage/.test(q) && /front/.test(q) && /left/.test(q)) return { ...base, status: "answered", title: "Yes — the front-left scuff was visible at pickup", text: "The same short horizontal scuff appears in the August 3 pickup photo and the August 8 return photo at the same bumper position.", confidence: .97, confidence_label: "high", subject_id: "white-rental-car", evidence: evidence("car-pickup-front-left", "car-return-front-left"), coverage_note: "Front-left exterior coverage is sufficient at both pickup and return.", steps: steps("Matched vehicle identity, body region, mark geometry and pickup timestamp.") };
    if (/scratch|scuff|mark|damage/.test(q)) return { ...base, status: "clarification_required", title: "Which mark do you mean?", text: "I found two different marks on the white rental car. Their evidence is not equivalent, so choosing for you could produce the wrong claim.", confidence: 0, confidence_label: "not_applicable", subject_id: "white-rental-car", evidence: evidence("car-return-front-left", "car-return-rear-right"), choices: ["Front-left bumper scuff", "Rear-right bumper scratch"], steps: steps("The supplied direction does not uniquely resolve a supported region.", "needs_input") };
    if (/bike|bicycle|project|restoration/.test(q)) return { ...base, status: "answered", title: "The bike moved through five restoration stages", text: "Reality Diff grouped the photos by the same petrol-blue frame and reconstructed: documented → stripped → prepared → repainted → reassembled. Preparation is first clearly visible on March 1; the completed bike is first visible on May 29.", confidence: .91, confidence_label: "high", subject_id: "blue-bike-project", evidence: evidence("bike-feb-08", "bike-mar-01"), follow_up: "Open the project timeline to inspect every stage and its source photo.", steps: steps("Clustered by frame identity and ordered the observations.") };
    return { ...base, status: "not_found", title: "I need a more specific physical subject", text: "I searched the indexed observations but could not connect that question to a supported subject. Try the home office, white rental car, or blue bike project.", confidence: 0, confidence_label: "not_applicable", choices: quickPrompts().slice(0,3), steps: steps("No subject passed the retrieval threshold.", "needs_input") };
  }

  function renderSources() {
    const activity = [...(state.data.ingestion_runs || []).map((run) => ({ time: "now", title: "Incremental scan completed", detail: `${run.discovered} discovered · ${run.indexed} indexed · ${run.subjects_updated} subjects updated`, status: "complete" })), ...state.data.agent_activity];
    const live = Boolean(state.runtime?.live_models);
    main.innerHTML = `<div class="page"><header class="page-head"><div><p class="eyebrow">Inputs and agent activity</p><h1 class="page-title">Sources</h1><p class="page-intro">What Reality Diff can see, what it indexed, and exactly which model handled each stage.</p></div><div class="page-actions"><button class="secondary-button" data-action="add-photos">${icon("plus")} Add photos</button></div></header>
      <section class="source-grid">${sourceCard("camera", "Android photo library", "Incremental MediaStore index with explicit full-library permission.", `${state.data.summary.photos_indexed} indexed`, "Connected")}${sourceCard("folder", "Selected photo folder", "Browser directory picker with re-authorization when required.", "Reconnectable", "Available")}${sourceCard("plus", "Manual additions", "Photo Picker, folder selection, drag and drop, or multi-file upload.", `${(state.data.gallery || []).filter((item) => item.imported).length} this session`, "Available")}</section>
      <div class="section-head"><h2>Multimodel pipeline</h2><span class="demo-pill ${live ? "live" : ""}"><i></i>${live ? "Live on Vertex AI" : "Local sample mode"}</span></div>
      <section class="panel"><div class="panel-body"><div class="pipeline">${pipelineStep("01", "Discover", "MediaStore, picker or connected folder")}${pipelineStep("02", "Filter", "Hashes, duplicates and file safety")}${pipelineStep("03", "Triage", "Gemini 3.5 Flash-Lite")}${pipelineStep("04", "Understand", "Gemini 3.7 Flash")}${pipelineStep("05", "Retrieve", "Gemini Embedding 2")}${pipelineStep("06", "Partner", "Google ADK + evidence tools")}</div><div class="honesty-callout">${icon("info")}<div><strong>${live ? "Live model execution is enabled." : "The sample world remains truthful without cloud credentials."}</strong><br>${live ? "New uploads are stored privately and processed by the three Google models shown above. Preloaded temporal claims remain fixed so their evidence can be evaluated repeatedly." : "New files can still be added to the gallery and are marked queued. The bundled temporal answers replay pre-verified evidence and never pretend to be a live Gemini response."}</div></div></div></section>
      <div class="section-head"><h2>Recent agent activity</h2><a href="/api/v1/proof" target="_blank" rel="noreferrer">Open proof JSON →</a></div><section class="panel"><div class="panel-body"><div class="activity-list">${activity.map((item) => `<article class="activity-row"><time>${escapeHtml(item.time)}</time><i class="${item.status}"></i><div><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.detail)}</span></div><span>${item.status === "attention" ? "review" : "done"}</span></article>`).join("")}</div></div></section>
    </div>`;
  }

  function sourceCard(iconName, title, text, count, status) {
    return `<article class="source-card"><div class="source-icon">${icon(iconName)}</div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(text)}</p><div class="source-foot"><span>${escapeHtml(count)}</span><strong>${escapeHtml(status)}</strong></div></article>`;
  }
  function pipelineStep(number, title, text) { return `<div class="pipeline-step"><b>${number}</b><strong>${title}</strong><span>${text}</span></div>`; }

  function renderMemory() {
    const memory = state.data.memory;
    const corrections = memory.corrections || [];
    main.innerHTML = `<div class="page"><header class="page-head"><div><p class="eyebrow">Persistent context</p><h1 class="page-title">What Reality Diff remembers</h1><p class="page-intro">Aliases, corrections and significance preferences learned through ordinary conversation—not a maintenance queue.</p></div></header><div class="memory-grid"><section class="panel"><header class="panel-head"><h2>Names and aliases</h2><span>${memory.aliases.length}</span></header><div class="panel-body">${memory.aliases.map((item) => memoryItem(`“${item.term}” = ${item.means}`, "A natural-language shortcut used in retrieval.", item.source)).join("")}</div></section><section class="panel"><header class="panel-head"><h2>Preferences</h2><span>${memory.preferences.length}</span></header><div class="panel-body">${memory.preferences.map((item) => memoryItem(item.statement, "Changes how future questions are ranked, never the underlying evidence.", item.source)).join("")}</div></section><section class="panel" style="grid-column:1/-1"><header class="panel-head"><h2>Your corrections in this demo</h2><span>${corrections.length}</span></header><div class="panel-body">${corrections.length ? corrections.map((item) => memoryItem(item.statement, `${item.kind} correction${item.subject_id ? ` · ${subject(item.subject_id)?.name || item.subject_id}` : ""}`, item.created_at ? formatDate(item.created_at) : "this session")).join("") : `<div style="padding:30px;text-align:center;color:var(--muted);font-size:12px">No correction yet. Ask a question, then choose <strong>Correct this</strong>.</div>`}</div></section></div><div class="honesty-callout">${icon("shield")}<div><strong>Memory is context, not evidence.</strong><br>A correction can improve identity matching or query ranking, but it cannot rewrite an original observation or manufacture a missing photograph.</div></div></div>`;
  }

  function memoryItem(title, text, source) { return `<article class="memory-item"><strong>${escapeHtml(title)}</strong><p>${escapeHtml(text)}</p><small>${escapeHtml(source)}</small></article>`; }

  function renderNotFound() {
    main.innerHTML = `<div class="page" style="text-align:center;padding-top:15vh"><p class="eyebrow">404</p><h1 class="page-title">That reality isn’t here.</h1><p class="page-intro" style="margin:14px auto 24px">The route may have changed, but your indexed history has not.</p><a class="primary-button" href="/#home">Return home</a></div>`;
  }

  function subject(id) { return state.data.subjects.find((item) => item.id === id); }
  function asset(id) { return state.data.assets.find((item) => item.id === id); }

  function openModal(html) {
    modalContent.innerHTML = html;
    if (typeof modal.showModal === "function" && !modal.open) modal.showModal();
    else modal.setAttribute("open", "");
  }

  function modalHeader(title) {
    return `<header class="modal-head"><h2>${escapeHtml(title)}</h2><button class="modal-close" data-action="close-modal" aria-label="Close">${icon("close")}</button></header>`;
  }

  function showEvidence(ids, title = "Evidence") {
    const values = ids.map(asset).filter(Boolean);
    openModal(`${modalHeader(title)}<div class="modal-body">${values.map((item) => `<article style="margin-bottom:22px"><img class="modal-photo" src="${item.image}" alt="${escapeHtml(item.label)}"><div class="evidence-detail"><div><small>Captured</small><strong>${formatDate(item.captured_at)}</strong></div><div><small>Source region</small><strong>${escapeHtml(item.region)}</strong></div><div><small>Observed fact</small><strong>${escapeHtml(item.observation)}</strong></div><div><small>Observation confidence</small><strong>${percent(item.confidence)}</strong></div></div></article>`).join("")}</div>`);
  }

  function showGalleryPhoto(id) {
    const item = galleryPhotos().find((photo) => photo.id === id);
    if (!item) return;
    const analysis = item.analysis || {};
    const pipeline = analysis.pipeline || {};
    const model = pipeline.reasoning_model || pipeline.triage_model || "Not analyzed";
    const execution = ({ live: "Live Gemini analysis", fixture: "Verified sample observation", local_pending: "Queued for cloud analysis", error: "Analysis needs retry" })[pipeline.execution] || "Gallery metadata";
    openModal(`<div class="photo-viewer"><div class="photo-viewer-image"><img src="${item.image}" alt="${escapeHtml(item.title)}"></div><div class="photo-viewer-info">${modalHeader(item.title)}<div class="photo-viewer-body"><p>${escapeHtml(analysis.description || "An ordinary moment in the connected photo history.")}</p><div class="evidence-detail"><div><small>Captured</small><strong>${formatDate(item.captured_at)}</strong></div><div><small>Collection</small><strong>${escapeHtml(item.category)}</strong></div><div><small>Location</small><strong>${escapeHtml(item.location || "Location unavailable")}</strong></div><div><small>Source</small><strong>${escapeHtml(item.origin || item.source || "Connected library")}</strong></div></div><div class="model-proof"><span class="gemini-spark">✦</span><div><small>${escapeHtml(execution)}</small><strong>${escapeHtml(model)}</strong>${analysis.embedding_dimensions ? `<span>${analysis.embedding_dimensions}-dimension Gemini Embedding 2 vector</span>` : ""}</div></div>${item.evidence_id ? `<button class="secondary-button" style="width:100%" data-asset="${escapeHtml(item.evidence_id)}">${icon("eye")} Open evidence details</button>` : ""}${item.imported ? `<button class="secondary-button" style="width:100%;margin-top:9px;color:#b3261e" data-delete-media="${escapeHtml(item.id)}">Remove imported photo</button>` : ""}</div></div></div>`);
  }

  async function deleteMedia(id) {
    if (!confirm("Remove this imported photo and its analysis from Reality Diff?")) return;
    const item = (state.data.gallery || []).find((photo) => photo.id === id);
    if (state.apiOnline && !id.startsWith("local_upload_")) {
      try {
        const response = await fetch(`/api/v1/media/${encodeURIComponent(id)}`, { method: "DELETE" });
        if (!response.ok) return showToast("The photo could not be removed.");
      } catch (_error) {
        return showToast("The photo could not be removed.");
      }
    } else if (item?.image?.startsWith("blob:")) URL.revokeObjectURL(item.image);
    state.data.gallery = (state.data.gallery || []).filter((photo) => photo.id !== id);
    state.data.summary.photos_indexed = Math.max(0, state.data.summary.photos_indexed - 1);
    state.data.summary.photos_seen = Math.max(0, state.data.summary.photos_seen - 1);
    modal.close();
    showToast("Imported photo removed.");
    if (state.route === "gallery") renderGallery();
  }

  function showWhy() {
    const answer = state.lastAnswer || [...state.conversation].reverse().find((item) => item.answer?.steps?.length)?.answer;
    if (!answer) return showToast("Ask a question first.");
    openModal(`${modalHeader("Why this answer?")}<div class="modal-body"><p style="margin-top:0;color:var(--muted);font-size:12px;line-height:1.55">The agent records the retrieval and coverage decisions behind its answer. It does not expose hidden model reasoning.</p><div class="trace-list">${answer.steps.map((step, index) => `<article class="trace-step ${step.status}"><i>${index + 1}</i><div><strong>${escapeHtml(step.name)}</strong><span>${escapeHtml(step.detail)}</span></div></article>`).join("")}</div>${answer.coverage_note ? `<div class="honesty-callout">${icon("eye")}<div><strong>Coverage constraint</strong><br>${escapeHtml(answer.coverage_note)}</div></div>` : ""}</div>`);
  }

  function openCorrection() {
    const answer = state.lastAnswer;
    if (!answer) return showToast("Ask a question first.");
    openModal(`${modalHeader("Correct Reality Diff")}<form class="modal-body" id="correction-form"><p style="margin-top:0;color:var(--muted);font-size:12px;line-height:1.55">Write the correction naturally. It will guide later matching, but it will not overwrite source photos.</p><label style="display:block;font-size:11px;font-weight:650">Correction type<select name="kind" style="width:100%;margin-top:7px;padding:11px;border:1px solid var(--line);border-radius:9px;background:var(--surface)"><option value="identity">Object identity</option><option value="alias">Name or alias</option><option value="significance">What matters</option><option value="evidence">Evidence interpretation</option><option value="category">Use-case category</option></select></label><label style="display:block;margin-top:14px;font-size:11px;font-weight:650">What should I remember?<textarea name="statement" required minlength="3" maxlength="500" style="width:100%;min-height:110px;margin-top:7px;padding:11px;border:1px solid var(--line);border-radius:9px;resize:vertical" placeholder="Those two chairs are actually the same chair under different light."></textarea></label><input type="hidden" name="subject_id" value="${answer.subject_id || ""}"><button class="primary-button violet" style="width:100%;margin-top:15px" type="submit">${icon("check")} Remember correction</button></form>`);
  }

  function openSearch() {
    openModal(`<div class="search-modal-form">${icon("search")}<input id="search-input" autocomplete="off" placeholder="Search rooms, objects, projects…" aria-label="Search"></div><div class="search-results" id="search-results">${searchResults("")}</div>`);
    requestAnimationFrame(() => document.querySelector("#search-input")?.focus());
  }

  function searchResults(query) {
    const q = query.trim().toLowerCase();
    const matches = state.data.subjects.filter((item) => !q || [item.name, item.summary, ...item.aliases, ...item.latest_state].join(" ").toLowerCase().includes(q));
    const photos = q ? galleryPhotos().filter((item) => [item.title, item.category, item.location].filter(Boolean).join(" ").toLowerCase().includes(q)).slice(0, 6) : [];
    const subjectResults = matches.map((item) => `<button class="search-result" data-search-go="subject/${item.id}"><img src="${item.cover}" alt=""><span><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.summary)}</span></span>${icon("chevron")}</button>`).join("");
    const photoResults = photos.map((item) => `<button class="search-result" data-gallery-item="${escapeHtml(item.id)}"><img src="${item.image}" alt=""><span><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.category)} · ${formatDate(item.captured_at)}</span></span>${icon("gallery")}</button>`).join("");
    return subjectResults + photoResults || `<p style="padding:28px;text-align:center;color:var(--muted);font-size:12px">No matching reality or photo. Try asking a question instead.</p>`;
  }

  function openInfo() {
    openModal(`${modalHeader("About Reality Diff")}<div class="modal-body"><p style="margin-top:0;line-height:1.65;color:var(--muted);font-size:13px">Reality Diff is a semantic memory for the physical world. The bundled world pairs a realistic, Pexels-licensed lifestyle gallery with synthetic evidence sequences whose ground truth is safe to evaluate.</p><div class="evidence-detail"><div><small>Primary reasoning</small><strong>Gemini 3.7 Flash</strong></div><div><small>Fast gallery triage</small><strong>Gemini 3.5 Flash-Lite</strong></div><div><small>Cross-modal retrieval</small><strong>Gemini Embedding 2</strong></div><div><small>Agent & cloud</small><strong>Google ADK · Cloud Run · Firestore · Storage · Pub/Sub</strong></div></div><div class="honesty-callout">${icon("info")}<div>${state.runtime?.live_models ? "This deployment is connected to Vertex AI. Open Sources to inspect the execution boundary." : "Local sample mode is active. New uploads are retained and visibly queued until Vertex AI credentials are connected."}</div></div></div>`);
  }

  function openAddPhotos() {
    openModal(`${modalHeader("Add photos")}<div class="modal-body"><div class="source-grid import-options" style="grid-template-columns:1fr 1fr"><button class="source-card" data-import="web_folder" style="cursor:pointer;text-align:left"><div class="source-icon">${icon("folder")}</div><h3>Connect a folder</h3><p>Choose a photo directory. Reality Diff indexes supported images in batches.</p></button><button class="source-card" data-import="web_upload" style="cursor:pointer;text-align:left"><div class="source-icon">${icon("plus")}</div><h3>Select photos</h3><p>Add up to 60 JPEG, PNG, or WebP images from any source.</p></button></div><div class="dropzone" data-dropzone>${icon("gallery")}<strong>Or drop photos here</strong><span>Your browser never grants access without an explicit action.</span></div><input id="photo-input" type="file" accept="image/jpeg,image/png,image/webp" multiple hidden><div class="honesty-callout">${icon("shield")}<div>Connected media stays inside this deployment. Cloud mode uses a protected Storage bucket; local mode stores files only on this machine.</div></div></div>`);
  }

  async function chooseImport(sourceName) {
    if (sourceName === "web_folder" && "showDirectoryPicker" in window) {
      try {
        const root = await window.showDirectoryPicker({ mode: "read" });
        const files = await filesFromDirectory(root);
        if (files.length) await importPhotos(files.slice(0, 60), sourceName);
        else showToast("No supported photos were found in that folder.");
      } catch (error) {
        if (error.name !== "AbortError") showToast("That folder could not be opened.");
      }
      return;
    }
    const input = document.querySelector("#photo-input");
    if (!input) return;
    input.dataset.source = sourceName;
    if (sourceName === "web_folder") input.setAttribute("webkitdirectory", "");
    else input.removeAttribute("webkitdirectory");
    input.click();
  }

  async function filesFromDirectory(directory) {
    const found = [];
    for await (const handle of directory.values()) {
      if (found.length >= 60) break;
      if (handle.kind === "file") {
        const file = await handle.getFile();
        if (isSupportedImage(file)) found.push(file);
      } else if (handle.kind === "directory") {
        found.push(...await filesFromDirectory(handle));
      }
    }
    return found.slice(0, 60);
  }

  function isSupportedImage(file) {
    return ["image/jpeg", "image/png", "image/webp"].includes(file.type);
  }

  async function importPhotos(files, sourceName = "web_upload") {
    const selected = files.filter(isSupportedImage).slice(0, 60);
    if (!selected.length) return showToast("Choose JPEG, PNG, or WebP photos.");
    modal.close();
    showToast(`Indexing ${selected.length} photo${selected.length === 1 ? "" : "s"}…`);
    const items = [];
    let latestRun = null;
    let duplicateCount = 0;
    const totals = { discovered: 0, indexed: 0, deduplicated: 0, subjects_updated: 0, failures: 0 };
    if (state.apiOnline) {
      try {
        for (let index = 0; index < selected.length; index += 12) {
          const batch = selected.slice(index, index + 12);
          const body = new FormData();
          batch.forEach((file) => body.append("files", file, file.name));
          body.append("source", sourceName);
          const response = await fetch("/api/v1/media/analyze", { method: "POST", body });
          if (!response.ok) {
            const problem = await response.json().catch(() => ({}));
            throw new Error(problem.detail || `Upload failed (${response.status})`);
          }
          const payload = await response.json();
          items.push(...payload.items);
          duplicateCount += (payload.duplicates || []).length;
          Object.keys(totals).forEach((key) => { totals[key] += Number(payload.run?.[key] || 0); });
          latestRun = payload.run;
        }
        if (latestRun) latestRun = { ...latestRun, ...totals };
      } catch (error) {
        showToast(error.message || "The photos could not be indexed.");
        return;
      }
    } else {
      selected.forEach((file, index) => items.push({
        id: `local_upload_${Date.now()}_${index}`,
        image: URL.createObjectURL(file),
        captured_at: new Date(file.lastModified || Date.now()).toISOString(),
        title: file.name.replace(/\.[^.]+$/, "").replaceAll(/[-_]+/g, " "),
        category: "Imports",
        source: sourceName,
        origin: "Local browser preview",
        imported: true,
        status: "queued",
        analysis: { description: "Queued for Vertex AI analysis.", embedding_dimensions: 0, pipeline: { execution: "local_pending", reasoning_model: "gemini-3.7-flash" } },
      }));
      latestRun = { discovered: items.length, indexed: items.length, subjects_updated: 0, transport: "local_pending" };
    }
    state.data.gallery = [...items, ...(state.data.gallery || [])];
    state.data.summary.photos_indexed += items.length;
    state.data.summary.photos_seen += items.length;
    state.data.ingestion_runs = state.data.ingestion_runs || [];
    if (latestRun) state.data.ingestion_runs.unshift(latestRun);
    const duplicateNote = duplicateCount ? ` · ${duplicateCount} duplicate${duplicateCount === 1 ? "" : "s"} skipped` : "";
    showToast(`${items.length} photos added${duplicateNote} · ${latestRun?.transport?.startsWith("vertex_ai") ? "Gemini analysis complete" : "analysis queued"}`);
    location.hash = "gallery";
    if (state.route === "gallery") renderGallery();
  }

  async function runSync(discovered = 18, sourceName = "web_folder") {
    showToast("Indexing new photos through the demo pipeline…");
    let run = { discovered, indexed: Math.max(0, discovered - 2), subjects_updated: Math.min(3, discovered), transport: "recorded_demo" };
    if (state.apiOnline) {
      try {
        const response = await fetch("/api/v1/ingestion-runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source: sourceName, discovered }) });
        if (response.ok) run = await response.json();
      } catch (_error) { state.apiOnline = false; }
    }
    state.data.ingestion_runs = state.data.ingestion_runs || [];
    state.data.ingestion_runs.unshift(run);
    setTimeout(() => { showToast(`${run.indexed} photos indexed · ${run.subjects_updated} realities updated`); if (state.route === "sources") renderSources(); }, 700);
  }

  async function saveCorrection(form) {
    const payload = Object.fromEntries(new FormData(form));
    payload.subject_id = payload.subject_id || null;
    payload.conversation_id = state.conversationId;
    let correction;
    if (state.apiOnline) {
      try {
        const response = await fetch("/api/v1/corrections", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        if (!response.ok) throw new Error(`API ${response.status}`);
        correction = await response.json();
        state.data.memory.corrections.push(correction);
      } catch (_error) { state.apiOnline = false; }
    }
    if (!correction) {
      correction = { correction_id: `local_${Date.now()}`, ...payload, created_at: new Date().toISOString() };
      writeLocalCorrection(correction);
    }
    modal.close();
    showToast("Correction remembered for future questions.");
  }

  let toastTimer;
  function showToast(message) {
    clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.add("show");
    toastTimer = setTimeout(() => toast.classList.remove("show"), 2800);
  }

  document.addEventListener("click", (event) => {
    const target = event.target.closest("[data-go],[data-action],[data-evidence],[data-asset],[data-why],[data-prompt],[data-choice],[data-filter],[data-gallery-filter],[data-gallery-item],[data-ask-subject],[data-search-go],[data-import],[data-delete-media]");
    if (!target) return;
    if (target.dataset.go) location.hash = target.dataset.go;
    if (target.dataset.filter) { state.filter = target.dataset.filter; renderReality(); }
    if (target.dataset.galleryFilter) { state.galleryFilter = target.dataset.galleryFilter; renderGallery(); }
    if (target.dataset.galleryItem) showGalleryPhoto(target.dataset.galleryItem);
    if (target.dataset.evidence) showEvidence(target.dataset.evidence.split(","), target.dataset.changeTitle || "Evidence");
    if (target.dataset.asset) showEvidence([target.dataset.asset]);
    if (target.dataset.why) showWhy();
    if (target.dataset.prompt) askQuestion(target.dataset.prompt);
    if (target.dataset.choice) askQuestion(target.dataset.choice);
    if (target.dataset.askSubject) { sessionStorage.setItem("realitydiff-context", target.dataset.askSubject); location.hash = "ask"; }
    if (target.dataset.searchGo) { modal.close(); location.hash = target.dataset.searchGo; }
    if (target.dataset.import) chooseImport(target.dataset.import);
    if (target.dataset.deleteMedia) deleteMedia(target.dataset.deleteMedia);
    const action = target.dataset.action;
    if (action === "open-search") openSearch();
    if (action === "open-info") openInfo();
    if (action === "close-modal") modal.close();
    if (action === "add-photos") openAddPhotos();
    if (action === "run-sync" || action === "find-photos") runSync();
    if (action === "correct-answer") openCorrection();
  });

  document.addEventListener("keydown", (event) => {
    const card = event.target.closest?.("[data-go]");
    if (card && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); location.hash = card.dataset.go; }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openSearch(); }
    if (event.key === "Escape" && modal.open) modal.close();
  });

  document.addEventListener("input", (event) => {
    if (event.target.id === "search-input") document.querySelector("#search-results").innerHTML = searchResults(event.target.value);
    if (event.target.id === "question") { event.target.style.height = "auto"; event.target.style.height = `${Math.min(event.target.scrollHeight, 120)}px`; }
  });

  document.addEventListener("change", (event) => {
    if (event.target.id === "photo-input" && event.target.files?.length) importPhotos(Array.from(event.target.files), event.target.dataset.source || "web_upload");
  });

  document.addEventListener("dragover", (event) => {
    const zone = event.target.closest?.("[data-dropzone]");
    if (!zone) return;
    event.preventDefault();
    zone.classList.add("dragging");
  });

  document.addEventListener("dragleave", (event) => {
    event.target.closest?.("[data-dropzone]")?.classList.remove("dragging");
  });

  document.addEventListener("drop", (event) => {
    const zone = event.target.closest?.("[data-dropzone]");
    if (!zone) return;
    event.preventDefault();
    zone.classList.remove("dragging");
    importPhotos(Array.from(event.dataTransfer?.files || []), "web_upload");
  });

  document.addEventListener("submit", (event) => {
    if (event.target.id === "chat-form") { event.preventDefault(); const field = event.target.elements.question; const value = field.value; field.value = ""; askQuestion(value); }
    if (event.target.id === "correction-form") { event.preventDefault(); saveCorrection(event.target); }
  });

  modal.addEventListener("click", (event) => {
    if (event.target === modal) modal.close();
  });
  window.addEventListener("hashchange", route);
  loadData().catch((error) => {
    main.innerHTML = `<div class="page" style="padding-top:15vh;text-align:center"><h1 class="page-title">The demo could not load.</h1><p class="page-intro" style="margin:15px auto">${escapeHtml(error.message)}</p><p style="color:var(--muted);font-size:12px">Run <code>uvicorn realitydiff.api:app --port 8080</code> from the project folder.</p></div>`;
  });
})();
