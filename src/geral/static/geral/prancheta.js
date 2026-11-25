// Prancheta: draw and guess, live, in a private room (docs/features/prancheta.md). The server owns
// the rules, the clock and the word; this page only draws what each `estado` and event says, and
// sends my actions. A fresh `estado` (on connecting and on every change of phase or players)
// redraws everything, strokes included, so a reconnect never duplicates a line. My token for the
// room stays in localStorage (`prancheta:<id>`); without it, the room asks for a nickname and
// sends a request the host accepts or refuses (meanwhile the `estado` has `fase: "pedido"`).
(() => {
  const raiz = document.getElementById("pr");
  if (!raiz) return;
  const SALA = raiz.dataset.sala;
  const API = "/api/jogos/prancheta";
  const PUBLICO = (raiz.dataset.url || location.origin).replace(/\/$/, "");
  const LINK = `${PUBLICO}/jogos/prancheta/s/${SALA}`;
  const palco = document.getElementById("palco");
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const desktop = () => matchMedia("(min-width: 900px)").matches;

  const MAX_JOGADORES = 10;
  const DIF = { facil: ["Fácil", 5], media: ["Média", 7], dificil: ["Difícil", 10] };
  // Chalk: 0 is the eraser (the board's colour), 1–12 the sticks in the tray (two rows of 7).
  // The dark ones (marrom, azul-escuro, preto) read as shading on the slate, like real chalk.
  const CORES = [null, "#F3F1EA", "#F6D55C", "#F29E4C", "#E5604D", "#F2A7C3", "#8CC5EE", "#B5E08A", "#B99BE3", "#A87650", "#A3A6A1", "#4F73C4", "#191C1A"];
  const NOMES_COR = ["apagador", "giz branco", "giz amarelo", "giz laranja", "giz vermelho", "giz rosa", "giz azul", "giz verde", "giz roxo", "giz marrom", "giz cinza", "giz azul-escuro", "giz preto"];
  const ESP = [0, 0.006, 0.013, 0.026]; // stroke width as a share of the board's width
  const PEDACO = 64; // points per piece sent
  const TETO = 20000; // points per drawing

  // ---- my seat in the room -----------------------------------------------------------------
  const CHAVE = `prancheta:${SALA}`;
  const ler = () => {
    try {
      return JSON.parse(localStorage.getItem(CHAVE));
    } catch {
      return null;
    }
  };
  const gravar = (id, valor) => {
    try {
      localStorage.setItem(`prancheta:${id}`, JSON.stringify(valor));
    } catch {
      /* private mode: this tab still plays, a reload asks for a nickname again */
    }
  };
  const esquecer = () => {
    try {
      localStorage.removeItem(CHAVE);
    } catch {
      /* nothing kept */
    }
  };
  let eu = SALA ? ler() : null; // {jogador, token}

  async function postar(caminho, corpo) {
    try {
      const r = await fetch(`${API}${caminho}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
      let dados = null;
      try {
        dados = await r.json();
      } catch {
        /* 204 */
      }
      return { status: r.status, dados };
    } catch {
      return { status: 0, dados: null };
    }
  }
  async function acao(tipo, dados = {}) {
    if (!eu) return 0;
    const { status } = await postar(`/salas/${SALA}/acao`, { token: eu.token, tipo, ...dados });
    if (status === 403 || status === 404) caiu();
    return status;
  }

  // ---- the room as the server last told it -----------------------------------------------
  let est = null; // the last `estado`
  let seq = 0; // events up to this one are already in `est`
  let diferenca = 0; // server clock minus this device's
  let fonte = null; // the EventSource
  let tela = ""; // criar | entrar | espera | ao-vivo | fim | aviso
  let saindo = false;
  let ganhos = {}; // points scored in this play, from `acerto`
  let lanceAtual = ""; // which play `ganhos` and my strokes belong to
  let opcoesDoLance = null; // what the drawer chose from (only the drawer knows the difficulty)
  let escolhida = null;
  let pulou = false; // the drawer of this play gave up their turn

  const jogador = (id) => (est ? est.jogadores.find((j) => j.id === id) : null);
  const nome = (id) => (jogador(id) || { apelido: "alguém" }).apelido;
  const souEu = (id) => eu && id === eu.jogador;
  const euDesenho = () => est && souEu(est.desenhista);
  const presentes = () => est.jogadores.filter((j) => j.presente);
  const quemChuta = () => presentes().filter((j) => j.id !== est.desenhista);
  const restam = () => (est && est.prazo ? Math.max(0, Math.ceil((Date.parse(est.prazo) - (Date.now() + diferenca)) / 1000)) : 0);

  // ---- the board: strokes in 0–1000 on both axes of a 4:3 board ---------------------------
  let tracos = [], lousa = null, cv = null, ctx = null, sujo = false, padroes = {};
  function mulberry(a) {
    return () => {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function padrao(cor) {
    // a little grain so the line looks like chalk, not marker
    if (padroes[cor]) return padroes[cor];
    const c = document.createElement("canvas"); c.width = c.height = 64;
    const g = c.getContext("2d"); g.fillStyle = cor; g.fillRect(0, 0, 64, 64);
    const r = mulberry(cor.length * 97 + cor.charCodeAt(1));
    for (let i = 0; i < 420; i++) g.clearRect(Math.floor(r() * 64), Math.floor(r() * 64), 1, 1);
    g.globalAlpha = 0.25; g.fillStyle = "#000";
    for (let i = 0; i < 160; i++) g.fillRect(Math.floor(r() * 64), Math.floor(r() * 64), 1, 1);
    return (padroes[cor] = ctx.createPattern(c, "repeat"));
  }
  function ajustarCanvas() {
    if (!lousa) return;
    const r = devicePixelRatio || 1, w = lousa.clientWidth, h = lousa.clientHeight;
    cv.width = Math.round(w * r); cv.height = Math.round(h * r);
    ctx.setTransform(r, 0, 0, r, 0, 0); padroes = {}; desenhar();
  }
  function pedirDesenho() {
    if (!sujo) { sujo = true; requestAnimationFrame(() => { sujo = false; desenhar(); }); }
  }
  function desenhar() {
    if (!ctx) return;
    const w = lousa.clientWidth, h = lousa.clientHeight;
    ctx.clearRect(0, 0, w, h);
    ctx.lineCap = ctx.lineJoin = "round";
    for (const t of tracos) {
      const p = t.pts.map(([x, y]) => [(x / 1000) * w, (y / 1000) * h]);
      if (!p.length) continue;
      ctx.globalCompositeOperation = t.cor === 0 ? "destination-out" : "source-over";
      ctx.strokeStyle = ctx.fillStyle = t.cor === 0 ? "#000" : padrao(CORES[t.cor] || CORES[1]);
      ctx.lineWidth = Math.max(2, (ESP[t.esp] || ESP[2]) * w * (t.cor === 0 ? 2.4 : 1));
      ctx.beginPath();
      if (p.length === 1) { ctx.arc(p[0][0], p[0][1], ctx.lineWidth / 2, 0, 7); ctx.fill(); continue; }
      ctx.moveTo(p[0][0], p[0][1]);
      for (let i = 1; i < p.length - 1; i++) {
        // through the midpoints: a smooth line from a jittery finger
        ctx.quadraticCurveTo(p[i][0], p[i][1], (p[i][0] + p[i + 1][0]) / 2, (p[i][1] + p[i + 1][1]) / 2);
      }
      ctx.lineTo(p.at(-1)[0], p.at(-1)[1]);
      ctx.stroke();
    }
    ctx.globalCompositeOperation = "source-over";
  }
  const totalPts = () => tracos.reduce((n, t) => n + t.pts.length, 0);

  // Drawing with mouse, pen or finger. Pieces of ≤64 points go out every ~50 ms, one at a time,
  // in order; a refused piece (429) stays and joins the next one, so the line is never lost.
  let ferramenta = { cor: 1, esp: 2 }, atual = null, idTraco = 0, fila = [], enviando = false;
  function ligarDesenho() {
    const pt = (e) => {
      const r = cv.getBoundingClientRect();
      return [
        Math.round(Math.min(1000, Math.max(0, ((e.clientX - r.left) / r.width) * 1000))),
        Math.round(Math.min(1000, Math.max(0, ((e.clientY - r.top) / r.height) * 1000))),
      ];
    };
    cv.addEventListener("pointerdown", (e) => {
      if (!podeDesenhar() || atual || totalPts() >= TETO) return;
      e.preventDefault();
      cv.setPointerCapture(e.pointerId);
      atual = { id: ++idTraco, cor: ferramenta.cor, esp: ferramenta.esp, pts: [pt(e)], fim: false };
      tracos.push(atual); fila.push({ tipo: "traco", t: atual, enviado: 0 }); pedirDesenho();
    });
    cv.addEventListener("pointermove", (e) => {
      if (!atual) return;
      let n = totalPts();
      for (const ev of e.getCoalescedEvents ? e.getCoalescedEvents() : [e]) {
        const p = pt(ev), u = atual.pts.at(-1);
        if (Math.abs(p[0] - u[0]) + Math.abs(p[1] - u[1]) >= 3 && n < TETO) { atual.pts.push(p); n++; }
      }
      pedirDesenho();
    });
    const solta = () => { if (atual) { atual.fim = true; atual = null; } };
    cv.addEventListener("pointerup", solta);
    cv.addEventListener("pointercancel", solta);
    cv.addEventListener("lostpointercapture", solta);
  }
  const podeDesenhar = () => est && est.fase === "desenho" && euDesenho() && tela === "ao-vivo";
  async function enviarFila() {
    if (enviando || !fila.length) return;
    const item = fila[0];
    let corpo;
    if (item.tipo === "traco") {
      const t = item.t, pts = t.pts.slice(item.enviado, item.enviado + PEDACO);
      const fim = t.fim && item.enviado + pts.length >= t.pts.length;
      if (!pts.length && !fim) return; // waiting for the finger
      corpo = { id: t.id, cor: t.cor, esp: t.esp, pts, fim };
    }
    enviando = true;
    item.emVoo = true; // from here on the server may have it: undoing must tell the server
    const status = await acao(item.tipo, corpo);
    enviando = false;
    if (fila[0] !== item) return; // the play changed meanwhile
    if (status === 204) {
      if (item.tipo !== "traco") fila.shift();
      else {
        item.enviado += corpo.pts.length;
        if (corpo.fim) fila.shift();
      }
    } else if (status !== 429 && status !== 0) {
      fila = []; // 409/422: the drawing is over or refused; nothing more to send
    }
  }
  setInterval(enviarFila, 50);
  function desfazer() {
    if (atual) return;
    const t = tracos.pop();
    if (!t) return;
    const i = fila.findIndex((it) => it.t === t);
    if (i >= 0 && fila[i].enviado === 0 && !fila[i].emVoo) fila.splice(i, 1); // the server never saw it
    else fila.push({ tipo: "desfazer" });
    pedirDesenho();
  }
  function limpar() {
    if (atual) return;
    tracos = [];
    fila = fila.filter((it) => it.tipo !== "traco" || it.enviado > 0);
    fila.push({ tipo: "limpar" });
    pedirDesenho();
  }
  function receberTraco(p) {
    const t = tracos.find((x) => x.id === p.id);
    if (t) { t.pts.push(...p.pts); t.fim = p.fim; } else tracos.push({ ...p, pts: [...p.pts] });
    pedirDesenho();
  }

  // ---- pieces of the screen ------------------------------------------------------------------
  function placar({ meta, palavra, aviso, relogio = "" }) {
    const letras = palavra ? palavra.filter((c) => c.k === "acesa" || c.k === "apagada").length : 0;
    return `<div class="placar board" id="pr-placar">
      <div class="placar-top"><span class="lamp meta">${meta}</span><span class="lamp relogio" id="relogio">${relogio}</span></div>
      <div class="palavra" ${palavra ? `style="--n:${palavra.length}" aria-label="Palavra com ${letras} letras"` : ""}>${palavra ? palavra.map(lampada).join("") : `<span class="lamp aviso">${aviso}</span>`}</div>
    </div>`;
  }
  function lampada(c) {
    if (c.k === "vao") return `<span class="l vao"></span>`;
    if (c.k === "sinal") return `<span class="l sinal lamp">${esc(c.t)}</span>`;
    return c.k === "acesa" ? `<span class="l acesa">${esc(c.t.toLocaleUpperCase("pt-BR"))}</span>` : `<span class="l apagada"></span>`;
  }
  const tipo = (c) => (c === " " ? "vao" : /\p{L}/u.test(c) ? "acesa" : "sinal");
  const acesa = (texto) => [...texto].map((t) => ({ t, k: tipo(t) }));
  const daDica = (dica) => dica.map((t) => (t === null ? { k: "apagada" } : { t, k: tipo(t) }));

  function bandeja() {
    const cores = CORES.map((c, i) => (i === 0 ? "" : `<button class="ferr" type="button" data-cor="${i}" aria-label="${NOMES_COR[i]}" aria-pressed="${i === ferramenta.cor}"><span class="giz" style="--c:${c}"></span></button>`)).join("");
    const borracha = `<button class="ferr" type="button" data-cor="0" aria-label="Apagador" aria-pressed="${ferramenta.cor === 0}"><svg width="24" height="20" viewBox="0 0 24 20"><rect x="2" y="5" width="20" height="10" rx="1" fill="#E8E2D2" stroke="#14231A" stroke-width="2"/><rect x="2" y="11" width="20" height="4" fill="#7a6a52"/></svg></button>`;
    const esps = [1, 2, 3].map((e) => `<button class="ferr" type="button" data-esp="${e}" aria-label="Traço ${["", "fino", "médio", "grosso"][e]}" aria-pressed="${e === ferramenta.esp}"><span class="esp" style="width:${[0, 5, 10, 17][e]}px;height:${[0, 5, 10, 17][e]}px"></span></button>`).join("");
    return `<div class="grupo cores">${cores}${borracha}</div><div class="grupo">${esps}</div><div class="grupo"><button class="ferr txt" type="button" data-faz="desfazer">Desfazer</button><button class="ferr txt" type="button" data-faz="limpar">Limpar</button></div>`;
  }
  function cartoes(j) {
    return j.cartoes ? `<span class="vermelho"></span><span class="longo">${j.cartoes} de ${j.cartoes_para_sair} · </span>` : "";
  }
  function jogadoresHtml() {
    const ord = [...est.jogadores].sort((a, b) => b.pontos - a.pontos || a.id - b.id);
    return ord.map((j) => {
      const acertou = j.acertou && est.fase !== "escolha";
      const cls = ["jog", j.id === est.desenhista && est.fase !== "espera" && "desenha", acertou && "acertou", !j.presente && "ausente", souEu(j.id) && "voce"].filter(Boolean).join(" ");
      const ganho = ganhos[j.id] ? ` +${ganhos[j.id]}` : "";
      const st = !j.presente ? "ausente"
        : j.id === est.desenhista ? `<span class="curto">desenha</span><span class="longo">desenhando</span>`
        : acertou ? `<span class="curto">acertou</span><span class="longo">acertou${ganho}</span>`
        : j.anfitriao ? `<span class="selo">anfitrião</span>` : "chutando";
      const btn = souEu(j.id)
        ? `<button class="card-btn vazio" tabindex="-1" aria-hidden="true"></button>`
        : `<button class="card-btn" type="button" aria-label="Cartão vermelho para ${esc(j.apelido)}" data-cartao="${j.id}"><i></i></button>`;
      return `<li class="${cls}" data-jog="${j.id}"><span class="nome">${esc(j.apelido)}${souEu(j.id) ? " <i>você</i>" : ""}</span><span class="st">${cartoes(j)}${st}</span><span class="pts">${j.pontos}<small>pts</small></span>${btn}</li>`;
    }).join("");
  }
  function vaga(j, novo) {
    const st = j.anfitriao ? `<span class="selo">anfitrião</span>` : !j.presente ? "ausente" : novo ? "acabou de entrar" : "pronto";
    return `<li class="jog${novo ? " entrando" : ""}${souEu(j.id) ? " voce" : ""}${j.presente ? "" : " ausente"}" data-jog="${j.id}"><span class="nome">${esc(j.apelido)}${souEu(j.id) ? " <i>você</i>" : ""}</span><span class="st">${cartoes(j)}${st}</span><span class="pts"></span></li>`;
  }
  const vazias = (n) => "<li class='vazia'>vaga</li>".repeat(Math.max(0, n));
  const trocar = (el, html) => { if (el && el.__html !== html) { el.innerHTML = html; el.__html = html; } };
  const ZAP = `https://wa.me/?text=${encodeURIComponent(`Bora desenhar na Prancheta da Geral? Entra na sala: ${LINK}`)}`;

  // ---- feed ----------------------------------------------------------------------------------
  let feedNoFim = true; // keeps the newest guess in view, unless I scrolled up to read
  function noFeed(html, cls = "") {
    const ol = $("#feed");
    if (!ol) return;
    ol.insertAdjacentHTML("beforeend", `<li${cls ? ` class="${cls}"` : ""}>${html}</li>`);
    while (ol.children.length > 120) ol.firstElementChild.remove();
    if (feedNoFim) ol.scrollTop = ol.scrollHeight;
  }
  const sis = (t) => noFeed(esc(t), "sis");

  // ---- screens before the room: create, join, notices ----------------------------------------
  function telaCriar(erro = "") {
    tela = "criar";
    palco.className = "palco";
    palco.innerHTML = `<div class="espera">
      ${placar({ meta: "Sala nova", aviso: "Monte a sala", relogio: `0/${MAX_JOGADORES}` })}
      <form class="ticket" id="pr-criar">
        <h2>Nova sala</h2>
        <p>Escolha seu apelido e quantas rodadas. Depois é só mandar o link no grupo.</p>
        <label class="campo-f"><span>Seu apelido</span><input class="pr-apelido" id="pr-apelido" maxlength="16" minlength="2" required autocomplete="nickname" spellcheck="false" placeholder="Como a turma te chama"></label>
        <fieldset class="campo-f"><legend>Rodadas · cada um desenha uma vez por rodada</legend><div class="chips" id="pr-rodadas">
          ${[1, 2, 3].map((n) => `<button class="chip" type="button" data-rodadas="${n}" aria-pressed="${n === 2}">${n}</button>`).join("")}</div></fieldset>
        <p class="pr-erro" role="alert"${erro ? "" : " hidden"}>${esc(erro)}</p>
        <button class="btn lamp-btn" type="submit">Criar sala</button>
        <p class="fine">Quem cria é o anfitrião: começa a partida e pode tirar quem atrapalhar.</p>
      </form>
      <div class="ticket pr-so-pc"><h2>Na sala</h2><ul class="vagas">${vazias(MAX_JOGADORES)}</ul></div>
    </div>`;
    const chips = $("#pr-rodadas");
    chips.addEventListener("click", (e) => {
      const b = e.target.closest(".chip");
      if (b) chips.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", c === b));
    });
    $("#pr-criar").addEventListener("submit", async (e) => {
      e.preventDefault();
      const botao = e.target.querySelector("[type=submit]");
      botao.disabled = true;
      const rodadas = +$("[aria-pressed=true]", chips).dataset.rodadas;
      const { status, dados } = await postar("/salas", { apelido: $("#pr-apelido").value.trim(), rodadas });
      if (status === 200 || status === 201) {
        gravar(dados.id, { jogador: dados.jogador, token: dados.token });
        location.href = `/jogos/prancheta/s/${dados.id}`;
        return;
      }
      botao.disabled = false;
      mostrarErro(e.target, status === 429 ? "Muitas salas criadas daqui agora há pouco. Tente daqui a um tempo." : erroApelido(status));
    });
  }
  function telaEntrar(nota = "") {
    tela = "entrar";
    palco.className = "palco";
    palco.innerHTML = `<div class="espera so">
      ${placar({ meta: `Sala ${esc(SALA)}`, aviso: "Entre com um apelido" })}
      <form class="ticket" id="pr-entrar">
        <h2>Entrar na sala</h2>
        <p>${esc(nota || "Te chamaram para desenhar e adivinhar. Escolha um apelido e peça para entrar: o anfitrião aceita.")}</p>
        <label class="campo-f"><span>Seu apelido</span><input class="pr-apelido" id="pr-apelido" maxlength="16" minlength="2" required autocomplete="nickname" spellcheck="false" placeholder="Como a turma te chama"></label>
        <p class="pr-erro" role="alert" hidden></p>
        <button class="btn lamp-btn" type="submit">Pedir para entrar</button>
      </form>
    </div>`;
    $("#pr-entrar").addEventListener("submit", async (e) => {
      e.preventDefault();
      const botao = e.target.querySelector("[type=submit]");
      botao.disabled = true;
      const { status, dados } = await postar(`/salas/${SALA}/entrar`, { apelido: $("#pr-apelido").value.trim() });
      if (status === 200 || status === 201) {
        eu = { jogador: dados.jogador, token: dados.token, pendente: true };
        gravar(SALA, eu);
        conectar();
        return;
      }
      botao.disabled = false;
      if (status === 404) return aviso("A sala acabou", "A sala acabou ou o servidor reiniciou. Crie outra e mande o link de novo.");
      if (status === 409) return mostrarErro(e.target, "Muita gente pedindo para entrar agora, ou a partida já acabou. Tente daqui a pouco.");
      mostrarErro(e.target, erroApelido(status));
    });
  }
  // By the HTTP status and the action only: the server's reason is for logs, not for screens.
  function erroApelido(status) {
    if (status === 0) return "Sem conexão. Tente de novo.";
    if (status === 422) return "Esse apelido não vale: de 2 a 16 caracteres, sem palavrão e diferente dos outros na sala.";
    if (status === 429) return "Calma: muitas tentativas seguidas. Espere um pouco e tente de novo.";
    return "Não deu certo agora. Tente de novo.";
  }
  function mostrarErro(form, texto) {
    const p = $(".pr-erro", form);
    p.textContent = texto;
    p.hidden = false;
  }
  function aviso(titulo, texto, sumula = false) {
    tela = "aviso";
    pararFonte();
    $("#pr-sair-box").hidden = true;
    $("#pr-pedidos").hidden = true;
    palco.className = "palco";
    palco.innerHTML = `<div class="espera so">
      ${placar({ meta: SALA ? `Sala ${esc(SALA)}` : "Prancheta", aviso: esc(titulo) })}
      <div class="ticket"><h2>${esc(titulo)}</h2><p>${esc(texto)}</p>
        <div class="acoes"><a class="btn lamp-btn" href="/jogos/prancheta">Nova sala</a>${sumula ? `<a class="btn secondary" href="/jogos/prancheta/s/${esc(SALA)}">Ver a súmula</a>` : ""}</div></div>
    </div>`;
  }

  // ---- asked to join: waiting for the host's answer ----------------------------------------------
  function telaPedido() {
    const html = `<b>${esc(est.apelido)}</b>`;
    const quem = est.anfitriao ? esc(est.anfitriao) : "o anfitrião";
    if (tela !== "pedido") {
      tela = "pedido";
      $("#pr-sair-box").hidden = true;
      palco.className = "palco";
      palco.innerHTML = `<div class="espera so">
        ${placar({ meta: `Sala ${esc(SALA)}`, aviso: "Pedindo para entrar" })}
        <div class="ticket pr-pedido">
          <h2>Pedido enviado</h2>
          <p id="pr-pedido-texto"></p>
          <p class="pr-aguarde"><span class="lampadinha"></span><span class="lampadinha"></span><span class="lampadinha"></span> esperando a resposta</p>
          <p class="fine">Deixe esta página aberta. Se fechar por mais de 30 segundos, o pedido cai.</p>
        </div>
      </div>`;
    }
    $("#pr-pedido-texto").innerHTML = `Você pediu para entrar como ${html}. Agora é com ${quem}: quando aceitar, a sala abre aqui.`;
  }
  function recusado() {
    esquecer();
    eu = null;
    aviso("Pedido recusado", "O anfitrião não aceitou o pedido desta vez. Sem problema: dá para criar a sua sala e chamar a sua turma.");
  }

  // The host's answer box: who asked to join, over whatever screen is on.
  function mostrarPedidos() {
    const caixa = $("#pr-pedidos");
    const lista = est && est.pedidos && tela !== "fim" && tela !== "aviso" ? est.pedidos : [];
    caixa.hidden = !lista.length;
    trocar(caixa, lista.length ? `<p class="lamp pr-pedidos-tit">Pede${lista.length > 1 ? "m" : ""} para entrar</p><ul>${lista.map((p) =>
      `<li data-pedido="${p.id}"><b>${esc(p.apelido)}</b><span class="pr-pedido-nota" hidden></span><button class="btn lamp-btn" type="button" data-resposta="aceitar">Aceitar</button><button class="btn secondary" type="button" data-resposta="recusar">Recusar</button></li>`).join("")}</ul>` : "");
  }
  $("#pr-pedidos").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-resposta]");
    if (!b) return;
    const li = b.closest("li");
    li.querySelectorAll("button").forEach((x) => (x.disabled = true));
    const status = await acao(b.dataset.resposta, { pedido: +li.dataset.pedido });
    if (status === 204) return; // the next `estado` takes the request away
    li.querySelectorAll("button").forEach((x) => (x.disabled = false));
    const nota = $(".pr-pedido-nota", li);
    nota.hidden = false;
    nota.textContent = status === 409 ? "sala cheia" : "não deu, tente de novo";
  });

  // ---- the waiting room ------------------------------------------------------------------------
  let conhecidos = null; // ids already in the waiting room, to animate who just arrived
  function telaEspera() {
    const anfitriao = jogador(eu.jogador).anfitriao;
    const n = est.jogadores.length;
    if (tela !== "espera") {
      tela = "espera";
      palco.className = "palco";
      palco.innerHTML = `<div class="espera">
        <div id="pr-placar-box" class="placar-box"></div>
        <div class="ticket">
          <h2>Chame a turma</h2>
          <p>Mande o link no grupo. Quem abrir escolhe um apelido e pede para entrar; o anfitrião aceita.</p>
          <div class="link"><code>${esc(LINK)}</code><button class="btn" type="button" id="pr-copiar">Copiar</button></div>
          <div class="acoes"><a class="btn secondary" href="${ZAP}" target="_blank" rel="noopener">Mandar no Zap</a></div>
          <p class="pr-rodadas" id="pr-rodadas-info"></p>
          <button class="btn lamp-btn" type="button" id="pr-comecar">Começar a partida</button>
          <p class="fine" id="pr-comecar-nota"></p>
        </div>
        <div class="ticket"><h2>Na sala</h2><ul class="vagas" id="vagas"></ul></div>
      </div>`;
      $("#pr-copiar").addEventListener("click", (e) => copiar(e.target));
      $("#pr-comecar").addEventListener("click", async (e) => {
        e.target.disabled = true;
        const status = await acao("comecar");
        if (status !== 204) e.target.disabled = false;
      });
    }
    // the outer box keeps the grid's first row
    trocar($("#pr-placar-box"), placar({ meta: `Sala ${esc(SALA)}`, aviso: anfitriao ? "Esperando a turma" : "Esperando o anfitrião", relogio: `${n}/${MAX_JOGADORES}` }));
    $("#pr-rodadas-info").textContent = `${est.rodadas} rodada${est.rodadas > 1 ? "s" : ""} · cada um desenha uma vez por rodada`;
    const botao = $("#pr-comecar");
    const prontos = presentes().length;
    botao.hidden = !anfitriao;
    botao.disabled = prontos < 2;
    $("#pr-comecar-nota").textContent = !anfitriao
      ? `Só o anfitrião começa. Quando ${nome(est.jogadores.find((j) => j.anfitriao)?.id)} começar, a prancheta abre aqui.`
      : prontos < 2 ? "Precisa de pelo menos 2 na sala para começar." : "Quem chegar depois entra na fila da rodada.";
    const antes = conhecidos;
    conhecidos = new Set(est.jogadores.map((j) => j.id));
    trocar($("#vagas"), est.jogadores.map((j) => vaga(j, antes && !antes.has(j.id))).join("") + vazias(MAX_JOGADORES - n));
  }
  async function copiar(botao) {
    try {
      await navigator.clipboard.writeText(LINK);
      botao.textContent = "Copiado";
    } catch {
      /* the link is on screen to copy by hand */
    }
  }

  // ---- the live stage --------------------------------------------------------------------------
  let observadores = [];
  function montarAoVivo() {
    tela = "ao-vivo";
    palco.className = "palco ao-vivo";
    palco.innerHTML = `<div id="pr-placar-box" class="placar-box"></div>
      <div class="quadro" id="quadro"><div class="prancheta"><div class="lousa" id="lousa"><canvas aria-label="Prancheta de desenho"></canvas><div id="sobre"></div></div></div></div>
      <div class="bandeja" id="bandeja" role="toolbar" aria-label="Giz e apagador"></div>
      <div class="lado">
        <ul class="jogadores" id="jogadores" aria-label="Jogadores"></ul>
        <div class="feed"><h3>Chutes <span id="feed-sub"></span></h3><ol id="feed"></ol></div>
        <form class="entrada" id="chutar"><input id="chute" maxlength="40" autocomplete="off" spellcheck="false" enterkeyhint="send" placeholder="Seu chute" aria-label="Seu chute"><button class="btn" type="submit">Chutar</button></form>
        <div class="entrada" id="nota"><span class="nota" id="nota-texto"></span></div>
        <div class="entrada vez" id="vez"><button class="btn lamp-btn" type="button" id="pr-dica"></button><button class="btn secondary" type="button" id="pr-pular">Pular a vez</button></div>
      </div>`;
    lousa = $("#lousa"); cv = $("canvas", lousa); ctx = cv.getContext("2d"); padroes = {};
    observadores.forEach((o) => o.disconnect()); // the last stage's, if any
    observadores = [new ResizeObserver(ajustarCanvas), new ResizeObserver(encaixar)];
    observadores[0].observe(lousa);
    observadores[1].observe($("#quadro"));
    ligarDesenho();
    $("#bandeja").addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.cor) ferramenta.cor = +b.dataset.cor;
      if (b.dataset.esp) ferramenta.esp = +b.dataset.esp;
      if (b.dataset.faz === "desfazer") desfazer();
      if (b.dataset.faz === "limpar") limpar();
      $("#bandeja").querySelectorAll("[data-cor]").forEach((x) => x.setAttribute("aria-pressed", +x.dataset.cor === ferramenta.cor));
      $("#bandeja").querySelectorAll("[data-esp]").forEach((x) => x.setAttribute("aria-pressed", +x.dataset.esp === ferramenta.esp));
    });
    $("#sobre").addEventListener("click", async (e) => {
      const b = e.target.closest(".opcao");
      if (!b || b.disabled) return;
      $("#sobre").querySelectorAll(".opcao").forEach((o) => (o.disabled = true));
      escolhida = +b.dataset.i;
      if ((await acao("escolher", { indice: escolhida })) !== 204) {
        $("#sobre").querySelectorAll(".opcao").forEach((o) => (o.disabled = false));
      }
    });
    $("#pr-dica").addEventListener("click", async (e) => {
      e.target.disabled = true;
      if ((await acao("dica")) === 204) sis("Você acendeu uma letra para a turma."); // the new `estado` redraws the button
      botaoDica();
    });
    $("#pr-pular").addEventListener("click", async (e) => {
      if (!confirm("Pular a sua vez? A palavra aparece para todos, os pontos ficam e o jogo segue.")) return;
      e.target.disabled = true;
      if ((await acao("pular")) !== 204) e.target.disabled = false;
    });
    $("#chutar").addEventListener("submit", async (e) => {
      e.preventDefault();
      const campo = $("#chute"), texto = campo.value.trim();
      if (!texto) return;
      const status = await acao("chute", { texto });
      if (status === 204 || status === 409) campo.value = "";
    });
    $("#feed").addEventListener("scroll", (e) => {
      const ol = e.target;
      feedNoFim = ol.scrollHeight - ol.scrollTop - ol.clientHeight < 40;
    });
    $("#chute").addEventListener("focus", () => setTimeout(teclado, 300));
    $("#chute").addEventListener("blur", () => setTimeout(teclado, 300));
    $("#jogadores").addEventListener("click", (e) => {
      const alvo = e.target.closest("[data-cartao]") || (!desktop() && e.target.closest(".jog"));
      if (!alvo) return;
      const id = +(alvo.dataset.cartao || alvo.dataset.jog);
      if (!souEu(id)) abrirCartao(id);
    });
    requestAnimationFrame(() => scrollTo(0, palco.getBoundingClientRect().top + scrollY - 8));
  }
  function telaAoVivo() {
    if (tela !== "ao-vivo") montarAoVivo();
    const d = est.desenhista, desenho = est.fase === "desenho", rodada = `Rodada ${est.rodada} de ${est.rodadas}`;
    // the scoreboard
    let p;
    if (est.fase === "escolha") {
      p = euDesenho() ? { meta: `${rodada} · sua vez`, aviso: "Escolha o que desenhar" } : { meta: `${rodada} · ${esc(nome(d))} desenha`, aviso: `${esc(nome(d))} escolhe a palavra` };
    } else if (desenho) {
      p = euDesenho() ? { meta: `${rodada} · você desenha`, palavra: acesa(est.palavra || "") } : { meta: `${rodada} · ${esc(nome(d))} desenha`, palavra: daDica(est.dica || []) };
    } else {
      p = { meta: `Fim do lance · ${rodada}`, palavra: acesa(est.palavra || "") };
    }
    trocar($("#pr-placar-box"), placar(p));
    // what lies over the board
    let sobre = "";
    if (est.fase === "escolha" && euDesenho() && est.opcoes) {
      opcoesDoLance = est.opcoes;
      sobre = `<div class="sobre escuro"><div class="opcoes"><h3>Sua vez de desenhar</h3>${est.opcoes.map((o, i) => {
        const [n, v] = DIF[o.dificuldade] || ["", ""];
        return `<button class="opcao" type="button" data-i="${i}"><span class="nivel">${n}</span><b>${esc(o.texto)}</b><span class="vale">vale até ${v} pts</span></button>`;
      }).join("")}</div></div>`;
    } else if (est.fase === "escolha") {
      sobre = `<div class="sobre escuro"><p class="giz-texto">${esc(nome(d))} está escolhendo<small>A prancheta abre quando a palavra for escolhida.</small></p></div>`;
    } else if (est.fase === "intervalo") {
      sobre = `<div class="sobre escuro">${recorte()}</div>`;
    }
    trocar($("#sobre"), sobre);
    // the tray: only for whoever draws
    const comBandeja = desenho && euDesenho();
    palco.classList.toggle("sem-bandeja", !comBandeja);
    $("#bandeja").hidden = !comBandeja;
    trocar($("#bandeja"), comBandeja ? bandeja() : "");
    lousa.classList.toggle("pode", comBandeja);
    trocar($("#jogadores"), jogadoresHtml());
    // the guess box, or a note in its place
    const eu_ = jogador(eu.jogador);
    const chuta = desenho && !euDesenho() && eu_ && !eu_.acertou;
    const minhaVez = euDesenho() && (desenho || est.fase === "escolha");
    $("#chutar").hidden = !chuta;
    $("#nota").hidden = chuta || minhaVez;
    $("#vez").hidden = !minhaVez;
    $("#pr-dica").hidden = !desenho;
    $("#pr-pular").disabled = false;
    $("#nota-texto").textContent =
      est.fase === "escolha" ? (euDesenho() ? "Escolha uma palavra. Sem escolher, sai no sorteio." : `${nome(d)} está escolhendo a palavra.`)
      : desenho && euDesenho() ? "Na sua vez você não chuta. Desenhe!"
      : desenho && eu_ && eu_.acertou ? `Você acertou${ganhos[eu.jogador] ? ` +${ganhos[eu.jogador]}` : ""}! Agora é torcer.`
      : "Intervalo. O próximo lance começa já.";
    if (!chuta && document.activeElement === $("#chute")) $("#chute").blur();
    botaoDica();
    subtitulo();
    tic();
    encaixar();
    if (feedNoFim) $("#feed").scrollTop = $("#feed").scrollHeight; // the tray took or gave room
  }
  function recorte() {
    const certos = est.jogadores.filter((j) => j.acertou && j.id !== est.desenhista);
    const total = quemChuta().length;
    const op = opcoesDoLance && opcoesDoLance.find((o) => o.texto === est.palavra);
    const dif = op && DIF[op.dificuldade] ? `${DIF[op.dificuldade][0].toLowerCase()} · ` : "";
    const linhas = certos.map((j) => `<li>${esc(j.apelido)} <b>${ganhos[j.id] ? `+${ganhos[j.id]}` : "✓"}</b></li>`);
    if (certos.length && jogador(est.desenhista)) linhas.push(`<li>${esc(nome(est.desenhista))} (assist.) <b>+${2 * certos.length}</b></li>`);
    if (!est.palavra) {
      return `<div class="recorte"><div class="kicker"><span>Lance</span><span>sem desenho</span></div><h2>${pulou ? "Pulou a vez" : "Sem desenho"}</h2><p class="proximo">O próximo lance começa já.</p></div>`;
    }
    return `<div class="recorte"><div class="kicker"><span>Era</span><span>${dif}${certos.length} de ${Math.max(total, certos.length)} acertaram</span></div><h2>${esc(est.palavra)}</h2>
      ${linhas.length ? `<ul>${linhas.join("")}</ul>` : ""}<p class="proximo">${pulou ? `${esc(nome(est.desenhista))} pulou a vez. ` : certos.length ? "" : "Ninguém acertou. "}O próximo lance começa já.</p></div>`;
  }
  function subtitulo() {
    const sub = $("#feed-sub");
    if (!sub || !est) return;
    if (est.fase !== "desenho") return (sub.textContent = "");
    const s = restam(), faltam = quemChuta().filter((j) => !j.acertou).length;
    sub.textContent = `${faltam} chutando`;
  }
  // The drawer's hint: locked until its time, then one tap lights a letter for the others.
  const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  function botaoDica() {
    const b = $("#pr-dica");
    if (!b || !est || !est.dicas || b.hidden) return;
    const { dadas, marcos } = est.dicas, agora = Date.now() + diferenca;
    const liberadas = marcos.filter((m) => Date.parse(m) <= agora).length;
    let texto, pode = false, travada = false;
    if (!marcos.length) texto = "Sem dica: palavra curta";
    else if (dadas >= marcos.length) texto = "Dicas dadas";
    else if (dadas < liberadas) { texto = marcos.length > 1 ? `Dar dica ${dadas + 1} de ${marcos.length}` : "Dar dica"; pode = true; }
    else { texto = `Dica aos ${fmt(Math.round((Date.parse(est.prazo) - Date.parse(marcos[dadas])) / 1000))}`; travada = true; }
    const html = `${travada ? `<svg class="cadeado" width="12" height="15" viewBox="0 0 12 15" aria-hidden="true"><path d="M3 7V4.5a3 3 0 0 1 6 0V7" fill="none" stroke="currentColor" stroke-width="2"/><rect x="1" y="7" width="10" height="7.5" fill="currentColor"/></svg>` : ""}${texto}`;
    if (b.__html !== html) { b.innerHTML = html; b.__html = html; }
    b.disabled = !pode;
    b.classList.toggle("travada", travada);
  }

  // Fit the 4:3 board in its slot: by width on a phone, by width and height on a computer (and
  // on a phone with the keyboard open, where the board gives up height for the guess box).
  function encaixar() {
    const slot = $("#quadro"), l = $("#lousa");
    if (!slot || !l) return;
    const moldura = 2 * (9 + 3);
    let w = slot.clientWidth - moldura;
    if (desktop() || palco.classList.contains("teclado")) w = Math.min(w, ((slot.clientHeight - moldura) * 4) / 3);
    w = Math.max(80, Math.floor(w));
    const h = Math.round((w * 3) / 4);
    if (l.style.width !== `${w}px` || l.style.height !== `${h}px`) { l.style.width = `${w}px`; l.style.height = `${h}px`; }
  }
  addEventListener("resize", encaixar);
  // The phone's keyboard over the guess box: the stage shrinks to what is left of the screen.
  function teclado() {
    const vv = window.visualViewport;
    const aberto = Boolean(vv && !desktop() && document.activeElement === $("#chute") && innerHeight - vv.height > 120);
    if (aberto) palco.style.setProperty("--vv-h", `${Math.round(vv.height)}px`);
    if (palco.classList.contains("teclado") !== aberto) {
      palco.classList.toggle("teclado", aberto);
      encaixar();
    }
    if (aberto) $("#chutar").scrollIntoView({ block: "end" });
  }
  if (window.visualViewport) visualViewport.addEventListener("resize", () => tela === "ao-vivo" && teclado());

  // The red card: anyone votes; the host can also send off at once.
  let alvoCartao = null;
  const dialogo = $("#pr-cartao");
  function abrirCartao(id) {
    alvoCartao = id;
    preencherCartao();
    dialogo.showModal();
  }
  function preencherCartao() {
    const j = jogador(alvoCartao);
    if (!j) return dialogo.open && dialogo.close();
    $("#pr-cartao-nome").textContent = j.apelido;
    const precisa = j.cartoes_para_sair || 1, tem = j.cartoes || 0;
    $("#pr-cartao-votos").innerHTML = `${Array.from({ length: precisa }, (_, i) => `<i${i < tem ? ' class="on"' : ""}></i>`).join("")} ${tem} de ${precisa} cart${precisa > 1 ? "ões" : "ão"}`;
    $("#pr-cartao-tirar").hidden = !(eu && jogador(eu.jogador) && jogador(eu.jogador).anfitriao);
  }
  dialogo.querySelectorAll("[data-fecha]").forEach((b) => b.addEventListener("click", () => dialogo.close()));
  dialogo.addEventListener("click", (e) => { if (e.target === dialogo) dialogo.close(); });
  $("#pr-cartao-dar").addEventListener("click", async () => { await acao("cartao", { alvo: alvoCartao }); dialogo.close(); });
  $("#pr-cartao-tirar").addEventListener("click", async () => { await acao("tirar", { alvo: alvoCartao }); dialogo.close(); });
  $("#pr-sair").addEventListener("click", async () => {
    if (!confirm("Sair da sala? Seus pontos ficam na súmula.")) return;
    saindo = true;
    await acao("sair");
    esquecer();
    aviso("Você saiu da sala", "Seus pontos ficam na súmula quando a partida acabar.");
  });

  // ---- the end: the súmula, as the room's link shows it ---------------------------------------
  async function telaFim() {
    if (tela === "fim") return;
    tela = "fim";
    pararFonte();
    $("#pr-sair-box").hidden = true;
    $("#pr-pedidos").hidden = true;
    const ord = [...est.jogadores].sort((a, b) => b.pontos - a.pontos);
    palco.className = "palco";
    palco.innerHTML = `<div class="placar board campeao"><span class="lamp">Fim de jogo${ord.length ? ` · ${esc(ord[0].apelido)}` : ""}</span><span class="lamp n">${ord.length ? ord[0].pontos : 0} pts</span></div>
      <div class="ticket pr-fechando"><h2>Súmula</h2><p>Fechando a súmula…</p></div>`;
    // The súmula is written as the room ends: ask the room's link until it shows it.
    for (let tentativa = 0; tentativa < 8; tentativa++) {
      try {
        const r = await fetch(`/jogos/prancheta/s/${SALA}`, { cache: "no-store" });
        const html = await r.text();
        const sumula = new DOMParser().parseFromString(html, "text/html").getElementById("pr-sumula");
        if (sumula) {
          palco.innerHTML = sumula.innerHTML;
          palco.querySelectorAll("[data-copiar]").forEach((b) => b.addEventListener("click", () => copiar(b)));
          esquecer();
          return;
        }
      } catch {
        /* try again */
      }
      await new Promise((ok) => setTimeout(ok, 750));
    }
    palco.querySelector(".pr-fechando p").innerHTML = `A súmula fica no link da sala. <a href="/jogos/prancheta/s/${esc(SALA)}">Abrir a súmula</a>`;
  }

  // ---- what the server says ---------------------------------------------------------------------
  function narrar(antes, agora) {
    if (tela !== "ao-vivo") return;
    if (!antes) {
      // just arrived on the stage: who draws now
      if (agora.fase === "escolha" || agora.fase === "desenho") sis(`Rodada ${agora.rodada} de ${agora.rodadas}. ${souEu(agora.desenhista) ? "Sua vez de desenhar." : `${nome(agora.desenhista)} desenha.`}`);
      return;
    }
    const ids = new Set(antes.jogadores.map((j) => j.id));
    const novos = new Set(agora.jogadores.map((j) => j.id));
    agora.jogadores.filter((j) => !ids.has(j.id)).forEach((j) => sis(`${j.apelido} entrou na sala.`));
    antes.jogadores.filter((j) => !novos.has(j.id)).forEach((j) => sis(`${j.apelido} saiu da sala.`));
    const lance = antes.desenhista !== agora.desenhista || antes.rodada !== agora.rodada;
    if (agora.fase === "escolha" && (antes.fase !== "escolha" || lance)) {
      sis(`Rodada ${agora.rodada} de ${agora.rodadas}. ${souEu(agora.desenhista) ? "Sua vez de desenhar." : `${nome(agora.desenhista)} desenha.`}`);
    }
    if (agora.fase === "desenho" && antes.fase !== "desenho" && souEu(agora.desenhista) && agora.palavra) {
      const op = (opcoesDoLance || []).find((o) => o.texto === agora.palavra);
      sis(`Você ${escolhida === null ? "tirou no sorteio" : "escolheu"} ${agora.palavra}${op ? ` (${DIF[op.dificuldade][0].toLowerCase()})` : ""}.`);
    }
    if (agora.fase === "intervalo" && antes.fase === "escolha" && pulou) {
      sis(`${souEu(agora.desenhista) ? "Você" : nome(agora.desenhista)} pulou a vez.`);
    }
    if (agora.fase === "intervalo" && antes.fase === "desenho") {
      const chutam = agora.jogadores.filter((j) => j.presente && j.id !== agora.desenhista);
      const motivo = pulou ? `${souEu(agora.desenhista) ? "Você" : nome(agora.desenhista)} pulou a vez.`
        : !agora.jogadores.some((j) => j.id === agora.desenhista && j.presente) ? "Quem desenhava saiu."
        : chutam.length && chutam.every((j) => j.acertou) ? "Todo mundo acertou." : "Acabou o tempo.";
      sis(`${motivo} Era ${agora.palavra}.`);
    }
  }
  function receberEstado(novo) {
    const antes = est;
    est = novo;
    seq = novo.seq;
    tentativas = 0;
    diferenca = Date.parse(novo.agora) - Date.now();
    if (novo.fase === "pedido") return telaPedido();
    if (eu.pendente) { eu = { jogador: eu.jogador, token: eu.token }; gravar(SALA, eu); } // accepted
    mostrarPedidos();
    if (!novo.jogadores.some((j) => souEu(j.id))) {
      // I am no longer in the room: I left, or got the red card
      esquecer();
      if (!saindo) aviso("Cartão vermelho", "Você foi tirado da sala. Dá para criar outra e chamar a sua turma.");
      return;
    }
    $("#pr-sair-box").hidden = novo.fase === "fim";
    // A new play: its points and my strokes start over.
    const chave = `${novo.rodada}:${novo.desenhista}`;
    if (chave !== lanceAtual) { ganhos = {}; opcoesDoLance = null; escolhida = null; pulou = false; lanceAtual = chave; }
    if (novo.fase === "fim") return telaFim();
    if (novo.fase === "espera") return telaEspera();
    // Strokes: the server's, except the drawer's own drawing in progress (never thrown away by
    // an `estado` that arrives while drawing; a reload starts again from the server's copy).
    const meuDesenho = novo.fase === "desenho" && souEu(novo.desenhista) && antes && antes.fase === "desenho" && antes.desenhista === novo.desenhista && antes.rodada === novo.rodada;
    if (!meuDesenho) {
      atual = null; fila = [];
      tracos = novo.tracos.map((t) => ({ ...t, pts: t.pts.map((p) => [...p]) }));
      idTraco = Math.max(0, ...tracos.map((t) => t.id));
    }
    const estava = tela === "ao-vivo";
    telaAoVivo();
    narrar(estava ? antes : null, novo);
    pedirDesenho();
    if (dialogo.open) preencherCartao();
  }
  function receber(tipoEvento, d) {
    if (tipoEvento === "estado") return receberEstado(d);
    if (tipoEvento === "recusado") return recusado();
    if (!est || d.seq <= seq) return; // already in the last `estado`
    seq = d.seq;
    if (tipoEvento === "fim") return tela === "pedido" ? caiu() : telaFim();
    if (tela !== "ao-vivo") return;
    if (tipoEvento === "pulou") { pulou = true; return; }
    if (tipoEvento === "traco") return receberTraco(d);
    if (tipoEvento === "desfazer") { tracos = tracos.filter((t) => t.id !== d.id); return pedirDesenho(); }
    if (tipoEvento === "limpar") { tracos = []; return pedirDesenho(); }
    if (tipoEvento === "dica") { est.dica = d.dica; sis(`${nome(est.desenhista)} acendeu uma letra.`); return telaAoVivo(); }
    if (tipoEvento === "chute") return noFeed(`<b>${esc(nome(d.jogador))}:</b> ${esc(d.texto)}`);
    if (tipoEvento === "trave") return noFeed(`<b>Na trave!</b> “${esc(d.texto)}” passou perto.<small>Só você vê este aviso.</small>`, "trave");
    if (tipoEvento === "acerto") {
      const j = jogador(d.jogador), desenhista = jogador(est.desenhista);
      if (j) { j.acertou = true; j.pontos += d.pontos; }
      if (desenhista) { desenhista.pontos += 2; ganhos[desenhista.id] = (ganhos[desenhista.id] || 0) + 2; }
      ganhos[d.jogador] = (ganhos[d.jogador] || 0) + d.pontos;
      noFeed(`<span class="tag">Gol</span> ${souEu(d.jogador) ? "Você" : esc(nome(d.jogador))} acertou <span class="p">+${d.pontos}</span>`, "gol");
      return telaAoVivo();
    }
  }
  const EVENTOS = ["estado", "traco", "desfazer", "limpar", "chute", "acerto", "trave", "dica", "pulou", "recusado", "fim"];
  function conectar() {
    pararFonte();
    fonte = new EventSource(`${API}/salas/${SALA}/eventos?token=${encodeURIComponent(eu.token)}`);
    for (const t of EVENTOS) {
      fonte.addEventListener(t, (e) => {
        try {
          receber(t, JSON.parse(e.data));
        } catch (erro) {
          console.error("prancheta:", t, erro);
        }
      });
    }
    fonte.onerror = () => { if (fonte && fonte.readyState === EventSource.CLOSED) caiu(); };
  }
  function pararFonte() {
    if (fonte) { fonte.close(); fonte = null; }
  }
  // The events stream gave up (the browser retries by itself only on a dropped connection): the
  // room is gone, it is over, my seat is gone, or something in the way failed (a proxy's 502).
  // The seat is forgotten only when the server itself says 403 to my token.
  let checando = false;
  let tentativas = 0; // reconnections in a row without an `estado`, for the growing wait
  function reconectar() {
    const espera = Math.min(30000, 1000 * 2 ** tentativas);
    tentativas++;
    setTimeout(() => { checando = false; if (tela !== "fim" && tela !== "aviso") conectar(); }, espera);
  }
  // A cheap authenticated call with no effect: a red card for myself is always refused (422)
  // when my token is good, 409 while my request waits, 403 when it is gone, 404 with the room.
  async function meuToken() {
    const { status } = await postar(`/salas/${SALA}/acao`, { token: eu.token, tipo: "cartao", alvo: eu.jogador });
    return status;
  }
  async function caiu() {
    if (checando || tela === "fim" || tela === "aviso") return;
    checando = true;
    pararFonte();
    try {
      const r = await fetch(`/jogos/prancheta/s/${SALA}`, { cache: "no-store" });
      const html = await r.text();
      if (r.status === 404) {
        esquecer(); // the room is gone: its seat with it
        aviso("A sala acabou", "A sala acabou ou o servidor reiniciou. Crie outra e mande o link de novo.");
      }
      else if (html.includes('id="pr-sumula"')) location.reload();
      else if (r.ok && (await meuToken()) === 403) {
        const pedia = eu.pendente;
        esquecer(); eu = null; est = null; tela = "";
        telaEntrar(pedia ? "Seu pedido para entrar caiu. Peça de novo com um apelido." : "Seu lugar na sala caiu. Entre de novo com um apelido.");
      } else return reconectar();
    } catch {
      return reconectar();
    }
    checando = false;
  }

  // ---- the clock: the server's deadline, corrected by the difference of clocks ----------------
  function tic() {
    const el = $("#relogio");
    if (!el || !est || tela !== "ao-vivo") return;
    const s = restam();
    el.innerHTML = `${Math.floor(s / 60)}<span class="dp"></span>${String(s % 60).padStart(2, "0")}`;
    el.classList.toggle("fim", est.fase !== "intervalo" && s <= 10);
    subtitulo();
    botaoDica();
  }
  setInterval(tic, 250);

  if (!SALA) telaCriar();
  else if (!eu) telaEntrar();
  else conectar();
})();
