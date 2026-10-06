/**
 * Ambient 3D background — a field of slowly drifting wireframe
 * icosahedrons rendered with Three.js, sitting fixed behind the entire
 * app (pointer-events: none, so it can never intercept a click, drag,
 * or form interaction). Reacts subtly to scroll position and mouse
 * movement for a genuine sense of depth, without ever becoming the
 * thing the user has to interact with — the actual app underneath is
 * always what's clickable.
 *
 * Loaded via the same CDN-ESM pattern already used for Motion
 * (js/animations.js) — no build step, consistent with the rest of this
 * codebase's architecture (ADR-011/017).
 *
 * Like animations.js, this degrades silently: if the Three.js CDN import
 * fails for any reason (offline, ad-blocker, etc.), init() just resolves
 * without a scene rather than throwing — a decorative layer must never
 * be able to break the actual app underneath it.
 */

let renderer = null;
let scene = null;
let camera = null;
let shapes = [];
let scrollFraction = 0;
let mouseX = 0;
let mouseY = 0;

export async function initThreeBackground() {
  let THREE;
  try {
    THREE = await import("https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js");
  } catch (err) {
    console.warn("Three.js background failed to load — continuing without it:", err);
    return;
  }

  try {
    const canvas = document.getElementById("threeBackgroundCanvas");
    if (!canvas) return;

    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(window.innerWidth, window.innerHeight);

    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 100);
    camera.position.z = 18;

    // VachanAI's own accent colors — ties the background to the actual
    // app identity rather than being generic decoration.
    const palette = [0x7c9eff, 0x5fd28d, 0xf0a857];
    const geometry = new THREE.IcosahedronGeometry(1, 0);

    for (let i = 0; i < 22; i++) {
      const color = palette[i % palette.length];
      const material = new THREE.MeshBasicMaterial({ color, wireframe: true, transparent: true, opacity: 0.28 });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.set(
        (Math.random() - 0.5) * 30,
        (Math.random() - 0.5) * 30,
        (Math.random() - 0.5) * 20 - 5
      );
      const scale = 0.4 + Math.random() * 1.1;
      mesh.scale.set(scale, scale, scale);
      mesh.userData.rotationSpeed = {
        x: (Math.random() - 0.5) * 0.004,
        y: (Math.random() - 0.5) * 0.004,
      };
      mesh.userData.baseY = mesh.position.y;
      scene.add(mesh);
      shapes.push(mesh);
    }

    window.addEventListener("resize", onResize);
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("scroll", onScroll, { passive: true });

    animateFrame();
  } catch (err) {
    console.warn("Three.js background init failed — continuing without it:", err);
  }
}

function onResize() {
  if (!renderer || !camera) return;
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}

function onMouseMove(e) {
  mouseX = (e.clientX / window.innerWidth - 0.5) * 2;
  mouseY = (e.clientY / window.innerHeight - 0.5) * 2;
}

function onScroll() {
  // The sidebar uses position:sticky with height:100vh and .main-content
  // has no overflow/height constraint of its own — that combination only
  // works if the PAGE itself scrolls (not a nested scrollable div), so
  // this tracks window scroll, not any single element's scrollTop.
  const max = document.documentElement.scrollHeight - window.innerHeight;
  scrollFraction = max > 0 ? window.scrollY / max : 0;
}

function animateFrame() {
  if (!renderer || !scene || !camera) return;
  requestAnimationFrame(animateFrame);

  shapes.forEach((mesh) => {
    mesh.rotation.x += mesh.userData.rotationSpeed.x;
    mesh.rotation.y += mesh.userData.rotationSpeed.y;
  });

  // Subtle camera drift tied to scroll + mouse — enough to feel alive
  // and "3D scroll-based", never enough to be distracting from the
  // actual UI in front of it.
  camera.position.x += (mouseX * 2 - camera.position.x) * 0.02;
  camera.position.y += (-mouseY * 2 - scrollFraction * 4 - camera.position.y) * 0.02;
  camera.lookAt(0, -scrollFraction * 4, 0);

  renderer.render(scene, camera);
}

// Bound with capture:true so this fires even if some future element
// stops propagation of scroll events elsewhere in the app — this
// listener's only job is tracking window scroll position, independent
// of anything else happening in the DOM.
document.addEventListener("scroll", onScroll, true);
