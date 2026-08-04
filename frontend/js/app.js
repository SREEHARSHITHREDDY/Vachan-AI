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

import { getDigest, getCommitments, postMessage, updateCommitment, deleteCommitment } from "./api.js";
import { initTheme, toggleTheme } from "./theme.js";
import { initAnimations, fadeInStagger, slideInList, fadeInBanner, countUp } from "./animations.js";

let lastCounts = { atRisk: 0, pending: 0, fulfilled: 0 };
let calendarState = { year: new Date().getFullYear(), month: new Date().getMonth() };
let calendarCommitmentsCache = [];
let calendarPanelTarget = { mode: null, commitmentId: null, date: null };

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function openCalendarAssignPanel(dateKey) {
  const noDeadlineCommitments = calendarCommitmentsCache.filter((c) => !c.inferred_deadline);
  const panel = document.getElementById("calendarAssignPanel");
  const select = document.getElementById("calendarAssignSelect");
  const label = document.getElementById("calendarAssignLabel");
  const startLabel = document.getElementById("calendarAssignStartLabel");
  const startInput = document.getElementById("calendarAssignStartDateTime");
  const dateTimeInput = document.getElementById("calendarAssignDateTime");

  if (noDeadlineCommitments.length === 0) {
    label.textContent = `No commitments without a deadline to assign to ${dateKey}.`;
    select.style.display = "none";
    startLabel.style.display = "none";
    startInput.style.display = "none";
    dateTimeInput.style.display = "none";
    document.getElementById("calendarAssignSaveBtn").style.display = "none";
  } else {
    label.textContent = `Assign a deadline (or date range) on ${dateKey} to:`;
    select.style.display = "";
    startLabel.style.display = "";
    startInput.style.display = "";
    dateTimeInput.style.display = "";
    document.getElementById("calendarAssignSaveBtn").style.display = "";
    select.innerHTML = noDeadlineCommitments
      .map((c) => `<option value="${c.commitment_id}">${escapeHtml(c.description)}</option>`)
      .join("");
    startInput.value = "";
    dateTimeInput.value = `${dateKey}T17:00`;
  }

  calendarPanelTarget = { mode: "assign", commitmentId: null, date: dateKey };
  panel.style.display = "flex";
}

function openCalendarEditPanel(commitmentId) {
  const commitment = calendarCommitmentsCache.find((c) => c.commitment_id === commitmentId);
  if (!commitment) return;

  const panel = document.getElementById("calendarAssignPanel");
  document.getElementById("calendarAssignLabel").textContent = `Edit — ${commitment.description}`;
  document.getElementById("calendarAssignSelect").style.display = "none";
  document.getElementById("calendarAssignStartLabel").style.display = "";
  const startInput = document.getElementById("calendarAssignStartDateTime");
  startInput.style.display = "";
  startInput.value = toDatetimeLocalValue(commitment.starts_at);
  const dateTimeInput = document.getElementById("calendarAssignDateTime");
  dateTimeInput.style.display = "";
  dateTimeInput.value = toDatetimeLocalValue(commitment.inferred_deadline);
  document.getElementById("calendarAssignSaveBtn").style.display = "";

  calendarPanelTarget = { mode: "edit", commitmentId, date: null };
  panel.style.display = "flex";
}

function closeCalendarPanel() {
  document.getElementById("calendarAssignPanel").style.display = "none";
  calendarPanelTarget = { mode: null, commitmentId: null, date: null };
}


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
  if (viewName === "board") { fetchBoard(); }
  if (viewName === "actions") { fetchCalendar(); }
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

function toDatetimeLocalValue(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function actionButtonsHtml(c) {
  const id = c.commitment_id;
  if (c.state === "fulfilled") {
    return `<button class="mark-toggle-btn" data-toggle-commitment data-commitment-id="${id}" data-current-state="fulfilled" title="Mark as pending again">↺ Undo</button>`;
  }
  if (c.state === "at-risk") {
    return `
      <button class="mark-toggle-btn" data-set-state="pending" data-commitment-id="${id}" title="Move back to pending">↺ Pending</button>
      <button class="mark-toggle-btn" data-toggle-commitment data-commitment-id="${id}" data-current-state="at-risk" title="Manually mark fulfilled">✓ Mark Done</button>
    `;
  }
  // pending
  return `
    <button class="mark-toggle-btn" data-set-state="at-risk" data-commitment-id="${id}" title="Flag as at-risk even if the deadline math wouldn't yet">⚠ At Risk</button>
    <button class="mark-toggle-btn" data-toggle-commitment data-commitment-id="${id}" data-current-state="pending" title="Manually mark fulfilled">✓ Mark Done</button>
  `;
}

function formatRange(startsAt, deadline) {
  if (startsAt && deadline) return `📅 ${formatDate(startsAt)} → ${formatDate(deadline)}`;
  if (deadline) return `📅 ${formatDate(deadline)}`;
  return `📅 No deadline set`;
}

function deadlineRowHtml(c) {
  const display = formatRange(c.starts_at, c.inferred_deadline);
  return `
    <div class="deadline-row" data-deadline-row data-commitment-id="${c.commitment_id}"
         data-current-start="${c.starts_at || ""}" data-current-deadline="${c.inferred_deadline || ""}">
      <span class="deadline-display">${display}</span>
      <button class="deadline-edit-btn" data-edit-deadline title="Set or edit date/date range">Edit</button>
    </div>
  `;
}

function startEditingDeadline(row) {
  if (!row) return;
  const startValue = toDatetimeLocalValue(row.dataset.currentStart);
  const endValue = toDatetimeLocalValue(row.dataset.currentDeadline);
  row.innerHTML = `
    <span class="deadline-input-label">From (optional)</span>
    <input type="datetime-local" value="${startValue}" class="deadline-input" data-start-input />
    <span class="deadline-input-label">To</span>
    <input type="datetime-local" value="${endValue}" class="deadline-input" data-end-input />
    <button class="deadline-edit-btn deadline-save-btn" data-save-deadline>Save</button>
    <button class="deadline-edit-btn" data-cancel-deadline>Cancel</button>
  `;
}

function cancelEditingDeadline(row) {
  if (!row) return;
  const display = formatRange(row.dataset.currentStart, row.dataset.currentDeadline);
  row.innerHTML = `
    <span class="deadline-display">${display}</span>
    <button class="deadline-edit-btn" data-edit-deadline title="Set or edit date/date range">Edit</button>
  `;
}

function commitmentItemHtml(c) {
  const channelLabel = c.channel ? CHANNEL_LABELS[c.channel] || c.channel : null;
  const channelPart = channelLabel ? ` · via ${channelLabel}` : "";
  return `
    <div class="commitment-item" data-commitment-item>
      <div style="flex:1;">
        <div class="commitment-desc">${escapeHtml(c.description)}</div>
        <div class="commitment-meta">${c.commitment_type}${channelPart} · created ${formatDate(c.created_at)}${c.resolved_at ? " · resolved " + formatDate(c.resolved_at) : ""}</div>
        ${deadlineRowHtml(c)}
      </div>
      <div style="display:flex; align-items:center; gap:8px; flex-shrink:0;">
        ${badgeHtml(c.state)}
        ${actionButtonsHtml(c)}
        <button class="delete-btn" data-delete-commitment data-commitment-id="${c.commitment_id}" title="Delete this commitment">🗑</button>
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
  } catch (err) {
    listEl.innerHTML = "";
    showError("Could not load commitments — is the backend running at localhost:8000?");
  }
}

async function fetchBoard() {
  try {
    const data = await getCommitments();
    renderKanbanBoard(data);
  } catch (err) {
    showError("Could not load board — is the backend running at localhost:8000?");
  }
}

async function fetchCalendar() {
  try {
    const data = await getCommitments();
    calendarCommitmentsCache = data;
    renderCalendarGrid();
    renderNoDeadlineList(data);
  } catch (err) {
    showError("Could not load calendar — is the backend running at localhost:8000?");
  }
}

function dateRangeKeys(startIso, endIso) {
  // Every YYYY-MM-DD key from startIso through endIso inclusive. Used so a
  // ranged commitment (starts_at + inferred_deadline) shows up on EVERY
  // day it spans, not just the final deadline day.
  //
  // Deliberately does UTC date math (Date.UTC / getUTC*), not local-time
  // accessors — matching how the rest of this file keys calendar days
  // (todayKey and the plain-deadline path both slice(0,10) off the raw
  // UTC ISO string). Mixing local-time math in here would risk a ranged
  // and non-ranged commitment landing on different cells for the same
  // instant, depending on the browser's timezone offset.
  const keys = [];
  const start = new Date(startIso);
  const end = new Date(endIso);
  let cursor = Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate());
  const endDay = Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), end.getUTCDate());
  while (cursor <= endDay) {
    keys.push(new Date(cursor).toISOString().slice(0, 10));
    cursor += 24 * 60 * 60 * 1000;
  }
  return keys;
}

function renderCalendarGrid() {
  const { year, month } = calendarState;
  document.getElementById("calendarMonthLabel").textContent = `${MONTH_NAMES[month]} ${year}`;

  // Map date (YYYY-MM-DD) -> commitments touching that day, for O(1)
  // lookup per cell instead of re-scanning the full list per day. A
  // ranged commitment (starts_at set) is added to EVERY day it spans;
  // a plain deadline is added only to its single day, same as before.
  const byDate = {};
  calendarCommitmentsCache.forEach((c) => {
    if (!c.inferred_deadline) return;
    const keys = c.starts_at ? dateRangeKeys(c.starts_at, c.inferred_deadline) : [c.inferred_deadline.slice(0, 10)];
    keys.forEach((key, i) => {
      const position = keys.length === 1 ? "single" : i === 0 ? "start" : i === keys.length - 1 ? "end" : "middle";
      (byDate[key] = byDate[key] || []).push({ ...c, _rangePosition: position });
    });
  });

  const firstOfMonth = new Date(year, month, 1);
  const startWeekday = firstOfMonth.getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const todayKey = new Date().toISOString().slice(0, 10);

  let cellsHtml = "";
  for (let i = 0; i < startWeekday; i++) {
    cellsHtml += `<div class="calendar-cell calendar-cell-empty"></div>`;
  }
  for (let day = 1; day <= daysInMonth; day++) {
    const dateKey = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const events = byDate[dateKey] || [];
    const isToday = dateKey === todayKey;
    cellsHtml += `
      <div class="calendar-cell${isToday ? " calendar-cell-today" : ""}" data-calendar-day data-date="${dateKey}">
        <div class="calendar-date">${day}</div>
        ${events.slice(0, 3).map((c) => `<div class="calendar-event calendar-event-${c._rangePosition} badge-state-${c.state}" data-calendar-event data-commitment-id="${c.commitment_id}" title="Click to edit — ${escapeHtml(c.description)}">${escapeHtml(c.description)}</div>`).join("")}
        ${events.length > 3 ? `<div class="calendar-more">+${events.length - 3} more</div>` : ""}
      </div>
    `;
  }

  document.getElementById("calendarGrid").innerHTML = cellsHtml;
}

function renderNoDeadlineList(data) {
  const el = document.getElementById("calendarNoDeadlineList");
  const noDeadline = data.filter((c) => !c.inferred_deadline);
  el.innerHTML = noDeadline.length
    ? noDeadline.map(commitmentItemHtml).join("")
    : `<div class="empty-state">Every tracked commitment has a deadline — nothing to show here.</div>`;
}

function kanbanCardHtml(c) {
  const channelLabel = c.channel ? CHANNEL_LABELS[c.channel] || c.channel : null;
  return `
    <div class="kanban-card" draggable="true" data-kanban-card
         data-commitment-id="${c.commitment_id}" data-current-state="${c.state}">
      <div class="kanban-card-desc">${escapeHtml(c.description)}</div>
      <div class="kanban-card-meta">${c.commitment_type}${channelLabel ? " · " + channelLabel : ""}</div>
      ${c.inferred_deadline ? `<div class="kanban-card-deadline">${formatRange(c.starts_at, c.inferred_deadline)}</div>` : ""}
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
    await Promise.all([fetchDigest(), fetchCommitments(), fetchBoard(), fetchCalendar()]);
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
    const toggleBtn = e.target.closest("[data-toggle-commitment]");
    if (toggleBtn) {
      const commitmentId = toggleBtn.dataset.commitmentId;
      const currentState = toggleBtn.dataset.currentState;
      const newState = currentState === "fulfilled" ? "pending" : "fulfilled";

      toggleBtn.disabled = true;
      try {
        await updateCommitment(commitmentId, { state: newState });
        await Promise.all([fetchDigest(), fetchCommitments(), fetchBoard(), fetchCalendar()]);
      } catch (err) {
        showError("Could not update commitment — is the backend running?");
        toggleBtn.disabled = false;
      }
      return;
    }

    const setStateBtn = e.target.closest("[data-set-state]");
    if (setStateBtn) {
      const commitmentId = setStateBtn.dataset.commitmentId;
      const targetState = setStateBtn.dataset.setState;

      setStateBtn.disabled = true;
      try {
        await updateCommitment(commitmentId, { state: targetState });
        await Promise.all([fetchDigest(), fetchCommitments(), fetchBoard(), fetchCalendar()]);
      } catch (err) {
        showError("Could not update commitment — is the backend running?");
        setStateBtn.disabled = false;
      }
      return;
    }

    const editBtn = e.target.closest("[data-edit-deadline]");
    if (editBtn) {
      startEditingDeadline(editBtn.closest("[data-deadline-row]"));
      return;
    }

    const saveBtn = e.target.closest("[data-save-deadline]");
    if (saveBtn) {
      const row = saveBtn.closest("[data-deadline-row]");
      const startInput = row.querySelector("[data-start-input]");
      const endInput = row.querySelector("[data-end-input]");
      const commitmentId = row.dataset.commitmentId;
      const endValue = endInput.value; // "YYYY-MM-DDTHH:mm", local time —
      // the browser's datetime-local input has no timezone; new Date()
      // parses it as local time, and .toISOString() converts to UTC for
      // the backend's timezone-aware datetime field.
      const startValue = startInput.value; // optional — a plain deadline
      // (no range) is still the common case, so this can be left blank.
      if (!endValue) return;

      saveBtn.disabled = true;
      try {
        const updates = { inferred_deadline: new Date(endValue).toISOString() };
        if (startValue) updates.starts_at = new Date(startValue).toISOString();
        await updateCommitment(commitmentId, updates);
        await Promise.all([fetchDigest(), fetchCommitments(), fetchBoard(), fetchCalendar()]);
      } catch (err) {
        showError("Could not update deadline — is the backend running?");
        saveBtn.disabled = false;
      }
      return;
    }

    const cancelBtn = e.target.closest("[data-cancel-deadline]");
    if (cancelBtn) {
      const row = cancelBtn.closest("[data-deadline-row]");
      cancelEditingDeadline(row);
      return;
    }

    const deleteBtn = e.target.closest("[data-delete-commitment]");
    if (deleteBtn) {
      const confirmed = window.confirm("Delete this commitment? This can't be undone from the UI.");
      if (!confirmed) return;

      const commitmentId = deleteBtn.dataset.commitmentId;
      deleteBtn.disabled = true;
      try {
        await deleteCommitment(commitmentId);
        await Promise.all([fetchDigest(), fetchCommitments(), fetchBoard(), fetchCalendar()]);
      } catch (err) {
        showError("Could not delete commitment — is the backend running?");
        deleteBtn.disabled = false;
      }
    }
  });

  // Calendar prev/next month navigation
  document.getElementById("calendarPrevBtn")?.addEventListener("click", () => {
    calendarState.month -= 1;
    if (calendarState.month < 0) { calendarState.month = 11; calendarState.year -= 1; }
    renderCalendarGrid();
  });
  document.getElementById("calendarNextBtn")?.addEventListener("click", () => {
    calendarState.month += 1;
    if (calendarState.month > 11) { calendarState.month = 0; calendarState.year += 1; }
    renderCalendarGrid();
  });

  // Calendar day/event clicks — event delegation since cells are rendered
  // dynamically. Clicking an event pill opens edit mode for that specific
  // commitment; clicking anywhere else in a day cell opens assign mode
  // for that date (stopPropagation on the event pill prevents both
  // firing at once).
  document.getElementById("calendarGrid")?.addEventListener("click", (e) => {
    const eventPill = e.target.closest("[data-calendar-event]");
    if (eventPill) {
      e.stopPropagation();
      openCalendarEditPanel(eventPill.dataset.commitmentId);
      return;
    }
    const dayCell = e.target.closest("[data-calendar-day]");
    if (dayCell) {
      openCalendarAssignPanel(dayCell.dataset.date);
    }
  });

  document.getElementById("calendarAssignCancelBtn")?.addEventListener("click", closeCalendarPanel);

  document.getElementById("calendarAssignSaveBtn")?.addEventListener("click", async () => {
    const dateTimeInput = document.getElementById("calendarAssignDateTime");
    const startInput = document.getElementById("calendarAssignStartDateTime");
    const value = dateTimeInput.value;
    if (!value) return;

    const commitmentId =
      calendarPanelTarget.mode === "edit"
        ? calendarPanelTarget.commitmentId
        : document.getElementById("calendarAssignSelect").value;
    if (!commitmentId) return;

    const saveBtn = document.getElementById("calendarAssignSaveBtn");
    saveBtn.disabled = true;
    try {
      const updates = { inferred_deadline: new Date(value).toISOString() };
      if (startInput.value) updates.starts_at = new Date(startInput.value).toISOString();
      await updateCommitment(commitmentId, updates);
      closeCalendarPanel();
      await Promise.all([fetchDigest(), fetchCommitments(), fetchBoard(), fetchCalendar()]);
    } catch (err) {
      showError("Could not set deadline — is the backend running?");
    } finally {
      saveBtn.disabled = false;
    }
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
        await updateCommitment(commitmentId, { state: targetState });
        await Promise.all([fetchDigest(), fetchCommitments(), fetchBoard(), fetchCalendar()]);
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
