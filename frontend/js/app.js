/**
 * Main application entry point — sidebar navigation, rendering, and
 * event wiring. Imports the smaller focused modules (api, theme,
 * animations, background) rather than doing everything in one file.
 *
 * Sidebar scope note: per the UI/UX design doc (docs/05_UIUX_Design.md,
 * Section 6.3), the full screen list includes Contacts, Actions, and
 * Settings. Contacts now has a real backend + UI (Phase 1); Settings
 * remains an honest "Soon" panel — no backend route built for it yet.
 */

import {
  getDigest, getCommitments, postMessage, updateCommitment, deleteCommitment,
  getContacts, createContact, updateContact, deleteContact,
  getMe, updateMe,
  inspectWhatsApp, importWhatsApp, syncGmail, getConnectorStatus, getContactCommitments,
} from "./api.js";
import { initTheme, toggleTheme } from "./theme.js";
import { initAnimations, fadeInStagger, slideInList, fadeInBanner, countUp, scrollReveal3D } from "./animations.js";
import { initAuthScreen, logout } from "./auth.js";
import { initThreeBackground } from "./three-background.js";

let lastCounts = { atRisk: 0, pending: 0, fulfilled: 0 };
let calendarState = { year: new Date().getFullYear(), month: new Date().getMonth() };
let calendarCommitmentsCache = [];
let calendarPanelTarget = { mode: null, commitmentId: null, date: null };
let contactsCache = []; // populated at init() so the contact-assign
// dropdown on every commitment card is ready even before the user ever
// opens the Contacts tab itself.

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const ROLE_TAG_EMOJI = {
  friend: "🙂", professor: "🎓", recruiter: "💼",
  teammate: "🤝", family: "👨‍👩‍👧", other: "👤",
};

function highlightSelectedDay(dateKey) {
  document.querySelectorAll("[data-calendar-day].calendar-cell-selected")
    .forEach((el) => el.classList.remove("calendar-cell-selected"));
  const cell = document.querySelector(`[data-calendar-day][data-date="${dateKey}"]`);
  if (cell) cell.classList.add("calendar-cell-selected");
}

function clearSelectedDay() {
  document.querySelectorAll("[data-calendar-day].calendar-cell-selected")
    .forEach((el) => el.classList.remove("calendar-cell-selected"));
}

function openCalendarAssignPanel(dateKey) {
  const noDeadlineCommitments = calendarCommitmentsCache.filter((c) => !c.inferred_deadline);
  const panel = document.getElementById("calendarAssignPanel");
  const select = document.getElementById("calendarAssignSelect");
  const label = document.getElementById("calendarAssignLabel");
  const startLabel = document.getElementById("calendarAssignStartLabel");
  const startInput = document.getElementById("calendarAssignStartDateTime");
  const dateTimeInput = document.getElementById("calendarAssignDateTime");

  highlightSelectedDay(dateKey);

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

  clearSelectedDay();

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
  clearSelectedDay();
}

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
  gmail: "Gmail",
  whatsapp: "WhatsApp",
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
  if (viewName === "contacts") { fetchContacts(); }
  if (viewName === "settings") { fetchSettings(); }
  if (viewName === "connect") { fetchConnectorStatus(); }

  // Scroll-triggered 3D reveal has to (re-)run AFTER the section is
  // actually visible — an element inside a display:none view has no
  // layout box, so a scroll observer attached while it's hidden won't
  // reliably fire once it becomes visible. Scoped to just the newly
  // active view, not the whole document, so already-revealed elements
  // in other views don't get re-triggered every time you switch tabs.
  scrollReveal3D(`#view-${viewName}[class*="active"] [data-animate]`);
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

function contactAssignHtml(c) {
  const options = contactsCache
    .map((ct) => `<option value="${ct.contact_id}" ${ct.contact_id === c.contact_id ? "selected" : ""}>${ROLE_TAG_EMOJI[ct.role_tag] || "👤"} ${escapeHtml(ct.name)}</option>`)
    .join("");
  return `
    <select class="contact-assign-select" data-assign-contact data-commitment-id="${c.commitment_id}" title="Link this commitment to a contact">
      <option value="">No contact linked</option>
      ${options}
    </select>
  `;
}

const REMINDER_OPTIONS = [
  [0, "No reminder"],
  [15, "15 min before"],
  [60, "1 hour before"],
  [1440, "1 day before"],
];

function reminderRowHtml(c) {
  // Calendar Actions: only makes sense once a deadline exists — "remind
  // me before X" is meaningless with no X. Nothing rendered otherwise,
  // rather than a disabled/confusing control.
  if (!c.inferred_deadline) return "";
  const current = c.reminder_minutes_before || 0;
  const options = REMINDER_OPTIONS
    .map(([mins, label]) => `<option value="${mins}" ${mins === current ? "selected" : ""}>${label}</option>`)
    .join("");
  return `
    <div class="deadline-row" style="margin-top:6px;">
      <span class="deadline-display">🔔 Reminder:</span>
      <select class="contact-assign-select" data-set-reminder data-commitment-id="${c.commitment_id}" title="Get a browser notification before this is due" style="margin-top:0;">
        ${options}
      </select>
    </div>
  `;
}

function commitmentItemHtml(c) {
  const channelLabel = c.channel ? CHANNEL_LABELS[c.channel] || c.channel : null;
  const channelPart = channelLabel ? ` · via ${channelLabel}` : "";
  return `
    <div class="commitment-item" data-commitment-item>
      <div style="flex:1;">
        <div class="commitment-desc">${escapeHtml(c.description)}</div>
        ${c.contact_name ? `<div class="commitment-meta" style="font-weight:600;">👤 With ${escapeHtml(c.contact_name)}</div>` : ""}
        <div class="commitment-meta">${c.commitment_type}${channelPart} · created ${formatDate(c.created_at)}${c.resolved_at ? " · resolved " + formatDate(c.resolved_at) : ""}</div>
        ${deadlineRowHtml(c)}
        ${contactAssignHtml(c)}
        ${reminderRowHtml(c)}
      </div>
      <div style="display:flex; align-items:center; gap:8px; flex-shrink:0;">
        ${badgeHtml(c.state)}
        ${actionButtonsHtml(c)}
        <button class="delete-btn" data-delete-commitment data-commitment-id="${c.commitment_id}" title="Delete this commitment">🗑</button>
      </div>
    </div>
  `;
}

function contactItemHtml(c) {
  const open = c.open_commitments || 0;
  const done = c.fulfilled_commitments || 0;
  const status = open || done
    ? `${open} open · ${done} fulfilled${c.next_deadline ? " · next: " + formatDate(c.next_deadline) : ""}`
    : "No commitments yet";
  return `
    <div class="commitment-item" data-contact-item>
      <div style="flex:1;">
        <div class="commitment-desc">${ROLE_TAG_EMOJI[c.role_tag] || "👤"} ${escapeHtml(c.name)}</div>
        <div class="commitment-meta">${escapeHtml(c.email_or_handle)} · ${c.role_tag}</div>
        <div class="commitment-meta" style="font-weight:600;">${status}</div>
        <button class="deadline-edit-btn" style="margin-top:8px;" data-toggle-contact-commitments data-contact-id="${c.contact_id}">Commitments ▾</button>
        <div data-contact-commitments="${c.contact_id}" style="display:none;"></div>
      </div>
      <div style="display:flex; align-items:center; gap:8px; flex-shrink:0;">
        <button class="delete-btn" data-delete-contact data-contact-id="${c.contact_id}" title="Delete this contact">🗑</button>
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

async function fetchContactsCache() {
  try {
    contactsCache = await getContacts();
  } catch (err) {
    console.warn("Could not preload contacts:", err);
  }
}

async function fetchContacts() {
  const listEl = document.getElementById("contactsList");
  listEl.innerHTML = skeletonCommitmentItems(2);

  try {
    contactsCache = await getContacts();
    listEl.innerHTML = contactsCache.length
      ? contactsCache.map(contactItemHtml).join("")
      : `<div class="empty-state">No contacts yet — add the people you make and receive promises with.</div>`;
    slideInList("#contactsList [data-contact-item]");
  } catch (err) {
    listEl.innerHTML = "";
    showError("Could not load contacts — is the backend running at localhost:8000?");
  }
}

async function fetchSettings() {
  try {
    const me = await getMe();
    document.getElementById("settingsEmail").textContent = me.email;
    document.getElementById("settingsVerified").textContent = me.is_verified ? "✓ Verified" : "Not verified";
    document.getElementById("settingsCreatedAt").textContent = formatDate(me.created_at);
    document.getElementById("settingsPersonaSelect").value = me.persona_mode;
  } catch (err) {
    showError("Could not load account settings — is the backend running at localhost:8000?");
  }
}

function dateRangeKeys(startIso, endIso) {
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
  const reminderTag = c.reminder_minutes_before ? " 🔔" : "";
  return `
    <div class="kanban-card" draggable="true" data-kanban-card
         data-commitment-id="${c.commitment_id}" data-current-state="${c.state}">
      <div class="kanban-card-desc">${escapeHtml(c.description)}${reminderTag}</div>
      <div class="kanban-card-meta">${c.commitment_type}${channelLabel ? " · " + channelLabel : ""}${c.contact_name ? " · " + escapeHtml(c.contact_name) : ""}</div>
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

// ---------- Message connectors (WhatsApp export, Gmail sent mail) ----------

let waFiles = []; // [{ name, text, chatName }]
const WA_MAX_BYTES = 3_000_000;
const WA_MAX_FILES = 8;

function plural(n, word) { return `${n} ${word}${n === 1 ? "" : "s"}`; }

function showConnectBanner(id, text, kind) {
  const el = document.getElementById(id);
  el.textContent = text;
  el.className = `result-banner ${kind}`;
  el.style.display = "block";
  fadeInBanner(el);
}

function ingestSummaryText(s) {
  const parts = [
    `${plural(s.processed, "message")} read`,
    plural(s.commitments_created, "new commitment"),
    `${s.commitments_resolved} fulfilled`,
  ];
  if (s.incoming_processed) parts.push(`${s.incoming_processed} from other people`);
  if (s.duplicates_skipped) parts.push(`${plural(s.duplicates_skipped, "duplicate")} merged`);
  if (s.already_imported) parts.push(`${s.already_imported} already imported`);
  if (s.skipped_trivial) parts.push(`${s.skipped_trivial} too short to track`);
  if (s.contacts_created) parts.push(plural(s.contacts_created, "new contact"));
  let text = `✓ ${parts.join(" · ")}`;
  if (s.aborted) text += ` — stopped early after repeated errors (${s.errors[0]}). Check the backend and GROQ_API_KEY, then run it again; nothing is lost.`;
  else if (s.errors.length) text += ` — ${s.errors.length} message(s) failed and will be retried next time.`;
  return text;
}

function mergeSummaries(list) {
  const sum = (k) => list.reduce((a, s) => a + (s[k] || 0), 0);
  const people = new Map();
  for (const s of list) {
    for (const p of s.by_person || []) {
      const cur = people.get(p.contact_name) ||
        { contact_name: p.contact_name, messages: 0, commitments_created: 0, commitments_resolved: 0 };
      cur.messages += p.messages;
      cur.commitments_created += p.commitments_created;
      cur.commitments_resolved += p.commitments_resolved;
      people.set(p.contact_name, cur);
    }
  }
  return {
    processed: sum("processed"), incoming_processed: sum("incoming_processed"),
    commitments_created: sum("commitments_created"), commitments_resolved: sum("commitments_resolved"),
    duplicates_skipped: sum("duplicates_skipped"), already_imported: sum("already_imported"),
    skipped_trivial: sum("skipped_trivial"), contacts_created: sum("contacts_created"),
    errors: list.flatMap((s) => s.errors || []), aborted: list.some((s) => s.aborted),
    items: list.flatMap((s) => s.items || []),
    awaiting_reply: list.flatMap((s) => s.awaiting_reply || [])
      .sort((a, b) => new Date(b.sent_at) - new Date(a.sent_at)),
    by_person: [...people.values()],
  };
}

// Results are grouped by PERSON so it is obvious who each promise is with.
function renderIngestResults(containerId, s) {
  const groups = new Map();
  for (const it of s.items) {
    const key = it.contact_name || "Not linked to a person";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(it);
  }
  let html = "";
  for (const [person, items] of groups) {
    const stats = (s.by_person || []).find((p) => p.contact_name === person);
    html += `<div class="settings-label" style="margin-top:18px;">👤 ${escapeHtml(person)}` +
      (stats ? ` <span class="commitment-meta" style="display:inline;">· ${plural(stats.commitments_created, "new commitment")}, ${stats.commitments_resolved} fulfilled</span>` : "") +
      `</div>`;
    html += items.map((it) => {
      const title = it.new_commitment
        ? `📌 ${escapeHtml(it.new_commitment)}`
        : "✅ Marked an earlier commitment as fulfilled";
      const when = it.deadline ? `⏰ ${formatDate(it.deadline)} · ` : "";
      return `
        <div class="commitment-item" style="margin-top:8px;">
          <div>
            <div class="commitment-desc">${title}</div>
            <div class="commitment-meta">${when}from ${escapeHtml(it.from_name || "—")} · ${formatDate(it.sent_at)} · "${escapeHtml(it.preview)}"</div>
          </div>
        </div>`;
    }).join("");
  }
  if (s.awaiting_reply && s.awaiting_reply.length) {
    html += `<div class="settings-label" style="margin-top:22px;">↩️ Waiting for your reply</div>` +
      s.awaiting_reply.map((a) => `
        <div class="commitment-item" style="margin-top:8px;">
          <div>
            <div class="commitment-desc">${escapeHtml(a.contact_name)} is waiting to hear back</div>
            <div class="commitment-meta">${formatDate(a.sent_at)} · "${escapeHtml(a.preview)}"</div>
          </div>
        </div>`).join("");
  }
  document.getElementById(containerId).innerHTML = html;
}

async function refreshAfterIngest() {
  // Contacts first: commitment cards show their person from this cache, and
  // a contact created by the import must be in it before they render.
  await fetchContactsCache();
  await Promise.all([fetchDigest(), fetchCommitments(), fetchBoard(), fetchCalendar(),
                     fetchConnectorStatus()]);
}

async function fetchConnectorStatus() {
  try {
    const st = await getConnectorStatus();
    for (const [key, id] of [["whatsapp", "waStatus"], ["gmail", "gmStatus"]]) {
      const { messages, last_synced_at } = st[key];
      document.getElementById(id).textContent = messages
        ? `${plural(messages, "message")} imported so far · last ${formatDate(last_synced_at)}`
        : "Nothing imported yet.";
    }
  } catch (err) { /* status line is optional; the cards still work without it */ }
}

async function handleWhatsAppFile(e) {
  const files = Array.from(e.target.files);
  const pickRow = document.getElementById("waPickRow");
  const hint = document.getElementById("waPickHint");
  pickRow.style.display = "none";
  hint.style.display = "none";
  document.getElementById("waResult").style.display = "none";
  document.getElementById("waItems").innerHTML = "";
  waFiles = [];
  if (!files.length) return;

  if (files.length > WA_MAX_FILES) {
    showConnectBanner("waResult", `Pick at most ${WA_MAX_FILES} chats at a time.`, "none");
    return;
  }

  const sightings = new Map(); // sender name -> { messages }
  const namesPerChat = [];      // one Set of names per chat that has 2+ people
  let totalMessages = 0;
  try {
    for (const file of files) {
      if (file.size > WA_MAX_BYTES) throw new Error(`"${file.name}" is too large (limit ~3 MB). Export without media.`);
      if (/\.zip$/i.test(file.name)) throw new Error(`"${file.name}" is a .zip — unzip it and choose the .txt inside.`);
      const text = await file.text();
      const nameMatch = file.name.match(/WhatsApp Chat (?:with|-) (.+?)(?:\.txt)?$/i);
      const info = await inspectWhatsApp(text).catch((err) => { throw new Error(`${file.name}: ${err.message}`); });
      waFiles.push({ name: file.name, text, chatName: nameMatch ? nameMatch[1].trim() : null });
      totalMessages += info.total_messages;
      for (const p of info.participants) {
        const cur = sightings.get(p.name) || { messages: 0 };
        cur.messages += p.message_count;
        sightings.set(p.name, cur);
      }
      // A chat where only the other person wrote (you never replied) can't
      // tell us who "you" are, so it must not veto the candidates.
      if (info.participants.length > 1) namesPerChat.push(new Set(info.participants.map((p) => p.name)));
    }
  } catch (err) {
    waFiles = [];
    showConnectBanner("waResult", err.message, "none");
    return;
  }

  // "Me" is whoever appears in every chat that has 2+ people; if that
  // narrows nothing down (e.g. a single chat), offer everyone.
  let candidates = [...sightings.entries()].filter(([name]) => namesPerChat.every((set) => set.has(name)));
  if (!candidates.length || !namesPerChat.length) candidates = [...sightings.entries()];
  candidates.sort((a, b) => b[1].messages - a[1].messages);
  document.getElementById("waMyName").innerHTML = candidates
    .map(([name, v]) => `<option value="${escapeHtml(name)}">${escapeHtml(name)} (${v.messages})</option>`)
    .join("");
  hint.textContent = `${plural(waFiles.length, "chat")} · ${plural(totalMessages, "message")} found. Choose which person is you.`;
  hint.style.display = "block";
  pickRow.style.display = "block";
}

async function handleWhatsAppImport() {
  if (!waFiles.length) return;
  const btn = document.getElementById("waImportBtn");
  btn.disabled = true;
  btn.textContent = "Importing...";
  document.getElementById("waResult").style.display = "none";
  document.getElementById("waItems").innerHTML = "";

  const myName = document.getElementById("waMyName").value;
  const maxMessages = Number(document.getElementById("waMax").value);
  const includeIncoming = document.getElementById("waIncoming").checked;
  const summaries = [];
  const failed = [];
  try {
    for (const f of waFiles) {
      btn.textContent = `Importing ${summaries.length + failed.length + 1}/${waFiles.length}...`;
      try {
        summaries.push(await importWhatsApp({ text: f.text, myName, chatName: f.chatName, maxMessages, includeIncoming }));
      } catch (err) {
        failed.push(`${f.name}: ${err.message}`);
      }
    }
    if (summaries.length) {
      const merged = mergeSummaries(summaries);
      let text = ingestSummaryText(merged);
      if (failed.length) text += ` — skipped ${failed.length} chat(s): ${failed.join(" | ")}`;
      showConnectBanner("waResult", text,
        merged.commitments_created || merged.commitments_resolved ? "extracted" : "none");
      renderIngestResults("waItems", merged);
      await refreshAfterIngest();
    } else {
      showConnectBanner("waResult", failed.join(" | "), "none");
    }
  } finally {
    btn.disabled = false;
    btn.textContent = "Import";
  }
}

async function handleGmailSync() {
  const address = document.getElementById("gmAddress").value.trim();
  const passwordInput = document.getElementById("gmAppPassword");
  if (!address || !passwordInput.value) {
    showConnectBanner("gmResult", "Enter your Gmail address and an app password.", "none");
    return;
  }
  const btn = document.getElementById("gmSyncBtn");
  btn.disabled = true;
  btn.textContent = "Syncing...";
  document.getElementById("gmResult").style.display = "none";
  document.getElementById("gmItems").innerHTML = "";
  try {
    const summary = await syncGmail({
      address,
      appPassword: passwordInput.value,
      days: Number(document.getElementById("gmDays").value),
    });
    passwordInput.value = ""; // never keep the secret in the page after use
    showConnectBanner("gmResult", ingestSummaryText(summary),
      summary.commitments_created || summary.commitments_resolved ? "extracted" : "none");
    renderIngestResults("gmItems", summary);
    await refreshAfterIngest();
  } catch (err) {
    showConnectBanner("gmResult", err.message, "none");
  } finally {
    btn.disabled = false;
    btn.textContent = "Sync sent mail";
  }
}

// Contacts page: expand a person to see everything tied to them.
async function handleToggleContactCommitments(e) {
  const btn = e.target.closest("[data-toggle-contact-commitments]");
  if (!btn) return;
  const id = btn.dataset.contactId;
  const box = document.querySelector(`[data-contact-commitments="${id}"]`);
  if (!box) return;
  if (box.style.display !== "none") {
    box.style.display = "none";
    btn.textContent = "Commitments ▾";
    return;
  }
  btn.disabled = true;
  try {
    const items = await getContactCommitments(id);
    box.innerHTML = items.length
      ? items.map((c) => `
          <div class="commitment-meta" style="margin-top:8px;">
            ${badgeHtml(c.state)} <b>${escapeHtml(c.description)}</b>
            ${c.inferred_deadline ? " · ⏰ " + formatDate(c.inferred_deadline) : ""}
            ${c.channel ? " · via " + (CHANNEL_LABELS[c.channel] || c.channel) : ""}
          </div>`).join("")
      : `<div class="commitment-meta" style="margin-top:8px;">Nothing tracked with this person yet.</div>`;
    box.style.display = "block";
    btn.textContent = "Commitments ▴";
  } catch (err) {
    showError(err.message);
  } finally {
    btn.disabled = false;
  }
}

async function handleAddContact() {
  const nameInput = document.getElementById("contactNameInput");
  const handleInput = document.getElementById("contactHandleInput");
  const roleSelect = document.getElementById("contactRoleSelect");
  const addBtn = document.getElementById("addContactBtn");

  const name = nameInput.value.trim();
  const handle = handleInput.value.trim();
  if (!name || !handle) {
    showError("A contact needs at least a name and an email or handle.");
    return;
  }

  addBtn.disabled = true;
  try {
    await createContact(name, handle, roleSelect.value);
    nameInput.value = "";
    handleInput.value = "";
    roleSelect.value = "other";
    await fetchContacts();
  } catch (err) {
    showError("Could not add contact — is the backend running?");
  } finally {
    addBtn.disabled = false;
  }
}

async function handleSavePersona() {
  const select = document.getElementById("settingsPersonaSelect");
  const btn = document.getElementById("settingsPersonaSaveBtn");
  const statusEl = document.getElementById("settingsPersonaStatus");
  statusEl.style.display = "none";

  btn.disabled = true;
  try {
    await updateMe({ persona_mode: select.value });
    statusEl.textContent = "Saved.";
    statusEl.style.display = "block";
    setTimeout(() => { statusEl.style.display = "none"; }, 3000);
  } catch (err) {
    showError("Could not save persona — is the backend running?");
  } finally {
    btn.disabled = false;
  }
}

// ---------- Init ----------

function wireNav() {
  document.querySelectorAll(".nav-item[data-view]").forEach((item) => {
    item.addEventListener("click", () => switchView(item.dataset.view));
  });
  document.getElementById("themeToggle").addEventListener("click", toggleTheme);
  document.getElementById("submitBtn").addEventListener("click", handleSubmitMessage);
  document.getElementById("addContactBtn")?.addEventListener("click", handleAddContact);
  document.getElementById("waFile")?.addEventListener("change", handleWhatsAppFile);
  document.getElementById("waImportBtn")?.addEventListener("click", handleWhatsAppImport);
  document.getElementById("gmSyncBtn")?.addEventListener("click", handleGmailSync);
  document.addEventListener("click", handleToggleContactCommitments);
  document.getElementById("settingsPersonaSaveBtn")?.addEventListener("click", handleSavePersona);
  document.getElementById("settingsLogoutBtn")?.addEventListener("click", logout);
  document.querySelectorAll(".channel-option").forEach((btn) => {
    btn.addEventListener("click", () => selectChannel(btn.dataset.channel));
  });

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
      const endValue = endInput.value;
      const startValue = startInput.value;
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
      return;
    }

    const deleteContactBtn = e.target.closest("[data-delete-contact]");
    if (deleteContactBtn) {
      const confirmed = window.confirm("Delete this contact? Commitments already linked to them will keep their history, just without a visible contact name.");
      if (!confirmed) return;

      const contactId = deleteContactBtn.dataset.contactId;
      deleteContactBtn.disabled = true;
      try {
        await deleteContact(contactId);
        await fetchContacts();
      } catch (err) {
        showError("Could not delete contact — is the backend running?");
        deleteContactBtn.disabled = false;
      }
    }
  });

  document.addEventListener("change", async (e) => {
    const assignSelect = e.target.closest("[data-assign-contact]");
    if (assignSelect) {
      const commitmentId = assignSelect.dataset.commitmentId;
      const contactId = assignSelect.value;
      if (!contactId) return;

      assignSelect.disabled = true;
      try {
        await updateCommitment(commitmentId, { contact_id: contactId });
        await Promise.all([fetchDigest(), fetchCommitments(), fetchBoard(), fetchCalendar()]);
      } catch (err) {
        showError("Could not link contact — is the backend running?");
      } finally {
        assignSelect.disabled = false;
      }
      return;
    }

    const reminderSelect = e.target.closest("[data-set-reminder]");
    if (reminderSelect) {
      const commitmentId = reminderSelect.dataset.commitmentId;
      const minutes = parseInt(reminderSelect.value, 10);

      // The actual confirmation gate: setting any real reminder (not
      // "No reminder") requires the browser's own explicit permission
      // prompt — the user has to confirm twice, once by picking an
      // offset here and once in the browser's own dialog, before
      // anything can ever notify them.
      if (minutes > 0 && await requestNotificationPermission() === false) {
        showError("Notifications were blocked — enable them in your browser settings to use reminders.");
        reminderSelect.value = "0";
        return;
      }

      reminderSelect.disabled = true;
      try {
        await updateCommitment(commitmentId, { reminder_minutes_before: minutes });
        await Promise.all([fetchDigest(), fetchCommitments(), fetchBoard(), fetchCalendar()]);
      } catch (err) {
        showError("Could not set reminder — is the backend running?");
      } finally {
        reminderSelect.disabled = false;
      }
    }
  });

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
      if (zone.dataset.dropzone === "at-risk") return;
      e.preventDefault();
      zone.classList.add("drag-over");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    zone.addEventListener("drop", async (e) => {
      e.preventDefault();
      zone.classList.remove("drag-over");
      const targetState = zone.dataset.dropzone;
      if (targetState === "at-risk") return;

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

// ---------- Calendar Actions (reminders) ----------
// Deliberately confirmation-gated at two layers: (1) the user must
// explicitly pick a non-zero offset on a specific commitment — nothing
// is ever reminded by default, and (2) that action triggers the
// browser's own native permission prompt, which the user can still
// decline even after opting in here. Nothing can ever notify without
// both of those explicit confirmations having happened.

let firedReminderIds = new Set();

async function requestNotificationPermission() {
  if (!("Notification" in window)) {
    showError("Your browser doesn't support notifications.");
    return false;
  }
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") return false;
  const result = await Notification.requestPermission();
  return result === "granted";
}

async function checkReminders() {
  // No-op (not an error) if permission was never granted — this is what
  // makes it safe to always have the polling interval running in the
  // background from app startup, rather than only starting it after the
  // first reminder is set.
  if (!("Notification" in window) || Notification.permission !== "granted") return;

  try {
    const data = await getCommitments();
    const now = Date.now();
    data.forEach((c) => {
      if (!c.reminder_minutes_before || !c.inferred_deadline) return;
      if (c.state === "fulfilled") return;
      if (firedReminderIds.has(c.commitment_id)) return;

      const deadlineMs = new Date(c.inferred_deadline).getTime();
      const reminderMs = deadlineMs - c.reminder_minutes_before * 60 * 1000;
      if (now >= reminderMs) {
        new Notification("VachanAI Reminder", {
          body: `"${c.description}" — due ${formatDate(c.inferred_deadline)}`,
          icon: "favicon.svg",
        });
        firedReminderIds.add(c.commitment_id); // once per session — a
        // page reload will re-check and could re-fire, which is
        // reasonable (the user asked to be reminded, and a reload isn't
        // "I saw it already").
      }
    });
  } catch (err) {
    console.warn("Reminder check failed:", err);
  }
}

function startReminderPolling() {
  checkReminders();
  setInterval(checkReminders, 60 * 1000);
}

// ---------- 3D tilt-on-hover ----------
// Event-delegated (not per-element listeners) since .kanban-card and
// .commitment-item elements are constantly re-rendered via innerHTML on
// every fetch — attaching listeners directly to them would mean
// re-attaching after every single re-render. One pair of document-level
// listeners handles every current and future matching element instead.
function attachTiltEffect() {
  const TILT_DEGREES = 8;

  document.addEventListener("mousemove", (e) => {
    const el = e.target.closest(".card, .kanban-card");
    // Skip entirely while a card is being dragged (kanban) — the tilt
    // transform would fight with the drag-and-drop system's own visual
    // state (`.dragging` sets opacity via CSS; adding a transform here
    // too would be a confusing, unintended combination during a drag).
    if (!el || el.classList.contains("dragging")) return;

    const rect = el.getBoundingClientRect();
    const relX = (e.clientX - rect.left) / rect.width - 0.5;
    const relY = (e.clientY - rect.top) / rect.height - 0.5;

    el.style.transform =
      `perspective(700px) rotateX(${(-relY * TILT_DEGREES).toFixed(2)}deg) ` +
      `rotateY(${(relX * TILT_DEGREES).toFixed(2)}deg) translateZ(4px)`;
  });

  // mouseleave doesn't bubble, but a capture-phase listener on document
  // still receives it for every element as the event travels down to
  // its target — this is the standard workaround for delegating a
  // non-bubbling event type.
  document.addEventListener("mouseleave", (e) => {
    const el = e.target?.closest?.(".card, .kanban-card");
    if (el) el.style.transform = "";
  }, true);
}

async function init() {
  const authenticated = initAuthScreen();
  if (!authenticated) return; // auth screen is showing; nothing else should run yet

  initTheme();
  wireNav();
  document.getElementById("logoutBtn")?.addEventListener("click", logout);
  selectChannel("message");
  fetchContactsCache();
  startReminderPolling();
  initThreeBackground(); // ambient 3D scene — decorative, degrades silently on failure
  attachTiltEffect();

  try {
    await initAnimations();
    // fadeInStagger removed here — scrollReveal3D (called per-view from
    // switchView) is the new, scroll-triggered replacement for section
    // entrance animation. Keeping both would double-animate the same
    // [data-animate] elements.
  } catch (err) { console.warn("Animations failed to load:", err); }

  switchView("digest");
}

init();
