// "Onde jogou?": pick clubs from a searchable, country-filtered, paged list; the server judges
// every club picked so far. The day's picks and the streak live in localStorage (per edition).
// No dependencies.
(() => {
  const root = document.getElementById("oj");
  if (!root) return;
  const { edition, label, player } = root.dataset;
  const number = Number(root.dataset.number);
  const max = Number(root.dataset.max);
  const $ = (id) => document.getElementById(id);
  const form = $("oj-form");
  const search = $("oj-search");
  const KEY = `onde-jogou:${edition}`;
  const PAGE = 12;
  const ALL = "Todos";

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

  // The club list: every name and alias searchable without accents.
  const clubs = JSON.parse($("oj-club-data").textContent).map((club) => ({
    ...club,
    keys: [club.nome, ...club.apelidos].map(plain),
  }));
  const byCountry = new Map();
  clubs.forEach((club) => byCountry.set(club.pais, (byCountry.get(club.pais) || 0) + 1));
  // Brazil first, then the countries with more clubs; "Outros" last.
  const countries = [...byCountry.keys()].sort(
    (a, b) =>
      (b === "Brasil") - (a === "Brasil") ||
      (a === "Outros") - (b === "Outros") ||
      byCountry.get(b) - byCountry.get(a) ||
      a.localeCompare(b, "pt"),
  );

  // The full list follows the same order: Brazil's clubs first.
  const rank = new Map(countries.map((name, i) => [name, i]));
  clubs.sort((a, b) => rank.get(a.pais) - rank.get(b.pais) || a.nome.localeCompare(b.nome, "pt"));
  const TOP = 8; // countries shown as chips; the rest go in a menu

  let day = read(KEY, null);
  // A new day, or the list changed today's player: start over.
  if (!day || day.number !== number || day.player !== player) {
    day = { number, player, palpites: [], desistiu: false };
  }
  let verdict = null;
  let busy = false;
  let country = ALL;
  let page = 0;

  const error = (text) => {
    $("oj-error").textContent = text;
    $("oj-error").hidden = !text;
  };

  const matches = () => {
    const query = plain(search.value);
    let found = clubs.filter((c) => country === ALL || c.pais === country);
    if (query) {
      found = found
        .filter((c) => c.keys.some((k) => k.includes(query)))
        .sort(
          (a, b) =>
            b.keys.some((k) => k.startsWith(query)) - a.keys.some((k) => k.startsWith(query)) ||
            a.nome.localeCompare(b.nome, "pt"),
        );
    }
    return found;
  };

  const picked = () => {
    // Club name -> "found" | "wrong", from the last verdict.
    const marks = new Map();
    // The edition's own team comes lit from the page, before any guess.
    document.querySelectorAll(".slot-club.given").forEach((s) => marks.set(s.textContent, "found"));
    if (!verdict) return marks;
    verdict.slots.forEach((s) => (s.achado || s.dado) && marks.set(s.clube, "found"));
    verdict.erros.forEach((name) => marks.set(name, "wrong"));
    return marks;
  };

  const choose = (name) => {
    country = name;
    page = 0;
    drawCountries();
    drawResults();
  };

  const drawCountries = () => {
    const chips = [ALL, ...countries.slice(0, TOP)].map((name) => {
      const count = name === ALL ? clubs.length : byCountry.get(name);
      const chip = el("button", "chip", `${name} (${count})`);
      chip.type = "button";
      chip.setAttribute("aria-pressed", String(name === country));
      chip.addEventListener("click", () => choose(name));
      return chip;
    });
    const rest = countries.slice(TOP);
    if (rest.length) {
      const menu = el("select", `chip${rest.includes(country) ? " on" : ""}`);
      menu.setAttribute("aria-label", "Outro país");
      menu.append(el("option", "", "Outro país…"));
      menu.firstChild.value = "";
      rest.forEach((name) => {
        const option = el("option", "", `${name} (${byCountry.get(name)})`);
        option.value = name;
        option.selected = name === country;
        menu.append(option);
      });
      menu.addEventListener("change", () => choose(menu.value || ALL));
      chips.push(menu);
    }
    $("oj-countries").replaceChildren(...chips);
  };

  const drawResults = () => {
    const found = matches();
    const pages = Math.max(1, Math.ceil(found.length / PAGE));
    page = Math.min(page, pages - 1);
    const marks = picked();
    $("oj-results").replaceChildren(
      ...found.slice(page * PAGE, page * PAGE + PAGE).map((club) => {
        const li = el("li");
        const button = el("button", `club ${marks.get(club.nome) || ""}`.trim());
        button.type = "button";
        button.append(el("span", "club-name", club.nome), el("span", "club-country", club.pais));
        button.title = club.nome; // the full name when two lines cut it
        button.disabled = marks.has(club.nome) || busy;
        button.addEventListener("click", () => guess(club.nome));
        li.append(button);
        return li;
      }),
    );
    if (!found.length) $("oj-results").append(el("li", "empty", "Nenhum clube com esse nome. Tente um apelido ou outro país."));
    $("oj-page").textContent = `Página ${page + 1} de ${pages} · ${found.length} clubes`;
    $("oj-prev").disabled = page === 0;
    $("oj-next").disabled = page >= pages - 1;
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
    $("oj-streak").textContent = stats.streak;
    $("oj-wins").textContent = stats.wins;
    $("oj-played").textContent = stats.played;
  };

  const render = () => {
    const slots = $("oj-slots").children;
    verdict.slots.forEach((slot, i) => {
      if (!slot.clube) return;
      const shown = slots[i].lastElementChild;
      const kind = slot.dado ? "given" : slot.achado ? "found" : "missed";
      shown.replaceWith(el("span", `slot-club ${kind}`, slot.clube));
    });
    $("oj-wrong").textContent = verdict.erros.length
      ? `Errou (${verdict.erros.length} de ${max}): ${verdict.erros.join(", ")}`
      : "";
    form.hidden = verdict.over;
    $("oj-result").hidden = !verdict.over;
    drawResults();
    if (!verdict.over) return;
    $("oj-title").textContent = verdict.solved ? "Carreira completa!" : "Fim de jogo";
    $("oj-final").textContent = `${verdict.achados} de ${verdict.total} clubes`;
    finish();
  };

  const judge = async () => {
    const response = await fetch(`/api/jogos/onde-jogou/${edition}/${number}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ palpites: day.palpites, desistiu: day.desistiu }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    verdict = await response.json();
    render();
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
    } catch {
      undo();
      error("Não deu para conferir agora. Tente de novo.");
    } finally {
      busy = false;
      drawResults();
    }
  };

  const guess = (name) =>
    play(
      () => day.palpites.push(name),
      () => day.palpites.pop(),
    );

  search.addEventListener("input", () => {
    page = 0;
    drawResults();
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault(); // Enter picks the club when the search leaves only one
    const found = matches();
    if (found.length === 1 && !picked().has(found[0].nome)) guess(found[0].nome);
  });
  $("oj-prev").addEventListener("click", () => {
    page -= 1;
    drawResults();
  });
  $("oj-next").addEventListener("click", () => {
    page += 1;
    drawResults();
  });
  $("oj-give-up").addEventListener("click", () =>
    play(
      () => (day.desistiu = true),
      () => (day.desistiu = false),
    ),
  );

  $("oj-share").addEventListener("click", async () => {
    const found = verdict.achados;
    const squares = "🟩".repeat(found) + "⬛".repeat(verdict.total - found);
    const text = `Onde jogou? #${number} · ${label} ${found}/${verdict.total}\n${squares}\n${location.href}`;
    try {
      if (navigator.share) await navigator.share({ text });
      else {
        await navigator.clipboard.writeText(text);
        $("oj-copied").textContent = "Copiado!";
      }
    } catch {
      /* the user closed the share sheet */
    }
  });

  drawCountries();
  drawResults();
  if (day.palpites.length || day.desistiu) {
    form.hidden = true; // until we know whether today's game is over
    judge().catch(() => {
      form.hidden = false;
    });
  }
})();
