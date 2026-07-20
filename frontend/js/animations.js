/**
 * Animation helpers using Motion (the vanilla-JS sibling of Framer
 * Motion — same creators, no React/build-step required).
 *
 * Every exported function degrades gracefully if the Motion CDN import
 * fails: `animate`/`stagger` stay null, and each helper falls back to
 * an instant, no-animation state change instead of throwing. Decorative
 * layers must never be able to break the actual app.
 */

let animate = null;
let stagger = null;

export async function initAnimations() {
  const motion = await import("https://cdn.jsdelivr.net/npm/motion@11/+esm");
  animate = motion.animate;
  stagger = motion.stagger;
}

export function fadeInStagger(selector) {
  if (!animate) return;
  try {
    animate(selector, { opacity: [0, 1], y: [16, 0] }, { duration: 0.5, delay: stagger(0.08), easing: "ease-out" });
  } catch (_) { /* decorative only — never throw */ }
}

export function slideInList(selector) {
  if (!animate) return;
  try {
    animate(selector, { opacity: [0, 1], x: [-8, 0] }, { duration: 0.35, delay: stagger(0.05), easing: "ease-out" });
  } catch (_) { /* decorative only — never throw */ }
}

export function fadeInBanner(el) {
  if (!animate) return;
  try {
    animate(el, { opacity: [0, 1], y: [-6, 0] }, { duration: 0.3, easing: "ease-out" });
  } catch (_) { /* decorative only — never throw */ }
}

export function countUp(el, from, to) {
  if (from === to) { el.textContent = to; return; }
  if (!animate) { el.textContent = to; return; }
  try {
    const obj = { val: from };
    animate(obj, { val: to }, {
      duration: 0.6,
      easing: "ease-out",
      onUpdate: (latest) => { el.textContent = Math.round(latest.val); },
    });
  } catch (_) {
    el.textContent = to;
  }
}
