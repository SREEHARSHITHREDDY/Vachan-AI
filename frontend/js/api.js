/**
 * Thin API client — wraps fetch calls to the backend, returns parsed
 * JSON, throws on non-success responses. No DOM logic here at all
 * (kept separate from app.js) so the API contract is testable/reusable
 * independent of how it's rendered.
 *
 * Per-user isolation update: every commitments/contacts request now
 * attaches the logged-in user's JWT as an Authorization header, read
 * directly from localStorage (same key auth.js writes to). This file
 * intentionally does NOT import from auth.js — auth.js already imports
 * signup/login FROM this file, and a two-way import between them would
 * be a circular dependency. Duplicating just the one storage key name
 * is a small, safe price for avoiding that.
 */

const API_BASE = "http://localhost:8000/api/v1";
const TOKEN_KEY = "vachanai_token";

function authHeaders() {
  const token = localStorage.getItem(TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  const json = await res.json();
  if (!json.success) {
    throw new Error(json.error?.message || json.detail || `Request to ${path} failed`);
  }
  return json.data;
}

export function getDigest() {
  return request("/digest/today");
}

export function getCommitments(state = null) {
  const query = state ? `?state=${encodeURIComponent(state)}` : "";
  return request(`/commitments${query}`);
}

export function postMessage(body, channel = "message") {
  return request("/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body, channel }),
  });
}

export function updateCommitment(commitmentId, updates) {
  return request(`/commitments/${commitmentId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
}

export function deleteCommitment(commitmentId) {
  return request(`/commitments/${commitmentId}`, { method: "DELETE" });
}


// ---------- Contacts (Phase 1 feature) ----------
// Now shares the same authHeaders() helper as the rest of this file —
// contacts are per-user too, same as commitments.

export function getContacts() {
  return request("/contacts");
}

export function createContact(name, emailOrHandle, roleTag) {
  return request("/contacts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email_or_handle: emailOrHandle, role_tag: roleTag }),
  });
}

export function updateContact(contactId, updates) {
  return request(`/contacts/${contactId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
}

export function deleteContact(contactId) {
  return request(`/contacts/${contactId}`, { method: "DELETE" });
}

// ---------- Auth (signup / login) ----------
// Deliberately does NOT attach an Authorization header — signup and
// login are the only two calls a user makes before they have a token at
// all. Kept on its own request helper (not the shared one above) for
// exactly that reason, and because its error shape is different (plain
// FastAPI {"detail": "..."}, not this app's {"success","error"} envelope).

async function authRequest(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const json = await response.json();
  if (response.status >= 400) {
    throw new Error(json.detail || "Request failed");
  }
  return json;
}

export function signup(email, password, personaMode) {
  return authRequest("/auth/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, persona_mode: personaMode }),
  });
}

export function login(email, password) {
  return authRequest("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}
