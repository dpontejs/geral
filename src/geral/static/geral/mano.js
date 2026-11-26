// Mano a Mano: the live room (docs/features/mano-a-mano.md). The server owns the rules, the clock
// and the result; this page draws what each `estado` says and sends my choices. Every `estado`
// (on connecting and on every change) is the whole room, so a reload or a reconnect rebuilds the
// screen from it: the kick being chosen, the run-up already under way, the end. The 3D scene is
// mano-cena.js; the screens around it (create, join, waiting, the end) are drawn here. My token
// for the room stays in localStorage (`mano:<id>`).
import { criarCena, letreiroDoLance } from "/static/geral/mano-cena.js";
import { faixaBoa, faixaCavadinha } from "/static/geral/mano-faixa.js";
import { visual } from "/static/geral/mano-visual.js";

const raiz = document.getElementById("mano");
const API = "/api/jogos/mano";
let SALA = raiz.dataset.sala;
const PUBLICO = (raiz.dataset.url || location.origin).replace(/\/$/, "");
const linkDa = (id) => `${PUBLICO}/jogos/mano/s/${id}`;
const palco = document.getElementById("palco");
const palcoCena = document.getElementById("mn-palco");
const cenaEl = document.getElementById("mn-cena");
const sairBox = document.getElementById("mn-sair-box");
const $ = (s, el = document) => el.querySelector(s);
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

const MODOS = { penaltis: "Pênaltis", faltas: "Faltas" };
// Free kicks can be off on the server (MANO_FALTAS): then the form offers only penalties.
const MODOS_OFERTA = raiz.dataset.faltas ? MODOS : { penaltis: MODOS.penaltis };
const BOTS = { facil: "Bot fácil", medio: "Bot médio", dificil: "Bot difícil" };
// The Geral's six teams (geral/games/mano/times.py): each player wears one.
const TIMES = { abc: "ABC", csa: "CSA", flamengo: "Flamengo", nautico: "Náutico", palmeiras: "Palmeiras", vasco: "Vasco" };
const ERROS = {
  "nickname must have 2 to 16 characters": "O apelido precisa ter de 2 a 16 letras.",
  "nickname not allowed": "Esse apelido não pode. Escolha outro.",
  "nickname already in the room": "Esse apelido já está na sala. Escolha outro.",
  "too many rooms, try later": "Muitas salas criadas daqui agora. Tente de novo daqui a pouco.",
  "unknown team": "Escolha o seu time.",
};

// The last team picked, so the next form comes with it marked (a convenience: may be empty).
function timeGuardado() {
  try {
    const t = localStorage.getItem("mano:time");
    return t in TIMES ? t : null;
  } catch {
    return null;
  }
}
function guardarTime(t) {
  try {
    localStorage.setItem("mano:time", t);
  } catch {
    /* private mode */
  }
}
const campoTime = () =>
  `<fieldset class="campo-f"><legend>Seu time</legend><div class="chips mn-times" id="mn-time">${chips("time", TIMES, timeGuardado())}</div></fieldset>`;
/** The marked team, or an error on the form when none is. */
function timeEscolhido() {
  const t = marcado($("#mn-time"), "time");
  if (!t) {
    const p = $(".pr-erro");
    p.textContent = "Escolha o seu time.";
    p.hidden = false;
  }
  return t;
}

// ---- my seat in the room -------------------------------------------------------------------
const chave = (id) => `mano:${id}`;
function ler(id) {
  try {
    return JSON.parse(localStorage.getItem(chave(id)));
  } catch {
    return null;
  }
}
function gravar(id, valor) {
  try {
    localStorage.setItem(chave(id), JSON.stringify(valor));
  } catch {
    /* private mode: this tab still plays, a reload asks for a nickname again */
  }
}
function esquecer() {
  try {
    localStorage.removeItem(chave(SALA));
  } catch {
    /* nothing kept */
  }
}
let eu = SALA ? ler(SALA) : null; // {jogador, token}

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

// ---- the room as the server last told it ------------------------------------------------------
let est = null; // the last `estado`
let recebido = 0; // performance.now() when `est` arrived
let fonte = null;
let tela = ""; // criar | entrar | espera | jogo | fim | aviso
let cena = null;

// The kick's identity: the match and how many kicks were taken before it.
const lanceDe = (e) => `${e.partida}:${e.serie[0].length + e.serie[1].length}`;
let montado = ""; // the kick the scene is set for (position, wall, camera)
let barreiraMontada = ""; // the wall the scene shows, as JSON
let pedido = ""; // `${lance}:${fase}` of the choice the scene is asking for
let cobrando = ""; // the kick being animated
let entregarLance = null; // resolves the animated kick's Promise with the real lance
let saidaEnviada = false;
let letreiroDe = ""; // the kick whose sign was put up without its animation

/** A server time (ISO) as this page's performance.now(), by the clocks of the last `estado`. */
const local = (iso, agoraIso = est.agora, base = recebido) => base + (Date.parse(iso) - Date.parse(agoraIso));
const restam = () => (est && est.prazo ? Math.max(0, (local(est.prazo) - performance.now()) / 1000) : 0);
const outro = () => (est ? est.jogadores[1 - est.voce] : null);
const nome = (i) => (est && est.jogadores[i] ? est.jogadores[i].apelido : "");

function garantirCena() {
  palcoCena.hidden = false;
  if (cena) return cena;
  cena = criarCena(cenaEl, { papel: est.papel || "batedor", modo: est.modo });
  cena.onSaida(() => {
    if (saidaEnviada) return;
    saidaEnviada = true;
    acao("saida");
  });
  palcoCena.scrollIntoView({ block: "start", behavior: "smooth" });
  return cena;
}

// ---- screens before the match: create, join, waiting, notices ---------------------------------
function chips(nomeGrupo, opcoes, marcado) {
  return Object.entries(opcoes)
    .map(([valor, rotulo]) => `<button class="chip" type="button" data-${nomeGrupo}="${valor}" aria-pressed="${valor === marcado}">${rotulo}</button>`)
    .join("");
}
function escolherChip(grupo, aoEscolher = () => {}) {
  grupo.addEventListener("click", (e) => {
    const b = e.target.closest(".chip");
    if (!b) return;
    grupo.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", String(c === b)));
    aoEscolher();
  });
}
// Picking a team clears the "pick your team" error.
const limparErroDeTime = () => {
  const p = $(".pr-erro");
  if (p && p.textContent === "Escolha o seu time.") p.hidden = true;
};
const marcado = (grupo, attr) => grupo.querySelector('[aria-pressed="true"]')?.dataset[attr];

// Join by the room's code instead of the link, like the Gartic (dev, 2026-11-26): a plain GET
// form, the server sends it to the room's page (/jogos/{jogo}/entrar).
function formCodigo(jogo) {
  return `<form class="ticket codigo-form" method="get" action="/jogos/${jogo}/entrar">
      <h2>Tem um código?</h2>
      <p>Te passaram o código da sala? Digite e entre.</p>
      <div class="link"><input name="codigo" maxlength="9" required autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="K7M2QX" aria-label="Código da sala"><button class="btn" type="submit">Entrar</button></div>
    </form>`;
}

function telaCriar(erro = "") {
  tela = "criar";
  palcoCena.hidden = true;
  palco.innerHTML = `<div class="espera so">
    <form class="ticket" id="mn-criar">
      <h2>Nova sala</h2>
      <p>Batedor contra goleiro. Jogue contra o bot ou mande o link para um amigo.</p>
      <label class="campo-f"><span>Seu apelido</span><input class="pr-apelido" id="mn-apelido" maxlength="16" minlength="2" required autocomplete="nickname" spellcheck="false" placeholder="Como a turma te chama"></label>
      ${campoTime()}
      <fieldset class="campo-f"${raiz.dataset.faltas ? "" : " hidden"}><legend>Modo</legend><div class="chips" id="mn-modo">${chips("modo", MODOS_OFERTA, "penaltis")}</div></fieldset>
      <fieldset class="campo-f"><legend>Contra quem</legend><div class="chips" id="mn-contra">${chips("contra", { amigo: "Um amigo", ...BOTS }, "amigo")}</div></fieldset>
      <p class="pr-erro" role="alert"${erro ? "" : " hidden"}>${esc(erro)}</p>
      <button class="btn lamp-btn" type="submit">Criar sala</button>
      <p class="fine">Cinco cobranças para cada um, alternando quem bate. Quem começa batendo é sorteado.</p>
    </form>
    ${formCodigo("mano")}
  </div>`;
  const modo = $("#mn-modo");
  const contra = $("#mn-contra");
  escolherChip($("#mn-time"), limparErroDeTime);
  escolherChip(modo);
  escolherChip(contra);
  $("#mn-criar").addEventListener("submit", async (e) => {
    e.preventDefault();
    const time = timeEscolhido();
    if (!time) return;
    const botao = e.target.querySelector("[type=submit]");
    botao.disabled = true;
    const c = marcado(contra, "contra");
    guardarTime(time);
    const { status, dados } = await postar("/salas", {
      apelido: $("#mn-apelido").value.trim(),
      time,
      modo: marcado(modo, "modo"),
      bot: c === "amigo" ? null : c,
    });
    if (status !== 201) {
      botao.disabled = false;
      const p = $(".pr-erro");
      p.textContent = ERROS[dados?.erro] || (status === 422 ? "Confira o apelido." : "Não deu para criar a sala. Tente de novo.");
      p.hidden = false;
      return;
    }
    SALA = dados.id;
    eu = { jogador: dados.jogador, token: dados.token };
    gravar(SALA, eu);
    raiz.dataset.sala = SALA;
    history.replaceState(null, "", `/jogos/mano/s/${SALA}`);
    conectar();
  });
}

function telaEntrar(erro = "") {
  tela = "entrar";
  palcoCena.hidden = true;
  palco.innerHTML = `<div class="espera so">
    <form class="ticket" id="mn-entrar">
      <h2>Entrar na sala</h2>
      <p>Te chamaram para um Mano a Mano. Escolha um apelido e entre.</p>
      <label class="campo-f"><span>Seu apelido</span><input class="pr-apelido" id="mn-apelido" maxlength="16" minlength="2" required autocomplete="nickname" spellcheck="false" placeholder="Como a turma te chama"></label>
      ${campoTime()}
      <p class="fine">Mesmo time do amigo? Vale: quem entra depois joga com a camisa reserva.</p>
      <p class="pr-erro" role="alert"${erro ? "" : " hidden"}>${esc(erro)}</p>
      <button class="btn lamp-btn" type="submit">Entrar</button>
    </form>
  </div>`;
  escolherChip($("#mn-time"), limparErroDeTime);
  $("#mn-entrar").addEventListener("submit", async (e) => {
    e.preventDefault();
    const time = timeEscolhido();
    if (!time) return;
    const botao = e.target.querySelector("[type=submit]");
    botao.disabled = true;
    guardarTime(time);
    const { status, dados } = await postar(`/salas/${SALA}/entrar`, { apelido: $("#mn-apelido").value.trim(), time });
    if (status === 200) {
      eu = { jogador: dados.jogador, token: dados.token };
      gravar(SALA, eu);
      return conectar();
    }
    if (status === 409) return aviso("Sala cheia", "Essa sala já tem dois jogadores, ou é uma partida contra o bot. Crie a sua e chame alguém.");
    if (status === 404) return aviso("A sala acabou", "A sala acabou ou o servidor reiniciou. Crie outra e mande o link de novo.");
    botao.disabled = false;
    const p = $(".pr-erro");
    p.textContent = ERROS[dados?.erro] || "Não deu para entrar. Tente de novo.";
    p.hidden = false;
  });
}

function aviso(titulo, texto) {
  tela = "aviso";
  pararFonte();
  if (cena) {
    cena.destruir();
    cena = null;
  }
  palcoCena.hidden = true;
  sairBox.hidden = true;
  palco.innerHTML = `<div class="espera so"><div class="ticket" role="alert"><h2>${esc(titulo)}</h2><p>${esc(texto)}</p>
    <div class="acoes"><a class="btn lamp-btn" href="/jogos/mano">Nova sala</a></div></div></div>`;
}

function telaEspera() {
  tela = "espera";
  palcoCena.hidden = true;
  const link = linkDa(SALA);
  const zap = `https://wa.me/?text=${encodeURIComponent(`Bora um Mano a Mano na Geral? ${MODOS[est.modo]}, eu contra você: ${link}`)}`;
  const html = `<div class="espera so"><div class="ticket mn-espera">
    <h2>Esperando o adversário</h2>
    <p>${MODOS[est.modo]}. Mande o link, ou passe o código: a partida começa quando ele entrar.</p>
    <p class="codigo-sala">Código <strong>${esc(SALA.toUpperCase())}</strong></p>
    <div class="link"><code>${esc(link)}</code></div>
    <div class="acoes"><button class="btn lamp-btn" type="button" id="mn-copiar">Copiar link</button><a class="btn secondary" href="${zap}" target="_blank" rel="noopener">Mandar no Zap</a></div>
    <p class="fine">Só entra quem tem o link ou o código. A sala fecha se ficar 10 minutos sem ninguém.</p>
  </div></div>`;
  if (palco.__html === html) return;
  palco.innerHTML = palco.__html = html;
  $("#mn-copiar").addEventListener("click", async (e) => {
    try {
      await navigator.clipboard.writeText(link);
      e.target.textContent = "Copiado";
    } catch {
      /* the link is on screen */
    }
  });
}

// ---- the match ---------------------------------------------------------------------------------
function faixaStrip() {
  const voce = est.papel === "batedor" ? "Você bate" : est.papel === "goleiro" ? "Você defende" : "";
  const o = outro();
  const linhas = [];
  if (o && o.saiu) linhas.push(`${esc(o.apelido)} saiu da sala.`);
  else if (o && !o.presente) linhas.push(`${esc(o.apelido)} caiu. Se não voltar em 30 segundos, perde por W.O.`);
  return `<div class="mn-strip board"><span class="lamp">${MODOS[est.modo]} · ${voce}</span><span class="lamp mn-contra">contra ${esc(o ? o.apelido : "")}${o?.time_nome ? ` (${esc(o.time_nome)})` : ""}</span></div>${linhas.map((l) => `<p class="mn-alerta">${l}</p>`).join("")}`;
}

function placar() {
  cena.placar({
    nomes: est.jogadores.map((j) => (j.time_nome ? { time: j.time_nome, apelido: j.apelido } : j.apelido)),
    series: est.serie.map((s) => s.map((g) => (g ? "g" : "e"))),
    gols: est.placar,
  });
}

/**
 * Each player in his team's kit for his role in the kick `k` (the scene skips an unchanged one).
 * The kicker looks like a different player each kick and the keeper is always the same one of
 * his team: both derived from the room and the kick, so both browsers show the same men.
 */
function vestir(k) {
  const eu_ = est.jogadores[est.voce];
  const ele = outro();
  if (!eu_ || !ele || !est.papel) return;
  const [b, g] = est.papel === "batedor" ? [eu_, ele] : [ele, eu_];
  const [partida, n] = k.split(":");
  const vaga = est.jogadores.indexOf(g);
  cena.vestir({
    batedor: { time: b.time, uniforme: b.uniforme, visual: visual(`${SALA}:${partida}`, Number(n)) },
    goleiro: { time: g.time, uniforme: g.uniforme, visual: visual(`${SALA}:goleiro:${vaga}:${g.time}`, 0, "goleiro") },
  });
}

/** Sets the scene for the kick `k`: the spot (and the wall, when it is known) and my camera. */
function montar(k) {
  const falta = est.modo === "faltas";
  const barreira = falta ? JSON.stringify(est.barreira) : "";
  vestir(k);
  if (montado === k && barreiraMontada === barreira && cena.papel === est.papel) return;
  if (montado !== k) cena.reiniciar();
  cena.trocarPapel(est.papel);
  if (falta) cena.posicionarFalta({ nome: est.posicao?.nome ?? "meia_lua", barreira: est.barreira });
  else if (cena.modo !== "penaltis" || montado !== k) cena.trocarModo("penaltis");
  montado = k;
  barreiraMontada = barreira;
}

/** Sends a choice; refused for a reason other than "too late", the scene asks again. */
async function enviar(k, fase, tipo, dados) {
  let status = await acao(tipo, dados);
  for (let i = 0; status === 429 && i < 3; i++) {
    // one action every 0.3 s: the wall and the dive can come faster than that
    await new Promise((r) => setTimeout(r, 350));
    if (pedido !== `${k}:${fase}`) return;
    status = await acao(tipo, dados);
  }
  if ([204, 409, 403, 404].includes(status)) return;
  setTimeout(() => {
    if (pedido === `${k}:${fase}`) {
      pedido = "";
      render();
    }
  }, 400);
}

async function pedirBarreira(k) {
  pedido = `${k}:barreira`;
  const v = await cena.pedirBarreira({ segundos: restam() });
  if (v && pedido === `${k}:barreira`) enviar(k, "barreira", "barreira", { n: v.n, x: Math.round(v.x) });
}

async function pedirEscolha(k) {
  pedido = `${k}:escolha`;
  const falta = est.modo === "faltas";
  if (est.papel === "batedor") {
    const v = await cena.pedirChute({ falta, faixa: (alvo) => faixaBoa(alvo, falta), faixaCavadinha, segundos: restam() });
    if (v && pedido === `${k}:escolha`) enviar(k, "escolha", "chute", v);
  } else {
    const v = await cena.pedirDefesa({ segundos: restam() });
    if (v && pedido === `${k}:escolha`) enviar(k, "escolha", "defesa", v);
  }
}

/** The run-up to `chute_em` (server clock) and the flight once the server sends the lance. */
function rodarCobranca(k, chuteEmIso, agoraIso, base) {
  cobrando = k;
  pedido = "";
  saidaEnviada = false;
  entregarLance = null; // a kick that never got its lance: reiniciar() below stops it
  const lance = new Promise((resolve, reject) => {
    entregarLance = (l) => {
      entregarLance = null;
      if (l) resolve(l);
      else reject(new Error("kick ended without a lance"));
    };
  });
  lance.catch(() => {}); // the scene logs and stops on a lost lance
  cena.reiniciar(); // closes a choice still on screen: the server already decided it
  montado = "";
  montar(k);
  cena.dica("");
  cena.cobrar({ chute_em: local(chuteEmIso, agoraIso, base), lance });
}

function telaJogo() {
  const deRevanche = tela === "fim"; // the rematch began: back up to the scene
  if (tela !== "jogo") {
    tela = "jogo";
    palco.innerHTML = palco.__html = "";
  }
  garantirCena();
  if (deRevanche) palcoCena.scrollIntoView({ block: "start", behavior: "smooth" });
  sairBox.hidden = false;
  const strip = faixaStrip();
  if (palco.__html !== strip) palco.innerHTML = palco.__html = strip;
  placar();
  const fase = est.fase;
  if (fase === "resultado") {
    // The kick just taken: its lance, if the event was lost (a reconnect, a background tab);
    // after a reload, or a reconnect that missed the whole kick, at least the sign, with the
    // ball on its spot (a free kick's, not the penalty mark).
    if (entregarLance && est.ultimo && cobrando === anterior()) entregarLance(est.ultimo);
    else if (cobrando !== anterior() && est.ultimo && letreiroDe !== anterior()) {
      entregarLance = null; // a kick still waiting is an older one: its lance is not this
      letreiroDe = anterior();
      montar(anterior());
      cena.letreiro(letreiroDoLance(est.ultimo));
    }
    return;
  }
  const k = lanceDe(est);
  if (fase === "corrida" || fase === "voo") {
    if (cobrando !== k) rodarCobranca(k, est.chute_em, est.agora, recebido);
    return;
  }
  montar(k);
  if (fase === "barreira") {
    if (est.papel === "goleiro") {
      if (pedido !== `${k}:barreira`) pedirBarreira(k);
    } else cena.dica(`${nome(1 - est.voce)} arma a barreira`);
    return;
  }
  if (fase === "escolha") {
    if (!est.travou.voce) {
      if (pedido !== `${k}:escolha`) pedirEscolha(k);
    } else cena.dica(est.papel === "batedor" ? "Esperando o goleiro escolher" : "Esperando o batedor escolher");
  }
}
// The kick before the current count: what `resultado` is showing.
const anterior = () => `${est.partida}:${est.serie[0].length + est.serie[1].length - 1}`;

// ---- the end: súmula and rematch ------------------------------------------------------------
let sumulaCarregada = "";
async function telaFim() {
  const primeira = tela !== "fim";
  tela = "fim";
  sairBox.hidden = true;
  entregarLance = null; // a W.O. mid-kick: the kick is stopped below, not failed
  if (cena) {
    if (primeira) {
      // a W.O. can end the match mid-kick: its sign must not land over the final one
      cena.reiniciar();
      montado = "";
      cobrando = "";
      cena.dica("");
      const venceu = est.vencedor; // a W.O. wins even when behind on the score
      cena.letreiro(venceu === null ? "FIM DE JOGO" : venceu === est.voce ? "VOCÊ GANHOU" : "VOCÊ PERDEU");
    }
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  }
  if (sumulaCarregada !== est.sumula) {
    sumulaCarregada = est.sumula;
    palco.innerHTML = palco.__html = `<div class="mn-revanche" id="mn-revanche"></div><div class="mn-sumula-viva"><p class="fine">Carregando a súmula…</p></div>`;
    try {
      const r = await fetch(`/jogos/mano/s/${est.sumula}`, { cache: "no-store" });
      const doc = new DOMParser().parseFromString(await r.text(), "text/html");
      const s = doc.getElementById("mn-sumula");
      if (s) $(".mn-sumula-viva").innerHTML = s.innerHTML;
      for (const nova of palco.querySelectorAll('a[href="/jogos/mano"]')) nova.addEventListener("click", irParaNovaSala);
      for (const botao of palco.querySelectorAll("[data-copiar]")) {
        botao.addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(botao.dataset.copiar);
            botao.textContent = "Copiado";
          } catch {
            /* the link is on screen */
          }
        });
      }
    } catch {
      $(".mn-sumula-viva").innerHTML = `<p class="fine">A súmula fica em <a href="/jogos/mano/s/${esc(est.sumula)}">${esc(linkDa(est.sumula))}</a>.</p>`;
    }
    setTimeout(() => $("#mn-revanche")?.scrollIntoView({ block: "start", behavior: "smooth" }), 2200);
  }
  revanche();
}

function revanche() {
  const box = $("#mn-revanche");
  if (!box || !est) return;
  const o = outro();
  let html;
  if (o && o.saiu) html = `<span class="lamp">${esc(o.apelido)} saiu da sala</span>`;
  else if (est.revanche.voce) html = `<span class="lamp">Esperando ${esc(o.apelido)} topar a revanche</span>`;
  else {
    const chamada = est.revanche.outro && !o.bot ? `${esc(o.apelido)} quer revanche!` : "Mais uma?";
    html = `<span class="lamp">${chamada}</span><button class="btn lamp-btn" type="button" id="mn-de-novo">Revanche</button>`;
  }
  html = `<div class="mn-strip board">${html}</div>`;
  if (box.__html === html) return;
  box.innerHTML = box.__html = html;
  $("#mn-de-novo")?.addEventListener("click", (e) => {
    e.target.disabled = true;
    acao("revanche");
  });
}
// Leaving for a new room: this one closes for me (the other sees that I left).
async function irParaNovaSala(e) {
  e.preventDefault();
  await acao("sair");
  esquecer();
  location.href = "/jogos/mano";
}

// ---- events --------------------------------------------------------------------------------
function render() {
  if (!est) return;
  if (est.fase === "fim") return telaFim();
  if (est.jogadores.length < 2 || est.fase === "espera") return telaEspera();
  sumulaCarregada = "";
  telaJogo();
}

function receber(tipo, d) {
  if (tipo === "estado") {
    est = d;
    recebido = performance.now();
    tentativas = 0;
    return render();
  }
  if (!est || !cena) return;
  if (tipo === "cobranca_inicio") {
    const k = lanceDe(est);
    if (cobrando !== k) rodarCobranca(k, d.chute_em, d.agora, performance.now());
    return;
  }
  if (tipo === "cobranca") {
    entregarLance?.(d.lance);
  }
}

const EVENTOS = ["estado", "cobranca_inicio", "cobranca", "fim"];
function conectar() {
  pararFonte();
  fonte = new EventSource(`${API}/salas/${SALA}/eventos?token=${encodeURIComponent(eu.token)}`);
  for (const t of EVENTOS) {
    fonte.addEventListener(t, (e) => {
      try {
        receber(t, JSON.parse(e.data));
      } catch (erro) {
        console.error("mano:", t, erro);
      }
    });
  }
  fonte.onerror = () => {
    if (fonte && fonte.readyState === EventSource.CLOSED) caiu();
  };
}
function pararFonte() {
  if (fonte) {
    fonte.close();
    fonte = null;
  }
}

// The events stream gave up (the browser retries by itself only on a dropped connection): the
// room is gone or over, my seat is gone, or something in the way failed (a proxy's 502).
let checando = false;
let tentativas = 0;
function reconectar() {
  const espera = Math.min(30000, 1000 * 2 ** tentativas);
  tentativas++;
  setTimeout(() => {
    checando = false;
    if (tela !== "aviso") conectar();
  }, espera);
}
// A cheap authenticated call with no effect: an empty dive is refused (409 or 422) while my
// token is good, 403 when it is gone, 404 with the room.
async function meuToken() {
  const { status } = await postar(`/salas/${SALA}/acao`, { token: eu.token, tipo: "defesa", lado: "" });
  return status;
}
async function caiu() {
  if (checando || tela === "aviso") return;
  checando = true;
  pararFonte();
  try {
    const r = await fetch(`/jogos/mano/s/${SALA}`, { cache: "no-store" });
    const html = await r.text();
    if (r.status === 404) {
      esquecer();
      aviso("A sala acabou", "A sala acabou ou o servidor reiniciou. Crie outra e mande o link de novo.");
    } else if (html.includes('id="mn-sumula"')) {
      esquecer();
      location.reload();
    } else if (r.ok && (await meuToken()) === 403) {
      esquecer();
      eu = null;
      est = null;
      telaEntrar("Seu lugar na sala caiu. Entre de novo com um apelido.");
    } else return reconectar();
  } catch {
    return reconectar();
  }
  checando = false;
}

document.getElementById("mn-sair").addEventListener("click", async () => {
  const emJogo = est && !["espera", "fim"].includes(est.fase);
  if (emJogo && !confirm("Sair agora é perder por W.O. Sair mesmo?")) return;
  await acao("sair");
  esquecer();
  location.href = "/jogos/mano";
});

if (!SALA) telaCriar();
else if (!eu && raiz.dataset.cheia) aviso("Sala cheia", "Essa sala já tem dois jogadores, ou é uma partida contra o bot. Crie a sua e chame alguém.");
else if (!eu) telaEntrar();
else conectar();
