// "Quem é?": the career is on the board; pick players from a searchable, paged list. The server
// judges every pick so far; the day's picks and the streak live in localStorage (per edition).
// No dependencies.
(() => {
  const root = document.getElementById("qe");
  if (!root) return;
  const { edition, label, player } = root.dataset;
  const number = Number(root.dataset.number);
  const max = Number(root.dataset.max);
  const $ = (id) => document.getElementById(id);
  const form = $("qe-form");
  const search = $("qe-search");
  const KEY = `quem-e:${edition}`;
  const PAGE = 12;

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
    text.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const players = JSON.parse($("qe-player-data").textContent).map((p) => ({ ...p, key: plain(p.nome) }));

  let day = read(KEY, null);
  // A new day, or the list changed today's player: start over.
  if (!day || day.number !== number || day.player !== player) {
    day = { number, player, palpites: [], desistiu: false };
  }
  let verdict = null;
  let busy = false;
  let page = 0;

  const error = (text) => {
    $("qe-error").textContent = text;
    $("qe-error").hidden = !text;
  };

  const matches = () => {
    const query = plain(search.value);
    if (!query) return players;
    return players
      .filter((p) => p.key.includes(query))
      .sort((a, b) => b.key.startsWith(query) - a.key.startsWith(query) || a.nome.localeCompare(b.nome, "pt"));
  };

  const drawResults = () => {
    const found = matches();
    const pages = Math.max(1, Math.ceil(found.length / PAGE));
    page = Math.min(page, pages - 1);
    const tried = new Set(day.palpites);
    $("qe-results").replaceChildren(
      ...found.slice(page * PAGE, page * PAGE + PAGE).map((p) => {
        const li = el("li");
        const button = el("button", `club${tried.has(p.id) ? " wrong" : ""}`);
        button.type = "button";
        button.title = p.nome;
        button.append(el("span", "club-name", p.nome));
        button.disabled = tried.has(p.id) || busy;
        button.addEventListener("click", () => guess(p.id));
        li.append(button);
        return li;
      }),
    );
    if (!found.length) $("qe-results").append(el("li", "empty", "Nenhum jogador com esse nome."));
    $("qe-page").textContent = `Página ${page + 1} de ${pages} · ${found.length} jogadores`;
    $("qe-prev").disabled = page === 0;
    $("qe-next").disabled = page >= pages - 1;
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
    $("qe-streak").textContent = stats.streak;
    $("qe-wins").textContent = stats.wins;
    $("qe-played").textContent = stats.played;
  };

  const render = () => {
    $("qe-tries").replaceChildren(
      ...verdict.rows.map((row, i) => {
        const li = el("li");
        li.append(el("span", "n", `${i + 1}º`), el("span", `cell ${row.certo ? "certo" : "longe"}`, row.nome));
        return li;
      }),
    );
    $("qe-hints").replaceChildren(...verdict.hints.map((hint) => el("li", "", hint)));
    form.hidden = verdict.over;
    $("qe-result").hidden = !verdict.over;
    drawResults();
    if (!verdict.over) return;
    $("qe-name").textContent = verdict.reveal.nome;
    $("qe-name").classList.remove("blink");
    $("qe-title").textContent = verdict.solved ? `Acertou em ${verdict.rows.length}!` : "Não foi dessa vez";
    $("qe-final").textContent = `${verdict.reveal.nome}${verdict.reveal.posicao ? " · " + verdict.reveal.posicao : ""}`;
    finish();
  };

  const judge = async () => {
    const response = await fetch(`/api/jogos/quem-e/${edition}/${number}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ palpites: day.palpites, desistiu: Boolean(day.desistiu) }),
    });
    if (!response.ok) {
      const problem = new Error(`HTTP ${response.status}`);
      problem.status = response.status;
      throw problem;
    }
    verdict = await response.json();
    render();
  };

  // Saved picks the server no longer knows (the player list changed): start today over.
  const restart = () => {
    day = { number, player, palpites: [], desistiu: false };
    verdict = null;
    write(KEY, day);
    form.hidden = false;
    $("qe-tries").replaceChildren();
    $("qe-hints").replaceChildren();
    error("A lista de jogadores mudou e o jogo de hoje recomeçou.");
  };

  const play = async (change, undo) => {
    if (busy) return;
    busy = true; // one pick in flight at a time
    change();
    drawResults();
    try {
      await judge();
      write(KEY, day);
      error("");
      search.value = "";
      page = 0;
    } catch (problem) {
      if (problem.status === 422) restart();
      else {
        undo();
        error("Não deu para conferir agora. Tente de novo.");
      }
    } finally {
      busy = false;
      drawResults();
    }
  };

  const guess = (id) => {
    if (day.palpites.length >= max) return;
    play(
      () => day.palpites.push(id),
      () => day.palpites.pop(),
    );
  };

  search.addEventListener("input", () => {
    page = 0;
    drawResults();
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault(); // Enter picks the player when the search leaves only one
    const found = matches();
    if (found.length === 1 && !day.palpites.includes(found[0].id)) guess(found[0].id);
  });
  $("qe-give-up").addEventListener("click", () =>
    play(
      () => (day.desistiu = true),
      () => (day.desistiu = false),
    ),
  );
  $("qe-prev").addEventListener("click", () => {
    page -= 1;
    drawResults();
  });
  $("qe-next").addEventListener("click", () => {
    page += 1;
    drawResults();
  });

  $("qe-share").addEventListener("click", async () => {
    const score = verdict.solved ? verdict.rows.length : "X";
    // Giving up before any guess still shares a line, not an empty one.
    const squares = verdict.rows.map((row) => (row.certo ? "🟩" : "🟥")).join("") || "🏳️";
    const text = `Quem é? #${number} · ${label} ${score}/${max}\n${squares}\n${location.href}`;
    try {
      if (navigator.share) await navigator.share({ text });
      else {
        await navigator.clipboard.writeText(text);
        $("qe-copied").textContent = "Copiado!";
      }
    } catch {
      /* the user closed the share sheet */
    }
  });

  drawResults();
  if (day.palpites.length || day.desistiu) {
    form.hidden = true; // until we know whether today's game is over
    judge().catch((problem) => {
      if (problem.status === 422) restart();
      form.hidden = false;
      drawResults();
    });
  }
})();
