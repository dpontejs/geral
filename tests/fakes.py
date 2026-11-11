from collections.abc import Callable

from pydantic import BaseModel

from geral.summarizer.client import LLMClient
from geral.teams import Team

# The tests (and their saved pages) come from the Urubu News, so they run as Flamengo.
FLAMENGO = Team(
    slug="flamengo",
    name="Flamengo",
    newsletter="Urubu News",
    fans="rubro-negros",
    espn_id=819,
    ge_url="https://ge.globo.com/futebol/times/flamengo/",
    news_query="Flamengo futebol",
    keywords=("flamengo", "fla", "mengão", "rubro-negro", "rubro-negra", "rubro-negros"),
    accent="#A51C24",
    leagues=(
        "bra.1",
        "conmebol.libertadores",
        "bra.copa_do_brazil",
        "bra.camp.carioca",
        "bra.supercopa_do_brazil",
        "fifa.cwc",
    ),
    league="bra.1",
    other_sports={
        "Basquete": '"Flamengo" basquete OR NBB',
        "Vôlei": '"Sesc-Flamengo" OR "Flamengo" vôlei',
        "Futebol feminino": '"Flamengo" futebol feminino',
    },
)


class FakeLLMClient(LLMClient):
    """LLM client returning canned responses; records every prompt it receives."""

    def __init__(self, responder: Callable[[str, type[BaseModel]], BaseModel | dict]) -> None:
        self.responder = responder
        self.prompts: list[str] = []

    def generate_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        self.prompts.append(prompt)
        result = self.responder(prompt, schema)
        return schema.model_validate(result if isinstance(result, dict) else result.model_dump())
