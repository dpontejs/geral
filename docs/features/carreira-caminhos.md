# Carreira: decisões que mudam o caminho

- **Data:** 2026-11-23
- **Status:** aprovada (revisada por um leitor de fora; decisões de Claude marcadas em Contratos:
  mercado depois de "ficar", o que conta no teto, posição final)
- **ADRs:** —

## Objetivo

Dar ao torcedor mais influência e mais variedade na carreira. Hoje as decisões são quase só de
mercado (ficar/sair), as do dia a dia mexem pouco e não há aposta difícil; as manchetes se repetem.
Inspiração: o GAMBETA decide contrato, técnico, vestiário e imprensa (pesquisa em
`docs/pesquisa/joguinhos-de-carreira.md`). Caminho escolhido pelo dev: **marcas** no histórico que
o motor já tem (opção A; descartados medidores de reputação, difíceis de equilibrar e invisíveis, e
arcos roteirizados, caros de escrever — arcos curtos saem das próprias marcas).

## Fora de escopo

- Minijogos (projeto seguinte). Goleiro. Mostrar medidores numéricos.
- Rever as notas das lendas.

## Contratos

- **Marcas** (`carreira/marcas.toml`): `id`, `nome` ("Capitão"), `texto` da linha do tempo
  ("{nome} ganha a braçadeira"), `efeito: Efeito` aplicado uma vez ao ganhar. Guardadas em
  `_Simulacao.historico`, o mesmo conjunto que `Condicao.requer/exclui` já lê; por isso eventos,
  decisões, dia a dia e finais podem exigir ou excluir uma marca.
- `dados.Opcao` (decisão) ganha os campos de `OpcaoRotina`: `chance`, `bonus`, `sucesso`,
  `fracasso`, e mais `marca` / `marca_fracasso` (id gravado conforme o resultado). Sem `chance`,
  a opção é certa, como hoje. `OpcaoRotina` ganha `marca` / `marca_fracasso` também.
- `Efeito.posicao: str = ""`: muda a posição dali em diante ("virou meia"), recalculando a nota geral.
- Decisões fora do mercado usam `destino = "ficar"` (não muda de clube).
- `Escolha.info` passa a vir também nas decisões com risco (a tela já mostra chance e efeitos).
  Opção com chance ≤ 25% aparece marcada como **arriscada**.
- `Temporada.marcas: list[str]` (nomes ganhos naquela temporada, na linha do tempo) e
  `Final.marcas: list[str]` (no card e na tela final). `finais.toml` aceita `requer` de marcas.
- Perguntas por carreira: `MAX_ESCOLHAS` vira por modo — Rápida 5, Completa 8 (hoje 4 e 4). O
  teto conta só decisões (não as propostas de mercado nem o dia a dia, que seguem como hoje).
- Só uma resposta que **muda de clube** (ou aposenta) segura o mercado daquele inverno; decisão com
  `destino = "ficar"` deixa o mercado rodar depois (na Completa, pode vir decisão + proposta).
- Depois de "virou meia", tudo usa a posição final: card, `Resumo` do link, comparação com
  jogador real e Fábrica de craques. `Final.posicao` (nova) guarda a posição final; a linha do
  tempo mostra a mudança.
- Manchetes: o motor não repete na mesma carreira um texto de manchete já usado enquanto houver
  outro do mesmo evento.
- Carga dos dados falha se um `requer`/`exclui`/`marca` aponta para id que não existe.
- Link: `Entrada.escolhas` continua lista de índices; nada muda no formato do código.

### Conteúdo mínimo

- ≥ 25 decisões novas em 6 temas: contrato, técnico, vestiário, Seleção, imprensa, vida pessoal.
- ≥ 15 marcas (ex.: capitão, polêmico, ídolo de um clube só, andarilho, virou meia, rato de
  academia, xodó da torcida, brigou com o técnico, baladeiro, recusou a Seleção).
- ≥ 4 arcos curtos de 2–3 passos feitos com `requer` (briga com o técnico → reserva → sair ou
  pedir desculpas; braçadeira → crise → liderar ou se omitir).

### Arcos garantidos (decisão do dev)

- `Decisao.continua: bool = False`: um passo de arco. Quando uma marca é gravada e existe decisão
  `continua` cuja condição exige essa marca, ela é a pergunta **obrigatória da temporada
  seguinte**: pula o sorteio de `CHANCE_ESCOLHA` e os pesos. Se a condição de idade/nota não casar,
  tenta na temporada seguinte, até 2 vezes; depois o arco morre.
- O passo de arco **não conta** no teto de perguntas e sempre cabe: o teto barra só perguntas
  sorteadas. Um arco tem no máximo 3 passos, então a Rápida fica em até ~7 perguntas no pior caso.
- Os passos do meio são perguntas (o torcedor decide em cada passo); um evento de arco, se houver,
  só conta a consequência na linha do tempo.
- ≥ 8 opções arriscadas (chance base 15–25%) com prêmio ou tombo grande (teto ±, marca rara).
- ≥ 20 eventos novos ligados a marcas; todo evento com peso ≥ 1 tem ≥ 4 manchetes.

## Critérios de aceite (como testes)

- [ ] `test_marca_gravada_conforme_o_resultado`: dada uma opção com marca e chance, quando dá certo
  grava `marca`, quando dá errado grava `marca_fracasso`.
- [ ] `test_marca_libera_evento_e_decisao`: dado o histórico com uma marca, eventos e decisões que
  a exigem passam a caber; os que a excluem, não.
- [ ] `test_arco_segue_a_ordem`: o 2º passo de um arco só aparece depois do 1º.
- [ ] `test_arco_continua_na_temporada_seguinte`: dada uma resposta que grava marca de arco, a
  próxima pergunta da carreira é o passo `continua` (Rápida e Completa), mesmo com o teto cheio.
- [ ] `test_virou_meia_muda_posicao_e_nota`: efeito com `posicao` muda a posição e a nota geral.
- [ ] `test_dados_rejeitam_marca_inexistente`: `requer` com id desconhecido falha na carga.
- [ ] `test_manchete_nao_repete_na_carreira`: em 200 carreiras, nenhuma repete texto de manchete
  quando o evento tinha outro disponível.
- [ ] `test_mesmo_draft_caminhos_diferentes`: mesmo draft e semente, respostas diferentes dão
  conjuntos de marcas e linhas do tempo diferentes.
- [ ] `test_variedade_de_decisoes`: em 500 carreiras Completa, ≥ 60% das decisões (de
  `escolhas.toml`, sem contar propostas e dia a dia) não mudam de clube.
- [ ] `test_decisao_sem_clube_nao_segura_o_mercado`: depois de uma decisão "ficar", o mercado do
  inverno ainda pode trazer proposta.
- [ ] `test_arriscar_tudo_nao_quebra_o_realismo`: respondendo sempre a opção mais arriscada, lendas
  ≤ 5% e não decolam ≥ 15%; a distribuição de `test_carreira_realismo` continua valendo.
- [ ] `test_replay_estavel`: a mesma `Entrada` dá a mesma carreira (respostas antigas não mudam o passado).

## Verificação ponta a ponta

```bash
uv run pytest tests/test_carreira_*.py
uv run python scripts/carreira_amostra.py 20 --modo completa   # ler marcas e manchetes a olho
```

Jogar uma carreira Rápida e uma Completa em `/jogos/carreira`: ver opção arriscada, marca na
linha do tempo e marcas no card final; abrir o link compartilhado.

## Riscos e dúvidas abertas

- Mais perguntas alongam a Rápida (meta de 3–5 min): 5 perguntas é o teto; medir jogando.
- Volume de texto em pt-BR: escrito por Claude, o dev revisa no PR.
