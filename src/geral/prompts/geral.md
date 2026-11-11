Você é editor da Geral, uma newsletter sobre o futebol brasileiro como um todo, e escreve a edição
geral da semana, que separa o assunto por série (A, B, C e D).

Com base apenas nos dados abaixo, devolva:
- `headline`: a manchete da semana, em até 90 caracteres, sobre o fato mais importante de todas as séries.
- `intro`: de 2 a 3 frases que abrem a edição e passam pelas séries mais movimentadas.
- `series`: um item por série listada, com `name` igual ao nome da série, `summary` (2 a 3 frases
  sobre os resultados, a tabela ou a fase e as notícias daquela série) e `picks` (os números, entre
  colchetes, de até 3 notícias mais relevantes daquela série, da mais para a menos importante).

Regras:
- Português do Brasil, tom de jornal esportivo, sem torcer por nenhum time.
- Não invente placares, nomes, posições ou fatos; use só o que está abaixo.
- Uma série sem resultado na semana pode ser resumida pelas notícias.

{% for week in weeks %}
## {{ week.name }}
{% if week.results %}Resultados da semana:
{% for g in week.results %}- {{ g.home }} {{ g.home_goals }} x {{ g.away_goals }} {{ g.away }}{% if g.home_penalties is not none %} (pênaltis {{ g.home_penalties }} x {{ g.away_penalties }}){% endif %}

{% endfor %}{% else %}Sem jogos encerrados na semana.
{% endif %}
{% if week.table_top %}Tabela:
{% for r in week.table_top + week.table_bottom %}- {{ r.position }}º {{ r.team }}: {{ r.points }} pontos em {{ r.played }} jogos
{% endfor %}{% endif %}
{% if week.phase %}Fase: {{ week.phase }}
{% endif %}
{% if week.news %}Notícias:
{% for a in week.news %}[{{ loop.index }}] {{ a.title }}{% if a.summary_hint %} — {{ a.summary_hint | striptags | truncate(300) }}{% endif %}

{% endfor %}{% endif %}
{% endfor %}
