// Mano a Mano: the penalty / free-kick scene in Three.js (vendored, pinned 0.187.0).
// Low-poly in the Geral palette (lamps on black, concrete, paper, grass), rounded players with soft
// shading and cartoon timing (anticipation, squash and stretch, bursts) on the kick.
// The scoreboard and the buttons are HTML over the canvas, never 3D text.
//
// World: metres. Goal line on z = 0, the mouth from x = -3.66 to 3.66, crossbar at 2.44;
// the pitch runs towards +z. Contract coordinates (0-1000) are the goal as the kicker sees
// it: x = 0 is the kicker's left (world -x), y = 0 the ground, y = 1000 the crossbar.
import * as THREE from "../vendor/three/three.module.js";
import { periodoBarra, pressaBarra } from "./mano-faixa.js";
import { criarFesta, tituloCampeao } from "./mano-festa.js";
import { visual } from "./mano-visual.js";

const COR = {
  board: 0x0b0b0a,
  lamp: 0xffc21a,
  concreto: 0x8e8b84,
  concretoLt: 0xb9b5ac,
  concretoEsc: 0x4a4843,
  papel: 0xefe4cc,
  gramado: 0x1f7a3d,
  gramado2: 0x248a46,
  tinta: 0x14231a,
  tintaSoft: 0x3f3c36,
  giz: 0xf1f5ec,
  pele: 0xa47450,
};

export const GOL = { meia: 3.66, altura: 2.44, fundo: 2.0 };
const MARCA_PENALTI = 11;
const DIST_BARREIRA = 9.15;
const VAO_HOMENS = 0.66; // centre to centre of two men in the wall (shoulders are 0.46 m)
// Where a free kick is taken from, by the rules slice's `Posicao.nome`.
export const POSICOES = {
  meia_lua: { x: 0, z: 20.5 },
  entrada_esquerda: { x: -11.5, z: 18.5 },
  entrada_direita: { x: 11.5, z: 18.5 },
};

const lambert = (cor) => new THREE.MeshLambertMaterial({ color: cor, flatShading: true });
const basico = (cor) => new THREE.MeshBasicMaterial({ color: cor });

/** Contract (0-1000, as the kicker sees it) -> world point on the goal plane. */
export function golParaMundo(x, y, z = 0) {
  return new THREE.Vector3(-GOL.meia + (2 * GOL.meia * x) / 1000, (GOL.altura * y) / 1000, z);
}

/** World point on the goal plane -> contract coordinates (not clamped). */
export function mundoParaGol(p) {
  return [((p.x + GOL.meia) / (2 * GOL.meia)) * 1000, (p.y / GOL.altura) * 1000];
}

const LETREIROS = { gol: "GOOOL", defesa: "DEFENDEU", trave: "NA TRAVE", fora: "PRA FORA", barreira: "NA BARREIRA" };

/** The board's sign for a kick: over the crossbar (y past it) is "ISOLOU". */
export function letreiroDoLance(lance) {
  if (lance?.resultado === "fora" && lance.onde?.[1] > 1000) return "ISOLOU";
  return LETREIROS[lance?.resultado] ?? "";
}

export const prender = (v, lo = 0, hi = 1000) => Math.min(hi, Math.max(lo, v));

/** Barrier centre kept so its outer man is at most about one man outside a post. */
/** The span the wall blocks, as the rules count it: x ± n·55, cut at the posts. */
export const vaoDaBarreira = (n, x) => [Math.max(0, x - n * 55), Math.min(1000, x + n * 55)];

/**
 * The draft's good band of the bar for an aim point: narrower near a post or the crossbar.
 * Only an approximation for the draft; slice 4 passes the rules' own band to pedirChute.
 */
export function faixaBoa([x, y]) {
  const perto = Math.max(0, 1 - Math.min(x, 1000 - x) / 250, 1 - (1000 - y) / 250);
  const meia = 170 - 110 * Math.min(1, perto);
  return [500 - meia, 500 + meia];
}

/**
 * The ball's path from `origem` to `destino` (world points). Penalties fly almost straight;
 * free kicks bend by `curva` (-1..1, positive bulges to the kicker's right) and by trajectory.
 */
export function caminho(origem, destino, { trajetoria = null, curva = 0, cavadinha = false } = {}) {
  const meio = origem.clone().lerp(destino, 0.5);
  const chao = new THREE.Vector3(destino.x - origem.x, 0, destino.z - origem.z).normalize();
  const direita = new THREE.Vector3(-chao.z, 0, chao.x); // kicker's right, facing the goal
  const c = meio.clone();
  const pico = (h) => 2 * h - (origem.y + destino.y) / 2; // control y for a peak near h
  if (cavadinha) {
    c.y = pico(Math.max(destino.y + 0.9, 2.3)); // a slow chip, high over the dive
  } else if (!trajetoria) {
    c.y = pico(Math.max(origem.y, destino.y) * 0.75 + 0.12);
  } else if (trajetoria === "rasteira") {
    c.y = Math.max(0.11, pico(destino.y * 0.4 + 0.1));
    c.addScaledVector(direita, curva * 3);
  } else if (trajetoria === "por_cima") {
    c.y = pico(Math.max(3.1, destino.y + 1.2));
    c.addScaledVector(direita, curva * 3.2);
  } else {
    const lado = curva === 0 ? 1 : Math.sign(curva);
    c.y = pico(destino.y * 0.6 + 0.9);
    c.addScaledVector(direita, lado * 2.2 + curva * 1.6);
  }
  return new THREE.QuadraticBezierCurve3(origem.clone(), c, destino.clone());
}

// ---------------------------------------------------------------------------------------
// The set: pitch, goal and net, the old concrete bowl with its crowd and lamp rigs.

function caixa(w, h, d, mat, x = 0, y = 0, z = 0) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  m.position.set(x, y, z);
  return m;
}

/**
 * A cartoon burst: `n` short rays around a unit circle, flat, drawn over everything. The caller
 * places it, turns it to the camera, scales it and fades it (`material.opacity`).
 */
function estouro(cor, n) {
  const pos = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2 + 0.2;
    const [c, s] = [Math.cos(a), Math.sin(a)];
    const [px, py] = [-s * 0.07, c * 0.07]; // half the ray's width, across it
    const p = (r, k) => [c * r + px * k, s * r + py * k, 0];
    pos.push(...p(1, -1), ...p(1.7, -1), ...p(1.7, 1), ...p(1, -1), ...p(1.7, 1), ...p(1, 1));
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: cor, transparent: true, depthTest: false, side: THREE.DoubleSide }));
  m.renderOrder = 11;
  m.visible = false;
  return m;
}

/** A small seeded generator (mulberry32): the same grass on every load and in both browsers. */
function sorteio(semente) {
  let a = semente >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// The grass is one plane: a canvas tile of two mowing stripes (10.5 m) with blades and grain
// painted in, repeated over the pitch, times vertex colours for the big, slow variation (worn
// patches, damp ones, a darker edge by the stands), so the tile never reads as a pattern.
const LISTRA = 5.25;
function texturaGrama() {
  const N = 256;
  const tela = document.createElement("canvas");
  tela.width = tela.height = N;
  const ctx = tela.getContext("2d");
  const acaso = sorteio(1950);
  // The stripes a touch further apart than the flat ones were: the grain eats some contrast.
  const [esc, cla] = [new THREE.Color(COR.gramado).multiplyScalar(0.94), new THREE.Color(COR.gramado2).multiplyScalar(1.06)];
  ctx.fillStyle = `#${esc.getHexString()}`;
  ctx.fillRect(0, 0, N, N / 2);
  ctx.fillStyle = `#${cla.getHexString()}`;
  ctx.fillRect(0, N / 2, N, N / 2);
  // Blades: short strokes along the mowing, a shade either way of their stripe.
  for (let i = 0; i < 9000; i++) {
    const x = acaso() * N;
    const y = acaso() * N;
    const claro = acaso() < 0.5;
    ctx.fillStyle = claro ? "rgba(190,235,150,0.06)" : "rgba(0,30,10,0.09)";
    ctx.fillRect(x, y, 1, 1 + acaso() * 2);
  }
  // Grain: one random tint per pixel, small.
  const img = ctx.getImageData(0, 0, N, N);
  for (let i = 0; i < img.data.length; i += 4) {
    const k = 1 + (acaso() - 0.5) * 0.07;
    img.data[i] *= k;
    img.data[i + 1] *= k;
    img.data[i + 2] *= k;
  }
  ctx.putImageData(img, 0, 0);
  const t = new THREE.CanvasTexture(tela);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}

/** Smooth value noise in [0, 1] over the plane, a few octaves (for the vertex colours). */
function ruido(semente) {
  const acaso = sorteio(semente);
  const T = 64;
  const tab = Float32Array.from({ length: T * T }, acaso);
  const v = (i, j) => tab[(((j % T) + T) % T) * T + (((i % T) + T) % T)];
  const suave = (t) => t * t * (3 - 2 * t);
  const um = (x, y) => {
    const [i, j] = [Math.floor(x), Math.floor(y)];
    const [fx, fy] = [suave(x - i), suave(y - j)];
    const a = v(i, j) + (v(i + 1, j) - v(i, j)) * fx;
    const b = v(i, j + 1) + (v(i + 1, j + 1) - v(i, j + 1)) * fx;
    return a + (b - a) * fy;
  };
  return (x, y) => um(x, y) * 0.55 + um(x * 2.3 + 17, y * 2.3 + 5) * 0.3 + um(x * 5.1 + 3, y * 5.1 + 29) * 0.15;
}

function montarGramado(cena, anisotropia = 1) {
  const g = new THREE.Group();
  const [Z0, LARG, COMP] = [-8, 84, 24 * LISTRA]; // from behind the goal to past the far end
  const geo = new THREE.PlaneGeometry(LARG, COMP, 56, 80).rotateX(-Math.PI / 2).translate(0, 0, Z0 + COMP / 2);
  const pos = geo.attributes.position;
  const cores = new Float32Array(pos.count * 3);
  const manchas = ruido(7);
  // The bare, sandy patches where the game is played: a multiplier (linear) that turns the
  // grass's green into a dry olive.
  const gasto = new THREE.Color().setRGB(16, 1.2, 1.6);
  const c = new THREE.Color();
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    const z = pos.getZ(i);
    const n = manchas(x / 9, z / 9);
    c.setScalar(0.88 + n * 0.22);
    // Worn: the goalmouth and the spot, like any pitch at the end of a season.
    const boca = Math.exp(-((x / 4.2) ** 2) - ((z - 2.2) / 3) ** 2);
    const marca = Math.exp(-((x / 1.3) ** 2) - ((z - MARCA_PENALTI) / 1.6) ** 2);
    const meio = Math.exp(-((x / 6) ** 2) - ((z - 52.5) / 6) ** 2) * 0.5;
    c.lerp(gasto, Math.min(0.22, (boca * 0.22 + marca * 0.2 + meio * 0.16) * (0.6 + n * 0.8)));
    // Darker past the lines, where the floodlights reach less.
    const fora = Math.max(0, Math.abs(x) - 34, -z, z - 105);
    c.multiplyScalar(1 - Math.min(0.3, fora * 0.045));
    c.toArray(cores, i * 3);
  }
  geo.setAttribute("color", new THREE.BufferAttribute(cores, 3));
  const mapa = texturaGrama();
  mapa.repeat.set(LARG / (2 * LISTRA), COMP / (2 * LISTRA));
  mapa.anisotropy = anisotropia;
  const grama = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ map: mapa, vertexColors: true }));
  g.add(grama);
  const giz = basico(COR.giz);
  const linha = (x1, z1, x2, z2) => {
    const len = Math.hypot(x2 - x1, z2 - z1);
    const m = new THREE.Mesh(new THREE.PlaneGeometry(0.12, len + 0.12), giz);
    m.rotation.x = -Math.PI / 2;
    m.rotation.z = Math.atan2(x2 - x1, z2 - z1);
    m.position.set((x1 + x2) / 2, 0.012, (z1 + z2) / 2);
    g.add(m);
  };
  linha(-34, 0, 34, 0);
  linha(-34, 0, -34, 105);
  linha(34, 0, 34, 105);
  linha(-34, 52.5, 34, 52.5);
  linha(-20.16, 0, -20.16, 16.5);
  linha(20.16, 0, 20.16, 16.5);
  linha(-20.16, 16.5, 20.16, 16.5);
  linha(-9.16, 0, -9.16, 5.5);
  linha(9.16, 0, 9.16, 5.5);
  linha(-9.16, 5.5, 9.16, 5.5);
  const arco = (cx, cz, r, ini, comp) => {
    const m = new THREE.Mesh(new THREE.RingGeometry(r - 0.06, r + 0.06, 48, 1, ini, comp), giz);
    m.rotation.x = -Math.PI / 2;
    m.position.set(cx, 0.012, cz);
    g.add(m);
  };
  const a = Math.asin(5.5 / 9.15);
  arco(0, MARCA_PENALTI, 9.15, Math.PI + a, Math.PI - 2 * a);
  arco(0, 52.5, 9.15, 0, Math.PI * 2);
  const marca = new THREE.Mesh(new THREE.CircleGeometry(0.14, 12), giz);
  marca.rotation.x = -Math.PI / 2;
  marca.position.set(0, 0.013, MARCA_PENALTI);
  g.add(marca);
  cena.add(g);
}

function grade(pontosU, pontosV, f) {
  // Net as line segments over a (u, v) patch; f(u, v) -> [x, y, z].
  const pos = [];
  for (const u of pontosU) {
    for (let j = 0; j < pontosV.length - 1; j++) pos.push(...f(u, pontosV[j]), ...f(u, pontosV[j + 1]));
  }
  for (const v of pontosV) {
    for (let i = 0; i < pontosU.length - 1; i++) pos.push(...f(pontosU[i], v), ...f(pontosU[i + 1], v));
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  return geo;
}

const passos = (a, b, n) => Array.from({ length: n + 1 }, (_, i) => a + ((b - a) * i) / n);

function montarGol(cena) {
  const g = new THREE.Group();
  const branco = lambert(COR.giz);
  const r = 0.06;
  const trave = (x) => {
    const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, GOL.altura + r, 8), branco);
    m.position.set(x, (GOL.altura + r) / 2, 0);
    return m;
  };
  g.add(trave(-GOL.meia - r), trave(GOL.meia + r));
  const travessao = new THREE.Mesh(new THREE.CylinderGeometry(r, r, 2 * GOL.meia + 4 * r, 8), branco);
  travessao.rotation.z = Math.PI / 2;
  travessao.position.set(0, GOL.altura + r, 0);
  g.add(travessao);
  // Back stanchions and frame, in dark concrete so they read as iron, not as posts.
  const ferro = lambert(COR.concretoEsc);
  for (const x of [-GOL.meia - r, GOL.meia + r]) {
    g.add(caixa(0.05, GOL.altura, 0.05, ferro, x, GOL.altura / 2, -GOL.fundo));
    g.add(caixa(0.05, 0.05, GOL.fundo, ferro, x, GOL.altura, -GOL.fundo / 2));
  }
  const malha = new THREE.LineBasicMaterial({ color: COR.papel, transparent: true, opacity: 0.5 });
  const W = GOL.meia + r;
  const H = GOL.altura + r;
  const D = GOL.fundo;
  const xs = passos(-W, W, 48);
  const ys = passos(0, H, 16);
  const zs = passos(0, -D, 13);
  // The back panel is kept apart: a goal shakes it.
  const fundoGeo = grade(xs, ys, (x, y) => [x, y, -D]);
  const fundo = new THREE.LineSegments(fundoGeo, malha);
  fundo.userData.base = Float32Array.from(fundoGeo.attributes.position.array);
  g.add(fundo);
  g.add(new THREE.LineSegments(grade(xs, zs, (x, z) => [x, H, z]), malha));
  for (const s of [-1, 1]) g.add(new THREE.LineSegments(grade(zs, ys, (z, y) => [s * W, y, z]), malha));
  g.traverse((o) => o.isMesh && (o.castShadow = true));
  cena.add(g);
  return { rede: fundo };
}

/** A radial glow (white centre, soft falloff) for the lamps' halos. */
function texturaHalo() {
  const N = 64;
  const tela = document.createElement("canvas");
  tela.width = tela.height = N;
  const ctx = tela.getContext("2d");
  const grad = ctx.createRadialGradient(N / 2, N / 2, 0, N / 2, N / 2, N / 2);
  grad.addColorStop(0, "rgba(255,255,255,0.85)");
  grad.addColorStop(0.18, "rgba(255,255,255,0.45)");
  grad.addColorStop(0.5, "rgba(255,255,255,0.12)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, N, N);
  const t = new THREE.CanvasTexture(tela);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function montarEstadio(cena) {
  // The old bowl: an oval of concrete terraces around the pitch, the Geral at the bottom,
  // a moat, two tiers and the roof edge with yellow lamp rigs.
  const g = new THREE.Group();
  const cx = 0;
  const cz = 52.5;
  const perfil = [
    [0, -1.5],
    [0, 0.9], // wall of the moat
    [1.2, 0.9],
    [1.2, 0.2], // the Geral, standing, nearly at pitch level
    [5, 0.6],
    [5, 2.4],
  ];
  let r = 5;
  let y = 2.4;
  for (let i = 0; i < 16; i++) {
    r += 1.1;
    perfil.push([r, y]);
    y += 0.75;
    perfil.push([r, y]);
  }
  perfil.push([r + 0.6, y], [r + 0.6, y + 2.2], [r + 1.5, y + 2.2]); // balcony of the upper tier
  for (let i = 0; i < 14; i++) {
    r += 1.1;
    perfil.push([r, y + 2.2 + i * 0.85]);
    perfil.push([r, y + 2.2 + (i + 1) * 0.85]);
  }
  const topo = y + 2.2 + 14 * 0.85;
  perfil.push([r + 2, topo], [r + 2, topo + 3], [r - 6, topo + 4.5], [r - 6, topo + 4]); // roof lip
  const R0 = 46;
  const pts = perfil.map(([d, h]) => new THREE.Vector2(R0 + d, h));
  const lathe = new THREE.LatheGeometry(pts, 96);
  const anel = new THREE.Mesh(lathe, new THREE.MeshLambertMaterial({ color: 0x55524c, flatShading: true, side: THREE.DoubleSide }));
  anel.scale.set(1, 1, 1.42);
  anel.position.set(cx, 0, cz);
  g.add(anel);

  // The crowd: small paper/concrete/ink blocks on the steps, a few lamps' worth of light.
  const cores = [0x6d6a63, 0x5a5751, 0x45433e, 0x34322e, 0x8a8172, 0x2b2a26, 0xa89d84];
  const n = 14000;
  const povo = new THREE.InstancedMesh(new THREE.BoxGeometry(0.34, 0.5, 0.28), lambert(0xffffff), n);
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const sc = new THREE.Vector3(1, 1, 1);
  const cor = new THREE.Color();
  let k = 0;
  const degraus = [];
  for (const [d, h] of perfil.slice(6)) degraus.push([d, h]);
  while (k < n) {
    const ang = Math.random() * Math.PI * 2;
    const i = Math.floor(Math.random() * (degraus.length / 2 - 1)) * 2 + 1;
    const [d, h] = degraus[i];
    if (h > topo - 0.5) continue;
    const rr = R0 + d + 0.25 + Math.random() * 0.6;
    const p = new THREE.Vector3(cx + Math.cos(ang) * rr, h + 0.31, cz + Math.sin(ang) * rr * 1.42);
    sc.set(1, 0.85 + Math.random() * 0.35, 1);
    q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), -ang + Math.PI / 2);
    m.compose(p, q, sc);
    povo.setMatrixAt(k, m);
    // The rows by the pitch catch the floodlights; the top ones fade into the night.
    povo.setColorAt(k, cor.setHex(cores[Math.floor(Math.random() * cores.length)]).multiplyScalar(1.25 - 0.6 * (h / topo)));
    k++;
  }
  g.add(povo);
  // Lamp rigs on the roof edge: grids of yellow bulbs, as the old board.
  // One instanced mesh for every bulb keeps the draw calls down on phones.
  const angulos = [0.35, 1.2, 1.95, 2.8, 3.5, 4.3, 5.1, 5.9];
  // The bulbs and their halos skip the fog: a lamp at night reads from any distance.
  const bulbos = new THREE.InstancedMesh(new THREE.BoxGeometry(0.6, 0.6, 0.2), new THREE.MeshBasicMaterial({ color: COR.lamp, fog: false }), angulos.length * 24);
  const placa = basico(0x16150f);
  const halo = new THREE.SpriteMaterial({ map: texturaHalo(), color: 0xffd36a, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, fog: false });
  let nb = 0;
  for (const ang of angulos) {
    const rr = R0 + r - 3;
    const rig = new THREE.Group();
    rig.add(caixa(7.6, 3.2, 0.3, placa, 0, 0, 0.2));
    rig.position.set(cx + Math.cos(ang) * rr, topo + 6.5, cz + Math.sin(ang) * rr * 1.42);
    rig.lookAt(0, 0, 52.5);
    rig.updateMatrixWorld();
    for (let i = 0; i < 8; i++) {
      for (let j = 0; j < 3; j++) {
        m.makeTranslation(-3.15 + i * 0.9, -0.9 + j * 0.9, 0).premultiply(rig.matrixWorld);
        bulbos.setMatrixAt(nb++, m);
      }
    }
    g.add(rig);
    // A fake bloom: one soft additive sprite in front of each rig (no post-processing pass).
    const s = new THREE.Sprite(halo);
    s.position.set(0, 0, 3).applyMatrix4(rig.matrixWorld);
    s.scale.set(26, 15, 1);
    s.renderOrder = 2;
    g.add(s);
  }
  g.add(bulbos);
  cena.add(g);
}

// ---------------------------------------------------------------------------------------
// Players: rounded, in real proportions (dev, 2026-11-26, mockup "A · arredondado"): a capsule
// torso, cylinder shorts, a sphere head with hair, capsule limbs on hip/knee and shoulder/elbow
// pivots, soft shading. Faceless. The group's origin is the hip, so a dive is a translation plus
// a roll around the hip; `corpo` stretches along the body in the cartoon dive.

const QUADRIL = 0.95; // hip height of a standing player at scale 1
const GOLEIRO_QUADRIL = 0.88; // the keeper's, knees bent in his ready stance
const EIXO_Z = new THREE.Vector3(0, 0, 1);
const padrao = (cor) => new THREE.MeshStandardMaterial({ color: cor, roughness: 0.75, metalness: 0 });

// The torso's capsule wraps its texture once around (CapsuleGeometry: u = 0 on -x, the chest
// (+z) at u = 0.25, the back at 0.75; v from the bottom). The chest and back panels are
// FRENTE_U wide each side of their centre; the rest is the sides, under the sleeves.
const FRENTE_U = 0.18;
const TELA_CAMISA = 256;

let GEO = null;
function geometrias() {
  if (GEO) return GEO;
  const cap = (r, l, seg = 10) => new THREE.CapsuleGeometry(r, l, 4, seg);
  // A cap of hair: the top of a sphere down to `ate` (radians from the crown).
  const calota = (r, ate) => new THREE.SphereGeometry(r, 16, 7, 0, Math.PI * 2, 0, ate);
  const bota = cap(0.045, 0.14, 8).rotateX(Math.PI / 2);
  GEO = {
    tronco: cap(0.19, 0.32, 16),
    calcao: new THREE.CylinderGeometry(0.2, 0.22, 0.2, 14),
    pescoco: new THREE.CylinderGeometry(0.055, 0.065, 0.1, 8),
    cabeca: new THREE.SphereGeometry(0.13, 16, 12),
    coxa: cap(0.075, 0.27),
    canela: cap(0.065, 0.29),
    bota,
    braco: cap(0.06, 0.17),
    ante: cap(0.05, 0.17),
    mao: new THREE.SphereGeometry(0.05, 10, 8),
    luva: new THREE.SphereGeometry(0.075, 10, 8),
    faixa: new THREE.TorusGeometry(0.128, 0.016, 6, 20).rotateX(Math.PI / 2),
    // hair: the cap on the head and, for some styles, one extra piece
    curto: calota(0.136, Math.PI / 2.1),
    raspado: calota(0.1335, Math.PI / 2.5),
    black: new THREE.SphereGeometry(0.175, 14, 10),
    topo: cap(0.105, 0.05, 12),
    moicano: cap(0.03, 0.17, 6).rotateX(Math.PI / 2),
    coque: new THREE.SphereGeometry(0.055, 10, 8),
  };
  return GEO;
}

// Each style: the cap's geometry, its offset and scale on the head, and the extra piece.
const ESTILOS = {
  curto: { calota: "curto", pos: [0, 0.016, -0.006], esc: [0.95, 0.9, 1.02] },
  raspado: { calota: "raspado", pos: [0, 0.008, -0.004], esc: [0.97, 0.95, 1.02] },
  black: { calota: "black", pos: [0, 0.055, -0.05], esc: [1, 0.9, 0.9] },
  topo: { calota: "curto", pos: [0, 0.016, -0.006], esc: [0.95, 0.9, 1.02], extra: ["topo", [0, 0.1, -0.012], [1.08, 1, 1.02]] },
  careca: null,
  moicano: { calota: "raspado", pos: [0, 0.008, -0.004], esc: [0.97, 0.95, 1.02], extra: ["moicano", [0, 0.125, -0.01], [1, 1.5, 1]] },
  coque: { calota: "curto", pos: [0, 0.016, -0.006], esc: [0.95, 0.9, 1.02], extra: ["coque", [0, 0.07, -0.14], [1, 1, 1]] },
};

function montarJogador({ camisa, calcao, meia, luvas = null, cabelo = COR.tinta }) {
  const G = geometrias();
  const grupo = new THREE.Group();
  const corpo = new THREE.Group(); // everything hangs from the hip (y = 0 here)
  grupo.add(corpo);
  // One material per piece of the kit: vestirJogador() swaps colours and maps. `camisa` is the
  // torso (its own canvas: chest, back with the number, sides); `lado` the sleeves.
  const mats = {
    camisa: padrao(camisa),
    lado: padrao(camisa),
    calcao: padrao(calcao),
    meia: padrao(meia),
    pele: padrao(COR.pele),
    cabelo: padrao(cabelo),
    faixa: padrao(COR.giz),
  };
  // Only the big pieces cast shadows (torso, shorts, head, legs): fewer draw calls on phones.
  const add = (pai, geo, mat, x = 0, y = 0, z = 0, s = null, sombra = false) => {
    const m = new THREE.Mesh(geo, mat);
    m.position.set(x, y, z);
    if (s) m.scale.set(...s);
    m.castShadow = sombra;
    pai.add(m);
    return m;
  };
  const tronco = add(corpo, G.tronco, mats.camisa, 0, 0.37, 0, [1.18, 1, 0.72], true);
  add(corpo, G.calcao, mats.calcao, 0, 0.02, 0, [1, 1, 0.75], true);
  add(corpo, G.pescoco, mats.pele, 0, 0.72, 0);
  const cabeca = new THREE.Group();
  cabeca.position.set(0, 0.87, 0);
  corpo.add(cabeca);
  add(cabeca, G.cabeca, mats.pele, 0, 0, 0, [0.92, 1.05, 1], true);
  const calota = add(cabeca, G.curto, mats.cabelo, ...ESTILOS.curto.pos, ESTILOS.curto.esc);
  const extra = add(cabeca, G.coque, mats.cabelo);
  extra.visible = false;
  const faixa = add(cabeca, G.faixa, mats.faixa, 0, 0.045, -0.005, [0.93, 1, 1.03]);
  faixa.rotation.x = -0.12;
  faixa.visible = false;
  // boots and gloves are in `mats` too, so whoever disposes a player frees them all
  const botas = (mats.botas = padrao(COR.tinta));
  if (luvas) mats.luvas = padrao(luvas);
  const perna = (x) => {
    const quadril = new THREE.Group();
    quadril.position.set(x, -0.04, 0);
    corpo.add(quadril);
    add(quadril, G.coxa, mats.pele, 0, -0.21, 0, null, true);
    const joelho = new THREE.Group();
    joelho.position.y = -0.42;
    quadril.add(joelho);
    add(joelho, G.canela, mats.meia, 0, -0.21, 0, null, true);
    add(joelho, G.bota, botas, 0, -0.44, 0.06, [1.1, 1, 1]);
    return { quadril, joelho };
  };
  const braco = (x) => {
    const ombro = new THREE.Group();
    ombro.position.set(x, 0.6, 0);
    corpo.add(ombro);
    add(ombro, G.braco, mats.lado, 0, -0.145, 0);
    const cotovelo = new THREE.Group();
    cotovelo.position.y = -0.29;
    ombro.add(cotovelo);
    // A keeper's long sleeves and gloves.
    add(cotovelo, G.ante, luvas ? mats.lado : mats.pele, 0, -0.135, 0);
    add(cotovelo, luvas ? G.luva : G.mao, luvas ? mats.luvas : mats.pele, 0, -0.3, 0);
    return { ombro, cotovelo };
  };
  // pernaE/bracoE on -x: the player's right (he faces +z); the kicking leg is pernaE.
  const pE = perna(-0.1);
  const pD = perna(0.1);
  const bE = braco(-0.23);
  const bD = braco(0.23);
  const partes = {
    corpo,
    tronco,
    cabeca,
    pernaE: pE.quadril,
    pernaD: pD.quadril,
    joelhoE: pE.joelho,
    joelhoD: pD.joelho,
    bracoE: bE.ombro,
    bracoD: bD.ombro,
    cotoveloE: bE.cotovelo,
    cotoveloD: bD.cotovelo,
  };
  grupo.position.y = QUADRIL;
  const j = { grupo, partes, mats, cabelo: { calota, extra, faixa }, quadril: QUADRIL, tela: null, mapa: null };
  descansar(j);
  return j;
}

const ARTICULACOES = ["corpo", "pernaE", "pernaD", "joelhoE", "joelhoD", "bracoE", "bracoD", "cotoveloE", "cotoveloD"];

/** Standing at ease: every joint straight but the elbows, arms a little off the torso. */
function descansar(j) {
  const p = j.partes;
  for (const k of ARTICULACOES) p[k].rotation.set(0, 0, 0);
  p.corpo.scale.set(1, 1, 1);
  p.cabeca.rotation.set(0, 0, 0);
  j.cabelo.calota.rotation.set(0, 0, 0);
  j.cabelo.extra.rotation.set(0, 0, 0);
  p.bracoE.rotation.z = -0.12;
  p.bracoD.rotation.z = 0.12;
  p.cotoveloE.rotation.x = -0.25;
  p.cotoveloD.rotation.x = -0.25;
}

/** A player's look ({pele, cabelo, corCabelo, faixa, escala}, mano-visual.js). */
function aplicarVisual(j, v) {
  if (!v) return;
  j.mats.pele.color.set(v.pele);
  j.mats.cabelo.color.set(v.corCabelo);
  const { calota, extra, faixa } = j.cabelo;
  const e = ESTILOS[v.cabelo] ?? null;
  calota.visible = Boolean(e);
  extra.visible = Boolean(e?.extra);
  if (e) {
    calota.geometry = GEO[e.calota];
    calota.position.set(...e.pos);
    calota.scale.set(...e.esc);
    if (e.extra) {
      const [geo, pos, esc] = e.extra;
      extra.geometry = GEO[geo];
      extra.position.set(...pos);
      extra.scale.set(...esc);
    }
  }
  // A headband sits over short hair only; an afro or a high top would swallow it.
  faixa.visible = Boolean(v.faixa) && ["curto", "raspado", "careca", "moicano", "coque"].includes(v.cabelo);
  if (v.faixa) j.mats.faixa.color.set(v.faixa);
  j.quadril = QUADRIL * (v.escala ?? 1);
  j.grupo.scale.setScalar(v.escala ?? 1);
}

// ---------------------------------------------------------------------------------------
// Kits: each club's pattern on the shirt's chest and back (small canvas textures), the sides
// and sleeves plain or wrapped by the same hoops, plain shorts and socks. No crests, no logos
// (docs/features/identidade-visual-times.md). Two players of the same team: the one who joined
// second wears the away kit ("fora"). Keepers wear their club's usual goalkeeper colour (dev,
// 2026-11-26): Flamengo yellow, Vasco orange, Palmeiras sky blue, Náutico black, CSA yellow
// and blue; ABC's is a guess (green), no source found.

const BRANCO = "#FFFFFF";
const PRETO = "#141414";
const KIT_COR = { flamengo: "#B3121B", vasco: PRETO, palmeiras: "#006437", abc: PRETO, nautico: "#C60000", csa: "#1B4B9B" };

/** Shirt patterns, drawn in a w×h box; x runs left to right as you look at that panel. */
const ESTAMPAS = {
  // horizontal hoops, `cores` repeating from the collar down
  aros: (g, { cores, n }, w, h) => [...Array(n)].forEach((_, i) => ((g.fillStyle = cores[i % cores.length]), g.fillRect(0, (h * i) / n, w, h / n + 1))),
  // vertical stripes
  listras: (g, { cores, n }, w, h) => [...Array(n)].forEach((_, i) => ((g.fillStyle = cores[i % cores.length]), g.fillRect((w * i) / n, 0, w / n + 1, h))),
  // a sash from the wearer's right shoulder to his left hip: on the chest it runs from your
  // top-left to your bottom-right, on the back (`costas`) from your top-right to bottom-left
  faixa: (g, { base, cor, costas = false }, w, h) => {
    g.fillStyle = base;
    g.fillRect(0, 0, w, h);
    g.fillStyle = cor;
    g.beginPath();
    for (const [x, y] of [[0, 0.1], [0.3, 0.1], [1, 0.9], [0.7, 0.9]]) g.lineTo((costas ? 1 - x : x) * w, y * h);
    g.closePath();
    g.fill();
  },
  // plain, with an optional band of a detail colour across the chest
  liso: (g, { base, cor = base, peito = false }, w, h) => {
    g.fillStyle = base;
    g.fillRect(0, 0, w, h);
    g.fillStyle = cor;
    if (peito) g.fillRect(0, h * 0.3, w, h * 0.12);
  },
  // white with a band of hoops across the chest
  peito: (g, { base, cores }, w, h) => {
    g.fillStyle = base;
    g.fillRect(0, 0, w, h);
    cores.forEach((c, i) => ((g.fillStyle = c), g.fillRect(0, h * (0.28 + i * 0.07), w, h * 0.07 + 1)));
  },
};

// `camisa`: the chest's pattern (the back mirrors a sash); `lado`: sides and sleeves, a colour
// or "estampa" for the same pattern wrapping around (hoops).
const UNIFORMES = {
  flamengo: {
    casa: { camisa: ["aros", { cores: [KIT_COR.flamengo, PRETO], n: 8 }], lado: "estampa", calcao: BRANCO, meia: PRETO },
    fora: { camisa: ["peito", { base: BRANCO, cores: [KIT_COR.flamengo, PRETO, KIT_COR.flamengo] }], lado: BRANCO, calcao: BRANCO, meia: BRANCO },
  },
  vasco: {
    casa: { camisa: ["faixa", { base: BRANCO, cor: PRETO }], lado: BRANCO, calcao: PRETO, meia: BRANCO },
    fora: { camisa: ["faixa", { base: PRETO, cor: BRANCO }], lado: PRETO, calcao: BRANCO, meia: PRETO },
  },
  palmeiras: {
    casa: { camisa: ["liso", { base: KIT_COR.palmeiras }], lado: KIT_COR.palmeiras, calcao: BRANCO, meia: KIT_COR.palmeiras },
    fora: { camisa: ["liso", { base: BRANCO }], lado: BRANCO, calcao: KIT_COR.palmeiras, meia: BRANCO },
  },
  abc: {
    // home: black and white vertical stripes; away: all white (dev, 2026-11-26)
    casa: { camisa: ["listras", { cores: [PRETO, BRANCO], n: 7 }], lado: BRANCO, calcao: PRETO, meia: BRANCO },
    fora: { camisa: ["liso", { base: BRANCO }], lado: BRANCO, calcao: BRANCO, meia: BRANCO },
  },
  nautico: {
    casa: { camisa: ["listras", { cores: [KIT_COR.nautico, BRANCO], n: 7 }], lado: KIT_COR.nautico, calcao: BRANCO, meia: KIT_COR.nautico },
    fora: { camisa: ["liso", { base: BRANCO, cor: KIT_COR.nautico, peito: true }], lado: BRANCO, calcao: KIT_COR.nautico, meia: BRANCO },
  },
  csa: {
    casa: { camisa: ["listras", { cores: [KIT_COR.csa, BRANCO], n: 7 }], lado: KIT_COR.csa, calcao: KIT_COR.csa, meia: BRANCO },
    fora: { camisa: ["liso", { base: BRANCO, cor: KIT_COR.csa, peito: true }], lado: BRANCO, calcao: BRANCO, meia: KIT_COR.csa },
  },
};
// Each club's keeper: the shirt's colour, a band across the chest, the shorts.
const GOLEIROS = {
  flamengo: { base: "#F2C200", cor: PRETO, calcao: PRETO },
  vasco: { base: "#F07A1A", cor: PRETO, calcao: PRETO },
  palmeiras: { base: "#6EC1E4", cor: BRANCO, calcao: "#2C6E9B" },
  abc: { base: "#2E9B4A", cor: BRANCO, calcao: PRETO },
  nautico: { base: "#1E1E1E", cor: KIT_COR.nautico, calcao: "#1E1E1E" },
  csa: { base: "#F2C200", cor: KIT_COR.csa, calcao: KIT_COR.csa },
};

const texturas = new Map();
/** A small cached 64×64 texture of one pattern: a hooped kit's sleeves. */
function textura(chave, [estampa, params]) {
  if (!texturas.has(chave)) {
    const tela = document.createElement("canvas");
    tela.width = tela.height = 64;
    ESTAMPAS[estampa](tela.getContext("2d"), params, 64, 64);
    const t = new THREE.CanvasTexture(tela);
    t.colorSpace = THREE.SRGBColorSpace;
    t.magFilter = THREE.NearestFilter;
    t.minFilter = THREE.NearestFilter;
    t.generateMipmaps = false;
    texturas.set(chave, t);
  }
  return texturas.get(chave);
}

/**
 * The kit for `{time, uniforme}` in a role: {camisa: [estampa, params] for the chest, costas:
 * the same for the back (a sash mirrored), lado: colour or Texture (hoops) for the sides and
 * sleeves, aros: true when the sides take the chest's hoops, calcao, meia} (colours as CSS).
 */
export function uniforme({ time, uniforme: lado = "casa" } = {}, papel = "batedor") {
  if (!UNIFORMES[time]) return null;
  if (papel === "goleiro") {
    const { base, cor, calcao } = GOLEIROS[time];
    // the band across the chest only: the back is plain under the 1
    return { camisa: ["liso", { base, cor, peito: true }], costas: ["liso", { base }], lado: base, calcao, meia: base };
  }
  const kit = UNIFORMES[time][lado === "fora" ? "fora" : "casa"];
  const [estampa, params] = kit.camisa;
  // The back: a sash mirrored, a chest band left out (plain under the number), else the same.
  const costas =
    estampa === "faixa"
      ? [estampa, { ...params, costas: true }]
      : estampa === "peito" || params.peito
        ? ["liso", { base: params.base }]
        : kit.camisa;
  const aros = kit.lado === "estampa";
  return { camisa: kit.camisa, costas, lado: aros ? textura(`${time}:${lado}`, kit.camisa) : kit.lado, aros, calcao: kit.calcao, meia: kit.meia };
}

/** Light colour? (for the number: dark on light shirts, light on dark ones). */
function claro(css) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(css.slice(i, i + 2), 16) / 255);
  return 0.299 * r + 0.587 * g + 0.114 * b > 0.55;
}

/**
 * Paint a player's torso canvas: the sides plain (or the hoops all round), the chest and the
 * back panels with the club's pattern, the number big on the back.
 */
function pintarCamisa(tela, kit, numero) {
  const g = tela.getContext("2d");
  const W = tela.width;
  const H = tela.height;
  g.setTransform(1, 0, 0, 1, 0, 0);
  if (kit.aros) ESTAMPAS[kit.camisa[0]](g, kit.camisa[1], W, H);
  else {
    g.fillStyle = typeof kit.lado === "string" ? kit.lado : BRANCO;
    g.fillRect(0, 0, W, H);
  }
  const largura = 2 * FRENTE_U * W;
  for (const [centro, [estampa, params]] of [[0.25, kit.camisa], [0.75, kit.costas]]) {
    g.save();
    g.translate(centro * W - largura / 2, 0);
    g.beginPath();
    g.rect(0, 0, largura, H);
    g.clip();
    ESTAMPAS[estampa](g, params, largura, H);
    g.restore();
  }
  if (!numero) return;
  const [estampa, params] = kit.costas;
  const fundo = params.base ?? (estampa === "aros" ? params.cores[0] : params.cores[1]);
  const escuro = claro(fundo);
  g.save();
  g.translate(0.75 * W, H * 0.47);
  g.scale(1, 0.95);
  g.font = `900 ${Math.round(H * 0.3)}px "Arial Black", Impact, sans-serif`;
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.lineJoin = "round";
  g.lineWidth = H * 0.035;
  g.strokeStyle = escuro ? BRANCO : PRETO;
  g.fillStyle = escuro ? PRETO : BRANCO;
  g.strokeText(String(numero), 0, 0, largura * 0.9);
  g.fillText(String(numero), 0, 0, largura * 0.9);
  g.restore();
}

function vestir(mat, tinta) {
  const mapa = typeof tinta === "string" ? null : tinta;
  if (mat.map !== mapa) {
    mat.map = mapa;
    mat.needsUpdate = true;
  }
  mat.color.set(mapa ? 0xffffff : tinta);
}

/** Dress a player: the kit (from uniforme()) and the number on his back. */
function vestirJogador(j, kit, numero = null) {
  if (!j.tela) {
    j.tela = document.createElement("canvas");
    j.tela.width = j.tela.height = TELA_CAMISA;
    j.mapa = new THREE.CanvasTexture(j.tela);
    j.mapa.colorSpace = THREE.SRGBColorSpace;
    j.mapa.anisotropy = 4;
  }
  pintarCamisa(j.tela, kit, numero);
  j.mapa.needsUpdate = true;
  vestir(j.mats.camisa, j.mapa);
  for (const peca of ["lado", "calcao", "meia"]) vestir(j.mats[peca], kit[peca]);
}

// ---------------------------------------------------------------------------------------

/**
 * Build the scene inside `el`.
 * @param {HTMLElement} el
 * @param {{papel: "batedor"|"goleiro", modo: "penaltis"|"faltas"}} opcoes
 */
// ---------------------------------------------------------------------------------------
// Contact shadows: they keep everyone on the grass.

const PE = new THREE.Vector3(0, -0.44, 0.06); // the sole, in the knee's frame
const TRONCO = new THREE.Vector3(0, 0.3, 0); // the middle of the torso, in the hip's frame

/**
 * Soft dark blobs on the grass under each foot, under the body and under the ball: one
 * instanced quad and a tiny shader, one draw call. They follow whatever the animation did
 * (read from the world matrices once a frame), fading and spreading as a part leaves the ground.
 */
function criarSombras(cena) {
  const MAX = 64;
  const geo = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
  const forca = new THREE.InstancedBufferAttribute(new Float32Array(MAX), 1);
  forca.setUsage(THREE.DynamicDrawUsage);
  geo.setAttribute("forca", forca);
  const mat = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    vertexShader: `attribute float forca; varying vec2 vUv; varying float vForca;
      void main() { vUv = uv; vForca = forca; gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position, 1.0); }`,
    fragmentShader: `varying vec2 vUv; varying float vForca;
      void main() { float r = length(vUv - 0.5) * 2.0; float a = 1.0 - smoothstep(0.2, 1.0, r);
        gl_FragColor = vec4(0.0, 0.03, 0.01, a * vForca); }`,
  });
  const malha = new THREE.InstancedMesh(geo, mat, MAX);
  malha.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  malha.frustumCulled = false;
  malha.renderOrder = 1; // over the lines, under the players' transparent bits
  malha.count = 0;
  cena.add(malha);
  const jogadores = new Set();
  let bola = null;
  const [m, p, q, e, eixo] = [new THREE.Matrix4(), new THREE.Vector3(), new THREE.Quaternion(), new THREE.Vector3(), new THREE.Vector3()];
  const Y = new THREE.Vector3(0, 1, 0);
  let n = 0;
  const marcar = (x, z, sx, sz, ang, f) => {
    if (n >= MAX || f <= 0.01) return;
    q.setFromAxisAngle(Y, ang);
    m.compose(p.set(x, 0.02, z), q, e.set(sx, 1, sz));
    malha.setMatrixAt(n, m);
    forca.array[n++] = f;
  };
  const presente = (o) => {
    for (; o; o = o.parent) {
      if (!o.visible) return false;
      if (o === cena) return true;
    }
    return false;
  };
  const sat = (v) => Math.min(1, Math.max(0, v));
  return {
    seguir(j) {
      jogadores.add(j);
    },
    bola(o) {
      bola = o;
    },
    atualizar() {
      n = 0;
      for (const j of jogadores) {
        if (!presente(j.grupo)) {
          if (j.sombraVista && !j.grupo.parent) jogadores.delete(j); // a celebration's, gone
          continue;
        }
        j.sombraVista = true;
        j.grupo.updateMatrixWorld(true);
        const s = j.grupo.scale.y;
        for (const joelho of [j.partes.joelhoE, j.partes.joelhoD]) {
          p.copy(PE).applyMatrix4(joelho.matrixWorld);
          const h = Math.max(0, p.y - 0.05);
          const r = 0.34 * s * (1 + h * 1.2);
          marcar(p.x, p.z, r, r * 1.25, j.grupo.rotation.y, 0.8 * sat(1 - h / 0.5));
        }
        // The body: an ellipse along the torso's lean, darker the closer it is (a dive).
        const corpo = j.partes.corpo.matrixWorld;
        p.copy(TRONCO).applyMatrix4(corpo);
        const h = Math.max(0, p.y - 0.25);
        eixo.setFromMatrixColumn(corpo, 1);
        const deitado = Math.hypot(eixo.x, eixo.z) / Math.max(1e-6, eixo.length());
        const [x, z] = [p.x, p.z];
        const r = 0.62 * s * (1 + h * 0.35);
        marcar(x, z, r * (1 + deitado * 1.3), r, Math.atan2(-eixo.z, eixo.x), 0.55 * sat(1 - h / 1.8));
      }
      if (bola && presente(bola)) {
        bola.getWorldPosition(p);
        const h = Math.max(0, p.y - 0.13);
        const r = 0.36 * (1 + h * 0.6);
        marcar(p.x, p.z, r, r, 0, 0.7 * sat(1 - h / 2.5));
      }
      malha.count = n;
      malha.instanceMatrix.needsUpdate = true;
      forca.needsUpdate = true;
    },
  };
}

export function criarCena(el, { papel = "batedor", modo = "penaltis" } = {}) {
  el.classList.add("mn");
  el.innerHTML = `
    <canvas class="mn-canvas" aria-label="Cena do Mano a Mano"></canvas>
    <div class="mn-hud"></div>
    <button type="button" class="mn-tela" aria-label="Tela cheia">⛶ tela cheia</button>
    <div class="mn-gire" role="status"><span class="lamp">Gire o celular</span></div>`;
  const canvas = el.querySelector(".mn-canvas");
  const hud = el.querySelector(".mn-hud");
  const botaoTela = el.querySelector(".mn-tela");

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  // Only the players, the ball and the goal cast shadows, from the one sun, over the box.
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  const cena = new THREE.Scene();
  cena.background = new THREE.Color(COR.board);
  cena.fog = new THREE.Fog(COR.board, 45, 170);
  cena.add(new THREE.HemisphereLight(0xfff1d0, 0x1a2a1f, 1.4));
  const sol = new THREE.DirectionalLight(0xffe6b0, 1.7);
  sol.position.set(-30, 60, 50);
  sol.target.position.set(0, 0, 10);
  sol.castShadow = true;
  sol.shadow.mapSize.set(1024, 1024);
  Object.assign(sol.shadow.camera, { left: -18, right: 18, top: 18, bottom: -18, near: 40, far: 120 });
  sol.shadow.bias = -0.0005;
  sol.shadow.normalBias = 0.02;
  cena.add(sol, sol.target);
  const contra = new THREE.DirectionalLight(0xd6e2ff, 0.8); // cool, from behind the goal: a rim on the players
  contra.position.set(40, 50, -60);
  cena.add(contra);

  montarGramado(cena, Math.min(8, renderer.capabilities.getMaxAnisotropy()));
  cena.traverse((o) => o.isMesh && (o.receiveShadow = true));
  const { rede } = montarGol(cena);
  montarEstadio(cena);

  const batedor = montarJogador({ camisa: COR.papel, calcao: COR.tinta, meia: COR.papel });
  const goleiro = montarJogador({ camisa: COR.tintaSoft, calcao: COR.tinta, meia: COR.tinta, luvas: COR.papel, cabelo: COR.tinta });
  cena.add(batedor.grupo, goleiro.grupo);
  // The ball: `bola` is placed, squashed and stretched along its flight; its mesh spins inside.
  const bola = new THREE.Group();
  const bolaMalha = new THREE.Mesh(new THREE.IcosahedronGeometry(0.13, 2), new THREE.MeshStandardMaterial({ color: COR.giz, roughness: 0.55, flatShading: true }));
  bolaMalha.castShadow = true;
  bola.add(bolaMalha);
  cena.add(bola);
  // The cartoon bursts: paper lines at the strike, lamp lines at the net on a goal.
  const sombras = criarSombras(cena);
  sombras.bola(bolaMalha);
  sombras.seguir(batedor);
  sombras.seguir(goleiro);
  const estouroChute = estouro(COR.papel, 8);
  const estouroGol = estouro(COR.lamp, 12);
  cena.add(estouroChute, estouroGol);
  const barreiraGrupo = new THREE.Group();
  cena.add(barreiraGrupo);

  const camera = new THREE.PerspectiveCamera(40, 16 / 9, 0.1, 400);

  // No shake for who asked the system for less motion.
  const calmo = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  // The winners' celebration at the end (mano-festa.js): its own players, dressed here.
  const festa = criarFesta(THREE, {
    cena,
    camera,
    calmo,
    descansar,
    jogador({ papel: p, time, uniforme: u, visual: v }) {
      const j = montarJogador({ camisa: COR.papel, calcao: COR.tinta, meia: COR.papel, luvas: p === "goleiro" ? COR.papel : null });
      sombras.seguir(j);
      aplicarVisual(j, v);
      const kit = uniforme({ time, uniforme: u }, p);
      if (kit) vestirJogador(j, kit, v?.numero ?? null);
      return j;
    },
  });
  const estado = {
    tremor: 0, // the camera's shake (m), set by the goal
    papel,
    modo,
    falta: null, // {nome, x, z, barreira: {n, x} | null}
    bolaEm: new THREE.Vector3(0, 0.11, MARCA_PENALTI),
    destruida: false,
    animacao: null, // (t) => void, applied every frame
  };

  // ---- placement ------------------------------------------------------------------------

  function direcaoAoGol() {
    // Unit vector on the ground from the ball to the centre of the goal.
    const d = new THREE.Vector3(-estado.bolaEm.x, 0, -estado.bolaEm.z);
    return d.normalize();
  }

  // A pool of five men, so dragging the wall never rebuilds meshes.
  // Each man has his own fixed look; hands crossed in front, as a wall stands.
  const homens = Array.from({ length: 5 }, (_, i) => {
    const j = montarJogador({ camisa: COR.concretoLt, calcao: COR.tinta, meia: COR.concretoLt });
    aplicarVisual(j, visual("barreira", i));
    j.partes.bracoE.rotation.set(-0.25, 0, 0.3);
    j.partes.bracoD.rotation.set(-0.25, 0, -0.3);
    j.partes.cotoveloE.rotation.set(-1.0, 0, 0);
    j.partes.cotoveloD.rotation.set(-1.0, 0, 0);
    barreiraGrupo.add(j.grupo);
    sombras.seguir(j);
    return j;
  });

  function montarBarreira() {
    const b = estado.falta?.barreira;
    const lugares = b ? barreiraHomens(b) : [];
    homens.forEach((j, i) => {
      const p = lugares[i];
      j.grupo.visible = Boolean(p);
      if (!p) return;
      j.grupo.position.set(p.x, j.quadril, p.z);
      j.grupo.rotation.set(0, Math.atan2(estado.bolaEm.x - p.x, estado.bolaEm.z - p.z), 0);
    });
  }

  /** Where the n men stand: the contract span x ± n·55 seen from the ball, 9.15 m out. */
  function barreiraHomens({ n, x }) {
    const [lo, hi] = vaoDaBarreira(n, x);
    const borda = Math.min(55, (hi - lo) / (2 * n));
    const bola0 = estado.bolaEm;
    const naLinha = (cx) => {
      const alvo = golParaMundo(cx, 0);
      const d = new THREE.Vector3(alvo.x - bola0.x, 0, alvo.z - bola0.z).normalize();
      return new THREE.Vector3(bola0.x + d.x * DIST_BARREIRA, 0, bola0.z + d.z * DIST_BARREIRA);
    };
    let a = naLinha(lo + borda);
    let b = naLinha(hi - borda);
    // Drawing only: the men stand a hand apart, so the wall reads as people, not one block.
    // What it covers is still the rules' span.
    const passo = n > 1 ? a.distanceTo(b) / (n - 1) : 0;
    if (n > 1 && passo < VAO_HOMENS) {
      const meio = a.clone().lerp(b, 0.5);
      const eixo = b.clone().sub(a);
      if (eixo.lengthSq() < 1e-6) eixo.set(1, 0, 0);
      eixo.normalize().multiplyScalar((VAO_HOMENS * (n - 1)) / 2);
      a = meio.clone().sub(eixo);
      b = meio.clone().add(eixo);
    }
    return Array.from({ length: n }, (_, i) => (n === 1 ? a : a.clone().lerp(b, i / (n - 1))));
  }

  function posicionarJogadores() {
    const d = direcaoAoGol();
    const bx = estado.bolaEm.x;
    const bz = estado.bolaEm.z;
    bola.position.copy(estado.bolaEm);
    bola.quaternion.identity();
    bola.scale.set(1, 1, 1);
    bolaMalha.rotation.set(0, 0, 0);
    estouroChute.visible = estouroGol.visible = false;
    estado.tremor = 0;
    // Kicker 2.2 m behind the ball and a little to his left, facing the goal.
    const direita = new THREE.Vector3(-d.z, 0, d.x); // kicker's right on the ground
    batedor.grupo.position.set(bx - d.x * 2.2 - direita.x * 1.1, batedor.quadril, bz - d.z * 2.2 - direita.z * 1.1);
    batedor.grupo.rotation.set(0, Math.atan2(d.x, d.z), 0);
    descansar(batedor);
    rede.geometry.attributes.position.array.set(rede.userData.base);
    rede.geometry.attributes.position.needsUpdate = true;
    goleiro.grupo.position.set(0, GOLEIRO_QUADRIL, 0.35);
    goleiro.grupo.rotation.set(0, Math.atan2(bx, bz) * 0.6, 0);
    prontoGoleiro(goleiro, 0);
  }

  /** The keeper's ready stance (mockup): knees bent, arms out, elbows bent; `s` sways it. */
  function prontoGoleiro(g, s) {
    const p = g.partes;
    descansar(g);
    p.corpo.rotation.x = 0.15;
    p.pernaE.rotation.set(-0.35, 0, -0.25);
    p.pernaD.rotation.set(-0.35, 0, 0.25);
    p.joelhoE.rotation.x = 0.6;
    p.joelhoD.rotation.x = 0.6;
    p.bracoE.rotation.set(-0.3, 0, -0.9 - s * 0.08);
    p.bracoD.rotation.set(-0.3, 0, 0.9 + s * 0.08);
    p.cotoveloE.rotation.x = -0.5;
    p.cotoveloD.rotation.x = -0.5;
  }

  // Horizontal field of view kept at 16:9 values, so a tall window shows more sky, never
  // a squeezed goal.
  const LENTE = {
    batedor: { hfov: 58 },
    goleiro: { hfov: 76 },
  };

  function posicionarCamera() {
    const w = el.clientWidth || 16;
    const h = el.clientHeight || 9;
    const aspecto = w / h;
    const hfov = (LENTE[estado.papel].hfov * Math.PI) / 180;
    const vfov = 2 * Math.atan(Math.tan(hfov / 2) / aspecto);
    camera.fov = (Math.max(vfov, (28 * Math.PI) / 180) * 180) / Math.PI;
    camera.aspect = aspecto;
    const bz = estado.bolaEm;
    if (estado.papel === "batedor") {
      const d = direcaoAoGol();
      // Behind the ball and a step to the right, so the kicker never hides the goal.
      camera.position.set(bz.x - d.x * 7 - d.z * 0.6, 2.7, bz.z - d.z * 7 + d.x * 0.6);
      camera.lookAt(bz.x * 0.15, -0.3, 0);
    } else {
      // Inside the goal, back to the net, under the crossbar: the kicker at the spot.
      // A little off-centre, over the keeper's shoulder, so his head never hides the ball.
      camera.position.set(0.5, 2.3, -1.9);
      const olhar = new THREE.Vector3(bz.x * 0.9 + 0.2, 0.1, bz.z);
      const s = estado.seguir;
      if (s) {
        // During the dive the head turns with the body: the post and the ball come in.
        camera.position.x += (s.T.x * 0.3 - 0.5) * s.k;
        olhar.lerp(new THREE.Vector3(s.T.x * 1.1, Math.min(s.T.y, 1.6) * 0.6, 3.2), 0.55 * s.k);
      }
      camera.lookAt(olhar);
    }
    camera.updateProjectionMatrix();
  }

  function ajustar() {
    const w = el.clientWidth;
    const h = el.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    posicionarCamera();
  }

  const observador = new ResizeObserver(ajustar);
  observador.observe(el);

  // ---- fullscreen ----------------------------------------------------------------------

  function emTelaCheia() {
    return document.fullscreenElement === el;
  }
  botaoTela.addEventListener("click", async () => {
    try {
      if (emTelaCheia()) await document.exitFullscreen();
      else {
        await el.requestFullscreen({ navigationUI: "hide" });
        try {
          await screen.orientation?.lock?.("landscape");
        } catch {
          // Desktop browsers refuse orientation locks; the scene works either way.
        }
      }
    } catch {
      // Fullscreen refused (iframe, iOS Safari on iPhone): the 16:9 scene stays in the page.
    }
  });
  const aoTelaCheia = () => {
    botaoTela.textContent = emTelaCheia() ? "✕ sair da tela cheia" : "⛶ tela cheia";
    el.classList.toggle("mn-cheia", emTelaCheia());
    ajustar();
  };
  document.addEventListener("fullscreenchange", aoTelaCheia);

  // ---- loop ------------------------------------------------------------------------------

  function quadro() {
    if (estado.destruida) return;
    try {
      if (estado.animacao) estado.animacao(performance.now());
      sombras.atualizar();
      // The goal's shake: the camera jolts for a moment, then goes back where it was.
      const tremor = calmo ? 0 : estado.tremor;
      if (tremor > 0) {
        const t = performance.now();
        const desvio = new THREE.Vector3(Math.sin(t * 0.091) * tremor, Math.cos(t * 0.077) * tremor * 0.7, 0).applyQuaternion(camera.quaternion);
        camera.position.add(desvio);
        renderer.render(cena, camera);
        camera.position.sub(desvio);
      } else renderer.render(cena, camera);
    } finally {
      requestAnimationFrame(quadro); // one bad frame must not freeze the scene
    }
  }

  function arrumar() {
    estado.seguir = null;
    if (estado.modo === "faltas" && estado.falta) {
      estado.bolaEm.set(estado.falta.x, 0.11, estado.falta.z);
    } else {
      estado.bolaEm.set(0, 0.11, MARCA_PENALTI);
    }
    posicionarJogadores();
    montarBarreira();
    posicionarCamera();
  }

  // ---- HUD: board, hint, actions, bar ----------------------------------------------------

  hud.innerHTML = `
    <div class="mn-placar mn-board">
      <div class="mn-series"></div>
      <div class="mn-prazo lamp" aria-live="off"></div>
    </div>
    <div class="mn-letreiro lamp" aria-live="polite"></div>
    <div class="mn-dica lamp"></div>
    <div class="mn-baixo"><div class="mn-acoes"></div></div>
    <div class="mn-barra mn-board" hidden><div class="mn-celulas"></div></div>`;
  const $ = (sel) => hud.querySelector(sel);
  const dicaEl = $(".mn-dica");
  const acoesEl = $(".mn-acoes");
  const prazoEl = $(".mn-prazo");
  const barraEl = $(".mn-barra");
  const CELULAS = 25;
  $(".mn-celulas").innerHTML = Array.from({ length: CELULAS }, () => "<i></i>").join("");
  const celulas = [...barraEl.querySelectorAll("i")].reverse(); // index 0 at the bottom

  function dica(texto) {
    dicaEl.textContent = texto || "";
  }

  /** The "aim high, faster bar" hint shows once per browser; false the first time. */
  function avisouPressa() {
    try {
      if (localStorage.getItem("mano:pressa")) return true;
      localStorage.setItem("mano:pressa", "1");
    } catch {
      /* no storage: the hint shows every time, which is harmless */
    }
    return false;
  }

  /** Count `segundos` down on the board; calls aoZerar once at zero. Returns a stop(). */
  function contar(segundos, aoZerar) {
    const fim = performance.now() + segundos * 1000;
    let parado = false;
    const tique = () => {
      if (parado) return;
      const falta = Math.max(0, Math.ceil((fim - performance.now()) / 1000));
      prazoEl.textContent = String(falta).padStart(2, "0");
      prazoEl.classList.toggle("mn-urgente", falta <= 3);
      if (falta === 0) {
        parar();
        aoZerar();
      }
    };
    const relogio = setInterval(tique, 100);
    // The first tick waits for the caller to build its controls, even at zero.
    prazoEl.textContent = String(Math.max(0, Math.ceil(segundos))).padStart(2, "0");
    setTimeout(tique, 0);
    function parar() {
      parado = true;
      clearInterval(relogio);
      prazoEl.textContent = "";
    }
    return parar;
  }

  const raio = new THREE.Raycaster();
  function noPlano(ev, plano) {
    const r = canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    raio.setFromCamera(ndc, camera);
    return raio.ray.intersectPlane(plano, new THREE.Vector3());
  }
  const PLANO_GOL = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
  const PLANO_CHAO = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);

  // The aim: a lamp ring on the goal mouth, drawn over the net.
  const mira = new THREE.Group();
  const miraMat = new THREE.MeshBasicMaterial({ color: COR.lamp, depthTest: false, transparent: true });
  mira.add(new THREE.Mesh(new THREE.RingGeometry(0.17, 0.25, 24), miraMat));
  mira.add(new THREE.Mesh(new THREE.PlaneGeometry(0.05, 0.22), miraMat).translateY(0.34));
  mira.add(new THREE.Mesh(new THREE.PlaneGeometry(0.05, 0.22), miraMat).translateY(-0.34));
  mira.add(new THREE.Mesh(new THREE.PlaneGeometry(0.22, 0.05), miraMat).translateX(0.34));
  mira.add(new THREE.Mesh(new THREE.PlaneGeometry(0.22, 0.05), miraMat).translateX(-0.34));
  mira.renderOrder = 10;
  mira.traverse((o) => (o.renderOrder = 10));
  mira.visible = false;
  cena.add(mira);
  function porMira([x, y]) {
    mira.position.copy(golParaMundo(x, y, 0.06));
  }

  // The dashed path preview of a free kick.
  const previaMat = new THREE.LineDashedMaterial({ color: COR.lamp, dashSize: 0.35, gapSize: 0.25, transparent: true, opacity: 0.85, depthTest: false });
  const previa = new THREE.Line(new THREE.BufferGeometry(), previaMat);
  previa.renderOrder = 9;
  previa.visible = false;
  cena.add(previa);
  function desenharPrevia(alvo, escolha) {
    const pts = caminho(estado.bolaEm, golParaMundo(alvo[0], alvo[1]), escolha).getPoints(40);
    previa.geometry.dispose();
    previa.geometry = new THREE.BufferGeometry().setFromPoints(pts);
    previa.computeLineDistances();
    previa.visible = true;
  }

  function limparControles() {
    acoesEl.innerHTML = "";
    acoesEl.className = "mn-acoes";
    dica("");
    barraEl.hidden = true;
    mira.visible = false;
    previa.visible = false;
  }

  const acaso = (a, b) => a + Math.random() * (b - a);
  const sortear = (lista) => lista[Math.floor(Math.random() * lista.length)];

  let pedidoAtual = null; // the stop() of the pending pedir*, so a new one cancels it
  function comecarPedido(fn) {
    pedidoAtual?.();
    return new Promise((resolve) => {
      const limpar = [];
      let feito = false;
      const terminar = (valor) => {
        if (feito) return;
        feito = true;
        for (const f of limpar) f();
        limparControles();
        pedidoAtual = null;
        resolve(valor);
      };
      pedidoAtual = () => terminar(null);
      // Anything registered after the end (a deadline already at zero) is undone at once.
      const aoFim = (f) => (feito ? f() : limpar.push(f));
      const ouvir = (alvo, tipo, f) => {
        if (feito) return;
        alvo.addEventListener(tipo, f);
        limpar.push(() => alvo.removeEventListener(tipo, f));
      };
      fn({ terminar, aoFim, ouvir, terminado: () => feito });
    });
  }

  /**
   * Kicker's choice. Free kick: trajectory and curve first, then the aim, then the bar.
   * Resolves {alvo: [x, y], barra, trajetoria?, curva?, cavadinha?}; at 10 s, whatever is missing
   * is random. A penalty offers the cavadinha in place of the aim, with its own band.
   */
  function pedirChute({ falta = estado.modo === "faltas", faixa = faixaBoa, faixaCavadinha = () => [420, 580], segundos = 10 } = {}) {
    return comecarPedido(({ terminar, aoFim, ouvir }) => {
      const escolha = falta ? { trajetoria: null, curva: 0 } : {};
      let alvo = null;
      let mirado = false; // only a real aim counts; an untouched one is random at the deadline
      let travado = false;
      let barraLigada = false;
      let barraInicio = 0;
      let barraValor = 500;
      let cavadinha = false;
      const fechar = () =>
        terminar({
          ...(cavadinha ? { cavadinha: true } : {}),
          alvo: alvo && mirado ? alvo.map(Math.round) : [Math.round(acaso(0, 1000)), Math.round(acaso(0, 1000))],
          barra: Math.round(barraLigada ? barraValor : acaso(0, 1000)),
          ...(falta ? { trajetoria: escolha.trajetoria ?? sortear(["rasteira", "por_cima", "pelo_lado"]), curva: Math.round(escolha.curva * 100) / 100 } : {}),
        });
      aoFim(contar(segundos, fechar));

      const mirar = () => {
        acoesEl.innerHTML = falta ? "" : `<button type="button" class="mn-opcao mn-cavadinha">Cavadinha</button>`;
        dica("Mire no gol e clique");
        // The chip replaces the aim: straight to the bar, with its own narrower band.
        if (!falta)
          ouvir(acoesEl, "click", (ev) => {
            if (travado || !ev.target.closest(".mn-cavadinha")) return;
            cavadinha = true;
            alvo = [500, 500];
            mirado = true;
            porMira(alvo);
            travado = true;
            acoesEl.innerHTML = "";
            ligarBarra();
          });
        mira.visible = true;
        alvo = [500, 500];
        porMira(alvo);
        if (falta) desenharPrevia(alvo, escolha);
        ouvir(canvas, "pointermove", (ev) => {
          if (travado) return;
          const p = noPlano(ev, PLANO_GOL);
          if (!p) return;
          const [x, y] = mundoParaGol(p);
          alvo = [prender(x), prender(y)];
          mirado = true;
          porMira(alvo);
          if (falta) desenharPrevia(alvo, escolha);
        });
        ouvir(canvas, "pointerup", (ev) => {
          if (travado) return;
          const p = noPlano(ev, PLANO_GOL);
          if (p) {
            const [x, y] = mundoParaGol(p);
            alvo = [prender(x), prender(y)];
            mirado = true;
            porMira(alvo);
          }
          travado = true;
          ligarBarra();
        });
      };

      const ligarBarra = () => {
        acoesEl.innerHTML = ""; // the cavadinha button goes with the aim
        // One sweep is 1000 ms (30% faster than the first 1300, dev 2026-11-26), and faster still
        // the higher the aim (mano-faixa.js, dev 2026-11-26).
        const periodo = periodoBarra(alvo, cavadinha);
        const apressada = pressaBarra(alvo, cavadinha) > 1;
        barraEl.classList.toggle("mn-rapida", apressada);
        barraEl.style.setProperty("--mn-pisca", `${Math.round(periodo / 2)}ms`);
        if (apressada && !avisouPressa()) dica("Mais alto, barra mais rápida: pare na faixa acesa");
        else dica(cavadinha ? "Cavadinha: pare a barra na faixa acesa" : "Pare a barra na faixa acesa");
        const [lo, hi] = cavadinha ? faixaCavadinha() : faixa(alvo);
        celulas.forEach((c, i) => {
          const v = ((i + 0.5) / CELULAS) * 1000;
          c.className = v >= lo && v <= hi ? "boa" : "";
        });
        barraEl.hidden = false;
        barraLigada = true;
        barraInicio = performance.now();
        let parada = false;
        const rodar = () => {
          if (parada) return;
          const fase = ((performance.now() - barraInicio) / periodo) % 1;
          barraValor = (fase < 0.5 ? fase * 2 : 2 - fase * 2) * 1000;
          const k = Math.min(CELULAS - 1, Math.floor((barraValor / 1000) * CELULAS));
          celulas.forEach((c, i) => c.classList.toggle("on", i === k));
          requestAnimationFrame(rodar);
        };
        aoFim(() => (parada = true));
        requestAnimationFrame(rodar);
        const parar = (ev) => {
          if (ev.type === "keydown" && ev.code !== "Space") return;
          ev.preventDefault?.();
          fechar();
        };
        // The aim's own pointerup is over; the next press stops the bar.
        setTimeout(() => {
          ouvir(canvas, "pointerdown", parar);
          ouvir(barraEl, "pointerdown", parar);
        }, 0);
        ouvir(window, "keydown", parar);
      };

      if (!falta) return mirar();
      dica("Escolha a batida");
      acoesEl.classList.add("mn-acoes-falta");
      acoesEl.innerHTML = `
        <div class="mn-opcoes">
          <button type="button" class="mn-opcao" data-t="rasteira">Rasteira</button>
          <button type="button" class="mn-opcao" data-t="por_cima">Por cima</button>
          <button type="button" class="mn-opcao" data-t="pelo_lado">Pelo lado</button>
        </div>
        <label class="mn-curva"><span class="lamp">Curva</span>
          <input type="range" min="-100" max="100" step="5" value="0" aria-label="Curva">
        </label>
        <button type="button" class="mn-ok" disabled>Mirar ▸</button>`;
      const ok = acoesEl.querySelector(".mn-ok");
      const range = acoesEl.querySelector("input");
      const previaPadrao = () => desenharPrevia([500, 500], escolha);
      ouvir(acoesEl, "click", (ev) => {
        const b = ev.target.closest("[data-t]");
        if (b) {
          escolha.trajetoria = b.dataset.t;
          for (const o of acoesEl.querySelectorAll("[data-t]")) o.setAttribute("aria-pressed", String(o === b));
          ok.disabled = false;
          previaPadrao();
        }
        if (ev.target.closest(".mn-ok") && escolha.trajetoria) mirar();
      });
      ouvir(range, "input", () => {
        escolha.curva = Number(range.value) / 100;
        if (escolha.trajetoria) previaPadrao();
      });
    });
  }

  /** Goalkeeper's choice: three big buttons, laid out as his own camera sees the goal. */
  function pedirDefesa({ segundos = 10 } = {}) {
    return comecarPedido(({ terminar, aoFim, ouvir }) => {
      aoFim(contar(segundos, () => terminar({ lado: sortear(["esquerda", "fica", "direita"]) })));
      // Contract sides are the kicker's; from inside the goal they are mirrored, so the
      // button on the keeper's left sends "direita".
      const espelho = estado.papel === "goleiro";
      const ordem = espelho ? ["direita", "fica", "esquerda"] : ["esquerda", "fica", "direita"];
      const rotulos = ["◀ Esquerda", "Ficar", "Direita ▶"];
      dica("Pra onde você pula?");
      acoesEl.classList.add("mn-acoes-defesa");
      acoesEl.innerHTML = ordem
        .map((lado, i) => `<button type="button" class="mn-opcao mn-grande" data-lado="${lado}">${rotulos[i]}</button>`)
        .join("");
      ouvir(acoesEl, "click", (ev) => {
        const b = ev.target.closest("[data-lado]");
        if (b) terminar({ lado: b.dataset.lado });
      });
      ouvir(window, "keydown", (ev) => {
        const i = { ArrowLeft: 0, ArrowDown: 1, ArrowUp: 1, ArrowRight: 2 }[ev.key];
        if (i === undefined) return;
        ev.preventDefault();
        terminar({ lado: ordem[i] });
      });
    });
  }

  /** Goalkeeper sets the wall: drag it along, +/- men, "pronto". Resolves {n, x}. */
  function pedirBarreira({ segundos = 10, inicial = { n: 3, x: 500 } } = {}) {
    return comecarPedido(({ terminar, aoFim, ouvir }) => {
      if (!estado.falta) api.posicionarFalta({});
      const b = { n: inicial.n, x: prender(inicial.x) };
      const aplicar = () => {
        b.x = Math.round(prender(b.x));
        estado.falta.barreira = { ...b };
        montarBarreira();
        const n = acoesEl.querySelector(".mn-n");
        if (n) n.textContent = b.n;
      };
      aoFim(
        contar(segundos, () => {
          b.n = 2 + Math.floor(Math.random() * 4);
          b.x = acaso(0, 1000);
          aplicar();
          terminar({ ...b });
        }),
      );
      dica("Arraste a barreira");
      acoesEl.classList.add("mn-acoes-barreira");
      acoesEl.innerHTML = `
        <button type="button" class="mn-opcao" data-d="-1" aria-label="Tirar um homem">−</button>
        <span class="mn-n lamp"></span><span class="mn-homens lamp">na barreira</span>
        <button type="button" class="mn-opcao" data-d="1" aria-label="Pôr um homem">+</button>
        <button type="button" class="mn-ok">Pronto</button>`;
      aplicar();
      let arrastando = false;
      const mover = (ev) => {
        if (ev.type === "pointermove" && ev.pointerType !== "mouse" && !arrastando) return;
        const p = noPlano(ev, PLANO_CHAO);
        if (!p) return;
        const o = estado.bolaEm;
        // The ray from the ball through the pointer, carried to the goal line.
        const dz = p.z - o.z;
        if (dz > -0.5) return;
        const xGol = o.x + ((p.x - o.x) * (0 - o.z)) / dz;
        b.x = mundoParaGol(new THREE.Vector3(xGol, 0, 0))[0];
        aplicar();
      };
      ouvir(canvas, "pointerdown", (ev) => {
        arrastando = true;
        mover(ev);
      });
      ouvir(canvas, "pointermove", mover);
      ouvir(window, "pointerup", () => (arrastando = false));
      ouvir(acoesEl, "click", (ev) => {
        const d = ev.target.closest("[data-d]");
        if (d) {
          b.n = Math.min(5, Math.max(2, b.n + Number(d.dataset.d)));
          aplicar();
        }
        if (ev.target.closest(".mn-ok")) terminar({ ...b });
      });
    });
  }

  // ---- board: the shootout lines and the result sign --------------------------------------

  const seriesEl = $(".mn-series");
  const letreiroEl = $(".mn-letreiro");
  /** nomes: [a, b] (a name, or {time, apelido}: the team big, the nickname under it);
   * series: [[...], [...]] with "g" (goal) | "e" (missed); gols: [ga, gb]. */
  function placar({ nomes = ["", ""], series = [[], []], gols = null } = {}) {
    const vagas = Math.max(5, series[0].length, series[1].length);
    const conta = gols ?? series.map((s) => s.filter((v) => v === "g").length);
    seriesEl.innerHTML = [0, 1]
      .map((i) => {
        const bolas = Array.from({ length: vagas }, (_, k) => {
          const v = series[i][k];
          return v === "g" ? '<b class="mn-g">●</b>' : v === "e" ? '<b class="mn-e">✕</b>' : '<b class="mn-a">○</b>';
        }).join("");
        const n = nomes[i];
        const quem =
          n && typeof n === "object" && n.time
            ? `<span class="mn-quem"><span class="lamp mn-time">${escapar(n.time)}</span><span class="lamp mn-apelido">${escapar(n.apelido ?? "")}</span></span>`
            : `<span class="mn-quem lamp">${escapar(typeof n === "object" ? (n?.apelido ?? "") : n)}</span>`;
        return `<div class="mn-fila">${quem}<span class="mn-bolas lamp">${bolas}</span><span class="mn-gols lamp">${conta[i]}</span></div>`;
      })
      .join("");
  }
  const escapar = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  function letreiro(texto) {
    letreiroEl.textContent = texto || "";
    letreiroEl.classList.toggle("blink", Boolean(texto));
  }

  // ---- the kick ---------------------------------------------------------------------------
  //
  // Every frame is a pure function of the clock, so a background tab (rAF paused) or a
  // resize never leaves the kick halfway: the next frame, or the closing timer, lands it.
  //
  // Times (ms, performance.now()): t0 call; chute_em the kicker reaches the ball; the
  // strike waits for the result (server: window close, chute_em + 600 ms) - a "paradinha"
  // while the keeper's exit window is open; then ~0.6 s of flight and the outcome.

  const JANELA = 600;
  // The chip flies 550 ms longer; the server holds its result as long (sala.py VOO_CAVADINHA_A_MAIS).
  const VOO = { penaltis: 600, faltas: 800, cavadinha: 1150 };
  const msDeVoo = (lance) => (lance?.chute?.cavadinha ? VOO.cavadinha : VOO[estado.modo]);
  const DEPOIS = 1700;
  const ouvintesSaida = new Set();
  let ultimo = null; // {lance, modo, falta} of the last kick, for the replay
  let cobrancaAtual = null;

  const lerp = (a, b, k) => a + (b - a) * k;
  const suave = (k) => (k <= 0 ? 0 : k >= 1 ? 1 : k * k * (3 - 2 * k));
  const saiRapido = (k) => 1 - (1 - k) ** 3; // ease-out
  const emEntra = (k) => (k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2); // ease-in-out
  // ease-out-back: past the mark by about a tenth, then back to it
  const voltaAtras = (k) => (k <= 0 ? 0 : k >= 1 ? 1 : 1 + 2.70158 * (k - 1) ** 3 + 1.70158 * (k - 1) ** 2);
  const entre = (t, a, b) => Math.min(1, Math.max(0, (t - a) / (b - a)));

  function planejarVoo(lance) {
    const origem = estado.bolaEm.clone();
    const falta = estado.modo === "faltas";
    const [ox, oy] = lance.onde;
    let destino = golParaMundo(ox, oy);
    destino.y = Math.max(0.11, destino.y);
    if (lance.resultado === "trave") {
      // Snap to the frame: the crossbar if high, else the nearer post.
      if (oy >= 940 && ox > 40 && ox < 960) destino.y = GOL.altura + 0.02;
      else destino.x = Math.sign(destino.x || 1) * (GOL.meia + 0.02);
    }
    const escolha = falta
      ? { trajetoria: lance.chute.trajetoria ?? "por_cima", curva: lance.chute.curva ?? 0 }
      : { cavadinha: Boolean(lance.chute?.cavadinha) };
    const curva = caminho(origem, destino, escolha);
    let fim = 1;
    if (lance.resultado === "barreira") {
      for (let u = 0; u <= 1; u += 0.01) {
        const p = curva.getPoint(u);
        if (Math.hypot(p.x - origem.x, p.z - origem.z) >= DIST_BARREIRA - 0.25) {
          fim = u;
          break;
        }
      }
    }
    const chegada = curva.getPoint(fim);
    if (lance.resultado === "barreira") chegada.y = Math.min(chegada.y, 1.9);
    const tangente = curva.getTangent(fim);
    const velocidade = (curva.getLength() * fim) / (msDeVoo(lance) / 1000);
    return { curva, fim, chegada, tangente, velocidade, origem };
  }

  /** Where the ball is `dt` seconds after it arrives, by outcome. */
  function bolaDepois(plano, resultado, dt) {
    const { chegada: c, tangente: v, velocidade } = plano;
    const p = new THREE.Vector3();
    const queda = (y0, vy) => {
      // Bounces on the grass, losing half its height each time.
      let y = y0 + vy * dt - 4.9 * dt * dt;
      if (y >= 0.11) return y;
      const tChao = (vy + Math.sqrt(vy * vy + 19.6 * Math.max(0, y0 - 0.11))) / 9.8;
      const v2 = Math.max(0, 9.8 * tChao - vy) * 0.45;
      const d2 = dt - tChao;
      return Math.max(0.11, 0.11 + v2 * d2 - 4.9 * d2 * d2);
    };
    if (resultado === "gol") {
      const alcance = Math.min(3, (GOL.fundo - 0.15) / Math.max(0.2, -v.z));
      const k = 1 - Math.exp(-7 * dt);
      p.copy(c).addScaledVector(v, alcance * k);
      p.y = Math.max(0.11, p.y - 4.9 * Math.max(0, dt - 0.25) ** 2);
      return p;
    }
    if (resultado === "fora") {
      p.copy(c).addScaledVector(v, velocidade * Math.min(dt, 0.9));
      p.y = Math.max(0.11, c.y + v.y * velocidade * Math.min(dt, 0.9) - 4.9 * dt * dt);
      return p;
    }
    // Rebounds: off the keeper, the frame or the wall, back towards the pitch.
    const lado = Math.sign(c.x || 0.5);
    const rebote = {
      defesa: [lado * 2.6, 2.2, 6.5],
      trave: [c.y > GOL.altura - 0.1 ? lado * 0.6 : -lado * 2.4, c.y > GOL.altura - 0.1 ? 3.2 : 0.8, 8.5],
      barreira: [(Math.random() - 0.5) * 2, 2.6, 0],
    }[resultado];
    if (resultado === "barreira") {
      const volta = plano.origem.clone().sub(c).setY(0).normalize().multiplyScalar(4.5);
      rebote[0] += volta.x;
      rebote[2] = volta.z;
    }
    const k = Math.exp(-0.8 * dt);
    p.set(c.x + rebote[0] * dt * k, queda(c.y, rebote[1]), c.z + rebote[2] * dt * k);
    return p;
  }

  function sacudirRede(plano, resultado, dt) {
    const arr = rede.geometry.attributes.position.array;
    const base = rede.userData.base;
    const alvo = resultado === "gol" ? bolaDepois(plano, "gol", 0.5) : null;
    const amp = alvo && dt > 0.12 ? 0.55 * Math.exp(-3 * (dt - 0.12)) * Math.cos(9 * (dt - 0.12)) : 0;
    for (let i = 0; i < arr.length; i += 3) {
      if (!amp) {
        arr[i + 2] = base[i + 2];
        continue;
      }
      const d2 = (base[i] - alvo.x) ** 2 + (base[i + 1] - alvo.y) ** 2;
      arr[i + 2] = base[i + 2] - amp * Math.exp(-d2 / 1.1);
    }
    rede.geometry.attributes.position.needsUpdate = true;
  }

  function alvoDoGoleiro(lance, plano) {
    const lado = lance.defesa.lado;
    const s = lado === "esquerda" ? -1 : lado === "direita" ? 1 : 0;
    const alcance = lance.defesa.saida ? 3.1 : 2.4;
    if (lance.resultado === "defesa") {
      const c = plano.chegada.clone();
      c.x = prender(c.x, -alcance - 0.3, alcance + 0.3);
      return c;
    }
    if (s === 0) return new THREE.Vector3(0, 2.05, 0.45);
    const bolaDoLado = Math.sign(plano.chegada.x) === s;
    return new THREE.Vector3(s * alcance, bolaDoLado ? Math.min(Math.max(plano.chegada.y, 0.4), 2.1) : 1.0, 0.45);
  }

  // ---- the players' motion ----------------------------------------------------------------
  //
  // Both are pure functions of the kick's clock (no random, no frame dt), so both browsers in
  // a match draw the same frame. `calmo` (prefers-reduced-motion) keeps the motion but drops
  // the cartoon extras: squash and stretch, hops, overshoots and the hair lagging behind.

  /** Every key of `a` blended towards `b` by `w`. */
  const mistura = (a, b, w) => {
    const r = {};
    for (const k in a) r[k] = lerp(a[k], b[k] ?? a[k], w);
    return r;
  };

  // The leg's bones (montarJogador): hip to knee, knee to the boot's centre, the boot's centre
  // over its sole.
  const COXA = 0.42;
  const CANELA = 0.44;
  const SOLA = 0.045;
  const _pe = new THREE.Vector3();
  const arco = (x) => Math.acos(Math.min(1, Math.max(-1, x)));
  /**
   * Two-bone IK in the leg's plane: hip and knee bent so the boot sits at `pe` (world; y = 0 on
   * the grass). The knee only bends forward. Needs the player's matrices up to date.
   */
  function pisar(j, lado, pe) {
    const p = j.partes;
    const quadril = p[`perna${lado}`];
    const joelho = p[`joelho${lado}`];
    _pe.copy(pe);
    _pe.y += SOLA * j.grupo.scale.y;
    p.corpo.worldToLocal(_pe);
    const dy = _pe.y - quadril.position.y;
    const dz = _pe.z - quadril.position.z;
    const D = Math.max(0.05, Math.min(Math.hypot(dy, dz), COXA + CANELA - 1e-4));
    return {
      coxa: Math.atan2(-dz, -dy) - arco((COXA * COXA + D * D - CANELA * CANELA) / (2 * COXA * D)),
      joelho: Math.PI - arco((COXA * COXA + CANELA * CANELA - D * D) / (2 * COXA * CANELA)),
    };
  }

  // The run-up (dev, 2026-11-27): four steps whose feet stay where they land (the hip carries
  // the body over them, no skating), a longer last stride into the plant foot beside the ball.
  const PASSOS = [0.8, 1, 1, 1.15]; // relative lengths: right, left, right, left (the plant)
  const APOIO = 0.2; // m of the hip's travel each side of a planted foot while it bears weight
  // The run's distance over its time: a softer ease-in-out than emEntra, so the first stride is
  // not slow motion; still from 0 to 1.
  const corrida = (k) => lerp(k, emEntra(k), 0.5);

  /** The run's footprints, from where he stands to the plant (once per kick). */
  function planoCorrida(tl) {
    if (tl.plano) return tl.plano;
    const esc = batedor.grupo.scale.x;
    const S = tl.inicio.clone().setY(0);
    const P = tl.plantio.clone().setY(0);
    const u = P.clone().sub(S);
    const L = u.length();
    u.normalize();
    const direita = new THREE.Vector3(-u.z, 0, u.x); // the runner's right
    const C = APOIO * esc;
    const pegada = (x, lado, lateral = 0.1) => S.clone().addScaledVector(u, x).addScaledVector(direita, (lado === "E" ? 1 : -1) * lateral * esc);
    const soma = PASSOS.reduce((a, b) => a + b, 0);
    const total = L + 0.08 * esc;
    let x = 0;
    const xs = PASSOS.map((w) => (x += (total * w) / soma));
    // Each foot: where it stands, from which point of the hip's travel it bears weight
    // (`chega`) and when it lifts (`sai`). The kicking foot (right, E) goes first and ends
    // resting a little behind, lightly on its toes, for the wind-up.
    const pes = {
      E: [
        { pos: pegada(0, "E"), chega: -Infinity, sai: 0 },
        { pos: pegada(xs[0], "E"), chega: xs[0] - C, sai: xs[0] + C },
        { pos: pegada(xs[2], "E"), chega: xs[2] - C, sai: xs[2] + C },
        { pos: pegada(L - 0.22 * esc, "E", 0.14), chega: L, sai: Infinity, leve: true },
      ],
      D: [
        { pos: pegada(0, "D"), chega: -Infinity, sai: C },
        { pos: pegada(xs[1], "D"), chega: xs[1] - C, sai: xs[1] + C },
        { pos: pegada(xs[3], "D"), chega: xs[3] - C, sai: Infinity },
      ],
    };
    tl.plano = { S, P, u, L, esc, pes, yaw: Math.atan2(u.x, u.z) };
    return tl.plano;
  }

  /** A foot at the hip's travel `h`: {pos, apoio: 0-1 into its stance or -1 in the air}. */
  function peEm(lista, h, esc) {
    for (let i = 0; i < lista.length; i++) {
      const a = lista[i];
      if (h < a.chega) {
        // Swinging from the previous print to this one, lifted in an arc.
        const b = lista[i - 1];
        const s = entre(h, b.sai, a.chega);
        const pos = b.pos.clone().lerp(a.pos, suave(s));
        pos.y = (a.leve ? 0.05 : 0.13) * esc * Math.sin(Math.PI * suave(s)); // eased: no snap of the knee off the grass
        return { pos, apoio: -1 };
      }
      if (h <= a.sai) {
        // The resting toe bears no weight; the plant foot settles to midstance and stays there.
        if (a.leve) return { pos: a.pos.clone(), apoio: -1 };
        const apoio = Number.isFinite(a.sai) ? (h - a.chega) / (a.sai - a.chega) : Math.min(0.5, (h - a.chega) / (2 * APOIO * esc));
        return { pos: a.pos.clone(), apoio };
      }
    }
    return { pos: lista.at(-1).pos.clone(), apoio: 0.5 };
  }

  /** The run's pose at the hip's travel `h` (m): where the hip and both feet are, and the body. */
  function corridaEm(pl, h) {
    const { S, u, L, esc, pes } = pl;
    const E = peEm(pes.E, h, esc);
    const D = peEm(pes.D, h, esc);
    // Lowest over the middle of a stance, highest in the air between steps.
    const desce = Math.max(E.apoio >= 0 ? Math.sin(Math.PI * E.apoio) : 0, D.apoio >= 0 ? Math.sin(Math.PI * D.apoio) : 0);
    const entra = suave(h / (0.35 * esc)); // from standing into the run
    const freia = suave(entre(h, L - 0.6 * esc, L)); // the last stride, slowing into the plant
    const quadril = S.clone().addScaledVector(u, h);
    quadril.y = batedor.quadril - esc * entra * (0.05 + 0.025 * desce);
    // Arms against the legs: each one back while its leg is forward.
    const frente = (pe) => pe.pos.clone().sub(quadril).dot(u) / esc;
    return {
      quadril,
      pes: { E: E.pos, D: D.pos },
      corpo: {
        inclina: entra * (0.2 - 0.14 * freia),
        rola: 0.04 * entra * ((E.apoio >= 0 ? -Math.sin(Math.PI * E.apoio) : 0) + (D.apoio >= 0 ? Math.sin(Math.PI * D.apoio) : 0)),
        bEx: prender(1.5 * frente(E), -0.8, 0.8),
        bDx: prender(1.5 * frente(D), -0.8, 0.8),
        bEz: -0.12,
        bDz: 0.12,
        cot: -0.25 - 0.9 * entra,
        escala: 1,
        avanca: 0,
        baixa: 0,
      },
    };
  }

  // The kicker's body over the kick (ease: each pose blended into the next, never a snap).
  const PARADINHA = { inclina: 0.06, rola: 0, bEx: 0.15, bDx: 0.15, bEz: -0.15, bDz: 0.15, cot: -0.45, escala: 1, avanca: 0, baixa: 0.03 };
  // The wind-up: leaning back and over the plant foot, the free arm wide, the kicking leg cocked.
  const ARMADO = { inclina: -0.28, rola: -0.13, bEx: 0.75, bDx: -0.45, bEz: -0.6, bDz: 1.3, cot: -0.35, escala: 0.95, avanca: -0.06, baixa: 0.07, coxa: 1.0, joelho: 1.95 };
  // The strike, through the ball: over it, the arms swapped, stretched long.
  const GOLPE = { inclina: 0.16, rola: -0.06, bEx: -0.65, bDx: 0.1, bEz: -0.35, bDz: 1.0, cot: -0.4, escala: 1.07, avanca: 0.12, baixa: 0.04, coxa: -1.35, joelho: 0.05 };
  // After: the follow-through lands a step ahead, upright, arms down.
  const DEPOIS_CHUTE = { inclina: 0.06, rola: 0, bEx: 0.1, bDx: 0.1, bEz: -0.18, bDz: 0.18, cot: -0.4, escala: 1, avanca: 0.42, baixa: 0.02 };

  function animarBatedor(t, tl) {
    const b = batedor;
    const p = b.partes;
    const { lento, d } = tl;
    const pl = planoCorrida(tl);
    const { u, L, esc } = pl;
    const ef = calmo ? 0 : 1;
    descansar(b);
    const tAnt = tl.t0 + tl.antecipa;
    const tGolpe = tl.lance ? tl.tGolpe : Infinity;
    // The wind-up's start, kept once it began: a late result may pull tl.tArma earlier, and that
    // must not jump the pose or cut the wind-up short.
    if (tl.tArmaFixo === undefined && t >= tl.tArma) tl.tArmaFixo = Math.max(tl.tArma, tl.tVisto ?? tl.tArma);
    tl.tVisto = t;

    // The run (and before it, a rock back on the spot to get going), then the paradinha.
    const r = corridaEm(pl, L * corrida(entre(t, tAnt, tl.tChute)));
    let c = r.corpo;
    const pes = r.pes;
    const pos = r.quadril;
    if (t < tAnt) {
      const m = Math.sin(Math.PI * suave(entre(t, tl.t0, tAnt)));
      pos.addScaledVector(u, -0.07 * esc * m);
      c = { ...c, inclina: -0.15 * m, baixa: 0.04 * m, bEx: 0.5 * m, bDx: 0.5 * m };
    }
    const fixo = (t - tl.t0) / lento; // ms since the kick began, for the idle sway
    if (t > tl.tChute) {
      const parado = { ...PARADINHA, rola: 0.04 * Math.sin((t - tl.tChute) / lento / 110) };
      c = mistura(c, parado, suave(entre(t, tl.tChute, tl.tChute + 260 * lento)));
    }
    // Facing along the run, turning to the goal over the last stride.
    let yaw = lerp(pl.yaw, Math.atan2(d.x, d.z), suave(entre(t, lerp(tAnt, tl.tChute, 0.55), tl.tChute + 120 * lento)));
    const tArma = tl.tArmaFixo ?? Infinity;
    const golpe0 = tGolpe - 50 * lento;
    const wArma = suave(entre(Math.min(t, golpe0), tArma, tArma + 200 * lento));
    let perna = null; // the kicking leg's own pose, over the IK one: {coxa, joelho, w}
    if (wArma > 0) {
      const armado = { ...ARMADO, inclina: ARMADO.inclina + Math.sin(fixo / 35) * 0.012 };
      c = mistura(c, armado, wArma);
      perna = { coxa: ARMADO.coxa, joelho: ARMADO.joelho, w: wArma };
    }
    let pulo = null;
    if (t >= golpe0) {
      // The strike, at full speed through the ball; the knee snaps straight a beat after the
      // thigh (the whip), just before the contact at tGolpe.
      const s = entre(t, golpe0, tGolpe + 70 * lento);
      const sj = suave(entre(t, golpe0 + 10 * lento, tGolpe + 25 * lento));
      c = mistura(c, GOLPE, s);
      perna = { coxa: lerp(ARMADO.coxa * wArma, GOLPE.coxa, s), joelho: lerp(ARMADO.joelho * wArma, GOLPE.joelho, sj), w: 1 };
      const f = entre(t, tGolpe + 70 * lento, tGolpe + 650 * lento);
      if (f > 0) {
        // Follow-through: the leg rises on past the ball, comes down a step ahead; the body
        // carries on with a skip on the standing foot.
        c = mistura(c, DEPOIS_CHUTE, saiRapido(f));
        c.escala = lerp(GOLPE.escala, 1, saiRapido(entre(f, 0, 0.35)));
        perna.coxa = f < 0.15 ? lerp(GOLPE.coxa, -1.6, saiRapido(f / 0.15)) : lerp(-1.6, -0.5, suave((f - 0.15) / 0.35));
        perna.joelho = lerp(GOLPE.joelho, 0.35, suave(entre(f, 0.1, 0.4)));
        perna.w = 1 - suave(entre(f, 0.3, 0.62));
        const ahead = pes.D.clone().addScaledVector(d, 0.55 * esc).addScaledVector(new THREE.Vector3(-d.z, 0, d.x), 0.2 * esc);
        ahead.y = 0.08 * esc * (1 - suave(entre(f, 0.3, 0.6)));
        pes.E = ahead;
        const hf = entre(f, 0.08, 0.42);
        pulo = ef * 0.06 * esc * Math.sin(Math.PI * hf);
        pes.D.addScaledVector(d, 0.22 * esc * suave(hf));
        pes.D.y = pulo;
        // landing the skip: a small squash
        c.escala -= ef * 0.03 * Math.sin(Math.PI * entre(f, 0.38, 0.6));
      }
    }
    if (calmo) c.escala = 1;

    pos.addScaledVector(d, c.avanca * esc);
    pos.y -= c.baixa * esc;
    if (pulo) pos.y += pulo;
    b.grupo.position.copy(pos);
    b.grupo.rotation.set(0, yaw, 0);
    p.corpo.rotation.set(c.inclina, 0, c.rola);
    p.corpo.scale.set(1 / Math.sqrt(c.escala), c.escala, 1 / Math.sqrt(c.escala));
    b.grupo.updateMatrixWorld(true);
    for (const lado of ["E", "D"]) {
      const ik = pisar(b, lado, pes[lado]);
      p[`perna${lado}`].rotation.x = ik.coxa;
      p[`joelho${lado}`].rotation.x = ik.joelho;
    }
    if (perna) {
      p.pernaE.rotation.x = lerp(p.pernaE.rotation.x, perna.coxa, perna.w);
      p.joelhoE.rotation.x = lerp(p.joelhoE.rotation.x, perna.joelho, perna.w);
    }
    p.bracoE.rotation.set(c.bEx, 0, c.bEz);
    p.bracoD.rotation.set(c.bDx, 0, c.bDz);
    p.cotoveloE.rotation.x = p.cotoveloD.rotation.x = c.cot;
    // The head stays on the ball through the strike; the hair bobs a beat behind the body.
    const olhaBola = t >= tGolpe ? 1 - suave(entre(t, tGolpe + 200 * lento, tGolpe + 600 * lento)) : 1;
    p.cabeca.rotation.x = 0.28 * wArma * olhaBola;
    if (ef) {
      const atras = corridaEm(pl, Math.max(0, L * corrida(entre(t - 45 * lento, tAnt, tl.tChute))));
      balancarCabelo(b, (atras.quadril.y - r.quadril.y) / esc);
    }
  }

  /** The hair lagging the head: `dy` (m) how far the body just went up (+) or down. */
  function balancarCabelo(j, dy) {
    const { calota, extra } = j.cabelo;
    const v = prender(dy * 6, -0.12, 0.12);
    calota.rotation.x = -v * 0.6;
    extra.rotation.x = -v * 1.6;
  }

  /** The keeper's ready stance with the split step: a hop as the kicker winds up, landing low. */
  function goleiroPronto(g, t, tl, H0) {
    const p = g.partes;
    const { lento } = tl;
    const ef = calmo ? 0 : 1;
    const tA = tl.tArmaFixo ?? tl.tArma;
    const sp = entre(t, tA - 60 * lento, tA + 150 * lento);
    const agacha = suave(entre(t, tA + 60 * lento, tA + 220 * lento));
    const rel = (t - tl.t0) / lento;
    const s = Math.sin(rel / 140) * (1 - agacha);
    prontoGoleiro(g, s);
    const estende = ef * Math.sin(Math.PI * sp);
    p.pernaE.rotation.x = p.pernaD.rotation.x = -0.35 - 0.2 * agacha + 0.2 * estende;
    p.joelhoE.rotation.x = p.joelhoD.rotation.x = 0.6 + 0.35 * agacha - 0.35 * estende;
    p.corpo.rotation.x = 0.15 + 0.12 * agacha;
    p.bracoE.rotation.z -= 0.15 * agacha;
    p.bracoD.rotation.z += 0.15 * agacha;
    g.grupo.position.copy(H0);
    g.grupo.position.y += -Math.abs(s) * 0.025 - 0.06 * agacha + 0.07 * estende;
    g.grupo.position.x += Math.sin(rel / 260) * 0.04 * (1 - agacha);
    return agacha;
  }

  function animarGoleiro(t, tl) {
    const g = goleiro;
    const p = g.partes;
    const { lento } = tl;
    const ef = calmo ? 0 : 1;
    const H0 = new THREE.Vector3(0, GOLEIRO_QUADRIL, 0.35);
    // The exit: a step off the line, from the local press or from the result.
    const tSaida = tl.saidaLocal ?? (tl.lance?.defesa?.saida ? tl.tGolpe - 220 * lento : null);
    const passo = tSaida != null ? suave(entre(t, tSaida, tSaida + 200 * lento)) * 0.6 : 0;
    H0.z += passo;
    const tG = tl.tGolpe;
    if (!tl.lance || t < tG - 40 * lento) {
      goleiroPronto(g, t, tl, H0);
      return;
    }
    // Start from the stance as it was when the dive began.
    const agacha = goleiroPronto(g, tG - 40 * lento, tl, H0);
    const H = g.grupo.position.clone();
    const T = tl.alvoGoleiro;
    const lado = tl.lance.defesa.lado;
    const sx = lado === "esquerda" ? -1 : lado === "direita" ? 1 : 0;
    // The load (a dip and a lean to the side), the flight to full stretch, the fall, the landing.
    const kc = suave(entre(t, tG - 40 * lento, tG + 70 * lento));
    // Full stretch as the ball gets there (never slower than a real dive), then the fall.
    const voa = prender(msDeVoo(tl.lance) * tl.voo.fim - 60, 380, 560) * lento;
    const kd = entre(t, tG + 40 * lento, tG + voa);
    const k = suave(kd);
    // Cartoon: a touch past the mark, then back; pushing off (kd^1.5), not shot from a cannon.
    const kb = ef ? voltaAtras(kd ** 1.5) : k;
    if (estado.papel === "goleiro") {
      estado.seguir = { k, T };
      posicionarCamera();
    }
    const pe = new THREE.Vector3(H.x, 0.35, H.z);
    const dir = T.clone().sub(pe);
    dir.z = 0;
    dir.y = Math.max(dir.y, 0.15); // never head-first into the grass
    dir.normalize();
    const fica = Math.abs(dir.x) < 0.35;
    const lider = sx === 0 ? 0 : Math.sign(dir.x); // the side he flies to, -1 = his right (E)
    const alto = prender((T.y - 0.7) / 1.2, 0, 1);
    const QA = T.clone().addScaledVector(dir, -1.15);
    QA.y = Math.max(0.42, QA.y);
    QA.z = T.z;
    const theta = Math.atan2(-dir.x, dir.y);
    // Then down to the grass (not when he just jumped in the middle), and the landing.
    const q = fica ? 0 : suave(entre(t, tG + voa + 100 * lento, tG + voa + 430 * lento));
    const pouso = entre(t, tG + voa + 410 * lento, tG + voa + 680 * lento);
    const virado = Math.atan2(estado.bolaEm.x, estado.bolaEm.z) * 0.6; // stance facing the ball
    const H1 = H.clone();
    H1.y -= 0.05 * kc;
    H1.x += lider * 0.08 * kc;
    // Up early for a high ball (the peak as the ball comes), sideways and down for a low one.
    const sobe = alto > 0.3 ? lerp(k, saiRapido(kd), 0.35) : k;
    const queda = -lider * 1.42; // lying on his side, facing the pitch
    g.grupo.rotation.set(0, virado * (1 - k), lerp(lerp(0, 0.15 * -lider, kc), theta, kb) * (1 - q) + q * queda);
    g.grupo.position.set(
      lerp(H1.x, QA.x, kb) + lider * 0.22 * q,
      lerp(H1.y, QA.y, sobe) * (1 - q) + 0.3 * q + ef * 0.035 * Math.sin(Math.PI * pouso) * (1 - fica),
      lerp(H1.z, QA.z, k),
    );
    if (fica) g.grupo.position.y -= suave(entre(t, tG + voa - 20 * lento, tG + voa + 330 * lento)) * (QA.y - H1.y);
    descansar(g);
    // Squash and stretch: long in the air, squashed against the grass as he lands (his body's
    // x is the vertical when lying on his side); a jump in the middle lands on his feet.
    let estica = 1 + ef * (fica ? 0.08 : 0.14) * Math.sin(Math.PI * kd);
    let achata = 1;
    if (fica) estica -= ef * 0.08 * Math.sin(Math.PI * entre(t, tG + voa + 290 * lento, tG + voa + 480 * lento));
    else achata = 1 - ef * 0.13 * Math.sin(Math.PI * Math.min(1, pouso * 2.2));
    p.corpo.scale.set(achata / Math.sqrt(estica), estica * (2 - achata) ** 0.5, 1 / Math.sqrt(estica));
    // Jumping in the middle, the stretched legs must not sink into the grass.
    if (fica) g.grupo.position.y += (estica - 1) * GOLEIRO_QUADRIL;

    // Arms: reaching for the ball from the first moment (they lead the body). The near arm goes
    // up the side, the far one across the face, both ending past the head towards the ball.
    const a = suave(entre(t, tG - 30 * lento, tG + 230 * lento));
    for (const [ombro, cot, fora] of [[p.bracoE, p.cotoveloE, -1], [p.bracoD, p.cotoveloD, 1]]) {
      let alvo;
      if (fica) alvo = alto > 0.35 ? { x: -0.25, z: fora * 2.75, c: -0.1 } : { x: -1.35, z: fora * 0.35, c: -0.3 };
      else if (fora === lider) alvo = { x: -0.25, z: fora * (Math.PI - 0.32), c: -0.04 };
      else alvo = { x: -2.75, z: lider * 0.28, c: -0.22 };
      ombro.rotation.set(lerp(-0.3, alvo.x, a), 0, lerp(fora * (0.9 + 0.15 * agacha), alvo.z, a));
      cot.rotation.x = lerp(-0.5, alvo.c, a);
    }
    // Legs: the near one pushed straight, the far one tucked (higher for a high ball); on a jump
    // in the middle both tuck; lying on the grass they relax.
    for (const [perna, joelho, fora] of [[p.pernaE, p.joelhoE, -1], [p.pernaD, p.joelhoD, 1]]) {
      let alvo;
      if (fica) alvo = { x: -0.45, z: fora * 0.15, j: 0.6 };
      else if (fora === lider) alvo = { x: 0.25, z: fora * 0.12, j: 0.08 };
      else alvo = { x: lerp(-0.2, -0.7, alto), z: fora * 0.05, j: lerp(0.55, 1.1, alto) };
      const solto = { x: 0.1, z: fora * 0.1, j: 0.35 };
      const x0 = -0.35 - 0.2 * agacha;
      const j0 = 0.6 + 0.35 * agacha;
      perna.rotation.set(lerp(lerp(x0, alvo.x, k), solto.x, q), 0, lerp(lerp(fora * 0.25, alvo.z, k), solto.z, q));
      joelho.rotation.x = lerp(lerp(j0, alvo.j, k), solto.j, q);
    }
    p.corpo.rotation.set((0.15 + 0.12 * agacha) * (1 - k), 0, 0);
    // The head keeps his eyes nearer level, a beat behind the dive (and the hair a beat more).
    const atras = (ef ? voltaAtras(entre(t - 60 * lento, tG + 40 * lento, tG + voa) ** 1.5) : k) - kb;
    p.cabeca.rotation.z = -0.3 * (theta * k * (1 - q) + q * queda) - (fica ? 0 : 0.5 * theta * atras);
    if (ef) {
      const { calota, extra } = g.cabelo;
      calota.rotation.z = -theta * atras * 0.5;
      extra.rotation.z = -theta * atras * 1.2;
    }
  }

  function animarBola(t, tl) {
    const { lento } = tl;
    if (!tl.lance || t < tl.tGolpe) {
      bola.position.copy(estado.bolaEm);
      bola.quaternion.identity();
      bola.scale.set(1, 1, 1);
      estouroChute.visible = estouroGol.visible = false;
      estado.tremor = 0;
      return;
    }
    const voo = tl.voo;
    const fimVoo = tl.tGolpe + msDeVoo(tl.lance) * voo.fim * tl.lento;
    // The flash at the strike: paper lines out of the ball, a blink long.
    const kf = entre(t, tl.tGolpe, tl.tGolpe + 170 * lento);
    estouroChute.visible = kf < 1;
    if (kf < 1) {
      estouroChute.position.copy(estado.bolaEm);
      estouroChute.quaternion.copy(camera.quaternion);
      estouroChute.scale.setScalar(0.22 + 0.3 * kf);
      estouroChute.material.opacity = 1 - kf * kf;
    }
    // The ball squashes on the boot for a moment, then flies stretched along its path, the
    // stretch easing as it slows; the flight itself still lands at fimVoo.
    const tSai = tl.tGolpe + Math.min(55 * lento, (fimVoo - tl.tGolpe) * 0.15);
    if (t < tSai) {
      bola.position.copy(estado.bolaEm);
      bola.position.y -= 0.035;
      bola.quaternion.identity();
      bola.scale.set(1.35, 0.68, 1.35);
    } else if (t <= fimVoo) {
      const k = entre(t, tSai, fimVoo);
      const u = k * voo.fim;
      bola.position.copy(voo.curva.getPoint(u));
      bola.quaternion.setFromUnitVectors(EIXO_Z, voo.curva.getTangent(u));
      const e = 1.08 + (tl.lance.chute?.cavadinha ? 0.2 : 0.5) * Math.exp(-4 * k);
      bola.scale.set(1 / Math.sqrt(e), 1 / Math.sqrt(e), e);
      bolaMalha.rotation.x -= 0.5;
      bolaMalha.rotation.y += (lance_curva(tl.lance) || 0.1) * 0.4;
    } else {
      const dt = (t - fimVoo) / 1000 / tl.lento;
      bola.quaternion.identity();
      bola.scale.set(1, 1, 1);
      bola.position.copy(bolaDepois(voo, tl.lance.resultado, dt));
      bolaMalha.rotation.x -= 0.2 * Math.exp(-dt);
      sacudirRede(voo, tl.lance.resultado, dt);
      if (tl.lance.resultado === "gol") {
        // The goal: lamp lines burst where the ball hits the net, and the picture shakes.
        const kg = entre(dt, 0.1, 0.65);
        estouroGol.visible = kg > 0 && kg < 1;
        if (estouroGol.visible) {
          const dentro = estado.papel === "goleiro"; // the camera is in the net: the burst at the line
          tl.pontoGol ??= dentro ? voo.chegada.clone() : bolaDepois(voo, "gol", 0.5);
          estouroGol.position.copy(tl.pontoGol);
          estouroGol.quaternion.copy(camera.quaternion);
          estouroGol.scale.setScalar((0.35 + 0.95 * saiRapido(kg)) * (dentro ? 0.55 : 1));
          estouroGol.material.opacity = 1 - kg * kg;
        }
        estado.tremor = dt > 0.1 && dt < 0.45 ? 0.1 * ((0.45 - dt) / 0.35) : 0;
      }
    }
    if (!tl.letreiro && t >= fimVoo + 80 * tl.lento) {
      tl.letreiro = true;
      letreiro(letreiroDoLance(tl.lance));
    }
  }
  const lance_curva = (lance) => lance?.chute?.curva ?? 0;

  function rodarCobranca({ chute_em, lance, lento = 1, replay = false }) {
    cobrancaAtual?.parar();
    posicionarJogadores();
    letreiro("");
    estado.seguir = null;
    posicionarCamera();
    const d = direcaoAoGol();
    const direita = new THREE.Vector3(-d.z, 0, d.x);
    const tl = {
      t0: performance.now(),
      // A late start (or clock skew) still gets a short run-up, never a kick from 2 m away.
      tChute: Math.max(chute_em, performance.now() + 600 * lento),
      tGolpe: Infinity,
      // The cartoon anticipation before the run, and the wind-up held at the ball until the
      // result arrives (the window closes at chute_em + JANELA).
      antecipa: 0,
      tArma: Infinity,
      lance: null,
      lento,
      d,
      inicio: batedor.grupo.position.clone(),
      // the hip at the plant: the kicking (right) foot meets the ball, the other beside it
      plantio: estado.bolaEm.clone().addScaledVector(d, -0.14).addScaledVector(direita, -0.1),
      saidaLocal: null,
      letreiro: false,
    };
    tl.antecipa = Math.min(320 * lento, (tl.tChute - tl.t0) * 0.3);
    tl.tArma = Math.max(tl.tChute, chute_em + (JANELA - 230) * lento);
    let parado = false;
    let resolver;
    const pronto = new Promise((r) => (resolver = r));
    let relogio = null;
    const fechar = () => {
      if (parado) return;
      aplicar(tl.fim + 1); // land the final frame even if rAF never ran
      parar();
      resolver();
    };
    const aplicar = (t) => {
      animarBatedor(t, tl);
      animarGoleiro(t, tl);
      animarBola(t, tl);
    };
    function parar() {
      parado = true;
      clearTimeout(relogio);
      for (const f of soltar) f();
      if (estado.animacao === aplicar) estado.animacao = aplicarFinal;
      if (cobrancaAtual === controle) cobrancaAtual = null;
    }
    const aplicarFinal = () => {}; // the scene keeps the last frame until the next kick
    const receber = (l) => {
      if (parado) return;
      // Plan everything first: a malformed lance must not leave a half-set timeline.
      const voo = planejarVoo(l);
      const alvoGoleiro = alvoDoGoleiro(l, voo);
      tl.voo = voo;
      tl.alvoGoleiro = alvoGoleiro;
      tl.lance = l;
      // A result that comes late still gets the whole swing (50 ms) before the ball goes.
      tl.tGolpe = Math.max(chute_em + JANELA * lento, tl.tChute, performance.now() + 50 * lento);
      // A late result never brings the wind-up into the run, at most its last steps.
      tl.tArma = Math.max(tl.t0 + tl.antecipa, tl.tChute - 120 * lento, Math.min(tl.tArma, tl.tGolpe - 230 * lento));
      tl.fim = tl.tGolpe + (msDeVoo(l) * tl.voo.fim + DEPOIS) * lento;
      ultimo = { lance: l, modo: estado.modo, falta: estado.falta ? { ...estado.falta } : null };
      relogio = setTimeout(fechar, tl.fim - performance.now() + 20);
    };
    // The keeper's exit: space, Enter or a tap on the scene, once, from the run-up to the end
    // of the flight.
    const soltar = [];
    if (!replay && estado.papel === "goleiro") {
      const sair = (ev) => {
        if (ev.type === "keydown") {
          if (!["Space", "Enter", "NumpadEnter"].includes(ev.code)) return;
          ev.preventDefault(); // a focused button must not fire, nor fullscreen close
          if (ev.repeat) return;
        }
        const agora = performance.now();
        const fimVoo = tl.lance ? tl.tGolpe + msDeVoo(tl.lance) * tl.voo.fim : Infinity;
        if (tl.saidaLocal != null || agora > fimVoo) return;
        ev.preventDefault?.();
        tl.saidaLocal = agora;
        for (const cb of ouvintesSaida) cb({ ms: Math.round(agora - chute_em) });
      };
      window.addEventListener("keydown", sair);
      canvas.addEventListener("pointerdown", sair);
      soltar.push(() => window.removeEventListener("keydown", sair), () => canvas.removeEventListener("pointerdown", sair));
    }
    estado.animacao = aplicar;
    const controle = { parar: () => (parar(), resolver()) };
    cobrancaAtual = controle;
    // A lost lance (connection closed, W.O.) or a malformed one ends the kick where it is.
    Promise.resolve(lance)
      .then(receber)
      .catch((erro) => {
        console.error("mano: cobrança sem lance", erro);
        controle.parar();
      });
    return pronto;
  }

  /**
   * Run a kick: run-up until `chute_em` (performance.now() clock), strike when `lance` is
   * known (an object, or a Promise of one, as the server sends it at window close).
   * lance: {chute, defesa: {lado, saida}, barreira, onde: [x, y], resultado}.
   */
  function cobrar({ chute_em, lance }) {
    return rodarCobranca({ chute_em, lance });
  }

  /** The last kick again, slower, on the current camera. */
  function replay() {
    if (!ultimo) return Promise.resolve();
    estado.modo = ultimo.modo;
    estado.falta = ultimo.modo === "faltas" && ultimo.falta ? { ...ultimo.falta } : null;
    arrumar();
    const lento = 1.8;
    return rodarCobranca({ chute_em: performance.now() + 700 * lento, lance: ultimo.lance, lento, replay: true });
  }

  /** Back to the set position, sign and controls cleared. */
  function reiniciar() {
    pedidoAtual?.();
    cobrancaAtual?.parar();
    acabarFesta();
    estado.animacao = null;
    letreiro("");
    arrumar();
  }

  arrumar();
  ajustar();
  requestAnimationFrame(quadro);

  /** Dress the two players: {batedor: {time, uniforme, visual}, goleiro: {...}}. `visual` is
   * the look from mano-visual.js (skin, hair, number...), the same in both browsers; an unknown
   * team keeps the scene's own neutral kits. */
  let vestidos = "";
  function vestir({ batedor: b = null, goleiro: g = null } = {}) {
    const chave = JSON.stringify([b, g]);
    if (chave === vestidos) return;
    vestidos = chave;
    for (const [j, dados, papelDele] of [[batedor, b, "batedor"], [goleiro, g, "goleiro"]]) {
      const v = dados?.visual ?? null;
      aplicarVisual(j, v);
      const kit = uniforme(dados ?? {}, papelDele);
      if (kit) vestirJogador(j, kit, v?.numero ?? (papelDele === "goleiro" ? 1 : null));
    }
    // A new look can change the kicker's height: his feet back on the grass (the keeper's
    // height is his stance's, set by posicionarJogadores and his animation).
    if (!cobrancaAtual) batedor.grupo.position.y = batedor.quadril;
  }

  /**
   * The match is over: the winners lift the cup (mano-festa.js) and the board reads "<TEAM>
   * CAMPEÃO". {time, uniforme, nome, semente: "room:match", goleiro: the keeper's look seed}.
   * Holds at the end; reiniciar() (the rematch) clears it.
   */
  function festejar(dados) {
    pedidoAtual?.();
    cobrancaAtual?.parar();
    dica("");
    barraEl.hidden = true;
    estado.tremor = 0;
    for (const o of [batedor.grupo, goleiro.grupo, bola, barreiraGrupo, estouroChute, estouroGol, mira, previa]) o.visible = false;
    festa.comecar(dados);
    estado.animacao = festa.aplicar;
    el.classList.add("mn-festa"); // the board's line goes down, under the cup
    letreiro(tituloCampeao(dados.nome));
  }
  function acabarFesta() {
    if (!festa.ativa) return;
    festa.parar();
    el.classList.remove("mn-festa");
    for (const o of [batedor.grupo, goleiro.grupo, bola, barreiraGrupo]) o.visible = true;
  }

  const api = {
    vestir,
    festejar,
    get papel() {
      return estado.papel;
    },
    get modo() {
      return estado.modo;
    },
    trocarPapel(novo) {
      estado.papel = novo;
      el.dataset.papel = novo;
      posicionarCamera();
    },
    trocarModo(novo) {
      estado.modo = novo;
      if (novo === "penaltis") estado.falta = null;
      arrumar();
    },
    /** Place a free kick: `nome` from POSICOES, barrier `{n, x}` (contract) or null. */
    posicionarFalta({ nome = "meia_lua", barreira = null } = {}) {
      const p = POSICOES[nome] ?? POSICOES.meia_lua;
      estado.modo = "faltas";
      estado.falta = { nome, x: p.x, z: p.z, barreira };
      arrumar();
    },
    pedirChute,
    pedirDefesa,
    pedirBarreira,
    cobrar,
    replay,
    reiniciar,
    placar,
    letreiro,
    /** A line of lamps under the board (waiting for the other, whose turn it is); "" clears. */
    dica,
    /** cb({ms}) once per kick when the keeper presses space / taps, ms from chute_em. */
    onSaida(cb) {
      ouvintesSaida.add(cb);
      return () => ouvintesSaida.delete(cb);
    },
    destruir() {
      pedidoAtual?.();
      cobrancaAtual?.parar();
      festa.parar();
      if (emTelaCheia()) document.exitFullscreen().catch(() => {});
      cena.traverse((o) => {
        o.geometry?.dispose();
        for (const m of [].concat(o.material ?? [])) {
          m.map?.dispose();
          m.dispose();
        }
      });
      renderer.forceContextLoss();
      estado.destruida = true;
      observador.disconnect();
      document.removeEventListener("fullscreenchange", aoTelaCheia);
      renderer.dispose();
      el.innerHTML = "";
    },
    // internals for the later slices of this file
    _interno: { mira, previa, celulas, THREE, el, hud, cena, camera, renderer, estado, batedor, goleiro, bola, rede, barreiraHomens, montarBarreira, posicionarJogadores, posicionarCamera, arrumar },
  };
  el.dataset.papel = papel;
  return api;
}
