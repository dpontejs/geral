// The player search of the jogo da velha (a dialog over the board), for the duel by link:
// GeralVelhaBusca({ onPick(id), taken() -> Set }) returns { open(title), close(), error(text) }.
window.GeralVelhaBusca = ({ onPick, taken }) => {
  const $ = (id) => document.getElementById(id);
  const dialog = $("jv-dialog");
  const search = $("jv-search");
  const results = $("jv-results");
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const error = (text) => {
    $("jv-error").textContent = text;
    $("jv-error").hidden = !text;
  };
  const draw = (found) => {
    const used = taken();
    results.replaceChildren(
      ...found.map((p) => {
        const li = el("li");
        const button = el("button", "club");
        button.type = "button";
        button.append(el("span", "club-name", p.nome), el("span", "club-country", [p.anos, p.posicao].filter(Boolean).join(" · ")));
        button.disabled = used.has(p.id);
        button.addEventListener("click", () => onPick(p.id));
        li.append(button);
        return li;
      }),
    );
    if (!found.length && search.value.trim().length >= 2) results.append(el("li", "empty", "Nenhum jogador com esse nome."));
  };
  let timer = null;
  let pending = null;
  search.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (pending) pending.abort();
      pending = new AbortController();
      const asked = search.value;
      try {
        const response = await fetch(`/api/jogos/velha/jogadores?q=${encodeURIComponent(asked)}`, { signal: pending.signal });
        if (response.ok && search.value === asked) draw(await response.json());
      } catch {
        /* a newer search replaced this one */
      }
    }, 250);
  });
  $("jv-form").addEventListener("submit", (event) => {
    event.preventDefault(); // Enter picks the player when the search leaves only one
    const only = results.querySelectorAll("button.club:not(:disabled)");
    if (only.length === 1) only[0].click();
  });
  $("jv-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  return {
    open(title) {
      $("jv-cell-label").textContent = title;
      search.value = "";
      results.replaceChildren();
      error("");
      dialog.showModal();
      search.focus();
    },
    close() {
      if (dialog.open) dialog.close();
    },
    error,
    dialog,
  };
};
