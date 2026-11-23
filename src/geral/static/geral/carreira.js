// Carreira: build a player in a draft of legends, watch his career season by season, share the card.
// Four steps on one page (player → draft → career → card); the server simulates, this only shows.
(() => {
  const root = document.getElementById("cr");
  if (!root) return;
  const jogo = JSON.parse(document.getElementById("cr-data").textContent);
  const API = `/api/jogos/carreira/${jogo.edicao}`;
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const nomeAtributo = Object.fromEntries(jogo.atributos.map((a) => [a.id, a.nome]));
  // Only vertical: scrollIntoView would also scroll the pitch (.wall hides a wider decoration).
  const rolar = (node, onde = "start") => {
    const r = node.getBoundingClientRect();
    const barra = $("cr-bar").offsetHeight || 0; // the sticky bar must not cover what we scroll to
    const alvo = onde === "center" ? r.top - (innerHeight - r.height) / 2 : r.top - barra - 16;
    window.scrollTo({ top: scrollY + alvo, behavior: "smooth" });
  };
  const show = (step) =>
    ["cr-craque", "cr-draft", "cr-carreira"].forEach((id) => ($(id).hidden = id !== step));

  let estado;
  const novo = () => ({
    craque: null,
    oferta: null,
    vagas: [0, 1, 2, 3, 4, 5, 6, 7], // the offer's name shown at each of the 8 turns
    reservas: [8, 9], // two re-rolls: each swaps the current name for the next spare
    vez: 0,
    roubos: {}, // atributo -> {lenda, nota}
    semente: null,
    escolhas: [],
    mostradas: 0,
    modo: "completa", // the only mode offered; old Rápida links still replay on the server
    temporadas: [],
    corpo: null,
  });

  // -- 1. the player --------------------------------------------------------------------------

  const form = $("cr-craque");
  const pressed = (attr) => form.querySelector(`[data-${attr}][aria-pressed="true"]`).dataset[attr];
  form.querySelectorAll(".cr-choice").forEach((group) =>
    group.addEventListener("click", (event) => {
      const chip = event.target.closest(".chip");
      if (!chip) return;
      group.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
    }),
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const nome = $("cr-nome").value.trim();
    if (!nome) return $("cr-nome").focus();
    estado = novo();
    estado.craque = {
      nome,
      camisa: Math.min(99, Math.max(1, Number($("cr-camisa").value) || 10)),
      posicao: pressed("posicao"),
      pe: pressed("pe"),
      clube: $("cr-clube").value,
    };
    const go = form.querySelector(".cr-go");
    go.disabled = true;
    try {
      estado.oferta = await post(`${API}/oferta`, { clube: estado.craque.clube });
      show("cr-draft");
      desenharDraft();
      rolar($("cr-draft"), "start");
    } catch (erro) {
      alert(erro.message);
    } finally {
      go.disabled = false;
    }
  });

  // -- 2. the draft -----------------------------------------------------------------------------

  const pesos = () => jogo.pesos[estado.craque.posicao];
  const destaques = () =>
    Object.entries(pesos())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([a]) => a);

  function geral() {
    const feitos = Object.entries(estado.roubos);
    if (!feitos.length) return "–";
    let soma = 0;
    let peso = 0;
    for (const [atributo, { nota }] of feitos) {
      soma += nota * pesos()[atributo];
      peso += pesos()[atributo];
    }
    return Math.round(soma / peso);
  }

  function desenharDraft() {
    const { craque } = estado;
    $("cr-quem").textContent = `${craque.nome} · #${craque.camisa} · ${craque.posicao}`;
    $("cr-overall").textContent = geral();
    const lista = $("cr-attrs");
    lista.replaceChildren();
    for (const a of jogo.atributos) {
      const roubo = estado.roubos[a.id];
      const li = el("li", roubo ? "cr-attr done" : "cr-attr");
      li.append(el("span", "cr-attr-name", a.nome), el("span", "lamp cr-attr-val", roubo ? roubo.nota : "--"));
      li.append(el("span", "cr-attr-from", roubo ? roubo.lenda : ""));
      lista.append(li);
    }
    if (estado.vez >= 8) return;
    const lenda = estado.oferta.lendas[estado.vagas[estado.vez]];
    $("cr-count").textContent = `Escolha ${estado.vez + 1} de 8`;
    $("cr-legend-name").textContent = lenda.nome;
    const lendaDeVerdade = lenda.tipo !== "jogador";
    const selo = $("cr-legend-tag");
    selo.className = lendaDeVerdade ? "cr-legend-tag lenda" : "cr-legend-tag jogador";
    selo.textContent = lendaDeVerdade
      ? lenda.regiao === "nordeste" ? "Lenda · ídolo do Nordeste" : "Lenda"
      : `${lenda.resumo}${lenda.regiao === "nordeste" ? " · jogou no Nordeste" : ""}`;
    selo.hidden = false;
    const sobram = estado.reservas.length;
    $("cr-reroll").hidden = sobram === 0;
    $("cr-reroll").textContent = `Sortear outro (${sobram})`;
    const botoes = $("cr-steal");
    botoes.replaceChildren();
    const fortes = destaques();
    for (const a of jogo.atributos) {
      const b = el("button", "cr-stat");
      b.type = "button";
      b.disabled = Boolean(estado.roubos[a.id]);
      if (fortes.includes(a.id)) b.classList.add("key-attr");
      b.append(el("span", "cr-stat-name", a.nome), el("span", "cr-stat-val", lenda.notas[a.id]));
      b.addEventListener("click", () => roubar(lenda, a.id));
      botoes.append(b);
    }
  }

  function roubar(lenda, atributo) {
    estado.roubos[atributo] = { lenda: lenda.nome, nota: lenda.notas[atributo] };
    estado.vez += 1;
    desenharDraft();
    if (estado.vez === 8) comecarCarreira();
  }

  $("cr-reroll").addEventListener("click", () => {
    if (!estado.reservas.length) return;
    estado.vagas[estado.vez] = estado.reservas.shift(); // a spare takes this turn
    desenharDraft();
  });

  // -- 3. the career ----------------------------------------------------------------------------

  const pedido = () => ({
    semente_draft: estado.oferta.semente_draft,
    semente: estado.semente,
    craque: estado.craque,
    modo: estado.modo,
    roubos: Object.entries(estado.roubos).map(([atributo, r]) => ({ lenda: r.lenda, atributo })),
    escolhas: estado.escolhas,
  });

  async function post(url, body) {
    const resposta = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const dados = await resposta.json().catch(() => ({}));
    if (!resposta.ok) {
      const detalhe = typeof dados.detail === "string" ? dados.detail : "Algo deu errado. Tente de novo.";
      throw new Error(detalhe);
    }
    return dados;
  }

  const quem = (c) => `${c.nome} · #${c.camisa} · ${c.posicao}`;

  function comecarCarreira() {
    show("cr-carreira");
    $("cr-bar-who").textContent = quem(estado.craque);
    $("cr-bar-nota").textContent = `geral ${geral()}`;
    $("cr-now").replaceChildren();
    delete $("cr-now").dataset.temporada;
    $("cr-timeline").replaceChildren();
    $("cr-shelf").replaceChildren();
    $("cr-cabinet").hidden = true;
    rolar($("cr-carreira"), "start");
    simular();
  }

  async function simular() {
    $("cr-error").hidden = $("cr-retry").hidden = true;
    try {
      const corpo = await post(`${API}/simular`, pedido());
      estado.semente = corpo.semente;
      estado.temporadas = corpo.carreira.temporadas;
      estado.corpo = corpo;
      avancar();
    } catch (erro) {
      $("cr-error").textContent = erro.message || "Sem conexão. Tente de novo.";
      $("cr-error").hidden = $("cr-retry").hidden = false;
    }
  }

  // One season on screen at a time; the earlier ones go to the timeline.
  function avancar() {
    const { temporadas } = estado;
    if (estado.mostradas < temporadas.length) {
      mostrarTemporada(temporadas[estado.mostradas]);
      estado.mostradas += 1;
      const faltam = estado.mostradas < temporadas.length;
      $("cr-next").hidden = !faltam;
      if (faltam) return;
    }
    $("cr-next").hidden = true;
    const { pendente, final } = estado.corpo.carreira;
    if (pendente) return perguntar(pendente);
    if (final) fim(final, estado.corpo.codigo);
  }

  $("cr-next").addEventListener("click", avancar);
  $("cr-retry").addEventListener("click", () => simular());

  const chip = (texto, cls = "cr-chip") => el("span", cls, texto);

  // Our own trophy drawings, one shape per kind of competition (no photos: the real trophies'
  // designs and pictures have owners). Static markup only: no data goes into it.
  const BASE = '<rect x="15" y="34" width="10" height="5"/><rect x="10" y="39" width="20" height="6" rx="1"/>';
  const DESENHOS = {
    liga: '<path d="M7 5h26v9c0 9-6 15-13 15S7 23 7 14z"/><path d="M7 8H2v4c0 5 3 8 6 8M33 8h5v4c0 5-3 8-6 8" fill="none" stroke="currentColor" stroke-width="2.5"/><rect x="17" y="28" width="6" height="7"/>' + BASE,
    copa: '<path d="M12 3h16v14c0 7-4 11-8 11s-8-4-8-11z"/><path d="M12 7H8v3c0 4 2 6 5 6M28 7h4v3c0 4-2 6-5 6" fill="none" stroke="currentColor" stroke-width="2.2"/><rect x="18" y="27" width="4" height="8"/>' + BASE,
    continental: '<path d="M11 5h18v11c0 7-4 12-9 12s-9-5-9-12z"/><path d="M11 8C3 6 1 14 4 18s7 3 9 1M29 8c8-2 10 6 7 10s-7 3-9 1" fill="none" stroke="currentColor" stroke-width="2.8"/><rect x="17" y="27" width="6" height="8"/>' + BASE,
    mundo: '<circle cx="20" cy="9" r="7"/><path d="M13 14c-1 7 2 12 7 14 5-2 8-7 7-14-2 3-5 4-7 4s-5-1-7-4z"/><rect x="17" y="27" width="6" height="8"/>' + BASE,
    estadual: '<path d="M13 9h14v9c0 6-3 10-7 10s-7-4-7-10z"/><path d="M13 12H9v2c0 3 2 5 4 5M27 12h4v2c0 3-2 5-4 5" fill="none" stroke="currentColor" stroke-width="2"/><rect x="18" y="27" width="4" height="8"/>' + BASE,
    nordeste: '<circle cx="20" cy="6" r="3.5"/><path d="M20 0v1.5M14 2l1.2 1.2M26 2l-1.2 1.2M12.5 6h1.5M26 6h1.5" stroke="currentColor" stroke-width="1.6"/><path d="M11 11h18v8c0 6-4 9-9 9s-9-3-9-9z"/><path d="M11 13H7v2c0 4 3 6 5 6M29 13h4v2c0 4-3 6-5 6" fill="none" stroke="currentColor" stroke-width="2.2"/><rect x="17" y="27" width="6" height="8"/>' + BASE,
  };
  const tipoDaTaca = (nome) => (jogo.tacas || {})[nome] || "copa";
  function taca(nome) {
    const tipo = tipoDaTaca(nome);
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 40 46");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("class", `cr-taca ${tipo}`);
    svg.innerHTML = DESENHOS[tipo] || DESENHOS.copa;
    return svg;
  }
  function selo(nome, cls = "cr-trophy") {
    const s = el("span", cls);
    s.append(taca(nome), el("span", "", nome));
    return s;
  }

  function mostrarTemporada(t) {
    const atual = $("cr-now");
    const anterior = atual.dataset.temporada;
    if (anterior) $("cr-timeline").prepend(linhaDoTempo(JSON.parse(anterior)));
    atual.dataset.temporada = JSON.stringify(t);
    atual.replaceChildren();
    atual.classList.remove("enter");
    void atual.offsetWidth; // restart the animation
    atual.classList.add("enter");
    atual.append(el("span", "cr-kicker", `${t.ano} · ${t.idade} anos · ${t.pais}`));
    if (t.chegada) atual.append(chip(t.chegada, "cr-arrival"));
    atual.append(el("h3", "cr-club-big", t.clube));
    const numeros = el("div", "cr-numbers");
    if (t.idade === 16) numeros.append(chip("Categorias de base"));
    else {
      numeros.append(chip(`${t.jogos} jogos`), chip(`${t.gols} gols`), chip(`${t.assistencias} assist.`));
      if (t.selecao) numeros.append(chip(`${t.selecao} pela Seleção`, "cr-chip selecao"));
    }
    atual.append(numeros);
    if (t.titulos.length) {
      const tacas = el("div", "cr-trophies");
      t.titulos.forEach((nome) => tacas.append(selo(nome)));
      atual.append(tacas);
    }
    atual.append(el("p", "cr-headline", t.manchete));
    (t.marcas || []).forEach((m) => atual.append(el("p", "cr-mark", m)));
    if (t.rotina) {
      const r = t.rotina;
      const linha = el("p", r.deu_certo ? "cr-routine ok" : "cr-routine bad");
      linha.append(el("b", "", r.deu_certo ? "Deu certo" : "Deu errado"));
      linha.append(document.createTextNode(` · ${r.escolha}${r.efeito ? `: ${r.efeito}` : ""}`));
      atual.append(linha);
    }
    $("cr-bar-nota").textContent = `${t.idade} anos · ${t.clube} · nota ${t.nota}`;
    const vistas = estado ? estado.temporadas.slice(0, estado.mostradas + 1) : [];
    const ate = estado ? vistas : (jogo.compartilhada?.carreira?.temporadas || []);
    $("cr-cabinet").hidden = salaDeTrofeus($("cr-shelf"), ate) === 0;
  }

  const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;

  function linhaDoTempo(t) {
    const li = el("li", "cr-line");
    li.append(el("span", "cr-line-age", t.idade));
    const corpo = el("div", "cr-line-body");
    const topo = el("div", "cr-line-top");
    topo.append(el("span", "cr-line-club", t.clube));
    const numeros = t.idade === 16 ? "categorias de base" : `${plural(t.jogos, "jogo", "jogos")} · ${plural(t.gols, "gol", "gols")}`;
    topo.append(el("span", "cr-line-nums", numeros));
    corpo.append(topo);
    if (t.titulos.length) {
      const tacas = el("div", "cr-line-trophies");
      t.titulos.forEach((nome) => tacas.append(selo(nome, "cr-line-trophy")));
      corpo.append(tacas);
    }
    if (t.marcas && t.marcas.length) corpo.append(el("div", "cr-line-marks", t.marcas.join(" · ")));
    li.append(corpo);
    li.title = t.manchete;
    return li;
  }

  // The trophy room: every title won so far, one shelf item per competition.
  function salaDeTrofeus(lista, temporadas) {
    const contagem = new Map();
    temporadas.forEach((t) => t.titulos.forEach((n) => contagem.set(n, (contagem.get(n) || 0) + 1)));
    lista.replaceChildren();
    const ordem = ["mundo", "continental", "liga", "copa", "nordeste", "estadual"];
    [...contagem.entries()]
      .sort((a, b) => ordem.indexOf(tipoDaTaca(a[0])) - ordem.indexOf(tipoDaTaca(b[0])) || b[1] - a[1])
      .forEach(([nome, vezes]) => {
        const item = el("li", `cr-shelf-item ${tipoDaTaca(nome)}`);
        item.append(taca(nome), el("b", "cr-shelf-n", `${vezes}×`), el("span", "cr-shelf-name", nome));
        lista.append(item);
      });
    return contagem.size;
  }

  const TIPOS = { dia: "Dia a dia", mercado: "Mercado", decisao: "Decisão" };

  function perguntar(pendente) {
    const caixa = $("cr-question");
    caixa.dataset.tipo = pendente.tipo;
    $("cr-q-kind").textContent = TIPOS[pendente.tipo] || "Decisão";
    $("cr-question-text").textContent = pendente.pergunta;
    const opcoes = $("cr-options");
    opcoes.replaceChildren();
    pendente.opcoes.forEach((texto, i) => {
      const info = (pendente.info || [])[i];
      const b = el("button", "cr-option");
      b.type = "button";
      if (info && info.arriscada) b.append(el("span", "cr-risky", "Arriscada"));
      b.append(el("span", "cr-option-text", texto));
      if (info && info.chance !== null && info.chance !== undefined) {
        const barra = el("span", "cr-chance");
        barra.style.setProperty("--chance", `${info.chance}%`);
        barra.append(el("span", "cr-chance-n", `${info.chance}%`));
        b.append(barra);
      }
      if (info && info.efeitos) b.append(el("span", "cr-option-effects", info.efeitos));
      b.addEventListener("click", () => {
        caixa.hidden = true;
        estado.escolhas.push(i);
        simular();
      });
      opcoes.append(b);
    });
    caixa.hidden = false;
    rolar($("cr-now"), "start"); // the season first, its question right below
  }

  // -- 4. the card ------------------------------------------------------------------------------

  let compartilhar = null; // {texto, url, arquivo}

  async function fim(final, codigo) {
    const craque = estado ? estado.craque : jogo.compartilhada.craque;
    const titulos = Object.values(final.titulos).reduce((a, b) => a + b, 0);
    const posicao = final.posicao || craque.posicao; // "virou meia" along the way
    $("cr-end-kicker").textContent = `${craque.nome} · #${craque.camisa} · ${posicao}`;
    $("cr-end-label").textContent = `${final.rotulo} · ${final.nota}`;
    $("cr-end-desc").textContent = `${final.descricao} Sua carreira lembra a de ${final.parecido}.`;
    const marcas = final.marcas || [];
    $("cr-end-marks").replaceChildren(...marcas.map((m) => el("li", "cr-end-mark", m)));
    $("cr-end-marks").hidden = !marcas.length;
    mostrarVereditos(final.vereditos || []);
    const placar = estado && estado.corpo ? estado.corpo.placar : null;
    $("cr-end-placar").hidden = !placar;
    if (placar) {
      const lugar = placar.posicao ? ` · ${placar.posicao}º na Fábrica de craques` : "";
      const conta = placar.novo ? "+1 craque formado" : "Já contou como craque formado";
      $("cr-end-placar").textContent = `${conta} ${placar.pelo}${lugar}`;
    }
    carregarFabrica(craque.clube);
    const todas = estado ? estado.temporadas : jogo.compartilhada.carreira.temporadas;
    $("cr-end-cabinet").hidden = salaDeTrofeus($("cr-end-shelf"), todas) === 0;
    const stats = $("cr-end-stats");
    stats.replaceChildren();
    const linhas = [
      ["Títulos", titulos],
      ["Jogos", final.jogos],
      ["Gols", final.gols],
      ["Clubes", final.clubes.length],
    ];
    if (final.selecao) linhas.push(["Pela Seleção", final.selecao]);
    for (const [rotulo, valor] of linhas) {
      const item = el("div", "cr-stat-item");
      item.append(el("dt", "", rotulo), el("dd", "", valor));
      stats.append(item);
    }
    const url = `${jogo.url || location.origin}/jogos/carreira/c/${codigo}`;
    const canvas = await desenharCard({ craque, final, titulos });
    const png = canvas.toDataURL("image/png");
    $("cr-card").src = png;
    $("cr-download").href = png;
    const blob = await new Promise((ok) => canvas.toBlob(ok, "image/png"));
    compartilhar = {
      texto: `Carreira na Geral: ${craque.nome} virou "${final.rotulo}" (nota ${final.nota}, ${titulos} títulos). E o seu craque?`,
      url,
      arquivo: blob ? new File([blob], "carreira.png", { type: "image/png" }) : null,
    };
    $("cr-end").hidden = false;
    rolar($("cr-end"), "start");
  }

  const CLASSE = { Traidor: "traidor", "Ídolo": "idolo", "Campeão": "campeao", "Passou em branco": "branco", Respeitado: "respeitado" };

  function mostrarVereditos(lista) {
    const ul = $("cr-verdict-list");
    ul.replaceChildren();
    for (const v of lista) {
      const li = el("li", `cr-verdict ${CLASSE[v.veredito] || ""}`);
      const topo = el("div", "cr-verdict-top");
      topo.append(el("span", "cr-verdict-club", v.clube), el("span", "cr-verdict-tag", v.veredito));
      const anos = plural(v.temporadas, "temporada", "temporadas");
      const partes = [anos, plural(v.jogos, "jogo", "jogos"), plural(v.gols, "gol", "gols")];
      if (v.titulos) partes.push(plural(v.titulos, "título", "títulos"));
      li.append(topo, el("span", "cr-verdict-nums", partes.join(" · ")), el("p", "cr-verdict-quote", v.frase));
      ul.append(li);
    }
    $("cr-end-vereditos").hidden = lista.length === 0;
  }

  // The Fábrica de craques: careers by starting club; the fan's club stands out.
  async function carregarFabrica(destaque) {
    const lista = $("cr-fabrica-list");
    let linhas = [];
    try {
      const resposta = await fetch("/api/jogos/carreira/placar");
      if (!resposta.ok) throw new Error(String(resposta.status));
      linhas = await resposta.json();
    } catch {
      $("cr-fabrica").hidden = true; // the game goes on without the scoreboard
      return;
    }
    $("cr-fabrica").hidden = false;
    lista.replaceChildren();
    if (!linhas.length) {
      lista.append(el("li", "cr-fabrica-empty", "Ninguém terminou uma carreira ainda: seja o primeiro."));
      return;
    }
    for (const l of linhas.slice(0, 10)) {
      const li = el("li", l.clube === destaque ? "cr-fabrica-row meu" : "cr-fabrica-row");
      li.append(el("span", "cr-fabrica-pos", `${l.posicao}º`), el("span", "cr-fabrica-club", l.nome));
      li.append(el("span", "cr-fabrica-n", plural(l.carreiras, "carreira", "carreiras")));
      li.append(el("span", "cr-fabrica-extra", `média ${l.media} · ${plural(l.lendas, "lenda", "lendas")}`));
      lista.append(li);
    }
  }
  carregarFabrica(null);

  $("cr-share").addEventListener("click", async () => {
    if (!compartilhar) return;
    const { texto, url, arquivo } = compartilhar;
    try {
      if (arquivo && navigator.canShare && navigator.canShare({ files: [arquivo] })) {
        return await navigator.share({ files: [arquivo], text: `${texto} ${url}` });
      }
      if (navigator.share) return await navigator.share({ text: texto, url });
    } catch (erro) {
      if (erro.name === "AbortError") return;
    }
    try {
      await navigator.clipboard.writeText(`${texto} ${url}`);
      $("cr-copied").textContent = "Copiado! Cole no grupo da torcida.";
    } catch {
      $("cr-copied").textContent = url;
    }
  });

  $("cr-again").addEventListener("click", () => {
    if (jogo.compartilhada) {
      location.href = `/jogos/carreira${jogo.edicao === "geral" ? "" : `/${jogo.edicao}`}`;
      return;
    }
    $("cr-end").hidden = true;
    $("cr-question").hidden = true;
    show("cr-craque");
    rolar(form, "start");
  });

  // The card is a Geral front page: masthead, the label as the main headline, the newsroom's
  // note, the numbers and the trophy shelf in columns, the clubs as the path, the score boxed.
  async function desenharCard({ craque, final, titulos }) {
    const css = getComputedStyle(document.documentElement);
    const cor = (nome) => css.getPropertyValue(nome).trim();
    const display = cor("--display");
    const stencil = cor("--stencil");
    const dots = cor("--dots");
    const body = cor("--body");
    try {
      await Promise.all([
        document.fonts.load(`900 120px ${display}`),
        document.fonts.load(`800 120px ${stencil}`),
        document.fonts.load(`900 60px ${dots}`),
        document.fonts.load(`600 30px ${body}`),
        document.fonts.load(`italic 500 30px ${body}`),
      ]);
    } catch {
      /* fallback fonts are fine */
    }
    const W = 1080;
    const H = 1350;
    const M = 70; // margin
    const canvas = el("canvas");
    canvas.width = W;
    canvas.height = H;
    const g = canvas.getContext("2d");
    const ink = cor("--ink");
    const paper = cor("--paper");
    const turf = cor("--turf");

    // newsprint
    g.fillStyle = paper;
    g.fillRect(0, 0, W, H);
    g.fillStyle = "rgba(20, 35, 26, .035)";
    for (let y = 0; y < H; y += 6) g.fillRect(0, y, W, 2);
    const regua = (y, grossa = 3) => {
      g.fillStyle = ink;
      g.fillRect(M, y, W - 2 * M, grossa);
    };
    const caber = (texto, max, fonte, tamanho) => {
      let t = tamanho;
      g.font = fonte(t);
      while (g.measureText(texto).width > max && t > 24) {
        t -= 4;
        g.font = fonte(t);
      }
      return t;
    };
    const linhasDe = (texto, max, fonte) => {
      g.font = fonte;
      const linhas = [];
      let linha = "";
      for (const p of texto.split(" ")) {
        const teste = linha ? `${linha} ${p}` : p;
        if (g.measureText(teste).width > max && linha) {
          linhas.push(linha);
          linha = p;
        } else linha = teste;
      }
      if (linha) linhas.push(linha);
      return linhas;
    };
    const quebrar = (texto, max, fonte, x, y, altura, linhasMax) => {
      g.font = fonte;
      const palavras = texto.split(" ");
      let linha = "";
      let n = 0;
      for (const p of palavras) {
        const teste = linha ? `${linha} ${p}` : p;
        if (g.measureText(teste).width > max && linha) {
          g.fillText(linha, x, y + n * altura);
          n += 1;
          linha = p;
          if (n >= linhasMax) return n;
        } else linha = teste;
      }
      if (linha) g.fillText(linha, x, y + n * altura);
      return n + 1;
    };
    g.textBaseline = "alphabetic";

    // masthead
    g.fillStyle = turf;
    g.fillRect(0, 0, W, 22);
    g.fillStyle = ink;
    g.textAlign = "center";
    g.font = `800 150px ${stencil}`;
    g.fillText("GERAL", W / 2, 180);
    regua(206, 6);
    regua(216, 2);
    g.font = `700 26px ${body}`;
    const ultima = (estado ? estado.temporadas : jogo.compartilhada.carreira.temporadas).at(-1);
    g.fillText(`EDIÇÃO ESPECIAL  ·  CARREIRA  ·  ${ultima ? ultima.ano : ""}`, W / 2, 256);
    regua(274, 2);
    g.textAlign = "left";

    // kicker and main headline
    g.fillStyle = "#B23A2A";
    g.font = `800 34px ${display}`;
    const posicao = (final.posicao || craque.posicao).toUpperCase();
    g.fillText(`${craque.nome.toUpperCase()} · #${craque.camisa} · ${posicao}`, M, 336);
    g.fillStyle = ink;
    const rotulo = final.rotulo.toUpperCase();
    const tam = caber(rotulo, W - 2 * M, (t) => `900 ${t}px ${display}`, 170);
    g.fillText(rotulo, M, 336 + tam * 0.95);
    let y = 336 + tam * 0.95 + 58;
    g.font = `italic 500 34px ${body}`;
    y += (quebrar(final.descricao, W - 2 * M, `italic 500 34px ${body}`, M, y, 44, 2) - 1) * 44;
    if (final.marcas && final.marcas.length) {
      // the marks of the career on one line, "CAPITÃO · VIROU MEIA", "…" when more don't fit:
      // the card has no room to spare above the path
      g.fillStyle = "#B23A2A";
      g.font = `800 26px ${display}`;
      const max = W - 2 * M - g.measureText("  …").width;
      let linha = "";
      for (const marca of final.marcas.map((m) => m.toUpperCase())) {
        const teste = linha ? `${linha}  ·  ${marca}` : marca;
        if (linha && g.measureText(teste).width > max) {
          linha += "  …";
          break;
        }
        linha = teste;
      }
      y += 38;
      g.fillText(linha, M, y);
      y -= 8; // a tighter gap to the rule below
      g.fillStyle = ink;
    }
    y += 36;
    regua(y, 3);

    // the score, boxed like the old scoreboard
    const colunaY = y + 34;
    g.fillStyle = cor("--board");
    g.fillRect(M, colunaY, 300, 300);
    g.fillStyle = cor("--lamp");
    g.font = `900 40px ${dots}`;
    g.fillText("NOTA", M + 28, colunaY + 66);
    g.font = `900 ${final.nota >= 100 ? 130 : 170}px ${dots}`;
    g.fillText(String(final.nota), M + 22, colunaY + 250);

    // the numbers and the shelf
    const X2 = M + 340;
    g.fillStyle = ink;
    g.font = `800 30px ${display}`;
    g.fillText("OS NÚMEROS", X2, colunaY + 26);
    g.font = `600 32px ${body}`;
    const numeros = [`${titulos} títulos`, `${final.jogos} jogos · ${final.gols} gols`];
    if (final.selecao) numeros.push(`${final.selecao} jogos pela Seleção`);
    numeros.forEach((linha, i) => g.fillText(linha, X2, colunaY + 74 + i * 44));
    let fimDaColuna = colunaY + 74 + (numeros.length - 1) * 44;
    const estante = Object.entries(final.titulos)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([n, q]) => `${q}× ${n}`);
    if (estante.length) {
      const yE = colunaY + 74 + numeros.length * 44 + 26;
      g.font = `800 30px ${display}`;
      g.fillText("A ESTANTE", X2, yE);
      g.font = `600 28px ${body}`;
      estante.forEach((linha, i) => {
        caber(linha, W - M - X2, (t) => `600 ${t}px ${body}`, 28);
        g.fillText(linha, X2, yE + 44 + i * 38);
      });
      fimDaColuna = yE + 44 + (estante.length - 1) * 38;
    }

    // the path: below the score box and below the longest column (numbers and shelf can grow)
    y = Math.max(colunaY + 340, fimDaColuna + 40);
    regua(y, 3);
    g.font = `800 30px ${display}`;
    g.fillText("O CAMINHO", M, y + 50);
    // The path fits the room left above the footer: a smaller font, then "…" at the end.
    const caminho = final.clubes.join(" → ").toUpperCase();
    const topo = y + 104;
    const espaco = H - 175 - topo;
    for (const tamanho of [38, 32, 27]) {
      const altura = Math.round(tamanho * 1.25);
      const cabem = Math.max(1, Math.floor(espaco / altura) + 1);
      const linhas = linhasDe(caminho, W - 2 * M, `800 ${tamanho}px ${display}`);
      if (linhas.length <= cabem || tamanho === 27) {
        const mostradas = linhas.slice(0, cabem);
        if (linhas.length > cabem) mostradas[cabem - 1] += " …";
        g.font = `800 ${tamanho}px ${display}`;
        mostradas.forEach((linha, i) => g.fillText(linha, M, topo + i * altura));
        break;
      }
    }

    // footer
    regua(H - 150, 2);
    g.font = `italic 500 30px ${body}`;
    if (final.parecido) g.fillText(`Sua carreira lembra a de ${final.parecido}.`, M, H - 100);
    g.font = `700 26px ${body}`;
    const site = (jogo.url || location.origin).replace(/^https?:\/\//, "");
    g.fillText(`Monte o seu craque: ${site}/jogos/carreira`, M, H - 56);
    g.fillStyle = turf;
    g.fillRect(0, H - 22, W, 22);
    return canvas;
  }

  // A shared link: the last season, the timeline, then the card.
  if (jogo.compartilhada && jogo.compartilhada.carreira) {
    const { carreira, codigo, craque } = jogo.compartilhada;
    show("cr-carreira");
    $("cr-bar-who").textContent = quem(craque);
    carreira.temporadas.forEach(mostrarTemporada);
    fim(carreira.final, codigo);
  } else if (jogo.compartilhada) {
    $("cr-craque").hidden = true;
  }
})();
