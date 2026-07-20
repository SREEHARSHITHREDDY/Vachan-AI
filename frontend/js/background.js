/**
 * Three.js animated background — 6 soft, slowly-drifting glowing orbs.
 * Purely decorative: wrapped so a load/runtime failure here can never
 * break the actual application (see the try/catch in app.js's init).
 */

export async function initBackground() {
  const THREE = await import("https://cdn.jsdelivr.net/npm/three@0.169.0/build/three.module.js");

  const canvas = document.getElementById("bgCanvas");
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 100);
  camera.position.z = 12;

  scene.add(new THREE.AmbientLight(0x404060, 1.2));
  const pointLight = new THREE.PointLight(0x7c9eff, 2, 50);
  pointLight.position.set(5, 5, 10);
  scene.add(pointLight);

  const colors = [0x7c9eff, 0x5fd28d, 0xf0a857];
  const orbs = [];
  for (let i = 0; i < 6; i++) {
    const geometry = new THREE.SphereGeometry(0.6 + Math.random() * 0.9, 32, 32);
    const material = new THREE.MeshStandardMaterial({
      color: colors[i % colors.length],
      emissive: colors[i % colors.length],
      emissiveIntensity: 0.4,
      transparent: true,
      opacity: 0.35,
      roughness: 0.4,
    });
    const orb = new THREE.Mesh(geometry, material);
    orb.position.set(
      (Math.random() - 0.5) * 14,
      (Math.random() - 0.5) * 10,
      (Math.random() - 0.5) * 8 - 4
    );
    orb.userData.offset = Math.random() * Math.PI * 2;
    scene.add(orb);
    orbs.push(orb);
  }

  function tick(t) {
    const time = t * 0.0004;
    orbs.forEach((orb) => {
      orb.position.y += Math.sin(time + orb.userData.offset) * 0.003;
      orb.position.x += Math.cos(time * 0.6 + orb.userData.offset) * 0.002;
      orb.rotation.y += 0.001;
    });
    renderer.render(scene, camera);
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);

  window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });
}
