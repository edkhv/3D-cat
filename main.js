/**
 * Чёрный котик + мяч за курсором.
 * Модель: cat.glb (кожа + арматура + клипы Idle/Run/Swipe).
 * Мех: "fur shells" — N копий скиннед-меша, раздутых по нормали,
 * альфа-срез процедурным 3D-шумом (без текстур).
 */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

// ------------------------------------------------------------------ tune
const FUR_LAYERS = /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent) ? 10 : 18;
const FUR_LEN    = 0.017;          // длина ворса в метрах
const ARENA      = 1.15;           // радиус площадки
const BALL_R     = 0.042;
const CAT_SPEED  = 1.15;           // м/с максимум
const CATCH_DIST = 0.30;           // с какой дистанции бьёт лапой

// ------------------------------------------------------------------ three
const app = document.getElementById('app');
const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.15;
app.appendChild(renderer.domElement);

const BG = new THREE.Color(0x05070a);
const scene = new THREE.Scene();
scene.background = BG;
scene.fog = new THREE.Fog(BG, 3.2, 9.5);

const camera = new THREE.PerspectiveCamera(42, innerWidth / innerHeight, 0.05, 60);
const camBase = new THREE.Vector3(1.45, 0.92, 1.50);
const camLook = new THREE.Vector3(0, 0.19, 0.06);
camera.position.copy(camBase);

// ------------------------------------------------------------------ lights
const hemi = new THREE.HemisphereLight(0x8fb2d4, 0x0a0d12, 0.55);
scene.add(hemi);

const key = new THREE.DirectionalLight(0xfff0dc, 1.55);
key.position.set(2.2, 3.1, 2.0);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
key.shadow.camera.near = 0.5;
key.shadow.camera.far = 12;
const S = 3.0;
key.shadow.camera.left = -S; key.shadow.camera.right = S;
key.shadow.camera.top = S;   key.shadow.camera.bottom = -S;
key.shadow.bias = -0.0012;
key.shadow.normalBias = 0.012;
scene.add(key);

const rim = new THREE.DirectionalLight(0x7fd8ff, 2.05);
rim.position.set(-2.4, 1.5, -2.2);
scene.add(rim);

const fill = new THREE.DirectionalLight(0x8fa8c8, 0.32);
fill.position.set(-1.6, 0.7, 2.4);
scene.add(fill);

// ------------------------------------------------------------------ stage
const floorMat = new THREE.MeshStandardMaterial({ color: 0x0a0e13, roughness: 0.92, metalness: 0.0 });
floorMat.onBeforeCompile = (shader) => {
  shader.uniforms.uFade = { value: new THREE.Color(BG) };
  shader.vertexShader = 'varying vec2 vFloorPos;\n' + shader.vertexShader.replace(
    '#include <begin_vertex>',
    '#include <begin_vertex>\n vFloorPos = position.xy;'
  );
  shader.fragmentShader = 'uniform vec3 uFade;\nvarying vec2 vFloorPos;\n' + shader.fragmentShader;
  shader.fragmentShader = shader.fragmentShader.replace(
    '#include <color_fragment>',
    `#include <color_fragment>
     vec2 gv = vFloorPos * 8.0;
     vec2 g = abs(fract(gv - 0.5) - 0.5) / fwidth(gv);
     float line = 1.0 - min(min(g.x, g.y), 1.0);
     float rad = length(vFloorPos);
     float r = rad / 3.0;
     diffuseColor.rgb += vec3(0.045, 0.14, 0.19) * line * (1.0 - smoothstep(0.12, 0.7, r)) * 0.9;
     diffuseColor.rgb += vec3(0.09, 0.30, 0.40) * smoothstep(0.015, 0.0, abs(rad - ${ARENA.toFixed(2)})) * 0.30;
     diffuseColor.rgb = mix(diffuseColor.rgb, uFade, smoothstep(0.42, 0.95, r));`
  );
};
const floor = new THREE.Mesh(new THREE.PlaneGeometry(6, 6), floorMat);
floor.rotation.x = -Math.PI / 2;
floor.receiveShadow = true;
scene.add(floor);

// ------------------------------------------------------------------ ball
const ball = new THREE.Mesh(
  new THREE.SphereGeometry(BALL_R, 32, 20),
  new THREE.MeshStandardMaterial({
    color: 0x9fe9ff, emissive: 0x2fc8ff, emissiveIntensity: 1.05,
    roughness: 0.25, metalness: 0.0,
  })
);
ball.castShadow = true;
ball.position.set(0.45, BALL_R, 0.35);
scene.add(ball);

const ballLight = new THREE.PointLight(0x63e2ff, 0.42, 1.5, 2.0);
ballLight.position.copy(ball.position);
scene.add(ballLight);

const ballVel = new THREE.Vector3();
const ballTarget = new THREE.Vector3(0.45, BALL_R, 0.35);

// ------------------------------------------------------------------ pointer
const ndc = new THREE.Vector2(0.35, 0.15);
const ray = new THREE.Raycaster();
const planeY = new THREE.Plane(new THREE.Vector3(0, 1, 0), -BALL_R);
let pointerActive = false;   // до первого движения мыши кот просто сидит

function pointerMove(e) {
  const t = e.touches ? e.touches[0] : e;
  ndc.x = (t.clientX / innerWidth) * 2 - 1;
  ndc.y = -(t.clientY / innerHeight) * 2 + 1;
  pointerActive = true;
  window.catDemo && (window.catDemo.active = true);
}
addEventListener('pointermove', pointerMove, { passive: true });
addEventListener('touchmove', pointerMove, { passive: true });
addEventListener('pointerdown', (e) => {
  pointerMove(e);
  // клик — подтолкнуть мяч от точки клика
  shootTarget();
});
function shootTarget() {
  const hit = new THREE.Vector3();
  ray.setFromCamera(ndc, camera);
  if (ray.ray.intersectPlane(planeY, hit)) {
    const dir = hit.clone().sub(ball.position).setY(0);
    if (dir.length() < 0.02) dir.set(Math.random() - 0.5, 0, Math.random() - 0.5);
    dir.normalize();
    ballVel.addScaledVector(dir, 2.6);
    ballVel.y += 1.1;
  }
}

// ------------------------------------------------------------------ fur
const GLSL_NOISE = `
float hash31(vec3 p){ p = fract(p * 0.3183099 + vec3(0.11, 0.37, 0.71)); p *= 17.0;
  return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
float vnoise(vec3 x){ vec3 i = floor(x), f = fract(x); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash31(i), hash31(i + vec3(1,0,0)), f.x),
                 mix(hash31(i + vec3(0,1,0)), hash31(i + vec3(1,1,0)), f.x), f.y),
             mix(mix(hash31(i + vec3(0,0,1)), hash31(i + vec3(1,0,1)), f.x),
                 mix(hash31(i + vec3(0,1,1)), hash31(i + vec3(1,1,1)), f.x), f.y), f.z); }
`;

// Мех — оболочки: 17 мм ворса заведомо выше глаз (они торчат на 4 мм) и носа,
// поэтому в шейдер передаются «дырки» — сферы вокруг радужек и носовой кожи.
const FUR_HOLES_MAX = 4;
const HOLE_GLSL = `
uniform vec4 uFurHoles[${FUR_HOLES_MAX}];
float furHoleMask(vec3 p) {
  float m = 1.0;
  for (int i = 0; i < ${FUR_HOLES_MAX}; i++) {
    vec4 h = uFurHoles[i];
    if (h.w > 0.0) m = min(m, smoothstep(h.w * 0.80, h.w * 1.45, distance(p, h.xyz)));
  }
  return m;
}
`;

function furMaterial(layer, layers, holes) {
  const u = layer / (layers - 1);            // 0 = кожа, 1 = кончики
  const mat = new THREE.MeshStandardMaterial({
    color: 0xffffff, vertexColors: true, roughness: 0.86, metalness: 0.0,
  });
  mat.onBeforeCompile = (shader) => {
    shader.uniforms.uLayer = { value: u };
    shader.uniforms.uFurLen = { value: FUR_LEN };
    shader.uniforms.uFurHoles = { value: (holes || []).concat(
      Array.from({ length: FUR_HOLES_MAX }, () => new THREE.Vector4(0, 0, 0, 0))).slice(0, FUR_HOLES_MAX) };
    shader.vertexShader = `
      uniform float uLayer; uniform float uFurLen;
      varying vec3 vFurPos_;
      varying vec3 vFurDisp_;
      ${GLSL_NOISE}
      ${HOLE_GLSL}
      ` + shader.vertexShader;
    shader.vertexShader = shader.vertexShader.replace(
      '#include <begin_vertex>',
      `#include <begin_vertex>
       vFurPos_ = position;
       float fmask = furHoleMask(position);
       float nv = vnoise(position * 420.0);
       transformed += objectNormal * (uLayer * uFurLen * (0.55 + 0.65 * nv) * fmask);
       vFurDisp_ = transformed;`
    );
    shader.fragmentShader = `
      uniform float uLayer; uniform float uFurLen;
      varying vec3 vFurPos_;
      varying vec3 vFurDisp_;
      ${GLSL_NOISE}
      ${HOLE_GLSL}
      ` + shader.fragmentShader;
    shader.fragmentShader = shader.fragmentShader.replace(
      '#include <color_fragment>',
      `float fn = vnoise(vFurPos_ * 430.0) * 0.58 + vnoise(vFurPos_ * 1150.0) * 0.42;
       float fmask = furHoleMask(vFurDisp_);
       float cut = pow(uLayer, 1.7) * 0.88;
       // слой 0 — это кожа, её не режем никогда: в «дырках» гасим только ворс
       if (uLayer > 1e-4) cut = mix(1.05, cut, fmask);
       if (fn < cut) discard;
       float ear = clamp(1.0 - vColor.g, 0.0, 1.0);      // 1 = кожа, >0 = внутренняя сторона уха
       vec3 root = vec3(0.0042, 0.0042, 0.0048);
       vec3 tip  = vec3(0.0300, 0.0272, 0.0265);
       vec3 furCol = mix(root, tip, pow(uLayer, 1.3));
       furCol = mix(furCol, vec3(0.20, 0.10, 0.09) * (0.25 + 0.8 * uLayer), ear);
       diffuseColor.rgb = furCol;`
    );
  };
  return mat;
}

// дырки в мехе берём прямо из геометрии морды: центры радужек и носовой кожи
// (вершины в bind-пространстве, как и у CatBody — оба меша дети арматуры)
function collectFurHoles(model) {
  const holes = [];
  const face = model.getObjectByName('CatFace');
  if (!face) return holes;
  face.traverse((o) => {
    if (!o.isMesh || !o.geometry) return;
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    const pos = o.geometry.attributes.position;
    const idx = o.geometry.index;
    // glTF-примитивы three грузит отдельными Mesh (тогда групп нет) — поддерживаем оба случая
    const groups = (o.geometry.groups && o.geometry.groups.length)
      ? o.geometry.groups
      : [{ start: 0, count: idx ? idx.count : pos.count, materialIndex: 0 }];
    for (const g of groups) {
      const m = mats[g.materialIndex];
      if (!m) continue;
      const scale = /Iris/i.test(m.name) ? 1.02 : (/Nose/i.test(m.name) ? 1.20 : 0);
      if (!scale) continue;
      const c = new THREE.Vector3();
      for (let i = g.start; i < g.start + g.count; i++) {
        const vi = idx ? idx.getX(i) : i;
        c.x += pos.getX(vi); c.y += pos.getY(vi); c.z += pos.getZ(vi);
      }
      c.multiplyScalar(1 / Math.max(1, g.count));
      let r = 0;
      for (let i = g.start; i < g.start + g.count; i++) {
        const vi = idx ? idx.getX(i) : i;
        r = Math.max(r, Math.hypot(pos.getX(vi) - c.x, pos.getY(vi) - c.y, pos.getZ(vi) - c.z));
      }
      if (r > 0) holes.push(new THREE.Vector4(c.x, c.y, c.z, r * scale));
    }
  });
  return holes.slice(0, FUR_HOLES_MAX);
}

// ------------------------------------------------------------------ cat
const catRoot = new THREE.Group();
scene.add(catRoot);

let catBody = null, catFace = null, mixer = null;
let actIdle = null, actRun = null, actSwipe = null;
let catYaw = 0, catSpeed = 0;
let state = 'idle';        // idle | chase | swipe | cooldown
let timer = 0;
const catPos = new THREE.Vector3(0, 0, 0);

const loaderEl = document.getElementById('loader');
const statsEl = document.getElementById('stats');

new GLTFLoader().load('./models/cat.glb', (gltf) => {
  const model = gltf.scene;
  model.traverse((o) => {
    if (o.isMesh) { o.castShadow = true; o.frustumCulled = false; o.receiveShadow = false; }
    if (o.isSkinnedMesh) o.frustumCulled = false;
  });
  catRoot.add(model);

  catBody = model.getObjectByName('CatBody');     // группа (2 примитива: кожа + ухо)
  catFace = model.getObjectByName('CatFace');

  // мех: базовый слой + раздутые копии (клоны делят скелет => общая анимация)
  const furHoles = collectFurHoles(model);
  if (location.hash === '#face') loaderEl.classList.add('hide');
  window.__furHoles = furHoles.map((h) => [h.x, h.y, h.z, h.w].map((v) => +v.toFixed(4)));
  if (catBody) {
    const bodyMeshes = [];
    catBody.traverse((o) => { if (o.isMesh) bodyMeshes.push(o); });
    for (const m of bodyMeshes) {
      m.material = furMaterial(0, FUR_LAYERS, furHoles);
      m.castShadow = true;
      m.receiveShadow = false;
      m.frustumCulled = false;
    }
    catBody.frustumCulled = false;
    for (let i = 1; i < FUR_LAYERS; i++) {
      const shell = catBody.clone();
      shell.traverse((o) => {
        if (!o.isMesh) return;
        o.material = furMaterial(i, FUR_LAYERS, furHoles);
        o.castShadow = i < 3;
        o.receiveShadow = false;
        o.frustumCulled = false;
        o.renderOrder = i;
      });
      catBody.parent.add(shell);
    }
    window.__furLayers = bodyMeshes.length;
  }
  // глаза чуть светятся, роговица — прозрачная
  catFace?.traverse((o) => {
    if (!o.isMesh) return;
    const list = Array.isArray(o.material) ? o.material : [o.material];
    for (const m of list) {
      if (/Iris/i.test(m.name)) {
        m.emissive = new THREE.Color(0x2a3a06);
        m.emissiveIntensity = 0.45;
        m.roughness = 0.22;
      }
      if (/Pupil/i.test(m.name)) { m.roughness = 0.12; }
      if (/Cornea/i.test(m.name)) {
        m.transparent = true; m.opacity = 0.12; m.depthWrite = false;
        m.roughness = 0.05; m.metalness = 0.0; m.color = new THREE.Color(0xffffff);
      }
      if (/Whisker/i.test(m.name)) { m.color = new THREE.Color(0xb9bcb4); m.roughness = 0.35; }
    }
  });

  mixer = new THREE.AnimationMixer(model);
  const byName = (n) => THREE.AnimationClip.findByName(gltf.animations, n);
  actIdle = mixer.clipAction(byName('Idle'));
  actRun = mixer.clipAction(byName('Run'));
  actSwipe = mixer.clipAction(byName('Swipe'));
  actSwipe.setLoop(THREE.LoopOnce, 1);
  actSwipe.clampWhenFinished = true;
  actIdle.play(); actRun.play(); actSwipe.play();
  actRun.setEffectiveWeight(0); actSwipe.setEffectiveWeight(0);

  loaderEl.classList.add('hide');
  window.__catReady = true;
}, undefined, (err) => {
  loaderEl.querySelector('.inner').textContent = 'не удалось загрузить cat.glb';
  console.error(err);
});

// небольшая внешняя ручка: удобно и для отладки, и для встраивания в страницу
window.catDemo = {
  ball, catRoot,
  get state() { return state; },
  get speed() { return catSpeed; },
  setPointer(nx, ny) { ndc.set(nx, ny); pointerActive = true; userActive = true; },
  snap() {
    return {
      state, speed: +catSpeed.toFixed(2),
      cat: [+catPos.x.toFixed(3), +catPos.z.toFixed(3)],
      ball: [+ball.position.x.toFixed(3), +ball.position.z.toFixed(3)],
      dist: +Math.hypot(ball.position.x - catPos.x, ball.position.z - catPos.z).toFixed(3),
      ballVel: +ballVel.length().toFixed(2),
      yaw: +catYaw.toFixed(2),
      anim: { idle: +actIdle.getEffectiveWeight().toFixed(2), run: +actRun.getEffectiveWeight().toFixed(2), swipe: +actSwipe.getEffectiveWeight().toFixed(2) },
    };
  },
  reset() {
    ball.position.set(0.45, BALL_R, 0.35); ballVel.set(0, 0, 0);
    catPos.set(0, 0, 0); catYaw = 0; state = 'idle'; userActive = false; pointerActive = false;
  },
};

// ------------------------------------------------------------------ loop
const clock = new THREE.Clock();
let fps = 60, frames = 0, fpsT = 0;

let userActive = false;

function updateBall(dt) {
  if (!userActive) return;                       // мяч спит, пока не двинули курсором
  ray.setFromCamera(ndc, camera);
  const hit = new THREE.Vector3();
  if (ray.ray.intersectPlane(planeY, hit)) {
    hit.x = THREE.MathUtils.clamp(hit.x, -2.0, 2.0);
    hit.z = THREE.MathUtils.clamp(hit.z, -2.0, 2.0);
    ballTarget.copy(hit);
  }
  // пружина к курсору + трение
  const k = 17, damp = 5.4;
  const acc = ballTarget.clone().sub(ball.position).multiplyScalar(k).addScaledVector(ballVel, -damp);
  ballVel.addScaledVector(acc, dt);
  ball.position.addScaledVector(ballVel, dt);
  if (ball.position.y < BALL_R) {
    ball.position.y = BALL_R;
    ballVel.y *= -0.45;
  }
  const maxR = ARENA - 0.10, r = Math.hypot(ball.position.x, ball.position.z);
  if (r > maxR) {
    const s = maxR / r;
    ball.position.x *= s; ball.position.z *= s;
    ballVel.multiplyScalar(0.4);
  }
  ball.rotation.x += ballVel.z * dt * 6;
  ball.rotation.z -= ballVel.x * dt * 6;
  ballLight.position.copy(ball.position).setY(ball.position.y + 0.02);
}

function updateCat(dt) {
  if (!mixer) return;
  userActive = userActive || pointerActive;
  if (!userActive) {                              // ждём первого движения курсора
    actIdle.setEffectiveWeight(1);
    actRun.setEffectiveWeight(0);
    catRoot.rotation.y = catYaw;
    mixer.update(dt);
    return;
  }
  const toBall = new THREE.Vector3().subVectors(ball.position, catPos).setY(0);
  const dist = toBall.length();
  const wantYaw = Math.atan2(-toBall.z, toBall.x);   // модель смотрит в +X

  if (state === 'swipe') {
    timer -= dt;
    catSpeed = THREE.MathUtils.damp(catSpeed, 0, 9, dt);
    if (timer <= 0) { state = 'cooldown'; timer = 0.45; }
  } else if (state === 'cooldown') {
    timer -= dt;
    catSpeed = THREE.MathUtils.damp(catSpeed, 0, 7, dt);
    if (timer <= 0) state = 'idle';
  } else if (dist > CATCH_DIST) {
    state = 'chase';
    const want = Math.min(CAT_SPEED, 0.42 + dist * 0.8);
    catSpeed = THREE.MathUtils.damp(catSpeed, want, 6, dt);
  } else {
    state = 'idle';
    catSpeed = THREE.MathUtils.damp(catSpeed, 0, 9, dt);
    if (dist < CATCH_DIST * 0.75) {
      actSwipe.reset();
      actSwipe.setEffectiveWeight(1);
      const dir = new THREE.Vector3().subVectors(ball.position, catPos).setY(0).normalize();
      ballVel.addScaledVector(dir, 3.2);
      ballVel.y += 0.85;
      state = 'swipe';
      timer = 0.62;
    }
  }

  // поворот к мячу
  let d = wantYaw - catYaw;
  while (d > Math.PI) d -= Math.PI * 2;
  while (d < -Math.PI) d += Math.PI * 2;
  catYaw += THREE.MathUtils.clamp(d, -3.6 * dt, 3.6 * dt);

  catPos.x += Math.cos(catYaw) * catSpeed * dt;
  catPos.z += -Math.sin(catYaw) * catSpeed * dt;
  const pr = Math.hypot(catPos.x, catPos.z);
  if (pr > ARENA) { catPos.x *= ARENA / pr; catPos.z *= ARENA / pr; }

  catRoot.position.copy(catPos);
  catRoot.rotation.y = catYaw;

  // веса анимаций
  const w = THREE.MathUtils.clamp(catSpeed / 0.75, 0, 1);
  const sw = state === 'swipe' ? 1 : 0;
  actIdle.setEffectiveWeight((1 - w) * (1 - sw));
  actRun.setEffectiveWeight(w * (1 - sw));
  actRun.timeScale = THREE.MathUtils.clamp(catSpeed / 0.85, 0.55, 1.8);
  if (sw === 0) actSwipe.setEffectiveWeight(THREE.MathUtils.damp(actSwipe.getEffectiveWeight(), 0, 10, dt));
  mixer.update(dt);
}

function tick() {
  requestAnimationFrame(tick);
  const dt = Math.min(clock.getDelta(), 0.05);
  updateBall(dt);
  updateCat(dt);

  // лёгкий параллакс камеры
  const px = ndc.x * 0.13, py = ndc.y * 0.07;
  camera.position.x += ((camBase.x + px) - camera.position.x) * 0.05;
  camera.position.y += ((camBase.y + py) - camera.position.y) * 0.05;
  camera.position.z += ((camBase.z + px * 0.4) - camera.position.z) * 0.05;
  camera.lookAt(camLook);
  if (location.hash === '#face') {          // отладочный ракурс: морда крупно
    camera.position.set(0.60, 0.335, 0.155);
    camera.lookAt(0.228, 0.288, 0.0);
  }

  renderer.render(scene, camera);

  frames++; fpsT += dt;
  if (fpsT > 0.5) {
    fps = frames / fpsT; frames = 0; fpsT = 0;
    const tris = renderer.info.render.triangles;
    statsEl.innerHTML = `${fps.toFixed(0)} fps · ${(tris / 1000).toFixed(0)}k tris · мех ${FUR_LAYERS} слоёв`;
  }
}
tick();

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

addEventListener('keydown', (e) => {
  if (e.key === 'r' || e.key === 'R' || e.key === 'к' || e.key === 'К') {
    window.catDemo.reset();
  }
});
