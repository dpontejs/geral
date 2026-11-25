// Mano a Mano: the bar's good band, the same numbers as the rules (geral/games/mano/regras.py,
// `faixa_boa`); tests/test_mano_faixa_js.py runs this module against the Python one.
// Pure, with no imports, so node can load it.

const FAIXA_MIN = 250;
const FAIXA_MAX = 500;
const FAIXA_POR_DIST = 3;
const FATOR_FALTA = 0.95;

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
  let faixa = Math.min(FAIXA_MAX, Math.max(FAIXA_MIN, FAIXA_MIN + FAIXA_POR_DIST * dist));
  if (falta) faixa *= FATOR_FALTA;
  return arredondar(faixa);
}

/** The band as the bar draws it, [lo, hi] in 0-1000: the bar is good within width/2 of 500. */
export function faixaBoa(alvo, falta = false) {
  const meia = larguraFaixa(alvo, falta) / 2;
  return [500 - meia, 500 + meia];
}
