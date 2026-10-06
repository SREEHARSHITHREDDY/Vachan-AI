/**
 * Animation helpers using Motion (the vanilla-JS sibling of Framer
 * Motion — same creators, no React/build-step required).
 *
 * Every exported function degrades gracefully if the Motion CDN import
 * fails: `animate`/`stagger`/`inView` stay null, and each helper falls
 * back to an instant, no-animation state change instead of throwing.
 * Decorative layers must never be able to break the actual app.
 *
 * scrollReveal3D is the new piece for the 3D/scroll-based redesign: it
 * uses Motion's inView() to trigger a 3D rotate+depth entrance the first
 * time each matched element scrolls into view within its container
 * (this app's real scroll container is .main-content, not the window —
 * the sidebar layout keeps <body> itself from scrolling).
 */

let animate = null;
let stagger = null;
let inView = null;

export async function initAnimations() {
  const motion = await import("https://cdn.jsdelivr.net/npm/motion@11/+esm");
  animate = motion.animate;
  stagger = motion.stagger;
  inView = motion.inView;
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
    animate(from, to, {
      duration: 0.6,
      easing: "ease-out",
      onUpdate: (latest) => { el.textContent = Math.round(latest); },
    });
  } catch (_) {
    el.textContent = to;
  }
}

/**
 * Scroll-triggered 3D entrance: each matched element starts tilted back
 * in 3D space and fades/rotates into place the moment it scrolls into
 * view. `once: true` means it only plays the first time — re-scrolling
 * past an already-revealed card shouldn't re-trigger it every time,
 * which would be distracting rather than immersive on a dashboard
 * someone uses daily.
 *
 * Falls back to setting final-state styles directly (no animation) if
 * Motion isn't available — the element must still end up visible and
 * correctly positioned either way.
 */
export function scrollReveal3D(selector, options = {}) {
  const elements = document.querySelectorAll(selector);
  if (!elements.length) return;

  const { rootMargin = "0px 0px -80px 0px" } = options;

  elements.forEach((el) => {
    el.style.opacity = "0";
    el.style.transform = "perspective(900px) rotateX(-10deg) translateY(28px)";

    if (!inView) {
      // No Motion available — just show it, no animation.
      el.style.opacity = "1";
      el.style.transform = "none";
      return;
    }

    try {
      inView(
        el,
        () => {
          animate(
            el,
            { opacity: [0, 1], transform: ["perspective(900px) rotateX(-10deg) translateY(28px)", "perspective(900px) rotateX(0deg) translateY(0px)"] },
            { duration: 0.7, easing: [0.16, 1, 0.3, 1] }
          );
        },
        { margin: rootMargin, amount: 0.2 }
        // No `root` override — Motion defaults to the browser viewport,
        // which is correct here since the page itself scrolls (the
        // sidebar's position:sticky + height:100vh only makes sense with
        // window-level scrolling, not a nested scrollable container).
      );
    } catch (_) {
      el.style.opacity = "1";
      el.style.transform = "none";
    }
  });
}
