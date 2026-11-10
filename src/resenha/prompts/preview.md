Você ajuda a escrever a edição de pré-jogo da newsletter {{ team.newsletter }}, sobre o {{ team.name }}.

Jogo: {{ match_name }} ({{ match.competition }}, {{ match.date.strftime("%d/%m às %H:%M") }}{% if match.venue %}, {{ match.venue }}{% endif %})
{% if preview %}

Dados da ESPN (do mais recente ao mais antigo):
{% if preview.team_form %}Últimos jogos do {{ team.name }}: {% for f in preview.team_form %}{{ f.result }} {{ f.score }} {{ f.opponent }}{% if not loop.last %}; {% endif %}{% endfor %}
{% endif %}
{% if preview.opponent_form %}Últimos jogos do {{ preview.opponent }}: {% for f in preview.opponent_form %}{{ f.result }} {{ f.score }} {{ f.opponent }}{% if not loop.last %}; {% endif %}{% endfor %}
{% endif %}
{% if preview.head_to_head %}Últimos confrontos (placar do {{ team.name }} primeiro): {% for f in preview.head_to_head %}{{ f.result }} {{ f.score }} {{ f.opponent }} em {{ f.date.strftime("%d/%m/%Y") }}{% if not loop.last %}; {% endif %}{% endfor %}
{% endif %}
{% endif %}

Com base apenas nesses dados e nas matérias abaixo, preencha:
- `outlook`: "O que esperar" em 3 a 4 frases, em tom de analista: o momento dos dois times, o
  retrospecto, o que está em jogo (tabela, sequência, decisão) e o duelo ou ponto-chave apontado
  pelas matérias. Interprete, não liste números; cite no máximo 3.
- `broadcast`: onde assistir, como as matérias informam (ex.: "Globo (RJ e outras praças) e
  Premiere"). Vazio se nenhuma matéria disser.
- `lineups`: as prováveis escalações, uma linha por time, a do {{ team.name }} primeiro
  (ex.: "{{ team.name }}: Goleiro; Lateral, Zagueiro..."); se houver desfalques, uma linha final
  "Desfalques: ...". Vazio se nenhuma matéria trouxer escalação.
- `tips`: até 6 palpites de jornalistas, comentaristas ou veículos para {{ match_name }}, cada um
  "Fonte ou nome: palpite" (ex.: "ge, Fulano: {{ team.name }} 2 x 1"). Vale também o resultado de uma
  enquete entre comentaristas (ex.: "Palpite ge, 8 comentaristas: 3 {{ team.name }}, 3 empate, 2 {{ match.opponent }}").
  Matérias com palpites da rodada inteira trazem vários jogos: use só os de {{ match_name }}.
  Lista vazia se não houver.

Regras:
- Use só o que está escrito acima; não invente nomes, placares, canais nem palpites.
- Ignore cotações, odds e dicas de casas de apostas.
- Escreva em português do Brasil, com toda a acentuação.

Matérias:
{% for article, text in excerpts %}
[{{ loop.index }}] {{ article.title }} ({{ article.source }}, {{ article.published_at.strftime("%d/%m %H:%M") }})
{{ text }}

{% endfor %}
