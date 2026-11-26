// Mano a Mano: the winners lift the cup when the match ends (dev, 2026-11-26). The winner's
// kicker and a few teammates in the team's kit, their keeper (the 1), gathered by the penalty
// spot; one lifts a plain low-poly cup (lamp yellow, no real competition's), the others jump with
// their arms up, lamp-yellow confetti falls and the camera slowly goes round them. Both browsers
// show the same men: the looks come from mano-visual.js, seeded by the room and the match.
//
// The timing and the placement are pure (node tests them); the meshes are built with the THREE
// that mano-cena.js passes in, so this module imports nothing heavy.

import { visual } from "./mano-visual.js";

/** How long the celebration plays (ms); then it holds its last pose. */
export const FESTA_MS = 7000;

/** The board's line: "<TEAM> CAMPEÃO" (the nickname when there is no team). */
export function tituloCampeao(nome) {
  const n = String(nome ?? "").trim();
  return n ? `${n.toLocaleUpperCase("pt-BR")} CAMPEÃO` : "CAMPEÃO";
}

// Where each one stands, around the spot (x, z in metres; the goal line is z = 0, the spot 11),
// facing the camera (+z). The lifter in front, the keeper behind him.
const LUGARES = [
  [0, 10.3],
  [-1.05, 10.0],
  [1.05, 10.05],
  [-0.55, 9.2],
  [0.6, 9.15],
];

/**
 * The squad: [{papel, visual, x, z, fase}] - the lifter first (the winner's kicker), then the
 * teammates, then the keeper (fixed look, number 1: the same `goleiro` seed as in the match).
 * `semente` is "room:match"; `goleiro` the keeper's seed.
 */
export function elenco(semente, goleiro) {
  const lista = [0, 1, 2, 3].map((i) => ({ papel: "batedor", visual: visual(`${semente}:festa`, i) }));
  lista.splice(3, 0, { papel: "goleiro", visual: visual(goleiro, 0, "goleiro") });
  return lista.map((j, i) => ({ ...j, x: LUGARES[i][0], z: LUGARES[i][1], fase: (i * 0.37) % 1 }));
}

const suave = (k) => (k <= 0 ? 0 : k >= 1 ? 1 : k * k * (3 - 2 * k));
const entre = (t, a, b) => Math.min(1, Math.max(0, (t - a) / (b - a)));

/**
 * The camera at `ms` into the celebration: {angulo (rad round the squad, 0 straight in front),
 * raio, altura}. It goes slowly round them and holds at the end; with less motion asked, it
 * stays still.
 */
export function cameraDaFesta(ms, calmo = false) {
  if (calmo) return { angulo: 0.25, raio: 8.4, altura: 1.9 };
  const k = suave(entre(ms, 0, FESTA_MS));
  return { angulo: -0.55 + 1.1 * k, raio: 9.4 - 1.0 * k, altura: 2.3 - 0.4 * k };
}

/** How high the cup is (0 at the chest, 1 over the head): up between 0.4 s and 1.5 s. */
export function taca(ms, calmo = false) {
  return calmo ? 1 : suave(entre(ms, 400, 1500));
}

/** A jump: 0 on the grass, 1 at the top; `fase` 0-1 staggers them. Still after FESTA_MS. */
export function pulo(ms, fase = 0, calmo = false) {
  if (calmo || ms >= FESTA_MS) return 0;
  const p = ((ms / 620 + fase) % 1 + 1) % 1;
  return Math.sin(Math.PI * p) * suave(entre(ms, 200, 700)) * (1 - suave(entre(ms, FESTA_MS - 600, FESTA_MS)));
}

// ---------------------------------------------------------------------------------------

/** The cup: base, stem, bowl and two handles, flat-shaded; its origin at the base. */
function montarTaca(THREE) {
  const mat = new THREE.MeshStandardMaterial({ color: "#FFC21A", roughness: 0.32, metalness: 0.35, emissive: "#6b4a00", emissiveIntensity: 0.35, flatShading: true });
  const perfil = [
    [0, 0], [0.1, 0], [0.1, 0.045], [0.06, 0.06], [0.03, 0.1], [0.026, 0.17], [0.045, 0.2],
    [0.09, 0.24], [0.125, 0.31], [0.135, 0.4], [0.13, 0.43], [0.118, 0.43], [0.11, 0.33], [0, 0.3],
  ].map(([r, y]) => new THREE.Vector2(r, y));
  const grupo = new THREE.Group();
  const corpo = new THREE.Mesh(new THREE.LatheGeometry(perfil, 10), mat);
  corpo.castShadow = true;
  const alca = new THREE.TorusGeometry(0.06, 0.014, 5, 8, Math.PI);
  for (const lado of [-1, 1]) {
    const a = new THREE.Mesh(alca, mat);
    a.position.set(lado * 0.125, 0.34, 0);
    a.rotation.set(0, 0, lado > 0 ? -Math.PI / 2 : Math.PI / 2);
    grupo.add(a);
  }
  grupo.add(corpo);
  return grupo;
}

// Confetti: one instanced mesh of small paper bits, lamp yellows and a little paper white.
const N_CONFETE = 150;
const CORES_CONFETE = ["#FFC21A", "#FFC21A", "#FFD95A", "#F2A900", "#FFE9A8"];

function montarConfete(THREE) {
  const malha = new THREE.InstancedMesh(new THREE.PlaneGeometry(0.07, 0.04), new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }), N_CONFETE);
  malha.frustumCulled = false;
  const cor = new THREE.Color();
  // A fixed sequence (not Math.random): every browser throws the same confetti.
  let s = 12345;
  const r = () => ((s = (Math.imul(s, 1103515245) + 12345) >>> 0) / 4294967296);
  const bits = Array.from({ length: N_CONFETE }, (_, i) => {
    malha.setColorAt(i, cor.set(CORES_CONFETE[i % CORES_CONFETE.length]));
    const a = r() * Math.PI * 2;
    const v = 1.2 + r() * 2.6;
    return {
      sai: 1400 + r() * 500, // thrown when the cup is up
      v: [Math.cos(a) * v * 0.6, 4.5 + r() * 3.5, Math.sin(a) * v * 0.45],
      giro: [r() * 9 - 4.5, r() * 9 - 4.5, r() * 9 - 4.5],
      onda: r() * Math.PI * 2,
    };
  });
  malha.instanceColor.needsUpdate = true;
  return { malha, bits };
}

/**
 * The celebration in the scene. `jogador({papel, time, uniforme, visual})` builds and dresses a
 * player (mano-cena.js), `descansar(j)` stands him at ease. Returns {comecar, aplicar, parar}.
 */
export function criarFesta(THREE, { cena, camera, jogador, descansar, calmo = false }) {
  let ativa = null; // {grupo, gente, taca, confete, t0}
  const m = new THREE.Object3D();
  // what the camera looks at: the cup clears the score board at the top of the picture and the
  // board's line (at the bottom during the celebration) sits on the grass
  const centro = new THREE.Vector3(0, 1.4, 9.9);

  function comecar({ time, uniforme, semente, goleiro, agora = performance.now() }) {
    parar();
    const grupo = new THREE.Group();
    const gente = elenco(semente, goleiro).map((e) => {
      const j = jogador({ papel: e.papel, time, uniforme, visual: e.visual });
      j.grupo.position.set(e.x, j.quadril, e.z);
      // a little turned to the middle, as a group in a photo
      j.grupo.rotation.y = -e.x * 0.18;
      grupo.add(j.grupo);
      return { ...e, j };
    });
    const tacaGrupo = montarTaca(THREE);
    gente[0].j.partes.corpo.add(tacaGrupo);
    const confete = calmo ? null : montarConfete(THREE);
    if (confete) grupo.add(confete.malha);
    cena.add(grupo);
    // the confetti comes out of the cup over the lifter's head
    const origemConfete = new THREE.Vector3(gente[0].x, 2.25, gente[0].z);
    ativa = { grupo, gente, taca: tacaGrupo, confete, origemConfete, t0: agora };
    aplicar(agora);
  }

  function aplicar(t) {
    if (!ativa) return;
    const ms = t - ativa.t0;
    const { gente } = ativa;
    // The lifter: from holding it at the chest to straight over his head, then pumping it.
    const lifter = gente[0].j;
    const p = lifter.partes;
    descansar(lifter);
    const k = taca(ms, calmo);
    const bomba = calmo || ms >= FESTA_MS ? 0 : Math.sin(Math.max(0, ms - 1500) / 210) * 0.12 * suave(entre(ms, 1500, 1800)) * (1 - suave(entre(ms, FESTA_MS - 500, FESTA_MS)));
    const braco = -1.25 - (Math.PI - 1.35 + bomba) * k; // forward at the chest -> straight up
    p.bracoE.rotation.set(braco, 0, 0.2 + 0.05 * k);
    p.bracoD.rotation.set(braco, 0, -0.2 - 0.05 * k);
    p.cotoveloE.rotation.x = p.cotoveloD.rotation.x = -0.35 * (1 - k);
    p.corpo.rotation.x = -0.12 * k; // leaning back a touch, chest out
    const L = 0.62; // shoulder to hands
    ativa.taca.position.set(0, 0.6 - L * Math.cos(braco) + 0.02, -L * Math.sin(braco) - 0.02);
    ativa.taca.rotation.set(-0.12 * k, 0, 0);
    lifter.grupo.position.y = lifter.quadril + 0.12 * pulo(ms + 300, 0, calmo);
    // The others: jumping, arms up, the keeper too.
    for (let i = 1; i < gente.length; i++) {
      const { j, fase } = gente[i];
      const q = j.partes;
      descansar(j);
      const h = pulo(ms, fase, calmo);
      const onda = calmo || ms >= FESTA_MS ? 0 : Math.sin(ms / 160 + i) * 0.25;
      const cima = -2.75 + onda;
      q.bracoE.rotation.set(cima, 0, -0.35);
      q.bracoD.rotation.set(-2.75 - onda, 0, 0.35);
      q.cotoveloE.rotation.x = q.cotoveloD.rotation.x = -0.3;
      // tucked legs at the top of the jump, bent knees on landing
      q.pernaE.rotation.x = q.pernaD.rotation.x = -0.45 * h;
      q.joelhoE.rotation.x = q.joelhoD.rotation.x = 0.9 * h;
      j.grupo.position.y = j.quadril + 0.42 * h;
    }
    // Confetti: thrown up from the cup, slowed by the air, swaying down to the grass.
    if (ativa.confete) {
      const { malha, bits } = ativa.confete;
      const base = ativa.origemConfete;
      const g = 3.2;
      const tau = 0.45;
      bits.forEach((b, i) => {
        const s = (ms - b.sai) / 1000;
        if (s < 0) {
          m.position.set(0, -5, 0); // not yet: under the grass
        } else {
          const e = tau * (1 - Math.exp(-s / tau));
          const y = base.y + (b.v[1] + g * tau) * e - g * tau * s;
          m.position.set(base.x + b.v[0] * e + 0.18 * Math.sin(s * 2.6 + b.onda), Math.max(0.02, y), base.z + b.v[2] * e + 0.12 * Math.cos(s * 2.1 + b.onda));
          const parado = y <= 0.02;
          m.rotation.set(parado ? -Math.PI / 2 : s * b.giro[0], parado ? 0 : s * b.giro[1], parado ? b.onda : s * b.giro[2]);
        }
        m.updateMatrix();
        malha.setMatrixAt(i, m.matrix);
      });
      malha.instanceMatrix.needsUpdate = true;
    }
    // The camera, slowly round them.
    const c = cameraDaFesta(ms, calmo);
    camera.position.set(centro.x + Math.sin(c.angulo) * c.raio, c.altura, centro.z + Math.cos(c.angulo) * c.raio);
    const aspecto = camera.aspect || 16 / 9;
    camera.fov = Math.max(30, (2 * Math.atan(Math.tan((44 * Math.PI) / 360) / aspecto) * 180) / Math.PI);
    camera.updateProjectionMatrix();
    camera.lookAt(centro);
  }

  function parar() {
    if (!ativa) return;
    cena.remove(ativa.grupo);
    // Each player's own materials and shirt canvas; the shared geometries and the cached
    // sleeve textures stay (the scene's other players use them).
    for (const { j } of ativa.gente) {
      for (const mat of Object.values(j.mats)) mat.dispose();
      j.mapa?.dispose();
    }
    ativa.taca.traverse((o) => o.isMesh && o.geometry.dispose());
    ativa.taca.children[0].material.dispose();
    if (ativa.confete) {
      ativa.confete.malha.geometry.dispose();
      ativa.confete.malha.material.dispose();
      ativa.confete.malha.dispose();
    }
    ativa = null;
  }

  return {
    comecar,
    aplicar,
    parar,
    get ativa() {
      return Boolean(ativa);
    },
  };
}
