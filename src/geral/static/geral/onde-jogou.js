// "Onde jogou?": the server judges every club guessed so far; the day's guesses and the streak
// live in localStorage (per edition). No dependencies.
(() => {
  const root = document.getElementById("oj");
  if (!root) return;
  const { edition, label, player } = root.dataset;
  const number = Number(root.dataset.number);
  const max = Number(root.dataset.max);
  const $ = (id) => document.getElementById(id);
  const form = $("oj-form");
  const input = $("oj-club");
  const submit = form.querySelector("button[type=submit]");
  const KEY = `onde-jogou:${edition}`;

  const read = (key, fallback) => {
    try {
      return JSON.parse(localStorage.getItem(key)) ?? fallback;
    } catch {
      return fallback;
    }
  };
  const write = (key, value) => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* private mode: the game still works, it just forgets */
    }
  };

  let day = read(KEY, null);
  // A new day, or the list changed today's player: start over.
  if (!day || day.number !== number || day.player !== player) {
    day = { number, player, palpites: [], desistiu: false };
  }
  let verdict = null;

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const error = (text) => {
    $("oj-error").textContent = text;
    $("oj-error").hidden = !text;
  };

  const finish = () => {
    const stats = read(`${KEY}:stats`, { streak: 0, wins: 0, played: 0, last: 0, counted: 0 });
    if (stats.counted !== number) {
      stats.played += 1;
      if (verdict.solved) {
        stats.wins += 1;
        stats.streak = stats.last === number - 1 ? stats.streak + 1 : 1;
        stats.last = number;
      } else {
        stats.streak = 0;
      }
      stats.counted = number;
      write(`${KEY}:stats`, stats);
    }
    $("oj-streak").textContent = stats.streak;
    $("oj-wins").textContent = stats.wins;
    $("oj-played").textContent = stats.played;
  };

  const render = () => {
    const slots = $("oj-slots").children;
    verdict.slots.forEach((slot, i) => {
      const li = slots[i];
      const shown = li.lastElementChild;
      if (!slot.clube) return;
      const club = el("span", `slot-club${slot.achado ? " found" : " missed"}`, slot.clube);
      shown.replaceWith(club);
    });
    $("oj-wrong").textContent = verdict.erros.length
      ? `Errou (${verdict.erros.length} de ${max}): ${verdict.erros.join(", ")}`
      : "";
    form.hidden = verdict.over;
    $("oj-result").hidden = !verdict.over;
    if (!verdict.over) return;
    $("oj-title").textContent = verdict.solved ? "Carreira completa!" : "Fim de jogo";
    $("oj-final").textContent = `${verdict.achados} de ${verdict.total} clubes`;
    finish();
  };

  const judge = async () => {
    const response = await fetch(`/api/jogos/onde-jogou/${edition}/${number}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ palpites: day.palpites, desistiu: day.desistiu }),
    });
    if (response.status === 422) {
      const body = await response.json();
      const problem = new Error("unknown club");
      problem.detail = typeof body.detail === "string" ? body.detail : "Clube desconhecido";
      throw problem;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    verdict = await response.json();
    render();
  };

  const play = async (change, undo) => {
    if (submit.disabled) return;
    submit.disabled = true; // one guess in flight at a time
    change();
    try {
      await judge();
      write(KEY, day);
      error("");
      form.reset();
      input.focus();
    } catch (problem) {
      undo();
      error(problem.detail ? `${problem.detail}. Escolha um clube da lista.` : "Não deu para conferir agora. Tente de novo.");
    } finally {
      submit.disabled = false;
    }
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const club = input.value.trim();
    if (!club) return;
    play(
      () => day.palpites.push(club),
      () => day.palpites.pop(),
    );
  });

  $("oj-give-up").addEventListener("click", () => {
    play(
      () => (day.desistiu = true),
      () => (day.desistiu = false),
    );
  });

  $("oj-share").addEventListener("click", async () => {
    const found = verdict.achados;
    const squares = "🟩".repeat(found) + "⬛".repeat(verdict.total - found);
    const text = `Onde jogou? #${number} · ${label} ${found}/${verdict.total}\n${squares}\n${location.href}`;
    try {
      if (navigator.share) await navigator.share({ text });
      else {
        await navigator.clipboard.writeText(text);
        $("oj-copied").textContent = "Copiado!";
      }
    } catch {
      /* the user closed the share sheet */
    }
  });

  if (day.palpites.length || day.desistiu) {
    form.hidden = true; // until we know whether today's game is over
    judge().catch(() => {
      form.hidden = false;
    });
  }
})();
