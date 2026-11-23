// Carreira's first minigame: the cup final's penalty, 90+4'. The aim wanders over the goal, a
// lamp bar sets the power, the keeper dives. The player's finishing (`finalizacao`) sets how wide
// the good power band is and how fast the aim moves. Click, touch or space: aim, then power.
//
// window.jogarPenalti(el, {finalizacao, clube, adversario, copa, camisa})
//   -> Promise<"gol" | "defesa" | "fora" | "trave" | "motor">
// The result comes from the browser: a game to share, not a ranking.
(() => {
  const W = 360, H = 470;
  const C = {
    paper: "#EFE4CC", concrete: "#8E8B84", concreteLt: "#B9B5AC", ink: "#14231A", ticket: "#E3B23C",
    board: "#0B0B0A", lamp: "#FFC21A", turf: "#0E3320", pitch: "#1F7A3D", pitch2: "#248A46",
  };
  const GOL = { x0: 72, x1: 288, topo: 128, chao: 232, fundo: 14 }; // fundo: how deep the net looks
  const MARCA = { x: 180, y: 392 };
  const ZONA = { centro: 0.68 };
  const FIM = { gol: "GOOOL", defesa: "DEFENDEU", fora: "PRA FORA", trave: "NA TRAVE" };
  const DICAS = {
    gol: "Gol! É campeão",
    defesa: "Defendeu. A taça escapou",
    fora: "Pra fora. A taça escapou",
    trave: "Na trave. A taça escapou",
  };
  const TEXTOS = {
    gol: [["É campeão! Frieza na marca da cal", "Aos 94 minutos, a bola no canto e o estádio abaixo."],
          ["Não tremeu: título na última bola", "Pênalti cobrado com a calma de quem já viu tudo."]],
    defesa: [["O goleiro adivinhou e a taça escapou", "A cobrança foi no canto que ele escolheu."],
             ["Pênalti defendido, festa adiada", "Faltou convicção na batida decisiva."]],
    fora: [["Isolou! A bola foi parar na Geral", "O título escapou no último lance da final."]],
    trave: [["Na trave! O grito ficou preso", "O barulho do poste ecoou no estádio calado."]],
  };

  // The crowd behind the goal: muted dots, a few ticket-yellow (radinho, papel picado).
  const TORCIDA = [];
  {
    let s = 7;
    const rng = () => (s = (s * 16807) % 2147483647) / 2147483647;
    for (let fila = 0; fila < 11; fila++) {
      const y = 62 + fila * 8;
      for (let x = 2; x < W; x += 5 + rng() * 3) {
        const tons = ["#2b2b28", "#3d3a34", "#57534b", "#6f6a60", C.paper, "#9c968a"];
        TORCIDA.push({ x, y: y + rng() * 3, c: rng() < 0.05 ? C.ticket : tons[Math.floor(rng() * tons.length)],
                       fase: rng() * 6.28, r: 1.6 + rng() * 0.9 });
      }
    }
  }

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const gauss = () => (Math.random() + Math.random() + Math.random() - 1.5) / 1.5;

  function jogarPenalti(raiz, { finalizacao, clube, adversario, copa, camisa = 9 }) {
    const numero = camisa;
    const fin = Math.max(40, Math.min(95, Number(finalizacao) || 60));
    const largZona = 0.10 + (fin - 40) / 55 * 0.16;
    const velMira = 1.5 - (fin - 40) / 55 * 0.6;

    // -- the markup: scoreboard, pitch, the hint strip, the clipping and the engine's button ---
    const palco = el("div", "pn-palco");
    const placar = el("div", "pn-placar");
    const gols = el("div", "pn-gols lamp", "1 × 1");
    const relogio = el("span", "", "90+4'");
    const linha2 = el("div", "pn-linha2 lamp");
    linha2.append(relogio, el("span", "pn-copa", copa));
    placar.append(el("div", "pn-time lamp", clube), gols, el("div", "pn-time lamp", adversario), linha2);
    const cv = el("canvas", "pn-campo");
    cv.setAttribute("role", "img");
    cv.setAttribute("aria-label", `Pênalti na final da ${copa}: toque ou aperte espaço para travar a mira e depois a força`);
    const dica = el("div", "pn-faixa", "Toque para travar a mira");
    dica.setAttribute("aria-live", "polite");
    palco.append(placar, cv, dica);

    const recorte = el("div", "pn-recorte");
    const jornal = el("div", "pn-jornal");
    jornal.append(el("span", "", "A Geral · Edição extra"), el("b", "", copa));
    const manchete = el("h2", "");
    const sub = el("p", "");
    recorte.append(jornal, manchete, sub);

    const controles = el("div", "pn-controles");
    const motor = el("button", "btn secondary pn-motor", "Deixar o motor bater");
    motor.type = "button";
    const seguir = el("button", "btn pn-seguir", "Seguir a carreira →");
    seguir.type = "button";
    seguir.hidden = true;
    controles.append(motor, seguir);

    const caixa = el("div", "pn");
    caixa.append(palco, recorte, controles);
    raiz.replaceChildren(caixa);

    const ctx = cv.getContext("2d");
    function ajustar() {
      const r = window.devicePixelRatio || 1;
      const w = cv.clientWidth || W;
      cv.width = Math.round(w * r);
      cv.height = Math.round(w * H / W * r);
      ctx.setTransform(cv.width / W, 0, 0, cv.height / H, 0, 0);
    }

    // -- the state ------------------------------------------------------------------------------
    let fase = "mira", t0 = performance.now(), forca = 0, chute = null, resultado = null;
    let festa = 0, rede = null, flash = 0, quadroId = 0;
    const mira = { x: 180, y: 175 };
    const goleiro = { x: 180, alvo: 180, alto: false };

    let resolver;
    const promessa = new Promise((r) => (resolver = r));
    function encerrar(valor) {
      cancelAnimationFrame(quadroId);
      removeEventListener("resize", ajustar);
      document.removeEventListener("keydown", tecla);
      resolver(valor);
    }

    function acao() {
      if (fase === "mira") {
        fase = "forca"; t0 = performance.now();
        dica.textContent = "Agora a força: pare na faixa acesa";
      } else if (fase === "forca") correr();
    }

    function correr() {
      const f = forca;
      const fora = Math.max(0, Math.abs(f - ZONA.centro) - largZona / 2);
      const erro = 6 + fora * 160 + (95 - fin) * 0.25;
      const alvo = { x: mira.x + gauss() * erro, y: mira.y + gauss() * erro * 0.6 };
      if (f > ZONA.centro + largZona / 2) alvo.y -= fora * 260;
      const velocidade = 0.55 + f * 0.6;
      chute = { de: { ...MARCA }, para: alvo, dur: 620 / velocidade, velocidade, corrida: 520 };
      const lado = alvo.x < 150 ? -1 : alvo.x > 210 ? 1 : 0;
      const escolha = Math.random() < 0.35 ? lado : [-1, 0, 1][Math.floor(Math.random() * 3)];
      goleiro.alvo = 180 + escolha * 78; goleiro.alto = Math.random() < 0.4;
      fase = "corrida"; t0 = performance.now();
      dica.textContent = "…";
      motor.hidden = true; // the kick is taken: no going back to the engine
    }

    function julgar() {
      const { x, y } = chute.para;
      const perto = (a, b) => Math.abs(a - b) < 5;
      if ((perto(x, GOL.x0) || perto(x, GOL.x1)) && y > GOL.topo - 4 && y < GOL.chao) return "trave";
      if (perto(y, GOL.topo) && x > GOL.x0 - 4 && x < GOL.x1 + 4) return "trave";
      if (x < GOL.x0 || x > GOL.x1 || y < GOL.topo) return "fora";
      const alcance = 32 + (1.15 - chute.velocidade) * 60;
      const gy = goleiro.alto ? 160 : 205;
      return Math.hypot(x - goleiro.alvo, (y - gy) * 0.8) < alcance ? "defesa" : "gol";
    }

    function terminar() {
      resultado = julgar(); fase = "fim"; t0 = performance.now();
      if (resultado === "gol") {
        festa = 1; flash = 1; gols.textContent = "2 × 1";
        rede = { x: chute.para.x, y: chute.para.y, t: performance.now() };
      }
      relogio.textContent = "Fim de jogo";
      const opcoes = TEXTOS[resultado];
      const [titulo, linha] = opcoes[Math.floor(Math.random() * opcoes.length)];
      manchete.textContent = titulo; sub.textContent = linha;
      dica.textContent = DICAS[resultado];
      setTimeout(() => {
        recorte.classList.add("on");
        seguir.hidden = false;
        seguir.focus({ preventScroll: true });
      }, 700);
    }

    // -- drawing --------------------------------------------------------------------------------
    function ceu() {
      const g = ctx.createLinearGradient(0, 0, 0, 120);
      g.addColorStop(0, "#05080a"); g.addColorStop(1, "#14211b");
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, 130);
      for (const x of [26, W - 26]) { // floodlights
        const luz = ctx.createRadialGradient(x, 18, 2, x, 18, 90);
        luz.addColorStop(0, "rgba(255,240,200,.55)"); luz.addColorStop(1, "rgba(255,240,200,0)");
        ctx.fillStyle = luz; ctx.fillRect(x - 90, 0, 180, 120);
        ctx.fillStyle = "#2a2a26"; ctx.fillRect(x - 2, 22, 4, 40);
        ctx.fillStyle = "#fff8de";
        for (let i = 0; i < 3; i++) for (let j = 0; j < 2; j++) ctx.fillRect(x - 9 + i * 6, 10 + j * 5, 4, 3);
      }
    }

    function arquibancada(agora) {
      ctx.fillStyle = C.concrete; ctx.fillRect(0, 56, W, 96);
      for (let i = 0; i < 12; i++) { ctx.fillStyle = i % 2 ? "#7f7c75" : "#88857e"; ctx.fillRect(0, 58 + i * 8, W, 4); }
      const pulo = festa ? Math.max(0, 1 - (agora - t0) / 4000) : 0;
      for (const p of TORCIDA) {
        const dy = pulo ? -Math.abs(Math.sin(agora / 110 + p.fase)) * 4 * pulo : Math.sin(agora / 900 + p.fase) * 0.4;
        ctx.fillStyle = p.c; ctx.beginPath(); ctx.arc(p.x, p.y + dy, p.r, 0, 7); ctx.fill();
      }
      // the low wall of the old Geral and the ad boards
      ctx.fillStyle = C.concreteLt; ctx.fillRect(0, 146, W, 10);
      ctx.fillStyle = C.board; ctx.fillRect(0, 150, W, 14);
      ctx.font = "900 9px Doto, monospace"; ctx.fillStyle = C.lamp; ctx.textAlign = "center";
      ctx.shadowColor = "rgba(255,194,26,.7)"; ctx.shadowBlur = 4;
      ctx.fillText("A GERAL · O JORNAL DA TORCIDA · A GERAL · O JORNAL DA TORCIDA", W / 2, 160);
      ctx.shadowBlur = 0;
    }

    function gramado() {
      for (let i = 0; i < 12; i++) {
        const y0 = 164 + i * i * 2.6 + i * 6, y1 = 164 + (i + 1) * (i + 1) * 2.6 + (i + 1) * 6;
        ctx.fillStyle = i % 2 ? C.pitch : C.pitch2; ctx.fillRect(0, y0, W, y1 - y0 + 1);
      }
      ctx.strokeStyle = "rgba(255,255,255,.75)"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(0, GOL.chao); ctx.lineTo(W, GOL.chao); ctx.stroke(); // goal line
      ctx.beginPath(); ctx.moveTo(40, GOL.chao); ctx.lineTo(18, 272); ctx.lineTo(342, 272); ctx.lineTo(320, GOL.chao); ctx.stroke(); // goal area
      ctx.beginPath(); ctx.moveTo(-10, 330); ctx.lineTo(370, 330); ctx.stroke(); // penalty area (front edge)
      ctx.beginPath(); ctx.ellipse(180, 352, 70, 16, 0, Math.PI * 0.08, Math.PI * 0.92); ctx.stroke(); // the arc
      ctx.fillStyle = "#fff"; ctx.beginPath(); ctx.ellipse(MARCA.x, MARCA.y + 9, 4, 2, 0, 0, 7); ctx.fill();
    }

    function golEsqueleto(agora) {
      const { x0, x1, topo, chao, fundo } = GOL;
      ctx.fillStyle = "rgba(10,20,14,.35)"; ctx.fillRect(x0 + fundo, topo - 10, x1 - x0 - fundo * 2, chao - topo + 10);
      let bojo = 0, bx = 0, by = 0;
      if (rede) { const t = (agora - rede.t) / 600; bojo = t < 1 ? Math.sin(t * Math.PI) * 10 * (1 - t * 0.5) : 0; bx = rede.x; by = rede.y; }
      ctx.strokeStyle = "rgba(255,255,255,.35)"; ctx.lineWidth = 1;
      const desloca = (x, y) => { if (!bojo) return [x, y]; const d = Math.hypot(x - bx, y - by); const k = Math.max(0, 1 - d / 60) * bojo; return [x, y - k]; };
      for (let x = x0 + fundo; x <= x1 - fundo; x += 9) {
        ctx.beginPath();
        for (let y = topo - 10; y <= chao; y += 6) { const [a, b] = desloca(x, y); y === topo - 10 ? ctx.moveTo(a, b) : ctx.lineTo(a, b); }
        ctx.stroke();
      }
      for (let y = topo - 10; y <= chao; y += 9) {
        ctx.beginPath();
        for (let x = x0 + fundo; x <= x1 - fundo; x += 6) { const [a, b] = desloca(x, y); x === x0 + fundo ? ctx.moveTo(a, b) : ctx.lineTo(a, b); }
        ctx.stroke();
      }
      ctx.beginPath(); ctx.moveTo(x0, topo); ctx.lineTo(x0 + fundo, topo - 10); ctx.lineTo(x0 + fundo, chao); ctx.moveTo(x1, topo); ctx.lineTo(x1 - fundo, topo - 10); ctx.lineTo(x1 - fundo, chao); ctx.stroke();
      ctx.strokeStyle = "rgba(0,0,0,.3)"; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(x0 + 3, chao + 3); ctx.lineTo(x1 + 3, chao + 3); ctx.stroke();
      ctx.strokeStyle = "#fbfbf6"; ctx.lineWidth = 6; ctx.lineCap = "square";
      ctx.beginPath(); ctx.moveTo(x0, chao); ctx.lineTo(x0, topo); ctx.lineTo(x1, topo); ctx.lineTo(x1, chao); ctx.stroke();
      ctx.lineCap = "butt";
    }

    function desenharGoleiro(agora) {
      let p = 0;
      if (fase === "voo" || fase === "fim") p = Math.min(1, Math.max(0, (agora - chute.inicio - 110) / 360));
      const balanco = fase === "mira" || fase === "forca" ? Math.sin(agora / 260) * 6 : 0;
      const x = goleiro.x + balanco + (goleiro.alvo - goleiro.x) * p;
      const dir = goleiro.alvo < 179 ? -1 : goleiro.alvo > 181 ? 1 : 0;
      const y = (goleiro.alto ? 196 - 46 * Math.sin(p * Math.PI * 0.6) : 196 - 6 * p) + (dir ? 14 * p : 0);
      ctx.save(); ctx.translate(x, y); ctx.rotate(dir * p * 1.25);
      ctx.fillStyle = "rgba(0,0,0,.25)"; ctx.beginPath(); ctx.ellipse(0, 36, 16, 4, 0, 0, 7); ctx.fill();
      ctx.fillStyle = "#1b1b1b"; ctx.fillRect(-9, 12, 7, 22); ctx.fillRect(2, 12, 7, 22); // legs
      ctx.fillStyle = "#111"; ctx.fillRect(-12, -16, 24, 30); // shirt: the old all-black keeper
      ctx.fillStyle = "#2c2c2c"; ctx.fillRect(-12, 6, 24, 6);
      const braco = fase === "voo" || fase === "fim" ? -18 - 10 * p : -6;
      ctx.fillStyle = "#111"; ctx.fillRect(-26, braco, 14, 6); ctx.fillRect(12, braco, 14, 6);
      ctx.fillStyle = C.ticket; ctx.fillRect(-30, braco - 1, 6, 8); ctx.fillRect(24, braco - 1, 6, 8); // gloves
      ctx.fillStyle = "#b98a64"; ctx.beginPath(); ctx.arc(0, -23, 7, 0, 7); ctx.fill();
      ctx.fillStyle = "#1e1e1e"; ctx.beginPath(); ctx.arc(0, -26, 7, Math.PI, 0); ctx.fill();
      ctx.restore();
    }

    function desenharCobrador(agora) {
      let k = 0; // run-up progress
      if (fase === "corrida") k = Math.min(1, (agora - t0) / chute.corrida);
      if (fase === "voo" || fase === "fim") k = 1;
      const x = 128 + (MARCA.x - 20 - 128) * k, y = 462 - (462 - 430) * k;
      const passo = fase === "corrida" ? Math.sin(agora / 50) * 5 : 0;
      ctx.save(); ctx.translate(x, y);
      ctx.fillStyle = "rgba(0,0,0,.25)"; ctx.beginPath(); ctx.ellipse(0, 40, 22, 6, 0, 0, 7); ctx.fill();
      ctx.fillStyle = "#1e1e1e"; ctx.fillRect(-11, 14 + passo, 9, 26); ctx.fillRect(3, 14 - passo, 9, 26); // legs
      ctx.fillStyle = C.ink; ctx.fillRect(-14, 6, 28, 12); // shorts
      ctx.fillStyle = C.paper; ctx.fillRect(-16, -26, 32, 34); // plain shirt, no club
      ctx.fillStyle = C.ink; ctx.font = "800 18px 'Big Shoulders Display', Impact"; ctx.textAlign = "center";
      ctx.fillText(String(numero), 0, -2);
      ctx.fillStyle = C.paper; ctx.fillRect(-24, -24, 9, 22); ctx.fillRect(15, -24, 9, 22);
      ctx.fillStyle = "#a87a55"; ctx.beginPath(); ctx.arc(0, -34, 9, 0, 7); ctx.fill();
      ctx.fillStyle = "#1e1e1e"; ctx.beginPath(); ctx.arc(0, -36, 9, Math.PI * 0.95, Math.PI * 2.05); ctx.fill();
      ctx.restore();
    }

    function bola(x, y, r, giro) {
      ctx.save(); ctx.translate(x, y); ctx.rotate(giro);
      ctx.fillStyle = "#fbfbf6"; ctx.beginPath(); ctx.arc(0, 0, r, 0, 7); ctx.fill();
      ctx.fillStyle = "#1e1e1e";
      ctx.beginPath(); for (let i = 0; i < 5; i++) { const a = i * 1.2566 - 1.57; ctx.lineTo(Math.cos(a) * r * 0.38, Math.sin(a) * r * 0.38); } ctx.fill();
      for (let i = 0; i < 5; i++) { const a = i * 1.2566 + 0.63; ctx.beginPath(); ctx.arc(Math.cos(a) * r * 0.85, Math.sin(a) * r * 0.85, r * 0.22, 0, 7); ctx.fill(); }
      ctx.restore();
      ctx.strokeStyle = "rgba(0,0,0,.4)"; ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.stroke();
    }

    function desenharMira(agora) {
      const pulsa = 1 + Math.sin(agora / 120) * 0.08;
      ctx.save(); ctx.translate(mira.x, mira.y); ctx.scale(pulsa, pulsa);
      ctx.shadowColor = "rgba(255,194,26,.9)"; ctx.shadowBlur = 8; ctx.strokeStyle = C.lamp; ctx.lineWidth = 2.5;
      ctx.beginPath(); ctx.arc(0, 0, 11, 0, 7); ctx.stroke();
      for (const [a, b, c, d] of [[-20, 0, -14, 0], [14, 0, 20, 0], [0, -20, 0, -14], [0, 14, 0, 20]]) { ctx.beginPath(); ctx.moveTo(a, b); ctx.lineTo(c, d); ctx.stroke(); }
      ctx.fillStyle = C.lamp; ctx.beginPath(); ctx.arc(0, 0, 2, 0, 7); ctx.fill();
      ctx.restore();
    }

    function barraDeLampadas() { // the power meter, made of scoreboard lamps
      const n = 24, x0 = 40, y = 302, passo = (W - 80) / n, z = largZona;
      ctx.fillStyle = C.board; ctx.fillRect(x0 - 10, y - 12, W - 60, 24);
      ctx.strokeStyle = C.ink; ctx.lineWidth = 2; ctx.strokeRect(x0 - 10, y - 12, W - 60, 24);
      const ini = ZONA.centro - z / 2, fim = ZONA.centro + z / 2;
      for (let i = 0; i < n; i++) {
        const v = (i + 0.5) / n, cx = x0 + i * passo + passo / 2;
        const naZona = v >= ini && v <= fim, acesa = v <= forca;
        ctx.beginPath(); ctx.arc(cx, y, 4.2, 0, 7);
        if (acesa) { ctx.fillStyle = naZona ? "#fff3c4" : (v > 0.92 ? "#ff6a3d" : C.lamp); ctx.shadowColor = "rgba(255,194,26,.9)"; ctx.shadowBlur = 8; }
        else { ctx.fillStyle = naZona ? "#4a3a10" : "#1d1c18"; ctx.shadowBlur = 0; }
        ctx.fill(); ctx.shadowBlur = 0;
      }
      ctx.strokeStyle = C.ticket; ctx.lineWidth = 1.5;
      ctx.strokeRect(x0 + ini * (W - 80) - 1, y - 8, (fim - ini) * (W - 80) + 2, 16);
    }

    function quadro(agora) {
      const t = (agora - t0) / 1000;
      if (fase === "mira") { mira.x = 180 + Math.sin(t * 2.3 * velMira) * 110; mira.y = 180 + Math.sin(t * 3.7 * velMira + 1) * 50; }
      if (fase === "forca") forca = (Math.sin(t * 3.2 * velMira - Math.PI / 2) + 1) / 2;
      if (fase === "corrida" && agora - t0 >= chute.corrida) { fase = "voo"; chute.inicio = agora; }

      ctx.save();
      if (fase === "fim" && resultado === "trave") { const s = Math.max(0, 1 - (agora - t0) / 300) * 3; ctx.translate((Math.random() - .5) * s, (Math.random() - .5) * s); }
      ceu(); arquibancada(agora); gramado(); golEsqueleto(agora);
      desenharGoleiro(agora);

      let bx = MARCA.x, by = MARCA.y, br = 9, giro = 0;
      if (chute && (fase === "voo" || fase === "fim")) {
        const p = Math.min(1, (agora - chute.inicio) / chute.dur);
        const e = 1 - Math.pow(1 - p, 2);
        let alvo = chute.para;
        if (fase === "fim" && resultado === "defesa") alvo = { x: chute.para.x + (goleiro.alvo - chute.para.x) * 0.5, y: chute.para.y };
        bx = chute.de.x + (alvo.x - chute.de.x) * e;
        by = chute.de.y + (alvo.y - chute.de.y) * e - Math.sin(p * Math.PI) * 22;
        br = 9 - 4.5 * e; giro = p * 14;
        if (fase === "fim" && resultado === "fora") by -= Math.max(0, (agora - t0) / 6);
        const sy = MARCA.y + 9 + (GOL.chao + 4 - MARCA.y - 9) * e; // shadow on the grass
        ctx.fillStyle = "rgba(0,0,0,.28)"; ctx.beginPath(); ctx.ellipse(bx, sy, br * 0.9, br * 0.3, 0, 0, 7); ctx.fill();
        if (p >= 1 && fase === "voo") terminar();
      } else {
        ctx.fillStyle = "rgba(0,0,0,.28)"; ctx.beginPath(); ctx.ellipse(bx, by + 9, 8, 2.5, 0, 0, 7); ctx.fill();
      }
      // the ball behind the kicker before the kick, in front of the keeper after it
      if (fase === "voo" || fase === "fim") { desenharCobrador(agora); bola(bx, by, br, giro); }
      else { bola(bx, by, br, giro); desenharCobrador(agora); }

      if (fase === "mira" || fase === "forca") desenharMira(agora);
      if (fase === "forca") barraDeLampadas();

      if (flash > 0) { ctx.fillStyle = `rgba(255,248,222,${flash * 0.5})`; ctx.fillRect(0, 0, W, H); flash = Math.max(0, flash - 0.04); }
      if (fase === "fim") {
        const a = Math.min(1, (agora - t0) / 200);
        ctx.globalAlpha = a; ctx.fillStyle = C.board; ctx.fillRect(40, 270, 280, 60);
        ctx.strokeStyle = C.ink; ctx.lineWidth = 3; ctx.strokeRect(40, 270, 280, 60);
        ctx.font = "900 38px Doto, monospace"; ctx.textAlign = "center"; ctx.fillStyle = C.lamp;
        ctx.shadowColor = "rgba(255,194,26,.8)"; ctx.shadowBlur = 12;
        const pisca = resultado === "gol" && Math.floor(agora / 250) % 2 === 0 ? 0.65 : 1;
        ctx.globalAlpha = a * pisca; ctx.fillText(FIM[resultado], 180, 313);
        ctx.shadowBlur = 0; ctx.globalAlpha = 1;
      }
      ctx.restore();
      quadroId = requestAnimationFrame(quadro);
    }

    // -- input: pointer events only (no click as well, or a tap would count twice) ---------------
    function tecla(e) {
      if (e.code !== "Space" || fase === "fim") return;
      if (e.target.closest && e.target.closest("button, input, select, textarea, a")) return;
      e.preventDefault();
      acao();
    }
    // A tap acts when the finger lifts where it went down: a scroll that starts on the pitch
    // (the canvas is most of a phone's screen) moves away or gets cancelled, and kicks nothing.
    let toque = null;
    cv.addEventListener("pointerdown", (e) => {
      if (e.button === 0) toque = { id: e.pointerId, x: e.clientX, y: e.clientY };
    });
    cv.addEventListener("pointercancel", () => (toque = null));
    cv.addEventListener("pointerup", (e) => {
      const t = toque;
      toque = null;
      if (!t || t.id !== e.pointerId || Math.hypot(e.clientX - t.x, e.clientY - t.y) > 12) return;
      e.preventDefault();
      acao();
    });
    document.addEventListener("keydown", tecla);
    addEventListener("resize", ajustar);
    motor.addEventListener("click", () => encerrar("motor"));
    seguir.addEventListener("click", () => encerrar(resultado));

    ajustar();
    quadroId = requestAnimationFrame(quadro);
    return promessa;
  }

  window.jogarPenalti = jogarPenalti;
})();
