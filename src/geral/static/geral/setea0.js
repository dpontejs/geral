// 7a0 do clube: pick a dream team of the club, one era per round, and try 7 wins out of 7.
// Four screens (start → pick → games → card); the server draws, validates and plays, this only
// shows. A shared link opens straight on the card.
(() => {
  const root = document.getElementById("s7");
  if (!root) return;
  const jogo = JSON.parse(document.getElementById("s7-data").textContent);
  const API = `/api/jogos/7a0/${jogo.edicao}`;
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const nomes = { ...(jogo.adversarios || {}), ...(jogo.compartilhada?.adversarios || {}) };
  const nomeDe = (slug) => nomes[slug] || slug;
  // "Edson (Edson Felipe da Cruz)": the reviewed lists tell namesakes apart in parentheses; the
  // pitch shows the short name, the offer the full one below it.
  const partes = (nome) => {
    const m = /^(.*?)\s*\((.*)\)$/.exec(nome);
    return m ? { curto: m[1], completo: m[2] } : { curto: nome, completo: "" };
  };
  const RODADAS = 11;
  const JOGOS = 7;
  const LINHAS = ["ATA", "MEI", "DEF", "GOL"]; // pitch rows, top to bottom
  const PAUSA_GOL = 400; // ms between goals lighting up
  const espera = (ms) => new Promise((r) => setTimeout(r, ms));
  // The page stays put while things change; it only scrolls when what changed is out of view
  // above (the Central's rule), or with `abaixo`, also when it sits below the screen.
  const rolar = (node, abaixo = false) => {
    const r = node.getBoundingClientRect();
    if (r.top >= 0 && !(abaixo && r.top > innerHeight - 80)) return;
    window.scrollTo({ top: scrollY + r.top - 16, behavior: "smooth" });
  };
  const tela = (id) =>
    ["s7-inicio", "s7-escalar", "s7-jogos", "s7-fim"].forEach((t) => ($(t).hidden = t !== id));

  let estado;
  const novo = () => ({
    modo: "classico",
    esquema: Object.keys(jogo.esquemas).includes("4-3-3") ? "4-3-3" : Object.keys(jogo.esquemas)[0],
    semente: null,
    versao: null,
    rodada: 0,
    troca: 0, // rerolls used so far in the game
    oferta: null,
    escolhas: [], // {rodada, troca, jogador, vaga}
    vagas: [], // slot -> {jogador, epoca} | null
    escolhido: null, // the player tapped in the offer
    cobrancas: [], // one list per shootout of the campaign, in order
    disputaDoJogo: {}, // game n -> index in cobrancas
    n: 1,
    simulando: false,
    ocupado: false, // a request is on its way: taps on the offer, slots and reroll wait for it
  });

  async function chamar(caminho, corpo) {
    const resposta = await fetch(`${API}/${caminho}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    });
    const dados = await resposta.json().catch(() => ({}));
    if (!resposta.ok) {
      const erro = new Error(dados.detail || "Algo deu errado. Tente de novo.");
      erro.atualizado = Boolean(dados.atualizado);
      throw erro;
    }
    return dados;
  }

  function falhar(erro) {
    const caixa = $("s7-erro");
    caixa.textContent = erro.message;
    caixa.hidden = false;
    rolar(caixa);
    if (erro.atualizado) setTimeout(() => location.reload(), 2500);
  }

  // --- 0. start ------------------------------------------------------------------------------

  function montarInicio() {
    const chips = $("s7-esquemas");
    const ORDEM = ["4-3-3", "4-4-2", "4-2-3-1", "3-5-2", "5-3-2"];
    const nomes = Object.keys(jogo.esquemas).sort(
      (x, y) => (ORDEM.indexOf(x) + 99) % 99 - (ORDEM.indexOf(y) + 99) % 99,
    );
    for (const nome of nomes) {
      const chip = el("button", "chip", nome);
      chip.type = "button";
      chip.dataset.esquema = nome;
      chip.setAttribute("aria-pressed", String(nome === estado.esquema));
      chips.append(chip);
    }
    chips.addEventListener("click", (e) => {
      const chip = e.target.closest("[data-esquema]");
      if (!chip) return;
      estado.esquema = chip.dataset.esquema;
      chips.querySelectorAll("[data-esquema]").forEach((c) =>
        c.setAttribute("aria-pressed", String(c === chip)),
      );
    });
    $("s7-modos").addEventListener("click", (e) => {
      const botao = e.target.closest("[data-modo]");
      if (!botao) return;
      estado.modo = botao.dataset.modo;
      $("s7-modos").querySelectorAll("[data-modo]").forEach((b) =>
        b.setAttribute("aria-pressed", String(b === botao)),
      );
    });
    $("s7-comecar").addEventListener("click", comecar);
  }

  async function comecar() {
    estado.vagas = jogo.esquemas[estado.esquema].map(() => null);
    $("s7-erro").hidden = true;
    try {
      await pedirOferta();
      tela("s7-escalar");
    } catch (erro) {
      falhar(erro);
    }
  }

  // --- 1. pick -------------------------------------------------------------------------------

  async function pedirOferta() {
    estado.ocupado = true;
    root.classList.add("s7-ocupado");
    $("s7-trocar").disabled = true;
    let r;
    try {
      r = await chamar("oferta", {
        semente: estado.semente,
        versao: estado.versao,
        modo: estado.modo,
        rodada: estado.rodada,
        troca: estado.troca,
      });
    } finally {
      estado.ocupado = false;
      root.classList.remove("s7-ocupado");
    }
    estado.semente = r.semente;
    estado.versao = r.versao;
    estado.oferta = r;
    estado.escolhido = null;
    desenharEscalar();
  }

  const linhaDe = (posicao) => (posicao === "LAT" || posicao === "ZAG" ? "DEF" : posicao);

  // The slots of a row in pitch order: full-backs on the edges of the defence.
  function vagasDaLinha(esquema, linha) {
    const vagas = jogo.esquemas[esquema]
      .map((p, i) => ({ p, i }))
      .filter((v) => linhaDe(v.p) === linha);
    if (linha !== "DEF") return vagas;
    const lat = vagas.filter((v) => v.p === "LAT");
    const zag = vagas.filter((v) => v.p === "ZAG");
    return lat.length === 2 ? [lat[0], ...zag, lat[1]] : [...lat, ...zag];
  }

  function desenharCampo(campo, esquema, vagas, interativo) {
    campo.replaceChildren();
    for (const linha of LINHAS) {
      const fila = el("div", "s7-linha");
      for (const { p, i } of vagasDaLinha(esquema, linha)) {
        const ocupada = vagas[i];
        const vaga = el(interativo ? "button" : "span", "s7-vaga");
        if (interativo) vaga.type = "button";
        vaga.dataset.vaga = i;
        if (ocupada) {
          vaga.append(el("b", "", partes(ocupada.jogador.nome).curto), el("small", "", ocupada.epoca));
          vaga.classList.add("ocupada");
        } else {
          vaga.classList.add("livre");
          vaga.append(el("b", "", p));
          const escolhido = interativo && estado.escolhido;
          if (escolhido && escolhido.posicoes.includes(p)) vaga.classList.add("encaixa");
        }
        fila.append(vaga);
      }
      campo.append(fila);
    }
  }

  function desenharEscalar() {
    const o = estado.oferta;
    const modo = estado.modo === "almanaque" ? "Almanaque" : "Clássico";
    $("s7-rodada").textContent =
      `Rodada ${estado.rodada + 1} de ${RODADAS} · ${estado.esquema} · ${modo}`;
    $("s7-epoca").textContent = `${jogo.nome} · ${o.epoca.rotulo}`;
    const trocar = $("s7-trocar");
    trocar.textContent = `Trocar época (${o.trocas_restantes})`;
    trocar.disabled = o.trocas_restantes <= 0;
    $("s7-oferta-titulo").textContent = `Quem jogou no ${jogo.nome} nos ${o.epoca.rotulo}`;

    const usados = new Set(estado.escolhas.map((e) => e.jogador));
    const lista = $("s7-lista");
    lista.replaceChildren();
    for (const j of o.jogadores) {
      const usado = usados.has(j.id);
      const op = el("button", "s7-op");
      op.type = "button";
      op.dataset.id = j.id;
      if (j.idolo) op.classList.add("idolo");
      if (usado) {
        op.classList.add("usado");
        op.disabled = true;
      }
      op.setAttribute("aria-pressed", String(estado.escolhido?.id === j.id));
      const quem = el("span");
      const { curto, completo } = partes(j.nome);
      const anos = usado ? "já está no time" : j.anos;
      quem.append(el("span", "nome", curto), el("span", "anos", [completo, anos].filter(Boolean).join(" · ")));
      const estrelas =
        j.estrelas == null ? "" : "★".repeat(j.estrelas) + "☆".repeat(5 - j.estrelas);
      op.append(el("span", "pos", j.posicoes[0]), quem, el("span", "estrelas", estrelas));
      lista.append(op);
    }
    root.classList.toggle("s7-escolhendo", Boolean(estado.escolhido));
    $("s7-dica").hidden = !estado.escolhido;
    desenharCampo($("s7-campo"), estado.esquema, estado.vagas, true);
  }

  $("s7-lista").addEventListener("click", (e) => {
    const op = e.target.closest(".s7-op");
    if (!op || op.disabled || estado.ocupado) return;
    estado.escolhido = estado.oferta.jogadores.find((j) => j.id === op.dataset.id);
    desenharEscalar();
    if (innerWidth <= 760) rolar($("s7-campo"));
  });

  $("s7-campo").addEventListener("click", async (e) => {
    const vaga = e.target.closest(".s7-vaga.livre:not(.ocupada)");
    if (!vaga || !estado.escolhido || estado.ocupado) return;
    const i = Number(vaga.dataset.vaga);
    estado.escolhas.push({
      rodada: estado.rodada,
      troca: estado.troca,
      jogador: estado.escolhido.id,
      vaga: i,
    });
    estado.vagas[i] = { jogador: estado.escolhido, epoca: estado.oferta.epoca.rotulo };
    estado.rodada += 1;
    estado.escolhido = null;
    try {
      if (estado.rodada < RODADAS) {
        await pedirOferta();
      } else {
        comecarJogos();
      }
    } catch (erro) {
      falhar(erro);
    }
  });

  $("s7-trocar").addEventListener("click", async () => {
    if (estado.ocupado || estado.oferta.trocas_restantes <= 0) return;
    estado.troca += 1;
    try {
      await pedirOferta();
    } catch (erro) {
      estado.troca -= 1;
      $("s7-trocar").disabled = estado.oferta.trocas_restantes <= 0;
      falhar(erro);
    }
  });

  // --- 2. games ------------------------------------------------------------------------------

  function lampadas(alvo, partidas, atual) {
    alvo.replaceChildren();
    for (let n = 1; n <= JOGOS; n++) {
      const feita = partidas.find((p) => p.n === n);
      const lamp = el("span", "j", n === JOGOS ? "F" : String(n));
      if (feita) lamp.classList.add(feita.venceu ? "v" : "d");
      else if (n === atual) lamp.classList.add("agora");
      alvo.append(lamp);
    }
  }

  const partidas = [];

  function comecarJogos() {
    partidas.length = 0;
    estado.n = 1;
    tela("s7-jogos");
    rolar($("s7-jogos"));
    jogar();
  }

  async function jogar() {
    $("s7-acoes").hidden = true;
    let r;
    try {
      r = await chamar("jogo", {
        semente: estado.semente,
        versao: estado.versao,
        modo: estado.modo,
        esquema: estado.esquema,
        escolhas: estado.escolhas,
        cobrancas: estado.cobrancas,
        n: estado.n,
      });
    } catch (erro) {
      $("s7-acoes").hidden = false;
      return falhar(erro);
    }
    if (r.pedido) return penalti(r.pedido, r.adversario.nome);
    fecharPenalti();
    await mostrarPartida(r.partida, r.adversario.nome);
    if (r.fim) return terminar(r.campanha, r.codigo);
    estado.n += 1;
    if (estado.simulando) return jogar();
    $("s7-situacao").textContent += ` · próximo: ${nomeDe(proximoAdversario())}`;
    $("s7-acoes").hidden = false;
  }

  function proximoAdversario() {
    const chave = jogo.chave || [];
    return chave[estado.n - 1] || "";
  }

  async function mostrarPartida(p, adversario) {
    partidas.push(p);
    lampadas($("s7-campanha"), partidas, p.n);
    $("s7-nos").textContent = jogo.nome;
    $("s7-eles").textContent = adversario;
    const gols = $("s7-gols");
    gols.replaceChildren();
    let nos = 0;
    let eles = 0;
    $("s7-gols-nos").textContent = "0";
    $("s7-gols-eles").textContent = "0";
    const rotulo = p.n === JOGOS ? "Final" : `Jogo ${p.n} de ${JOGOS}`;
    $("s7-situacao").textContent = `${rotulo} · seu ${jogo.nome} × ${adversario} de todos os tempos`;
    for (const g of p.gols) {
      if (!estado.simulando) await espera(PAUSA_GOL);
      if (g.nosso) nos += 1;
      else eles += 1;
      $("s7-gols-nos").textContent = String(nos);
      $("s7-gols-eles").textContent = String(eles);
      gols.append(el("li", g.nosso ? "nosso" : "deles", `${g.minuto}' ${partes(g.autor).curto}`));
    }
    $("s7-pontos").hidden = true;
    if (p.disputa) {
      const feitos = (lado) => lado.filter(Boolean).length;
      gols.append(
        el("li", "nosso", `Pênaltis: ${feitos(p.disputa.nossas)} × ${feitos(p.disputa.deles)}`),
      );
      pontos(p.disputa, adversario);
    }
    $("s7-situacao").textContent = `${rotulo} · ${p.venceu ? "vitória" : "fim da linha"}`;
  }

  // The shootout as on TV: one row per team, a lamp per kick (green goal, red miss, dark to
  // come). Five each, then one more a side while it goes on.
  function pontos(disputa, adversario) {
    // on the board, and right above the minigame, where the kicker's eyes are
    for (const id of ["s7-pontos", "s7-pontos-pen"]) desenharPontos($(id), disputa, adversario);
    $("s7-pontos").hidden = false;
  }

  function desenharPontos(caixa, disputa, adversario) {
    const total = Math.max(5, disputa.nossas.length, disputa.deles.length);
    caixa.replaceChildren();
    for (const [nome, lado] of [
      [jogo.nome, disputa.nossas],
      [adversario, disputa.deles],
    ]) {
      const fila = el("div", "s7-fila");
      fila.append(el("span", "lamp quem", nome));
      const bolas = el("span", "bolas");
      for (let i = 0; i < total; i++) {
        const p = el("span", "p");
        if (i < lado.length) p.classList.add(lado[i] ? "g" : "e");
        p.setAttribute("aria-label", i < lado.length ? (lado[i] ? "gol" : "perdeu") : "a cobrar");
        bolas.append(p);
      }
      fila.append(bolas);
      caixa.append(fila);
    }
  }

  async function penalti(pedido, adversario) {
    if (!(pedido.n in estado.disputaDoJogo)) {
      estado.disputaDoJogo[pedido.n] = estado.cobrancas.length;
      estado.cobrancas.push([]);
    }
    const lista = estado.cobrancas[estado.disputaDoJogo[pedido.n]];
    if (estado.simulando || !window.jogarPenalti) {
      lista.push({ resultado: "motor" });
      return jogar();
    }
    const feitos = (lado) => lado.filter(Boolean).length;
    lampadas($("s7-campanha"), partidas, pedido.n);
    $("s7-nos").textContent = jogo.nome;
    $("s7-eles").textContent = adversario;
    $("s7-gols-nos").textContent = String(pedido.nosso);
    $("s7-gols-eles").textContent = String(pedido.deles);
    $("s7-gols").replaceChildren();
    pontos(pedido.disputa, adversario);
    $("s7-situacao").textContent =
      `Pênaltis: ${jogo.nome} ${feitos(pedido.disputa.nossas)} × ` +
      `${feitos(pedido.disputa.deles)} ${adversario} · bate ${pedido.cobrador}`;
    const palco = $("s7-penalti");
    if (palco.hidden) {
      // the first kick of the shootout; the pitch then stays up until it ends, so the page
      // doesn't shrink and jump between kicks
      palco.hidden = false;
      rolar(palco, true);
    }
    const [nossos, deles] = [feitos(pedido.disputa.nossas), feitos(pedido.disputa.deles)];
    const resultado = await window.jogarPenalti($("s7-pen-jogo"), {
      finalizacao: pedido.chance,
      clube: jogo.nome,
      adversario,
      tipo: "disputa",
      minuto: "Pênaltis",
      competicao: pedido.n === JOGOS ? "Final" : `Jogo ${pedido.n}`,
      copa: "7a0",
      placar: [`${nossos} × ${deles}`, `${nossos + 1} × ${deles}`],
      seguir: "Próxima cobrança →",
    });
    lista.push({ resultado });
    jogar();
  }

  function fecharPenalti() {
    const palco = $("s7-penalti");
    if (palco.hidden) return;
    palco.hidden = true;
    $("s7-pen-jogo").replaceChildren();
  }

  $("s7-proximo").addEventListener("click", () => jogar());
  $("s7-simular").addEventListener("click", () => {
    estado.simulando = true;
    jogar();
  });

  // --- 3. card -------------------------------------------------------------------------------

  function desenharCard(campanha) {
    const ps = campanha.partidas;
    const ultima = ps[ps.length - 1];
    $("s7-kicker").textContent = `O 7a0 do ${jogo.nome}`;
    $("s7-titulo").textContent = campanha.campeao
      ? "Campeão invicto"
      : ultima.n === JOGOS
        ? "Caiu na final"
        : `Caiu no jogo ${ultima.n}`;
    lampadas($("s7-card-campanha"), ps, 0);
    const final = $("s7-placar-final");
    final.replaceChildren(
      el("span", "rotulo", ultima.n === JOGOS ? "Final" : `Jogo ${ultima.n}`),
      el("span", "", `${jogo.nome} ${ultima.nosso} × ${ultima.deles} ${nomeDe(ultima.adversario)}`),
    );
    if (ultima.disputa) {
      const [a, b] = [ultima.disputa.nossas, ultima.disputa.deles].map((l) => l.filter(Boolean).length);
      final.append(el("span", "rotulo", `Pênaltis: ${a} × ${b}`));
    }

    const pro = ps.reduce((s, p) => s + p.nosso, 0);
    const contra = ps.reduce((s, p) => s + p.deles, 0);
    const vitorias = ps.filter((p) => p.venceu).length;
    const autores = {};
    for (const p of ps) for (const g of p.gols) if (g.nosso) {
          const quem = partes(g.autor).curto;
          autores[quem] = (autores[quem] || 0) + 1;
        }
    const [artilheiro, gols] = Object.entries(autores).sort((a, b) => b[1] - a[1])[0] || [];
    const trilha = $("s7-trilha");
    trilha.replaceChildren();
    const linha = (rotulo, valor, resto) => {
      const li = el("li");
      li.append(el("b", "", rotulo), document.createTextNode(resto));
      if (valor) li.prepend(document.createTextNode(valor));
      return li;
    };
    trilha.append(
      linha(`${vitorias} ${vitorias === 1 ? "vitória" : "vitórias"}`, "", ` · ${pro} gols pró, ${contra} contra`),
    );
    if (artilheiro) trilha.append(linha(artilheiro, "Artilheiro: ", `, ${gols} ${gols === 1 ? "gol" : "gols"}`));

    const marcas = $("s7-marcas");
    marcas.replaceChildren();
    for (const id of campanha.marcas) {
      const m = (jogo.marcas || {})[id];
      const selo = el("span", "", m ? m.nome : id);
      if (m) selo.title = m.texto;
      marcas.append(selo);
    }
    const vagas = [];
    for (const e of campanha.escalacao) vagas[e.vaga] = { jogador: e.jogador, epoca: e.epoca.rotulo };
    desenharCampo($("s7-card-campo"), campanha.esquema, vagas, false);
  }

  function terminar(campanha, codigo) {
    desenharCard(campanha);
    const compartilhar = $("s7-compartilhar");
    compartilhar.hidden = !codigo;
    if (codigo) {
      const url = `${location.origin}/jogos/7a0/c/${codigo}`;
      const texto =
        `7a0 do ${jogo.nome}: ` +
        (campanha.campeao ? "campeão invicto 🏆" : `caí no jogo ${campanha.partidas.length}`);
      compartilhar.onclick = async () => {
        if (navigator.share) {
          try {
            await navigator.share({ title: "7a0 do clube", text: texto, url });
          } catch {
            /* closed the share sheet */
          }
          return;
        }
        await navigator.clipboard?.writeText(`${texto} ${url}`);
        compartilhar.textContent = "Link copiado";
      };
    }
    tela("s7-fim");
    rolar($("s7-fim"), true);
  }

  // --- start ---------------------------------------------------------------------------------

  estado = novo();
  if (jogo.compartilhada) {
    desenharCard(jogo.compartilhada.campanha);
    tela("s7-fim");
    return;
  }
  montarInicio();
  tela("s7-inicio");
})();
