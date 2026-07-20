/**
 * Thin API client — wraps fetch calls to the backend, returns parsed
 * JSON, throws on non-success responses. No DOM logic here at all
 * (kept separate from app.js) so the API contract is testable/reusable
 * independent of how it's rendered.
 */

const API_BASE = "http://localhost:8000/api/v1";

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  const json = await res.json();
  if (!json.success) {
    throw new Error(json.error?.message || `Request to ${path} failed`);
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

export function postMessage(body) {
  return request("/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body }),
  });
}
