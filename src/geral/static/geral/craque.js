// "Craque do dia": a Wordle of nicknames. The server judges every guess so far; the day's guesses
// and the streak live in localStorage (per edition). No dependencies.
(() => {
  const root = document.getElementById("cd");
  if (!root) return;
  const { edition, label } = root.dataset;
  const number = Number(root.dataset.number);
  const max = Number(root.dataset.max);
  const letters = Number(root.dataset.letters);
  const $ = (id) => document.getElementById(id);
  const form = $("cd-form");
  const input = $("cd-word");
  const button = form.querySelector("button");
  const KEY = `craque:${edition}`;
  const EMOJI = { certo: "🟩", existe: "🟨", nao: "⬜" };

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
  const plain = (text) =>
    text.normalize("NFKD").replace(/[̀-ͯ]/g, "").toUpperCase().trim();

  let day = read(KEY, null);
  // A new day, or the list changed the answer's length: start over.
  if (!day || day.number !== number || day.letters !== letters) day = { number, letters, guesses: [] };
  let verdict = null;

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
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
    $("cd-streak").textContent = stats.streak;
    $("cd-wins").textContent = stats.wins;
    $("cd-played").textContent = stats.played;
  };

  const render = () => {
    $("cd-tries").replaceChildren(
      ...verdict.rows.map((marks, i) => {
        const word = plain(day.guesses[i]);
        const li = el("li", "word");
        li.setAttribute("aria-label", `${i + 1}º chute: ${word}`);
        marks.forEach((mark, j) => li.append(el("span", `tile ${mark}`, word[j])));
        return li;
      }),
    );
    $("cd-hints").replaceChildren(...verdict.hints.map((hint) => el("li", "", hint)));
    form.hidden = verdict.over;
    const r = verdict.reveal;
    $("cd-result").hidden = !r;
    if (!r) return;
    $("cd-title").textContent = verdict.solved ? `Acertou em ${verdict.rows.length}!` : "Não foi dessa vez";
    $("cd-final").textContent = r.nome;
    $("cd-fact").textContent = `${r.completo} · ${r.posicao} · ${r.epoca}. ${r.fato}`;
    finish();
  };

  const judge = async () => {
    const response = await fetch(`/api/jogos/craque-do-dia/${edition}/${number}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ guesses: day.guesses }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    verdict = await response.json();
    render();
  };

  const error = (text) => {
    $("cd-error").textContent = text;
    $("cd-error").hidden = !text;
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const word = plain(input.value);
    if (!/^[A-Z]+$/.test(word) || word.length !== letters) {
      error(`O nome tem ${letters} letras, sem espaço nem número.`);
      return;
    }
    if (button.disabled || day.guesses.length >= max) return;
    error("");
    button.disabled = true; // one guess in flight at a time
    day.guesses.push(word);
    try {
      await judge();
      write(KEY, day);
      form.reset();
      input.focus();
    } catch {
      day.guesses.pop();
      error("Não deu para conferir o chute agora. Tente de novo.");
    } finally {
      button.disabled = false;
    }
  });

  $("cd-share").addEventListener("click", async () => {
    const score = verdict.solved ? verdict.rows.length : "X";
    const lines = verdict.rows.map((marks) => marks.map((m) => EMOJI[m]).join(""));
    const text = `Craque do dia #${number} · ${label} ${score}/${max}\n${lines.join("\n")}\n${location.href}`;
    try {
      if (navigator.share) await navigator.share({ text });
      else {
        await navigator.clipboard.writeText(text);
        $("cd-copied").textContent = "Copiado!";
      }
    } catch {
      /* the user closed the share sheet */
    }
  });

  if (day.guesses.length) {
    form.hidden = true; // until we know whether today's game is over
    judge().catch(() => {
      form.hidden = day.guesses.length >= max;
    });
  }
})();
