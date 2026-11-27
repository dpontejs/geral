// Mano a Mano: the camera's timing, pure so node can test it (tests/test_mano_camera_js.py).
// The push-in at the strike and the goal's slow-motion replay (dev, 2026-11-27).
// Times are on the page's performance.now() clock, like the scene's timeline.

const entre = (t, a, b) => (b === a ? (t >= b ? 1 : 0) : Math.min(1, Math.max(0, (t - a) / (b - a))));
const suave = (k) => (k <= 0 ? 0 : k >= 1 ? 1 : k * k * (3 - 2 * k));

/** How far the kicker's camera pushes in on the goal at the strike (1 = no zoom). */
export const ZOOM_CHUTE = 1.1;

/**
 * The kicker's camera zoom at `t`: in from just before the strike, held while the ball flies
 * and the sign comes up, then back out. 1 until the lance is known (tGolpe is Infinity).
 */
export function zoomDoChute(t, { tGolpe, fimVoo, lento = 1 }) {
  if (!Number.isFinite(tGolpe)) return 1;
  const entra = suave(entre(t, tGolpe - 120 * lento, tGolpe + 250 * lento));
  const sai = suave(entre(t, fimVoo + 700 * lento, fimVoo + 1500 * lento));
  return 1 + (ZOOM_CHUTE - 1) * entra * (1 - sai);
}

// The replay: from just before the strike to the ball in the net, slowed by a factor that fits
// what is left of the result's 3 s (RESULTADO in sala.py) before the next kick.
const ANTES = 250; // ms of the kick before the strike
const DEPOIS = 200; // ms after the ball reaches the goal
const ESPERA = 350; // after the landing: the GOL sign and the shake first
const MARGEM = 200; // done this long before the next kick's phase
const VOO_MINIMO = 300; // a replay shows at least this much of the flight
const REPLAY_LENTO_MIN = 1.25;
export const REPLAY_LENTO_MAX = 2;

/**
 * Plan the replay: {inicio, de, ate, fator} — from `inicio` (page time) the kick is shown again
 * from scene time `de` to `ate`, `fator` times slower. `ate` (the param) is when the next
 * kick's phase begins; null when unknown or when there is no time for a replay worth showing.
 * Short of time, it starts later in the kick (the flight to the net) before it gives up.
 */
export function planoReplay({ tGolpe, fimVoo, ate }) {
  if (ate == null || !Number.isFinite(ate) || !Number.isFinite(tGolpe)) return null;
  const inicio = fimVoo + ESPERA;
  const disponivel = ate - MARGEM - inicio;
  const fim = fimVoo + DEPOIS;
  let de = tGolpe - ANTES;
  let fator = Math.min(REPLAY_LENTO_MAX, disponivel / (fim - de));
  if (fator < REPLAY_LENTO_MIN) {
    fator = REPLAY_LENTO_MIN;
    de = fim - disponivel / fator;
    if (de > fimVoo - VOO_MINIMO) return null;
  }
  return { inicio, de, ate: fim, fator };
}

/** The scene time the replay shows at page time `t`; null before it starts and once it ends. */
export function relogioReplay(plano, t) {
  if (!plano || t < plano.inicio) return null;
  const cena = plano.de + (t - plano.inicio) / plano.fator;
  return cena > plano.ate ? null : cena;
}

/**
 * The replay's camera, like TV's from the side of the box: level with the goal line on the side
 * the ball goes, up a little, the kicker, the keeper and the goal in one picture.
 * `alvoX` is the world x (m) where the ball reaches the goal; `k` (0-1) is how far through the
 * replay: the camera drifts in a little, as a TV one does.
 */
export function cameraReplay(alvoX, k = 0) {
  const lado = alvoX >= 0 ? 1 : -1;
  return {
    posicao: [lado * (14 - 1.5 * k), 2.8 - 0.2 * k, 0.6 + 0.3 * k],
    olhar: [0, 1, 4.8],
  };
}
