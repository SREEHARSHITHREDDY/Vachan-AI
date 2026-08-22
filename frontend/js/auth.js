/**
 * Auth screen logic — login/signup forms, token storage, and gating the
 * app-shell behind a valid session. Loaded before app.js so the gate
 * check happens first.
 *
 * Deliberately simple: on successful login/signup, reload the page
 * rather than trying to hand off in-memory state to app.js's own init()
 * mid-flight. A reload is one extra network round-trip on an action the
 * user does once per session (or once ever) — not worth the added
 * complexity of coordinating two modules' startup order for that.
 */

import { signup, login } from "./api.js";

const TOKEN_KEY = "vachanai_token";
const PERSONA_KEY = "vachanai_persona";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getPersona() {
  return localStorage.getItem(PERSONA_KEY);
}

export function isAuthenticated() {
  return Boolean(getToken());
}

export function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(PERSONA_KEY);
  window.location.reload();
}

function showAuthError(message) {
  const el = document.getElementById("authError");
  el.textContent = message;
  el.style.display = "block";
}

function clearAuthError() {
  const el = document.getElementById("authError");
  el.style.display = "none";
}

function switchAuthTab(tab) {
  clearAuthError();
  document.querySelectorAll(".auth-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.authTab === tab);
  });
  document.getElementById("loginForm").style.display = tab === "login" ? "block" : "none";
  document.getElementById("signupForm").style.display = tab === "signup" ? "block" : "none";
}

async function handleLogin() {
  const email = document.getElementById("loginEmail").value.trim();
  const password = document.getElementById("loginPassword").value;
  const btn = document.getElementById("loginBtn");
  clearAuthError();

  if (!email || !password) {
    showAuthError("Enter both email and password.");
    return;
  }

  btn.disabled = true;
  btn.textContent = "Logging in...";
  try {
    const data = await login(email, password);
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(PERSONA_KEY, data.persona_mode);
    window.location.reload();
  } catch (err) {
    showAuthError(err.message || "Login failed.");
    btn.disabled = false;
    btn.textContent = "Log In";
  }
}

async function handleSignup() {
  const email = document.getElementById("signupEmail").value.trim();
  const password = document.getElementById("signupPassword").value;
  const persona = document.getElementById("signupPersona").value;
  const btn = document.getElementById("signupBtn");
  clearAuthError();

  if (!email || !password) {
    showAuthError("Enter both email and password.");
    return;
  }
  if (password.length < 8) {
    showAuthError("Password must be at least 8 characters.");
    return;
  }

  btn.disabled = true;
  btn.textContent = "Creating account...";
  try {
    const data = await signup(email, password, persona);
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(PERSONA_KEY, data.persona_mode);
    window.location.reload();
  } catch (err) {
    showAuthError(err.message || "Signup failed.");
    btn.disabled = false;
    btn.textContent = "Create Account";
  }
}

export function initAuthScreen() {
  if (isAuthenticated()) {
    document.getElementById("authScreen").style.display = "none";
    return true;
  }

  document.getElementById("authScreen").style.display = "flex";
  document.querySelectorAll("[data-auth-tab]").forEach((btn) => {
    btn.addEventListener("click", () => switchAuthTab(btn.dataset.authTab));
  });
  document.getElementById("loginBtn").addEventListener("click", handleLogin);
  document.getElementById("signupBtn").addEventListener("click", handleSignup);

  // Enter key submits whichever form is currently visible.
  document.getElementById("loginPassword").addEventListener("keydown", (e) => {
    if (e.key === "Enter") handleLogin();
  });
  document.getElementById("signupPassword").addEventListener("keydown", (e) => {
    if (e.key === "Enter") handleSignup();
  });

  return false;
}
