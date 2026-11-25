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
  // The Geral itself: a packed standing line right behind the moat.
  // Lamp rigs on the roof edge: grids of yellow bulbs, as the old board.
  const lampada = basico(COR.lamp);
  const placa = basico(0x16150f);
  for (const ang of [0.35, 1.2, 1.95, 2.8, 3.5, 4.3, 5.1, 5.9]) {
    const rr = R0 + r - 3;
    const rig = new THREE.Group();
    rig.add(caixa(7.6, 3.2, 0.3, placa, 0, 0, 0.2));
    for (let i = 0; i < 8; i++) for (let j = 0; j < 3; j++) rig.add(caixa(0.6, 0.6, 0.2, lampada, -3.15 + i * 0.9, -0.9 + j * 0.9, 0));
    rig.position.set(cx + Math.cos(ang) * rr, topo + 6.5, cz + Math.sin(ang) * rr * 1.42);
    rig.lookAt(0, 0, 52.5);
    g.add(rig);
  }
  // A dull old scoreboard frame behind the goal, unlit (the live one is the HTML board).
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
  const bola = new THREE.Mesh(new THREE.IcosahedronGeometry(0.11, 1), lambert(COR.giz));
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

  function montarBarreira() {
    barreiraGrupo.clear();
    const b = estado.falta?.barreira;
    if (!b) return;
    const homens = barreiraHomens(b);
    for (const p of homens) {
      const j = montarJogador({ camisa: COR.concretoLt, calcao: COR.tinta, meia: COR.concretoLt });
      pose(j, { bracos: 0 });
      j.partes.bracoE.rotation.set(-0.3, 0, 0.32);
      j.partes.bracoD.rotation.set(-0.3, 0, -0.32);
      j.grupo.position.set(p.x, 0.95, p.z);
      j.grupo.rotation.y = Math.atan2(estado.bolaEm.x - p.x, estado.bolaEm.z - p.z);
      barreiraGrupo.add(j.grupo);
    }
  }

  /** Where the n men stand: the contract span x ± n·55 seen from the ball, 9.15 m out. */
  function barreiraHomens({ n, x }) {
    const meio = n * 55;
    const c = prender(x, meio - 120, 1120 - meio);
    const bola0 = estado.bolaEm;
    const naLinha = (cx) => {
      const alvo = golParaMundo(cx, 0);
      const d = new THREE.Vector3(alvo.x - bola0.x, 0, alvo.z - bola0.z).normalize();
      return new THREE.Vector3(bola0.x + d.x * DIST_BARREIRA, 0, bola0.z + d.z * DIST_BARREIRA);
    };
    const a = naLinha(c - meio + 55);
    const b = naLinha(c + meio - 55);
    return Array.from({ length: n }, (_, i) => (n === 1 ? a : a.clone().lerp(b, i / (n - 1))));
  }

  function posicionarJogadores() {
    const d = direcaoAoGol();
    const bx = estado.bolaEm.x;
    const bz = estado.bolaEm.z;
    bola.position.copy(estado.bolaEm);
    bola.rotation.set(0, 0, 0);
    // Kicker 2.3 m behind the ball and a little to the left, facing the goal.
    const lado = new THREE.Vector3(-d.z, 0, d.x); // kicker's left on the ground
    batedor.grupo.position.set(bx - d.x * 2.2 - lado.x * 1.1, 0.95, bz - d.z * 2.2 - lado.z * 1.1);
    batedor.grupo.rotation.set(0, Math.atan2(d.x, d.z), 0);
    pose(batedor);
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
      camera.position.set(bz.x - d.x * 7, 2.7, bz.z - d.z * 7);
      camera.lookAt(bz.x * 0.15, 0.3, 0);
    } else {
      // Inside the goal, back to the net, under the crossbar: the kicker at the spot.
      camera.position.set(0, 2.3, -1.9);
      camera.lookAt(bz.x * 0.9, 0.1, bz.z);
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

  function quadro(t) {
    if (estado.destruida) return;
    if (estado.animacao) estado.animacao(t);
    renderer.render(cena, camera);
    requestAnimationFrame(quadro);
  }

  function arrumar() {
    if (estado.modo === "faltas" && estado.falta) {
      estado.bolaEm.set(estado.falta.x, 0.11, estado.falta.z);
    } else {
      estado.bolaEm.set(0, 0.11, MARCA_PENALTI);
    }
    posicionarJogadores();
    montarBarreira();
    posicionarCamera();
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
    destruir() {
      estado.destruida = true;
      observador.disconnect();
      document.removeEventListener("fullscreenchange", aoTelaCheia);
      renderer.dispose();
      el.innerHTML = "";
    },
    // internals for the later slices of this file
    _interno: { THREE, el, hud, cena, camera, renderer, estado, batedor, goleiro, bola, rede, barreiraHomens, montarBarreira, posicionarJogadores, posicionarCamera, arrumar },
  };
  el.dataset.papel = papel;
  return api;
}
