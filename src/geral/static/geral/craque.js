// "Craque do dia": a Wordle of nicknames. The server judges every guess so far; the day's guesses
// and the streak live in localStorage (per edition). No dependencies.
(() => {
  const root = document.getElementById("cd");
  if (!root) return;
  const { edition, label } = root.dataset;
  const number = Number(root.dataset.number);
  const archive = root.dataset.archive === "1"; // a past puzzle: its own save, no streak
  const max = Number(root.dataset.max);
  const letters = Number(root.dataset.letters);
  const $ = (id) => document.getElementById(id);
  const rows = [...$("cd-grid").children];
  const keys = $("cd-keys");
  const KEY = archive ? `craque:${edition}:${number}` : `craque:${edition}`;
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

  // Today's game is also kept under its number, for when it shows up among the past ones.
  const save = () => {
    write(KEY, day);
    if (!archive) write(`${KEY}:${number}`, day);
  };
  let day = read(KEY, null);
  if (!day && archive) {
    // Played on its own day as "today's game": show it as it was left.
    const daily = read(`craque:${edition}`, null);
    if (daily && daily.number === number) day = daily;
  }
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
    if (archive) return; // past puzzles don't count in the streak
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

  // The row being typed: one letter per square, the cursor where the next one goes (Termo-like).
  let typed = Array(letters).fill("");
  let cursor = 0;
  let busy = false; // one guess in flight at a time
  const RANK = { nao: 1, existe: 2, certo: 3 };

  const over = () => (verdict ? verdict.over : day.guesses.length >= max);
  const paint = () => {
    const marks = verdict ? verdict.rows : [];
    const best = {};
    rows.forEach((row, i) => {
      const squares = [...row.children];
      const active = !over() && i === day.guesses.length;
      row.classList.toggle("active", active);
      squares.forEach((sq, j) => {
        const mark = marks[i] && marks[i][j];
        const letter = i < day.guesses.length ? plain(day.guesses[i])[j] : active ? typed[j] : "";
        sq.textContent = letter || "";
        sq.className = `sq${mark ? ` ${mark}` : ""}${active && j === cursor ? " cursor" : ""}`;
        if (mark && (RANK[mark] > (RANK[best[letter]] || 0))) best[letter] = mark;
      });
      row.setAttribute(
        "aria-label",
        i < day.guesses.length ? `${i + 1}º chute: ${plain(day.guesses[i])}` : `linha ${i + 1}`,
      );
    });
    keys.querySelectorAll("[data-key]").forEach((key) => {
      key.className = `key${key.dataset.key.length > 1 ? " wide" : ""}${best[key.dataset.key] ? ` ${best[key.dataset.key]}` : ""}`;
    });
    keys.hidden = over();
  };

  const render = () => {
    paint();
    $("cd-hints").replaceChildren(...verdict.hints.map((hint) => el("li", "", hint)));
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

  const shake = () => {
    const row = rows[day.guesses.length];
    row.classList.remove("shake");
    void row.offsetWidth; // restart the animation
    row.classList.add("shake");
  };

  const submit = async () => {
    if (busy || over()) return;
    if (typed.some((letter) => !letter)) {
      error(`O nome tem ${letters} letras: preencha todas.`);
      shake();
      return;
    }
    error("");
    busy = true;
    day.guesses.push(typed.join(""));
    try {
      await judge();
      save();
      typed = Array(letters).fill("");
      cursor = 0;
      $("cd-status").textContent = `${day.guesses.length}º chute conferido.`;
    } catch {
      day.guesses.pop();
      error("Não deu para conferir o chute agora. Tente de novo.");
    } finally {
      busy = false;
      paint();
    }
  };

  const press = (key) => {
    if (busy || over()) return;
    if (key === "Enter") return submit();
    if (key === "Backspace") {
      if (!typed[cursor] && cursor > 0) cursor -= 1;
      typed[cursor] = "";
    } else if (key === "ArrowLeft") cursor = Math.max(0, cursor - 1);
    else if (key === "ArrowRight") cursor = Math.min(letters - 1, cursor + 1);
    else if (/^[A-Z]$/.test(key)) {
      typed[cursor] = key;
      // On to the next empty square after this one (or simply the next one).
      const next = typed.findIndex((letter, j) => j > cursor && !letter);
      cursor = next === -1 ? Math.min(letters - 1, cursor + 1) : next;
    } else return;
    error("");
    paint();
  };

  keys.addEventListener("mousedown", (event) => event.preventDefault()); // keys never keep focus
  keys.addEventListener("click", (event) => {
    const key = event.target.closest("[data-key]");
    if (key) press(key.dataset.key);
  });
  document.addEventListener("keydown", (event) => {
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.target.closest("input, textarea, select")) return;
    const key = event.key.length === 1 ? plain(event.key) : event.key;
    // A focused link or button (Compartilhar) keeps its Enter; the on-screen keys don't.
    if (key === "Enter" && event.target.closest("button:not(.key), a")) return;
    if (/^[A-Z]$/.test(key) || ["Enter", "Backspace", "ArrowLeft", "ArrowRight"].includes(key)) {
      event.preventDefault();
      press(key);
    }
  });
  $("cd-grid").addEventListener("click", (event) => {
    const sq = event.target.closest(".sq");
    const row = sq && sq.parentElement;
    if (!row || !row.classList.contains("active")) return;
    cursor = [...row.children].indexOf(sq);
    paint();
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

  paint();
  if (day.guesses.length) {
    judge().catch(() => paint());
  }
})();
