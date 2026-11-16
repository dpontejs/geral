// "Jogo da velha" duel: two players on one screen. The browser keeps the moves, the 30 s clock and
// the games won by each player; the server judges the whole history after each move
// (POST /api/jogos/velha/duelo). Who starts the first game is drawn; then they alternate.
(() => {
  const root = document.getElementById("jd");
  if (!root) return;
  const SECONDS = Number(root.dataset.seconds);
  const $ = (id) => document.getElementById(id);
  const dialog = $("jv-dialog");
  const search = $("jv-search");
  const cells = [...root.querySelectorAll(".vcell")];
  const heads = { rows: [...root.querySelectorAll(".velha-head.row")], cols: [...root.querySelectorAll(".velha-head.col")] };
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  let board = null; // {codigo, linhas, colunas}
  let jogadas = [];
  let state = null;
  let busy = false;
  let chosen = null;
  let deadline = 0;
  let ticker = null;
  let pending = null;
  let passing = false; // the "estouro" being sent is a pass, not a timeout
  let round = Math.random() < 0.5 ? 1 : 2; // who is X (and starts) in the first game is drawn
  let games = 1;
  const wins = { 1: 0, 2: 0 };
  const playerOf = (side) => ((side === "X") === (round % 2 === 1) ? 1 : 2);

  const status = (text) => {
    $("jv-error").textContent = text;
    $("jv-error").hidden = !text;
  };

  const draw = () => {
    const s = state || { casas: {}, jogadores: {}, vez: "X", over: false, linha: null };
    cells.forEach((cell, casa) => {
      const side = s.casas[casa];
      cell.className = "vcell";
      cell.querySelector(".vcell-mark").textContent = side || "";
      cell.querySelector(".vcell-name").textContent = side ? state.nomes[s.jogadores[casa]] || "" : "";
      if (side) cell.classList.add(side === "X" ? "mark-x" : "mark-o");
      if (s.linha && s.linha.includes(casa)) cell.classList.add("line");
      if (casa === chosen) cell.classList.add("chosen");
      cell.disabled = !board || Boolean(side) || s.over || busy;
    });
    const count = (side) => Object.values(s.casas).filter((v) => v === side).length;
    const lit = state && (s.over ? (s.vencedor === "empate" ? 0 : playerOf(s.vencedor)) : playerOf(s.vez));
    for (const n of [1, 2]) {
      $(`jd-p${n}-mark`).textContent = playerOf("X") === n ? "X" : "O";
      $(`jd-p${n}`).classList.toggle("turn", lit === n);
    }
    // Pass, new draw and end: on one screen both players see it, so "both agree" is a confirm.
    $("jd-tools").hidden = !state || s.over;
    for (const name of ["jd-pass", "jd-redraw", "jd-end"]) $(name).disabled = busy;
    $("jd-turn").textContent = !state ? `Partida ${games}` : s.over ? "Fim" : `Vez do ${s.vez}`;
    $("jd-result").hidden = !s.over;
    if (s.over) {
      const score = `${count("X")} × ${count("O")}`;
      $("jd-title").textContent =
        s.vencedor === "empate"
          ? `Empate (${score})`
          : s.linha
            ? `Jogador ${playerOf(s.vencedor)} venceu com três em linha!`
            : `Jogador ${playerOf(s.vencedor)} venceu com mais casas (${score})!`;
      $("jd-series").textContent =
        games > 1 || wins[1] + wins[2] > 1 ? `Na série: Jogador 1 ${wins[1]} × ${wins[2]} Jogador 2` : "";
    }
  };

  const tick = () => {
    const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
    $("jd-seconds").textContent = left;
    $("jd-clock").classList.toggle("hurry", left <= 5);
    if (left === 0 && !busy && state && !state.over) move({ estouro: true });
  };

  const startClock = () => {
    clearInterval(ticker);
    if (state && state.over) {
      $("jd-seconds").textContent = "–";
      return;
    }
    deadline = Date.now() + SECONDS * 1000;
    ticker = setInterval(tick, 200);
    tick();
  };

  const judge = async (moves) => {
    const response = await fetch("/api/jogos/velha/duelo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tabuleiro: board.codigo, jogadas: moves }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  };

  const move = async (jogada) => {
    if (busy) return;
    busy = true;
    draw(); // no new cell while this move is judged
    const who = state ? state.vez : "X";
    try {
      const next = [...jogadas, jogada];
      state = await judge(next);
      jogadas = next;
      if (state.over && state.vencedor !== "empate") wins[playerOf(state.vencedor)] += 1;
      const hit = state.acertos[state.acertos.length - 1];
      chosen = null;
      if (dialog.open) dialog.close();
      $("jd-status").textContent = jogada.encerrar
        ? "Partida encerrada em comum acordo."
        : jogada.estouro
        ? passing
          ? `O ${who} passou a vez.`
          : `O tempo do ${who} acabou.`
        : hit
          ? ""
          : `Não vale: ${state.nomes[jogada.jogador] || "esse jogador"} não serve nessa casa ou já foi usado.`;
      startClock();
    } catch {
      const text = "Não deu para conferir agora. Tente de novo.";
      if (dialog.open) status(text);
      else $("jd-status").textContent = text;
      // A timeout that could not be sent tries again in a few seconds, not on every tick.
      if (jogada.estouro) deadline = Date.now() + 3000;
    } finally {
      busy = false;
      draw();
    }
  };

  const drawResults = (found) => {
    const taken = new Set(Object.values(state ? state.jogadores : {}));
    $("jv-results").replaceChildren(
      ...found.map((p) => {
        const li = el("li");
        const button = el("button", "club");
        button.type = "button";
        button.append(el("span", "club-name", p.nome), el("span", "club-country", [p.anos, p.posicao].filter(Boolean).join(" · ")));
        button.disabled = taken.has(p.id) || busy;
        button.addEventListener("click", () => move({ casa: chosen, jogador: p.id }));
        li.append(button);
        return li;
      }),
    );
    if (!found.length && search.value.trim().length >= 2) $("jv-results").append(el("li", "empty", "Nenhum jogador com esse nome."));
  };

  let timer = null;
  search.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (pending) pending.abort();
      pending = new AbortController();
      const asked = search.value;
      try {
        const response = await fetch(`/api/jogos/velha/jogadores?q=${encodeURIComponent(asked)}`, { signal: pending.signal });
        if (response.ok && search.value === asked) drawResults(await response.json());
      } catch {
        /* a newer search replaced this one */
      }
    }, 250);
  });
  $("jv-form").addEventListener("submit", (event) => {
    event.preventDefault(); // Enter picks the player when the search leaves only one
    const only = $("jv-results").querySelectorAll("button.club:not(:disabled)");
    if (only.length === 1) only[0].click();
  });

  cells.forEach((cell, casa) =>
    cell.addEventListener("click", () => {
      chosen = casa;
      status("");
      $("jv-cell-label").textContent = `${state ? state.vez : "X"}: ${heads.rows[Math.floor(casa / 3)].textContent} × ${heads.cols[casa % 3].textContent}`;
      search.value = "";
      $("jv-results").replaceChildren();
      draw();
      dialog.showModal();
      search.focus();
    }),
  );
  $("jv-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    chosen = null;
    draw();
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });

  // Before "Começar": no board, no clock; the categories stay hidden ("?").
  const waitStart = () => {
    clearInterval(ticker);
    board = null;
    jogadas = [];
    state = null;
    heads.rows.concat(heads.cols).forEach((head) => (head.textContent = "?"));
    $("jd-seconds").textContent = SECONDS;
    $("jd-status").textContent = "";
    $("jd-start-title").textContent = `Jogador ${playerOf("X")} é X e começa`;
    $("jd-start").hidden = false;
    draw();
  };

  const start = async () => {
    $("jd-go").disabled = true;
    try {
      const response = await fetch("/api/jogos/velha/tabuleiro");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      board = await response.json();
      board.linhas.forEach((label, i) => (heads.rows[i].textContent = label));
      board.colunas.forEach((label, i) => (heads.cols[i].textContent = label));
      state = await judge([]);
      jogadas = []; // a new draw starts over (the sides stay)
      $("jd-start").hidden = true;
      $("jd-status").textContent = "";
      startClock();
    } catch {
      board = null;
      heads.rows.concat(heads.cols).forEach((head) => (head.textContent = "?"));
      $("jd-status").textContent = "Não deu para sortear o tabuleiro. Tente de novo.";
    } finally {
      $("jd-go").disabled = false;
      draw();
    }
  };

  $("jd-go").addEventListener("click", start);
  $("jd-pass").addEventListener("click", () => {
    passing = true;
    move({ estouro: true }).finally(() => (passing = false));
  });
  $("jd-end").addEventListener("click", () => {
    if (confirm("Os dois concordam em encerrar a partida? Vence quem tem mais casas.")) move({ encerrar: true });
  });
  $("jd-redraw").addEventListener("click", () => {
    if (!confirm("Os dois concordam em sortear um tabuleiro novo? As casas são zeradas.")) return;
    start(); // a fresh board and clock; the sides stay
  });
  // A duel by link: the creator plays X; the page of the duel keeps the token in localStorage.
  $("jd-link").addEventListener("click", async () => {
    $("jd-link").disabled = true;
    try {
      const response = await fetch("/api/jogos/velha/partidas", { method: "POST" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const created = await response.json();
      try {
        localStorage.setItem(`velha:p:${created.id}`, JSON.stringify({ token: created.token, side: created.lado }));
      } catch {
        /* private mode: the page will only watch */
      }
      location.href = `/jogos/velha/p/${created.id}#jogo`; // straight to the board
    } catch {
      $("jd-status").textContent = "Não deu para criar o duelo agora. Tente de novo.";
      $("jd-link").disabled = false;
    }
  });
  $("jd-again").addEventListener("click", () => {
    round += 1; // the other player starts
    games += 1;
    waitStart();
  });
  waitStart();
})();
