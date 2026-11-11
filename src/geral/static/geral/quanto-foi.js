// "Quanto foi?": sends every guess so far to the server, which judges them; remembers the day's
// guesses and the streak in localStorage (per edition). No dependencies.
(() => {
  const root = document.getElementById("qf");
  if (!root) return;
  const edition = root.dataset.edition;
  const number = Number(root.dataset.number);
  const label = root.dataset.label;
  const max = Number(root.dataset.max);
  const matchKey = root.dataset.match;
  const $ = (id) => document.getElementById(id);
  const form = $("qf-form");
  const KEY = `quanto-foi:${edition}`;
  const EMOJI = { certo: "🟩", perto: "🟨", longe: "⬜" };

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
  // A new day, or the same number on a different match (the data was updated): start over.
  if (!day || day.number !== number || day.match !== matchKey) day = { number, match: matchKey, guesses: [] };
  let verdict = null;

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const cell = (goals, side) => {
    const c = el("span", `cell ${side.status}`);
    c.append(el("span", "", String(goals)));
    if (side.hint) c.append(el("small", "", side.hint));
    c.setAttribute("aria-label", `${goals} gols: ${side.status}${side.hint ? ", " + side.hint : ""}`);
    return c;
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
    $("qf-streak").textContent = stats.streak;
    $("qf-wins").textContent = stats.wins;
    $("qf-played").textContent = stats.played;
  };

  const render = () => {
    const tries = $("qf-tries");
    tries.replaceChildren();
    verdict.rows.forEach(([home, away], i) => {
      const [h, a] = day.guesses[i];
      const li = el("li");
      li.append(el("span", "n", `${i + 1}º`), cell(h, home), cell(a, away));
      tries.append(li);
    });
    $("qf-hints").replaceChildren(...verdict.hints.map((hint) => el("li", "", hint)));
    form.hidden = verdict.over;
    const r = verdict.reveal;
    $("qf-result").hidden = !r;
    if (!r) return;
    $("qf-title").textContent = verdict.solved
      ? `Acertou em ${verdict.rows.length}!`
      : "Não foi dessa vez";
    $("qf-final").textContent = `${r.home} ${r.home_goals} × ${r.away_goals} ${r.away}`;
    const goals = [...r.home_scorers.map((g) => `${g} (${r.home})`), ...r.away_scorers.map((g) => `${g} (${r.away})`)];
    $("qf-goals").textContent = goals.length ? `Gols: ${goals.join(", ")}.` : "";
    finish();
  };

  const judge = async () => {
    const response = await fetch(`/api/jogos/quanto-foi/${edition}/${number}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ guesses: day.guesses }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    verdict = await response.json();
    render();
  };

  const button = form.querySelector("button");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (button.disabled || day.guesses.length >= max) return;
    button.disabled = true; // one guess in flight at a time
    day.guesses.push([Number($("qf-home").value), Number($("qf-away").value)]);
    try {
      await judge();
      write(KEY, day);
      form.reset();
      $("qf-home").focus();
    } catch {
      day.guesses.pop();
      alert("Não deu para conferir o chute agora. Tente de novo.");
    } finally {
      button.disabled = false;
    }
  });

  $("qf-share").addEventListener("click", async () => {
    const score = verdict.solved ? verdict.rows.length : "X";
    const lines = verdict.rows.map(([h, a]) => EMOJI[h.status] + EMOJI[a.status]);
    const text = `Quanto foi? #${number} · ${label} ${score}/${max}\n${lines.join("\n")}\n${location.href}`;
    try {
      if (navigator.share) await navigator.share({ text });
      else {
        await navigator.clipboard.writeText(text);
        $("qf-copied").textContent = "Copiado!";
      }
    } catch {
      /* the user closed the share sheet */
    }
  });

  if (day.guesses.length) {
    // Replays today's guesses; the form stays hidden until we know whether the game is over.
    form.hidden = true;
    judge().catch(() => {
      form.hidden = day.guesses.length >= max;
    });
  }
})();
