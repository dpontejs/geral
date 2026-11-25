// Mano a Mano: the penalty / free-kick scene in Three.js (vendored, pinned 0.187.0).
// Flat-shaded low-poly in the Geral palette: lamps on black, concrete, paper, grass.
// The scoreboard and the buttons are HTML over the canvas, never 3D text.
//
// World: metres. Goal line on z = 0, the mouth from x = -3.66 to 3.66, crossbar at 2.44;
// the pitch runs towards +z. Contract coordinates (0-1000) are the goal as the kicker sees
// it: x = 0 is the kicker's left (world -x), y = 0 the ground, y = 1000 the crossbar.
import * as THREE from "../vendor/three/three.module.js";

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
export function caminho(origem, destino, { trajetoria = null, curva = 0 } = {}) {
  const meio = origem.clone().lerp(destino, 0.5);
  const chao = new THREE.Vector3(destino.x - origem.x, 0, destino.z - origem.z).normalize();
  const direita = new THREE.Vector3(-chao.z, 0, chao.x); // kicker's right, facing the goal
  const c = meio.clone();
  const pico = (h) => 2 * h - (origem.y + destino.y) / 2; // control y for a peak near h
  if (!trajetoria) {
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

function montarGramado(cena) {
  const g = new THREE.Group();
  const listras = [lambert(COR.gramado), lambert(COR.gramado2)];
  for (let i = 0, z = -8; z < 113; i++, z += 5.25) {
    const faixa = new THREE.Mesh(new THREE.PlaneGeometry(84, 5.25), listras[i % 2]);
    faixa.rotation.x = -Math.PI / 2;
    faixa.position.set(0, 0, z + 2.625);
    g.add(faixa);
  }
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
  cena.add(g);
  return { rede: fundo };
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
    povo.setColorAt(k, cor.setHex(cores[Math.floor(Math.random() * cores.length)]));
    k++;
  }
  g.add(povo);
  // Lamp rigs on the roof edge: grids of yellow bulbs, as the old board.
  // One instanced mesh for every bulb keeps the draw calls down on phones.
  const angulos = [0.35, 1.2, 1.95, 2.8, 3.5, 4.3, 5.1, 5.9];
  const bulbos = new THREE.InstancedMesh(new THREE.BoxGeometry(0.6, 0.6, 0.2), basico(COR.lamp), angulos.length * 24);
  const placa = basico(0x16150f);
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
  }
  g.add(bulbos);
  cena.add(g);
}

// ---------------------------------------------------------------------------------------
// Players: blocky, faceless, as a table-football figure carved in concrete. The group's
// origin is the hip, so a dive is a translation plus a roll around the hip.

function montarJogador({ camisa, calcao, meia, luvas = null, cabelo = COR.tinta }) {
  const grupo = new THREE.Group();
  const corpo = new THREE.Group(); // everything hangs from the hip (y = 0 here)
  grupo.add(corpo);
  const mc = lambert(camisa);
  const pele = lambert(COR.pele);
  const tronco = caixa(0.46, 0.62, 0.26, mc, 0, 0.4, 0);
  corpo.add(tronco);
  corpo.add(caixa(0.44, 0.2, 0.27, lambert(calcao), 0, 0.03, 0));
  const cabeca = new THREE.Mesh(new THREE.IcosahedronGeometry(0.135, 0), pele);
  cabeca.position.set(0, 0.86, 0);
  corpo.add(cabeca);
  const topo = new THREE.Mesh(new THREE.IcosahedronGeometry(0.14, 0), lambert(cabelo));
  topo.scale.set(1, 0.55, 1);
  topo.position.set(0, 0.93, -0.02);
  corpo.add(topo);
  const perna = (x) => {
    const p = new THREE.Group();
    p.position.set(x, -0.05, 0);
    p.add(caixa(0.17, 0.42, 0.18, lambert(calcao === camisa ? meia : COR.pele), 0, -0.2, 0));
    p.add(caixa(0.16, 0.44, 0.17, lambert(meia), 0, -0.62, 0));
    p.add(caixa(0.17, 0.09, 0.28, lambert(COR.tinta), 0, -0.9, 0.05));
    corpo.add(p);
    return p;
  };
  const braco = (x) => {
    const b = new THREE.Group();
    b.position.set(x, 0.66, 0);
    b.add(caixa(0.13, 0.3, 0.14, mc, 0, -0.14, 0));
    b.add(caixa(0.11, 0.3, 0.12, luvas ? mc : pele, 0, -0.43, 0));
    if (luvas) b.add(caixa(0.16, 0.17, 0.12, lambert(luvas), 0, -0.64, 0));
    corpo.add(b);
    return b;
  };
  const partes = {
    corpo,
    tronco,
    cabeca,
    pernaE: perna(-0.12),
    pernaD: perna(0.12),
    bracoE: braco(-0.31),
    bracoD: braco(0.31),
  };
  grupo.position.y = 0.95;
  return { grupo, partes };
}

function pose(j, { pernas = 0, bracos = 0, abrir = 0 } = {}) {
  const p = j.partes;
  p.pernaE.rotation.x = pernas;
  p.pernaD.rotation.x = -pernas;
  p.bracoE.rotation.x = -bracos;
  p.bracoD.rotation.x = bracos;
  p.bracoE.rotation.z = -abrir;
  p.bracoD.rotation.z = abrir;
}

// ---------------------------------------------------------------------------------------

/**
 * Build the scene inside `el`.
 * @param {HTMLElement} el
 * @param {{papel: "batedor"|"goleiro", modo: "penaltis"|"faltas"}} opcoes
 */
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
  const cena = new THREE.Scene();
  cena.background = new THREE.Color(COR.board);
  cena.fog = new THREE.Fog(COR.board, 45, 170);
  cena.add(new THREE.HemisphereLight(0xfff1d0, 0x1a2a1f, 1.5));
  const sol = new THREE.DirectionalLight(0xffe6b0, 1.7);
  sol.position.set(-30, 60, 40);
  cena.add(sol);
  const contra = new THREE.DirectionalLight(0xfff3dc, 0.6);
  contra.position.set(40, 50, -60);
  cena.add(contra);

  montarGramado(cena);
  const { rede } = montarGol(cena);
  montarEstadio(cena);

  const batedor = montarJogador({ camisa: COR.papel, calcao: COR.tinta, meia: COR.papel });
  const goleiro = montarJogador({ camisa: COR.tintaSoft, calcao: COR.tinta, meia: COR.tinta, luvas: COR.papel, cabelo: COR.tinta });
  cena.add(batedor.grupo, goleiro.grupo);
  const bola = new THREE.Mesh(new THREE.IcosahedronGeometry(0.13, 1), lambert(COR.giz));
  cena.add(bola);
  const barreiraGrupo = new THREE.Group();
  cena.add(barreiraGrupo);

  const camera = new THREE.PerspectiveCamera(40, 16 / 9, 0.1, 400);

  const estado = {
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
  const homens = Array.from({ length: 5 }, () => {
    const j = montarJogador({ camisa: COR.concretoLt, calcao: COR.tinta, meia: COR.concretoLt });
    j.partes.bracoE.rotation.set(-0.3, 0, 0.32);
    j.partes.bracoD.rotation.set(-0.3, 0, -0.32);
    barreiraGrupo.add(j.grupo);
    return j;
  });

  function montarBarreira() {
    const b = estado.falta?.barreira;
    const lugares = b ? barreiraHomens(b) : [];
    homens.forEach((j, i) => {
      const p = lugares[i];
      j.grupo.visible = Boolean(p);
      if (!p) return;
      j.grupo.position.set(p.x, 0.95, p.z);
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
    bola.rotation.set(0, 0, 0);
    // Kicker 2.2 m behind the ball and a little to his left, facing the goal.
    const direita = new THREE.Vector3(-d.z, 0, d.x); // kicker's right on the ground
    batedor.grupo.position.set(bx - d.x * 2.2 - direita.x * 1.1, 0.95, bz - d.z * 2.2 - direita.z * 1.1);
    batedor.grupo.rotation.set(0, Math.atan2(d.x, d.z), 0);
    batedor.partes.corpo.rotation.set(0, 0, 0);
    pose(batedor);
    goleiro.grupo.rotation.set(0, 0, 0);
    goleiro.partes.bracoE.rotation.set(0, 0, 0);
    goleiro.partes.bracoD.rotation.set(0, 0, 0);
    rede.geometry.attributes.position.array.set(rede.userData.base);
    rede.geometry.attributes.position.needsUpdate = true;
    goleiro.grupo.position.set(0, 0.88, 0.35);
    goleiro.grupo.rotation.set(0, Math.atan2(bx, bz) * 0.6, 0);
    goleiro.partes.corpo.rotation.set(0.12, 0, 0);
    pose(goleiro, { pernas: 0.0, bracos: 0.35, abrir: 0.45 });
    goleiro.partes.pernaE.rotation.z = -0.12;
    goleiro.partes.pernaD.rotation.z = 0.12;
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
      renderer.render(cena, camera);
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
   * Resolves {alvo: [x, y], barra, trajetoria?, curva?}; at 10 s, whatever is missing is random.
   */
  function pedirChute({ falta = estado.modo === "faltas", faixa = faixaBoa, segundos = 10 } = {}) {
    return comecarPedido(({ terminar, aoFim, ouvir }) => {
      const escolha = falta ? { trajetoria: null, curva: 0 } : {};
      let alvo = null;
      let mirado = false; // only a real aim counts; an untouched one is random at the deadline
      let travado = false;
      let barraLigada = false;
      let barraInicio = 0;
      let barraValor = 500;
      const fechar = () =>
        terminar({
          alvo: alvo && mirado ? alvo.map(Math.round) : [Math.round(acaso(0, 1000)), Math.round(acaso(0, 1000))],
          barra: Math.round(barraLigada ? barraValor : acaso(0, 1000)),
          ...(falta ? { trajetoria: escolha.trajetoria ?? sortear(["rasteira", "por_cima", "pelo_lado"]), curva: Math.round(escolha.curva * 100) / 100 } : {}),
        });
      aoFim(contar(segundos, fechar));

      const mirar = () => {
        acoesEl.innerHTML = "";
        dica("Mire no gol e clique");
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
        dica("Pare a barra na faixa acesa");
        const [lo, hi] = faixa(alvo);
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
          const fase = ((performance.now() - barraInicio) / 1300) % 1;
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
  /** nomes: [a, b]; series: [[...], [...]] with "g" (goal) | "e" (missed); gols: [ga, gb]. */
  function placar({ nomes = ["", ""], series = [[], []], gols = null } = {}) {
    const vagas = Math.max(5, series[0].length, series[1].length);
    const conta = gols ?? series.map((s) => s.filter((v) => v === "g").length);
    seriesEl.innerHTML = [0, 1]
      .map((i) => {
        const bolas = Array.from({ length: vagas }, (_, k) => {
          const v = series[i][k];
          return v === "g" ? '<b class="mn-g">●</b>' : v === "e" ? '<b class="mn-e">✕</b>' : '<b class="mn-a">○</b>';
        }).join("");
        return `<div class="mn-fila"><span class="mn-quem lamp">${escapar(nomes[i])}</span><span class="mn-bolas lamp">${bolas}</span><span class="mn-gols lamp">${conta[i]}</span></div>`;
      })
      .join("");
  }
  const escapar = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  const LETREIROS = { gol: "GOOOL", defesa: "DEFENDEU", trave: "NA TRAVE", fora: "PRA FORA", barreira: "NA BARREIRA" };
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
  const VOO = { penaltis: 600, faltas: 800 };
  const DEPOIS = 1700;
  const ouvintesSaida = new Set();
  let ultimo = null; // {lance, modo, falta} of the last kick, for the replay
  let cobrancaAtual = null;

  const lerp = (a, b, k) => a + (b - a) * k;
  const suave = (k) => (k <= 0 ? 0 : k >= 1 ? 1 : k * k * (3 - 2 * k));
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
    const escolha = falta ? { trajetoria: lance.chute.trajetoria ?? "por_cima", curva: lance.chute.curva ?? 0 } : {};
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
    const velocidade = (curva.getLength() * fim) / (VOO[estado.modo] / 1000);
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

  function animarGoleiro(t, tl) {
    const g = goleiro;
    const { lento } = tl;
    const H0 = new THREE.Vector3(0, 0.88, 0.35);
    // The exit: a step off the line, from the local press or from the result.
    const tSaida = tl.saidaLocal ?? (tl.lance?.defesa?.saida ? tl.tGolpe - 220 * lento : null);
    const passo = tSaida != null ? suave(entre(t, tSaida, tSaida + 200 * lento)) * 0.6 : 0;
    H0.z += passo;
    if (!tl.lance || t < tl.tGolpe - 40 * lento) {
      // Ready stance, rocking on his toes.
      g.grupo.position.copy(H0);
      g.grupo.position.y += Math.sin(t / 140) * 0.015;
      return;
    }
    const T = tl.alvoGoleiro;
    const k = suave(entre(t, tl.tGolpe - 40 * lento, tl.tGolpe + 380 * lento));
    if (estado.papel === "goleiro") {
      estado.seguir = { k, T };
      posicionarCamera();
    }
    const pe = new THREE.Vector3(H0.x, 0.35, H0.z);
    const dir = T.clone().sub(pe);
    dir.z = 0;
    dir.y = Math.max(dir.y, 0.3); // never head-first into the grass
    dir.normalize();
    const quadrilAlvo = T.clone().addScaledVector(dir, -1.15);
    quadrilAlvo.y = Math.max(0.55, quadrilAlvo.y);
    quadrilAlvo.z = T.z;
    const fica = Math.abs(dir.x) < 0.35;
    const theta = Math.atan2(-dir.x, dir.y) * 1.0;
    // Then down to the grass (not when he just jumped in the middle).
    const q = fica ? 0 : suave(entre(t, tl.tGolpe + 420 * lento, tl.tGolpe + 900 * lento));
    const virado = Math.atan2(estado.bolaEm.x, estado.bolaEm.z) * 0.6; // stance facing the ball
    g.grupo.rotation.set(0, virado * (1 - k), lerp(0, theta, k) + q * (Math.sign(theta) * Math.PI) / 2 * 0.25);
    g.grupo.position.set(lerp(H0.x, quadrilAlvo.x, k), lerp(H0.y, quadrilAlvo.y, k) * (1 - q) + 0.32 * q, lerp(H0.z, quadrilAlvo.z, k));
    if (fica) g.grupo.position.y -= suave(entre(t, tl.tGolpe + 450 * lento, tl.tGolpe + 800 * lento)) * (quadrilAlvo.y - H0.y);
    const braco = -Math.PI * 0.95 * k;
    g.partes.bracoE.rotation.set(braco, 0, lerp(-0.45, 0.1, k));
    g.partes.bracoD.rotation.set(braco, 0, lerp(0.45, -0.1, k));
    g.partes.pernaE.rotation.set(0.35 * k, 0, -0.12 - 0.25 * k);
    g.partes.pernaD.rotation.set(-0.2 * k, 0, 0.12 + 0.15 * k);
    g.partes.corpo.rotation.set(0.12 * (1 - k), 0, 0);
  }

  function animarBatedor(t, tl) {
    const b = batedor;
    const { lento, inicio, plantio } = tl;
    const u = suave(entre(t, tl.t0, tl.tChute)) * 0.7 + entre(t, tl.t0, tl.tChute) * 0.3;
    const pos = inicio.clone().lerp(plantio, u);
    const correndo = t < tl.tChute;
    const passada = correndo ? Math.sin(u * Math.PI * 7) : 0;
    b.partes.pernaE.rotation.x = passada * 0.7;
    b.partes.pernaD.rotation.x = -passada * 0.7;
    b.partes.bracoE.rotation.x = -passada * 0.6;
    b.partes.bracoD.rotation.x = passada * 0.6;
    b.partes.corpo.rotation.x = correndo ? 0.18 : 0.08;
    // The strike: his right leg through the ball, the body following.
    const tGolpe = tl.lance ? tl.tGolpe : Infinity;
    const kg = entre(t, tGolpe - 160 * lento, tGolpe + 260 * lento);
    if (kg > 0) {
      const balanco = kg < 0.38 ? lerp(0, 0.9, kg / 0.38) : lerp(0.9, -1.5, suave((kg - 0.38) / 0.62));
      b.partes.pernaE.rotation.x = balanco;
      b.partes.pernaD.rotation.x = 0.1;
      b.partes.bracoE.rotation.set(0, 0, -0.6 * Math.sin(Math.PI * kg));
      b.partes.bracoD.rotation.set(-0.5 * Math.sin(Math.PI * kg), 0, 0.7 * Math.sin(Math.PI * kg));
      b.partes.corpo.rotation.x = -0.15 * Math.sin(Math.PI * kg);
      pos.addScaledVector(tl.d, 0.3 * suave(kg));
    } else if (!correndo) {
      // Paradinha: weight shifting by the ball.
      b.partes.corpo.rotation.z = Math.sin((t - tl.tChute) / 110) * 0.05;
    }
    pos.y = 0.95 + (correndo ? Math.abs(Math.sin(u * Math.PI * 7)) * 0.05 : 0);
    b.grupo.position.copy(pos);
  }

  function animarBola(t, tl) {
    if (!tl.lance || t < tl.tGolpe) {
      bola.position.copy(estado.bolaEm);
      return;
    }
    const voo = tl.voo;
    const fimVoo = tl.tGolpe + VOO[estado.modo] * voo.fim * tl.lento;
    if (t <= fimVoo) {
      const u = entre(t, tl.tGolpe, fimVoo) * voo.fim;
      bola.position.copy(voo.curva.getPoint(u));
      bola.rotation.x -= 0.5;
      bola.rotation.y += (lance_curva(tl.lance) || 0.1) * 0.4;
    } else {
      const dt = (t - fimVoo) / 1000 / tl.lento;
      bola.position.copy(bolaDepois(voo, tl.lance.resultado, dt));
      bola.rotation.x -= 0.2 * Math.exp(-dt);
      sacudirRede(voo, tl.lance.resultado, dt);
    }
    if (!tl.letreiro && t >= fimVoo + 80 * tl.lento) {
      tl.letreiro = true;
      letreiro(LETREIROS[tl.lance.resultado] ?? "");
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
      lance: null,
      lento,
      d,
      inicio: batedor.grupo.position.clone(),
      plantio: estado.bolaEm.clone().addScaledVector(d, -0.5).addScaledVector(direita, -0.45),
      saidaLocal: null,
      letreiro: false,
    };
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
      tl.tGolpe = Math.max(chute_em + JANELA * lento, tl.tChute, performance.now());
      tl.fim = tl.tGolpe + (VOO[estado.modo] * tl.voo.fim + DEPOIS) * lento;
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
        const fimVoo = tl.lance ? tl.tGolpe + VOO[estado.modo] * tl.voo.fim : Infinity;
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
    estado.animacao = null;
    letreiro("");
    arrumar();
  }

  arrumar();
  ajustar();
  requestAnimationFrame(quadro);

  const api = {
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
      if (emTelaCheia()) document.exitFullscreen().catch(() => {});
      cena.traverse((o) => {
        o.geometry?.dispose();
        for (const m of [].concat(o.material ?? [])) m.dispose();
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
