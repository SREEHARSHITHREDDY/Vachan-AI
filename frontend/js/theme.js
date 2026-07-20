/**
 * Theme toggle (dark/light), persisted in localStorage.
 *
 * Precedence: explicit user choice (localStorage) > OS preference
 * (prefers-color-scheme) > dark default. This is a plain local HTML/JS
 * app served by the user's own machine — NOT a claude.ai artifact — so
 * localStorage is the correct, normal tool here.
 */

const STORAGE_KEY = "vachanai-theme";

export function initTheme() {
  const stored = localStorage.getItem(STORAGE_KEY);
  const prefersLight = window.matchMedia("(prefers-color-scheme: light)").matches;
  const theme = stored || (prefersLight ? "light" : "dark");
  applyTheme(theme);
}

export function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem(STORAGE_KEY, theme);
  const label = document.getElementById("themeLabel");
  const icon = document.getElementById("themeIcon");
  if (label) label.textContent = theme === "dark" ? "Dark Mode" : "Light Mode";
  if (icon) icon.textContent = theme === "dark" ? "🌙" : "☀️";
}

export function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  applyTheme(current === "dark" ? "light" : "dark");
}
