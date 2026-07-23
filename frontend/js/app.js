/**
 * Main application entry point — sidebar navigation, rendering, and
 * event wiring. Imports the smaller focused modules (api, theme,
 * animations, background) rather than doing everything in one file.
 *
 * Sidebar scope note: per the UI/UX design doc (docs/05_UIUX_Design.md,
 * Section 6.3), the full screen list includes Contacts, Actions, and
 * Settings — none of those have backend routes built yet (Stage 4 only
 * built Messages/Commitments/Digest). Rather than hide them, they're
 * shown as real nav items marked "Soon" and click through to an honest
 * coming-soon panel — consistent with how every other unbuilt piece in
 * this project has been documented rather than silently omitted.
 */

import { getDigest, getCommitments, postMessage, updateCommitmentState } from "./api.js";
import { initTheme, toggleTheme } from "./theme.js";
import { initAnimations, fadeInStagger, slideInList, fadeInBanner, countUp } from "./animations.js";

let lastCounts = { atRisk: 0, pending: 0, fulfilled: 0 };

// Selected input channel — message (typed text), call, or in-person.
// The extraction/lifecycle mechanism processes all three identically;
// this only changes the hint text and gets tagged onto the saved
// Message row so it's visible later in the commitments list.
let selectedChannel = "message";

const CHANNEL_HINTS = {
  message: "Paste the message text as written.",
  call: "Summarize what was said/promised on the call, in your own words.",
  "in-person": "Summarize what was said/promised in person, in your own words.",
};

const CHANNEL_LABELS = {
  message: "Message",
  call: "Call",
  "in-person": "In-Person",
};

// ---------- View switching ----------

function switchView(viewName) {
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));

  document.getElementById(`view-${viewName}`)?.classList.add("active");
  document.querySelector(`.nav-item[data-view="${viewName}"]`)?.classList.add("active");

  if (viewName === "digest") { fetchDigest(); }
  if (viewName === "commitments") { fetchCommitments(); }
}

// ---------- Rendering helpers ----------

function showError(msg) {
  const el = document.getElementById("errorBanner");
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 5000);
}

function badgeHtml(state) {
  const label = state === "at-risk" ? "At Risk" : state.charAt(0).toUpperCase() + state.slice(1);
  return `<span class="badge ${state}">${label}</span>`;
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) + " " +
         d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function commitmentItemHtml(c) {
  const channelLabel = c.channel ? CHANNEL_LABELS[c.channel] || c.channel : null;
  const channelPart = channelLabel ? ` · via ${channelLabel}` : "";
  const isFulfilled = c.state === "fulfilled";
  return `
    <div class="commitment-item" data-commitment-item>
      <div>
        <div class="commitment-desc">${escapeHtml(c.description)}</div>
        <div class="commitment-meta">${c.commitment_type}${channelPart} · created ${formatDate(c.created_at)}${c.resolved_at ? " · resolved " + formatDate(c.resolved_at) : ""}</div>
      </div>
      <div style="display:flex; align-items:center; gap:10px;">
        ${badgeHtml(c.state)}
        <button
          class="mark-toggle-btn"
          data-toggle-commitment
          data-commitment-id="${c.commitment_id}"
          data-current-state="${c.state}"
          title="${isFulfilled ? 'Mark as pending again' : 'Manually mark fulfilled'}"
        >${isFulfilled ? "↺ Undo" : "✓ Mark Done"}</button>
      </div>
    </div>
  `;
}

// ---------- Data fetching + rendering ----------

function skeletonCommitmentItems(count = 2) {
  return Array(count)
    .fill(0)
    .map(
      () => `
        <div class="commitment-item">
          <div style="flex:1">
            <div class="skeleton skeleton-text"></div>
            <div class="skeleton skeleton-text short"></div>
          </div>
        </div>`
    )
    .join("");
}

async function fetchDigest() {
  const recentList = document.getElementById("digestRecentList");
  recentList.innerHTML = skeletonCommitmentItems();

  try {
    const data = await getDigest();

    const atRiskEl = document.getElementById("atRiskCount");
    const pendingEl = document.getElementById("pendingCount");
    const fulfilledEl = document.getElementById("fulfilledCount");

    countUp(atRiskEl, lastCounts.atRisk, data.at_risk_count);
    countUp(pendingEl, lastCounts.pending, data.pending_count);
    countUp(fulfilledEl, lastCounts.fulfilled, data.fulfilled_today_count);

    lastCounts = {
      atRisk: data.at_risk_count,
      pending: data.pending_count,
      fulfilled: data.fulfilled_today_count,
    };

    const combined = [...data.at_risk_commitments, ...data.upcoming_commitments].slice(0, 5);
    recentList.innerHTML = combined.length
      ? combined.map(commitmentItemHtml).join("")
      : `<div class="empty-state">You're all caught up — nothing needs attention today.</div>`;
    slideInList("#digestRecentList [data-commitment-item]");
  } catch (err) {
    recentList.innerHTML = "";
    showError("Could not load digest — is the backend running at localhost:8000?");
  }
}

async function fetchCommitments() {
  const listEl = document.getElementById("commitmentsList");
  listEl.innerHTML = skeletonCommitmentItems(3);

  try {
    const data = await getCommitments();
    listEl.innerHTML = data.length
      ? data.map(commitmentItemHtml).join("")
      : `<div class="empty-state">No commitments tracked yet — submit a message to get started.</div>`;
    slideInList("#commitmentsList [data-commitment-item]");
    renderKanbanBoard(data);
  } catch (err) {
    listEl.innerHTML = "";
    showError("Could not load commitments — is the backend running at localhost:8000?");
  }
}

function kanbanCardHtml(c) {
  const channelLabel = c.channel ? CHANNEL_LABELS[c.channel] || c.channel : null;
  return `
    <div class="kanban-card" draggable="true" data-kanban-card
         data-commitment-id="${c.commitment_id}" data-current-state="${c.state}">
      <div class="kanban-card-desc">${escapeHtml(c.description)}</div>
      <div class="kanban-card-meta">${c.commitment_type}${channelLabel ? " · " + channelLabel : ""}</div>
    </div>
  `;
}

function renderKanbanBoard(data) {
  const buckets = { pending: [], "at-risk": [], fulfilled: [] };
  data.forEach((c) => { if (buckets[c.state]) buckets[c.state].push(c); });

  const render = (id, countId, items) => {
    document.getElementById(id).innerHTML = items.length
      ? items.map(kanbanCardHtml).join("")
      : `<div class="kanban-empty">Nothing here</div>`;
    document.getElementById(countId).textContent = items.length;
  };

  render("kanbanPending", "kanbanPendingCount", buckets["pending"]);
  render("kanbanAtRisk", "kanbanAtRiskCount", buckets["at-risk"]);
  render("kanbanFulfilled", "kanbanFulfilledCount", buckets["fulfilled"]);
}

function selectChannel(channel) {
  selectedChannel = channel;
  document.querySelectorAll(".channel-option").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.channel === channel);
  });
  const hintEl = document.getElementById("channelHint");
  if (hintEl) hintEl.textContent = CHANNEL_HINTS[channel] || "";

  const textarea = document.getElementById("messageInput");
  if (textarea) {
    textarea.placeholder = channel === "message"
      ? "e.g. I'll send you the report by Friday."
      : "e.g. Talked with the recruiter — she'll send the offer once HR verification is done.";
  }
}

async function handleSubmitMessage() {
  const input = document.getElementById("messageInput");
  const btn = document.getElementById("submitBtn");
  const banner = document.getElementById("resultBanner");
  const body = input.value.trim();
  if (!body) return;

  btn.disabled = true;
  btn.textContent = "Processing...";
  banner.style.display = "none";
  banner.className = "result-banner";

  try {
    const data = await postMessage(body, selectedChannel);
    const { new_commitment, resolved_commitment_id, resolution_reasoning } = data;

    if (resolved_commitment_id) {
      banner.textContent = `✓ Resolved an existing commitment: ${resolution_reasoning || ""}`;
      banner.className = "result-banner resolved";
    } else if (new_commitment) {
      banner.textContent = `New commitment detected: "${new_commitment.description}" (${new_commitment.commitment_type})`;
      banner.className = "result-banner extracted";
    } else {
      banner.textContent = "No commitment detected in this entry.";
      banner.className = "result-banner none";
    }
    banner.style.display = "block";
    fadeInBanner(banner);

    input.value = "";
    await Promise.all([fetchDigest(), fetchCommitments()]);
  } catch (err) {
    showError("Failed to process — check the backend is running and GROQ_API_KEY is set.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Process";
  }
}

// ---------- Init ----------

function wireNav() {
  document.querySelectorAll(".nav-item[data-view]").forEach((item) => {
    item.addEventListener("click", () => switchView(item.dataset.view));
  });
  document.getElementById("themeToggle").addEventListener("click", toggleTheme);
  document.getElementById("submitBtn").addEventListener("click", handleSubmitMessage);
  document.querySelectorAll(".channel-option").forEach((btn) => {
    btn.addEventListener("click", () => selectChannel(btn.dataset.channel));
  });

  // Event delegation for manual mark-fulfilled/undo buttons — these are
  // added dynamically (via innerHTML in commitmentItemHtml), so a single
  // listener on the document catches clicks on any of them, present or
  // future, without re-binding per render.
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-toggle-commitment]");
    if (!btn) return;

    const commitmentId = btn.dataset.commitmentId;
    const currentState = btn.dataset.currentState;
    const newState = currentState === "fulfilled" ? "pending" : "fulfilled";

    btn.disabled = true;
    try {
      await updateCommitmentState(commitmentId, newState);
      await Promise.all([fetchDigest(), fetchCommitments()]);
    } catch (err) {
      showError("Could not update commitment — is the backend running?");
      btn.disabled = false;
    }
  });

  // List/Board toggle for Commitments view
  document.querySelectorAll("[data-commitments-view]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-commitments-view]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const isBoard = btn.dataset.commitmentsView === "board";
      document.getElementById("commitmentsListWrapper").style.display = isBoard ? "none" : "block";
      document.getElementById("commitmentsBoardWrapper").style.display = isBoard ? "block" : "none";
    });
  });

  // Kanban drag-and-drop — event delegation since cards are rendered
  // dynamically. At-risk is a read-only/computed dropzone (backend only
  // allows pending<->fulfilled via manual override), so drops there are
  // rejected rather than silently accepted.
  document.addEventListener("dragstart", (e) => {
    const card = e.target.closest("[data-kanban-card]");
    if (!card) return;
    e.dataTransfer.setData("text/commitment-id", card.dataset.commitmentId);
    e.dataTransfer.setData("text/current-state", card.dataset.currentState);
    card.classList.add("dragging");
  });
  document.addEventListener("dragend", (e) => {
    const card = e.target.closest("[data-kanban-card]");
    if (card) card.classList.remove("dragging");
  });
  document.querySelectorAll("[data-dropzone]").forEach((zone) => {
    zone.addEventListener("dragover", (e) => {
      if (zone.dataset.dropzone === "at-risk") return; // read-only, no drop allowed
      e.preventDefault();
      zone.classList.add("drag-over");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    zone.addEventListener("drop", async (e) => {
      e.preventDefault();
      zone.classList.remove("drag-over");
      const targetState = zone.dataset.dropzone;
      if (targetState === "at-risk") return; // computed automatically, not a manual target

      const commitmentId = e.dataTransfer.getData("text/commitment-id");
      const currentState = e.dataTransfer.getData("text/current-state");
      if (!commitmentId || currentState === targetState) return;

      try {
        await updateCommitmentState(commitmentId, targetState);
        await Promise.all([fetchDigest(), fetchCommitments()]);
      } catch (err) {
        showError("Could not move commitment — is the backend running?");
      }
    });
  });
}

async function init() {
  initTheme();
  wireNav();
  selectChannel("message");

  // Decorative layer — wrapped so a failure can never block the app.
  try {
    await initAnimations();
    fadeInStagger("[data-animate]");
  } catch (err) { console.warn("Animations failed to load:", err); }

  switchView("digest");
}

init();
