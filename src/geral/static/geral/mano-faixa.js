// Mano a Mano: the bar's good band, the same numbers as the rules (geral/games/mano/regras.py,
// `faixa_boa`, `FAIXA_CAVADINHA`); tests/test_mano_faixa_js.py runs this module against the Python one.
// Pure, with no imports, so node can load it.

const FAIXA_MIN = 250;
const FAIXA_MAX = 500;
const FAIXA_POR_DIST = 3;
const FATOR_FALTA = 0.95;
const FAIXA_PENALTI_MIN = 120;
const FAIXA_PENALTI_MAX = 450;
const FAIXA_PENALTI_POR_DIST = 1;
const FAIXA_CAVADINHA = 160;

/** Python's round(): halves go to the even neighbour. */
function arredondar(v) {
  const piso = Math.floor(v);
  const resto = v - piso;
  if (resto > 0.5) return piso + 1;
  if (resto < 0.5) return piso;
  return piso % 2 === 0 ? piso : piso + 1;
}

/** Width of the good band for an aim point: narrower near the posts and the crossbar. */
export function larguraFaixa([x, y], falta = false) {
  const dist = Math.min(x, 1000 - x, 1000 - y);
  // the penalty has its own, narrower band (dev, 2026-11-26)
  if (!falta) return arredondar(Math.min(FAIXA_PENALTI_MAX, FAIXA_PENALTI_MIN + FAIXA_PENALTI_POR_DIST * dist));
  const faixa = Math.min(FAIXA_MAX, Math.max(FAIXA_MIN, FAIXA_MIN + FAIXA_POR_DIST * dist));
  return arredondar(faixa * FATOR_FALTA);
}

/** The band as the bar draws it, [lo, hi] in 0-1000: the bar is good within width/2 of 500. */
export function faixaBoa(alvo, falta = false) {
  const meia = larguraFaixa(alvo, falta) / 2;
  return [500 - meia, 500 + meia];
}

/** The cavadinha's band: fixed and narrower than any aimed kick's (FAIXA_CAVADINHA). */
export function faixaCavadinha() {
  return [500 - FAIXA_CAVADINHA / 2, 500 + FAIXA_CAVADINHA / 2];
}

// Aiming high costs (dev, 2026-11-26): above y=600 the bar sweeps faster, up to +45% at the
// crossbar. Client-side timing only: the server's band rule does not change.
export const PERIODO_BARRA = 1000; // one sweep, up and back down (ms)
const MIRA_ALTA = 600;
const PRESSA_MAX = 0.45;

/** Speed of the bar for an aim point: 1 below MIRA_ALTA, ramping to 1 + PRESSA_MAX at y=1000. */
export function pressaBarra([, y], cavadinha = false) {
  if (cavadinha) return 1; // the cavadinha keeps its own pace
  const t = Math.min(1, Math.max(0, (y - MIRA_ALTA) / (1000 - MIRA_ALTA)));
  return 1 + PRESSA_MAX * t;
}

/** One sweep of the bar (ms) for that aim. */
export function periodoBarra(alvo, cavadinha = false) {
  return PERIODO_BARRA / pressaBarra(alvo, cavadinha);
}
