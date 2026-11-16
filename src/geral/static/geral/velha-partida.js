// "Jogo da velha" duel by link: the server keeps the moves, the rules and the clock; this page
// shows them live (server-sent events, polling every 3 s if they fail) and sends my moves with the
// number of moves I saw, so a retry never plays twice. My token stays in localStorage.
(() => {
  const root = document.getElementById("jp");
  if (!root) return;
  const id = root.dataset.duel;
  const API = `/api/jogos/velha/partidas/${id}`;
  const KEY = `velha:p:${id}`;
  const $ = (name) => document.getElementById(name);
  const cells = [...root.querySelectorAll(".vcell")];
  const heads = { rows: [...root.querySelectorAll(".velha-head.row")], cols: [...root.querySelectorAll(".velha-head.col")] };

  const read = () => {
    try {
      return JSON.parse(localStorage.getItem(KEY));
    } catch {
      return null;
    }
  };
  const write = (value) => {
    try {
      localStorage.setItem(KEY, JSON.stringify(value));
    } catch {
      /* private mode: this tab still plays, a reload would only watch */
    }
  };
  let me = read(); // {token, side} or null (a watcher, or O before joining)
  let view = null;
  let offset = 0; // server clock minus this device's clock
  let busy = false;
  let chosen = null;
  let polling = null;
  let askedAt = null; // the deadline we already asked the server about

  const busca = window.GeralVelhaBusca({
    onPick: (jogador) => play(jogador),
    taken: () => new Set(Object.values(view ? view.jogadores : {})),
  });
  busca.dialog.addEventListener("close", () => {
    chosen = null;
    draw();
  });

  const mine = () => me && view && !view.over && view.completo && view.vez === me.side;

  const draw = () => {
    if (!view) return;
    view.linhas.forEach((label, i) => (heads.rows[i].textContent = label));
    view.colunas.forEach((label, i) => (heads.cols[i].textContent = label));
    cells.forEach((cell, casa) => {
      const side = view.casas[casa];
      cell.className = "vcell";
      cell.querySelector(".vcell-mark").textContent = side || "";
      cell.querySelector(".vcell-name").textContent = side ? view.nomes[view.jogadores[casa]] || "" : "";
      if (side) cell.classList.add(side === "X" ? "mark-x" : "mark-o");
      if (view.linha && view.linha.includes(casa)) cell.classList.add("line");
      if (casa === chosen) cell.classList.add("chosen");
      cell.disabled = Boolean(side) || !mine() || busy;
    });
    const count = (side) => Object.values(view.casas).filter((v) => v === side).length;
    for (const side of ["X", "O"]) {
      $(`jp-${side}`).classList.toggle("turn", view.over ? view.vencedor === side : view.completo && view.vez === side);
      $(`jp-${side}-you`).hidden = !(me && me.side === side);
    }
    // The box over the board: share the link, join, or the end (and the rematch).
    const box = $("jp-box");
    for (const name of ["jp-share", "jp-join", "jp-rematch", "jp-watch", "jp-again"]) $(name).hidden = true;
    $("jp-box-note").textContent = "";
    // "Link copiado!" belongs to the waiting box only: the same box shows the end later.
    if (view.over || view.completo) $("jp-copied").textContent = "";
    if (view.over) {
      const score = `${count("X")} × ${count("O")}`;
      const how = view.linha ? "com três em linha" : `com mais casas (${score})`;
      $("jp-box-title").textContent =
        view.vencedor === "empate"
          ? `Empate (${score})`
          : me
            ? view.vencedor === me.side
              ? `Você venceu ${how}!`
              : `Você perdeu: o ${view.vencedor} venceu ${how}.`
            : `O ${view.vencedor} venceu ${how}.`;
      if (view.acordo) $("jp-box-note").textContent = "Partida encerrada em comum acordo.";
      if (me) {
        $("jp-rematch").hidden = false;
        $("jp-rematch").textContent = view.revanche ? "Aceitar revanche" : "Revanche";
        if (view.revanche) $("jp-box-note").textContent = "Seu adversário quer revanche. Os lados trocam.";
      } else if (view.revanche) {
        $("jp-watch").href = `/jogos/velha/p/${view.revanche}#jogo`;
        $("jp-watch").hidden = false;
      }
      $("jp-again").hidden = false;
      box.hidden = false;
    } else if (!view.completo) {
      if (me) {
        $("jp-box-title").textContent = `Você é ${me.side}. Mande o link para quem vai jogar com você`;
        $("jp-box-note").textContent = "O tabuleiro aparece quando a outra pessoa entrar.";
        $("jp-share").hidden = false;
      } else {
        $("jp-box-title").textContent = "Você foi desafiado para um jogo da velha";
        $("jp-box-note").textContent = "X ou O é por sorteio; o X começa.";
        $("jp-join").hidden = false;
      }
      box.hidden = false;
    } else {
      box.hidden = true;
    }
    box.classList.toggle("below", view.over); // at the end the final board stays in sight
    // Pass, new draw and end, for the players of a running duel; a proposal waits for the other.
    const playing = me && view.completo && !view.over;
    $("jp-tools").hidden = !playing;
    $("jp-pass").disabled = !mine() || busy;
    $("jp-redraw").disabled = $("jp-end").disabled = Boolean(view.proposta) || busy;
    const proposal = playing && view.proposta;
    $("jp-proposal").hidden = !proposal;
    if (proposal) {
      const what = view.proposta.tipo === "encerrar" ? "encerrar a partida (vence quem tem mais casas)" : "sortear um tabuleiro novo";
      const asked = view.proposta.lado === me.side;
      $("jp-proposal-text").textContent = asked
        ? `Esperando o ${me.side === "X" ? "O" : "X"} aceitar ${what}.`
        : `O ${view.proposta.lado} quer ${what}.`;
      $("jp-accept").hidden = asked;
      $("jp-refuse").textContent = asked ? "Cancelar" : "Recusar";
    }
    $("jp-turn").textContent = view.over ? "Fim" : !view.completo ? "Esperando" : mine() ? "Sua vez" : `Vez do ${view.vez}`;
    if (view.completo && !me && !view.over) $("jd-status").textContent = "Você está assistindo.";
  };

  const tick = () => {
    if (!view || !view.prazo) {
      $("jd-seconds").textContent = view && view.over ? "–" : root.dataset.seconds;
      return;
    }
    const deadline = Date.parse(view.prazo) - offset;
    const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
    $("jd-seconds").textContent = left;
    $("jd-clock").classList.toggle("hurry", left <= 5);
    if (left === 0 && askedAt !== view.prazo) {
      askedAt = view.prazo; // the server turns it into a timeout: ask once per deadline
      refresh();
    }
  };

  const apply = (next) => {
    // An older answer arriving late (same board, fewer moves); a new draw resets the moves.
    if (view && next.codigo === view.codigo && next.jogou < view.jogou) return;
    const before = view;
    view = next;
    offset = Date.parse(view.agora) - Date.now();
    if (next.over) {
      $("jd-status").textContent = ""; // the box under the board tells how it ended
    } else if (before && before.codigo && next.codigo && before.codigo !== next.codigo) {
      $("jd-status").textContent = "Tabuleiro novo sorteado.";
    } else if (before && next.jogou > before.jogou && !busy) {
      const last = next.acertos[next.acertos.length - 1];
      $("jd-status").textContent = last ? "" : "A vez passou.";
    }
    if (!mine()) busca.close();
    draw();
    tick();
  };

  const refresh = async () => {
    try {
      const response = await fetch(API);
      if (response.ok) apply(await response.json());
    } catch {
      /* the next poll or event tries again */
    }
  };

  const play = async (jogador) => {
    if (busy || chosen === null || !mine()) return;
    busy = true;
    draw();
    try {
      const response = await fetch(`${API}/jogada`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: me.token, vez_n: view.jogou, casa: chosen, jogador }),
      });
      if (response.ok) {
        const next = await response.json();
        const hit = next.casas[chosen] && next.jogadores[chosen] === jogador;
        apply(next);
        busca.close();
        $("jd-status").textContent = hit ? "" : "Não vale: esse jogador não serve nessa casa ou já foi usado.";
      } else if (response.status === 422) {
        busca.error("Jogador desconhecido.");
      } else {
        busca.close();
        await refresh(); // the turn moved on (timeout) or the duel ended
      }
    } catch {
      busca.error("Não deu para conferir agora. Tente de novo.");
    } finally {
      busy = false;
      draw();
    }
  };

  cells.forEach((cell, casa) =>
    cell.addEventListener("click", () => {
      if (!mine()) return;
      chosen = casa;
      draw();
      busca.open(`${me.side}: ${heads.rows[Math.floor(casa / 3)].textContent} × ${heads.cols[casa % 3].textContent}`);
    }),
  );

  $("jp-join").addEventListener("click", async () => {
    $("jp-join").disabled = true;
    try {
      const response = await fetch(`${API}/entrar`, { method: "POST" });
      if (response.ok) {
        const joined = await response.json();
        me = { token: joined.token, side: joined.lado };
        write(me);
      } else {
        $("jd-status").textContent = "Os dois jogadores já entraram. Você pode assistir.";
      }
    } finally {
      $("jp-join").disabled = false;
      await refresh();
    }
  });

  const send = async (path, body) => {
    if (busy) return;
    busy = true;
    draw();
    try {
      const response = await fetch(`${API}/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: me.token, ...body }),
      });
      if (response.ok) apply(await response.json());
      else await refresh(); // the duel moved on meanwhile
    } catch {
      $("jd-status").textContent = "Não deu para enviar agora. Tente de novo.";
    } finally {
      busy = false;
      draw();
    }
  };
  $("jp-pass").addEventListener("click", () => send("jogada", { vez_n: view.jogou, pular: true }));
  $("jp-redraw").addEventListener("click", () => send("propor", { tipo: "sortear" }));
  $("jp-end").addEventListener("click", () => send("propor", { tipo: "encerrar" }));
  $("jp-accept").addEventListener("click", () => send("responder", { aceita: true }));
  $("jp-refuse").addEventListener("click", () => send("responder", { aceita: false }));

  // Revanche: the first to ask creates it, the other accepts; both go there with their new side.
  $("jp-rematch").addEventListener("click", async () => {
    $("jp-rematch").disabled = true;
    try {
      const response = await fetch(`${API}/revanche`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: me.token }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const next = await response.json();
      try {
        localStorage.setItem(`velha:p:${next.id}`, JSON.stringify({ token: next.token, side: next.lado }));
      } catch {
        /* private mode: the rematch page will only watch */
      }
      location.href = `/jogos/velha/p/${next.id}#jogo`;
    } catch {
      $("jd-status").textContent = "Não deu para pedir a revanche agora. Tente de novo.";
      $("jp-rematch").disabled = false;
    }
  });

  $("jp-share").addEventListener("click", async () => {
    try {
      const url = location.href.split("#")[0] + "#jogo";
      if (navigator.share) await navigator.share({ text: "Topa um jogo da velha de futebol?", url });
      else {
        await navigator.clipboard.writeText(url);
        $("jp-copied").textContent = "Link copiado!";
      }
    } catch {
      /* the share sheet was closed */
    }
  });

  // Live: events first; if they fail, poll every 3 s until they come back.
  const listen = () => {
    const events = new EventSource(`${API}/eventos`);
    events.onmessage = (event) => {
      clearInterval(polling);
      polling = null;
      apply(JSON.parse(event.data));
      if (view.over && view.revanche) events.close(); // nothing more can change here
    };
    events.onerror = () => {
      if (view && view.over && view.revanche) return events.close();
      if (!polling) polling = setInterval(refresh, 3000);
    };
  };

  // Opened from "Desafiar por link", the shared link or a rematch: straight to the board.
  if (location.hash === "#jogo") document.getElementById("jogo").scrollIntoView();
  setInterval(tick, 200);
  refresh();
  listen();
})();
