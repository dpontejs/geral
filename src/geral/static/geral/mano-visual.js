// Mano a Mano: the look of whoever takes each kick, so the kicks read as different players.
// Pure (no DOM, no Three.js): both browsers derive the same look from data both have (the room,
// the match and the kick's count), never from Math.random, so both see the same kicker. Each
// team's keeper keeps one look and the number 1 for the whole match (dev, 2026-11-26).

// Skin tones, light to dark; hair colours, black the most common.
export const PELES = ["#F1C7A1", "#D9A47C", "#B97E55", "#8A5A3C", "#65402A", "#3F2718"];
export const CORES_CABELO = ["#15110E", "#15110E", "#2F1E14", "#4B301C", "#7A5230", "#C9A25B"];
// Hair styles the scene can draw: short, buzz cut, afro, curly high top, bald, mohawk, bun.
export const CABELOS = ["curto", "raspado", "black", "topo", "careca", "moicano", "coque"];
export const NUMEROS = [7, 9, 10, 11, 8, 19, 17, 21, 5, 20, 14, 23];
// Headbands: none most of the time.
const FAIXAS = [null, null, null, null, "#F7F7F2", "#141414"];

/** FNV-1a, 32 bits. */
function hash(texto) {
  let h = 0x811c9dc5;
  for (const c of String(texto)) {
    h ^= c.codePointAt(0);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h;
}

/** mulberry32: a small seeded generator, [0, 1). */
function gerador(semente) {
  let a = semente >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * The look for kick number `indice` of the match `semente` (e.g. "room:match"): {pele, cabelo,
 * corCabelo, faixa, escala, numero}. Hair style and number step through their lists with the
 * kick, so two kicks in a row never share them. `papel: "goleiro"` is the keeper's fixed look
 * (seed it with the room and the team; `indice` is ignored) and always wears the 1.
 */
export function visual(semente, indice = 0, papel = "batedor") {
  const goleiro = papel === "goleiro";
  const base = hash(`${semente}`);
  const n = goleiro ? 0 : Math.max(0, Math.floor(indice));
  const r = gerador(hash(`${semente}#${n}#${papel}`));
  const escolher = (lista) => lista[Math.floor(r() * lista.length)];
  return {
    pele: escolher(PELES),
    cabelo: CABELOS[(base + n * 3) % CABELOS.length],
    corCabelo: escolher(CORES_CABELO),
    faixa: goleiro ? null : escolher(FAIXAS),
    escala: goleiro ? 1 : Math.round((0.95 + r() * 0.1) * 100) / 100,
    numero: goleiro ? 1 : NUMEROS[((base >>> 8) + n * 5) % NUMEROS.length],
  };
}
