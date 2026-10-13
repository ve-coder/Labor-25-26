// 3D-Würfel mit three.js: Maus drehen, Mausrad zoomen, Klick auf Sticker,
// animierte Züge. Koordinaten wie im Backend: x = R, y = U, z = F.
import * as THREE from "./vendor/three.module.min.js";

const COLORS = {
  W: 0xf4f4f0, Y: 0xf2d230, R: 0xc8312c, O: 0xee7d22, G: 0x2f9e4a, B: 0x1f5fc4,
};
const UNKNOWN = 0x5f5e5a;
const NORMALS = {
  U: [0, 1, 0], D: [0, -1, 0], R: [1, 0, 0], L: [-1, 0, 0], F: [0, 0, 1], B: [0, 0, -1],
};

// gleiche Formel wie position_of() in app/cube_model.py
function positionOf(face, i) {
  const row = Math.floor(i / 3), col = i % 3;
  switch (face) {
    case "U": return [col - 1, 1, row - 1];
    case "D": return [col - 1, -1, 1 - row];
    case "F": return [col - 1, 1 - row, 1];
    case "B": return [1 - col, 1 - row, -1];
    case "R": return [1, 1 - row, 1 - col];
    case "L": return [-1, 1 - row, col - 1];
  }
}

export class Cube3D {
  constructor(el, { onStickerClick } = {}) {
    this.el = el;
    this.onStickerClick = onStickerClick;
    this.queue = [];
    this.busy = false;

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
    this.camera.position.set(0, 0, 11);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(this.renderer.domElement);

    this.scene.add(new THREE.AmbientLight(0xffffff, 1.6));
    const dir = new THREE.DirectionalLight(0xffffff, 1.4);
    dir.position.set(4, 6, 8);
    this.scene.add(dir);

    this.root = new THREE.Group();
    this.scene.add(this.root);
    this.pivot = new THREE.Group();
    this.root.add(this.pivot);
    this.resetView();

    this.cubies = [];
    this.stickers = {}; // "U0" -> mesh
    const body = new THREE.BoxGeometry(0.96, 0.96, 0.96);
    const bodyMat = new THREE.MeshStandardMaterial({ color: 0x121212, roughness: 0.6 });
    const stickerGeo = roundedPlane(0.82, 0.12);
    for (let x = -1; x <= 1; x++) for (let y = -1; y <= 1; y++) for (let z = -1; z <= 1; z++) {
      if (!x && !y && !z) continue;
      const cubie = new THREE.Mesh(body, bodyMat);
      cubie.position.set(x, y, z);
      cubie.userData.home = new THREE.Vector3(x, y, z);
      this.root.add(cubie);
      this.cubies.push(cubie);
    }
    for (const face of Object.keys(NORMALS)) {
      const n = new THREE.Vector3(...NORMALS[face]);
      for (let i = 0; i < 9; i++) {
        const p = positionOf(face, i);
        const cubie = this.cubies.find((c) => c.userData.home.equals(new THREE.Vector3(...p)));
        const mat = new THREE.MeshStandardMaterial({ color: UNKNOWN, roughness: 0.35 });
        const m = new THREE.Mesh(stickerGeo, mat);
        m.position.copy(n.clone().multiplyScalar(0.485));
        m.lookAt(n.clone().multiplyScalar(2));
        m.userData = { face, index: i };
        cubie.add(m);
        this.stickers[face + i] = m;
      }
    }
    this.addFaceLabels();
    this.bindPointer();
    new ResizeObserver(() => this.resize()).observe(el);
    this.resize();
    const loop = () => {
      requestAnimationFrame(loop);
      this.renderer.render(this.scene, this.camera);
    };
    loop();
  }

  addFaceLabels() {
    // kleine Buchstaben neben dem Würfel zeigen, welche Seite wo im Gerät ist
    for (const [face, n] of Object.entries(NORMALS)) {
      const c = document.createElement("canvas");
      c.width = c.height = 64;
      const g = c.getContext("2d");
      g.fillStyle = "rgba(160,160,150,0.9)";
      g.font = "bold 40px system-ui, sans-serif";
      g.textAlign = "center";
      g.textBaseline = "middle";
      g.fillText(face, 32, 34);
      const tex = new THREE.CanvasTexture(c);
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
      sprite.scale.set(0.45, 0.45, 1);
      sprite.position.set(...n.map((v) => v * 2.2));
      this.root.add(sprite);
    }
  }

  resetView() {
    this.root.quaternion.identity();
    this.root.rotateX(0.5);
    this.root.rotateY(-0.65);
    this.camera.position.set(0, 0, 11);
  }

  resize() {
    const w = this.el.clientWidth, h = this.el.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  bindPointer() {
    const dom = this.renderer.domElement;
    let down = null;
    dom.addEventListener("pointerdown", (e) => {
      down = { x: e.clientX, y: e.clientY, lx: e.clientX, ly: e.clientY, moved: false };
      dom.setPointerCapture(e.pointerId);
    });
    dom.addEventListener("pointermove", (e) => {
      if (!down) return;
      const dx = e.clientX - down.lx, dy = e.clientY - down.ly;
      down.lx = e.clientX; down.ly = e.clientY;
      if (Math.abs(e.clientX - down.x) + Math.abs(e.clientY - down.y) > 4) down.moved = true;
      const q = new THREE.Quaternion();
      q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), dx * 0.01);
      this.root.quaternion.premultiply(q);
      q.setFromAxisAngle(new THREE.Vector3(1, 0, 0), dy * 0.01);
      this.root.quaternion.premultiply(q);
    });
    dom.addEventListener("pointerup", (e) => {
      if (down && !down.moved) this.pick(e);
      down = null;
    });
    dom.addEventListener("wheel", (e) => {
      e.preventDefault();
      const z = this.camera.position.z * (e.deltaY > 0 ? 1.08 : 0.92);
      this.camera.position.z = Math.min(20, Math.max(6, z));
    }, { passive: false });
  }

  pick(e) {
    if (!this.onStickerClick) return;
    const r = this.renderer.domElement.getBoundingClientRect();
    const v = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    const ray = new THREE.Raycaster();
    ray.setFromCamera(v, this.camera);
    const hits = ray.intersectObjects(Object.values(this.stickers));
    if (hits.length) this.onStickerClick(hits[0].object.userData, e.clientX, e.clientY);
  }

  // --------------------------------------------------------------- Zustand
  setState(facelets) {
    this.queue.push({ kind: "state", facelets });
    this.pump();
  }

  animate(ev) {
    // nicht ewig hinterherlaufen: bei langer Warteschlange Animation überspringen
    if (this.queue.length > 6) return;
    this.queue.push({ kind: "anim", ...ev });
    this.pump();
  }

  resetPending() {
    // Würfelchen nach einer Animation erst zurücksetzen, wenn die neuen Farben da sind
    if (!this.pendingReset) return;
    for (const c of this.pendingReset) {
      this.root.attach(c);
      c.position.copy(c.userData.home);
      c.quaternion.identity();
    }
    this.pivot.quaternion.identity();
    this.pendingReset = null;
  }

  applyState(facelets) {
    this.resetPending();
    for (const [face, cols] of Object.entries(facelets)) {
      cols.forEach((c, i) => {
        const m = this.stickers[face + i];
        if (m) m.material.color.setHex(c ? COLORS[c] : UNKNOWN);
      });
    }
  }

  async pump() {
    if (this.busy) return;
    this.busy = true;
    while (this.queue.length) {
      const job = this.queue.shift();
      if (job.kind === "state") this.applyState(job.facelets);
      else if (job.kind === "anim") await this.runAnim(job);
    }
    this.busy = false;
  }

  runAnim({ kind, face, quarters, duration }) {
    if (kind === "free" || kind === "ambiguous") return Promise.resolve();
    this.resetPending();
    const n = new THREE.Vector3(...NORMALS[face]);
    const sel = kind === "whole" ? this.cubies : this.cubies.filter((c) => c.userData.home.dot(n) > 0.5);
    this.pivot.quaternion.identity();
    for (const c of sel) this.pivot.attach(c);
    const target = -quarters * Math.PI / 2; // im Uhrzeigersinn von außen gesehen
    const ms = Math.max(120, Math.min(duration || 300, 2500));
    const t0 = performance.now();
    return new Promise((resolve) => {
      const step = (t) => {
        const k = Math.min(1, (t - t0) / ms);
        const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
        this.pivot.quaternion.setFromAxisAngle(n, target * e);
        if (k < 1) requestAnimationFrame(step);
        else {
          this.pendingReset = sel;
          resolve();
        }
      };
      requestAnimationFrame(step);
    });
  }
}

function roundedPlane(size, r) {
  const s = size / 2;
  const shape = new THREE.Shape();
  shape.moveTo(-s + r, -s);
  shape.lineTo(s - r, -s);
  shape.quadraticCurveTo(s, -s, s, -s + r);
  shape.lineTo(s, s - r);
  shape.quadraticCurveTo(s, s, s - r, s);
  shape.lineTo(-s + r, s);
  shape.quadraticCurveTo(-s, s, -s, s - r);
  shape.lineTo(-s, -s + r);
  shape.quadraticCurveTo(-s, -s, -s + r, -s);
  return new THREE.ShapeGeometry(shape);
}
