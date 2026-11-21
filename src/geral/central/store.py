"""The snapshot on disk: written whole (temp file + rename), read on every page view."""

import logging
from pathlib import Path

from pydantic import ValidationError

from geral.central.models import CentralSnapshot

logger = logging.getLogger(__name__)


def save_snapshot(path: Path | str, snapshot: CentralSnapshot) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(snapshot.model_dump_json(), encoding="utf-8")
    tmp.replace(path)  # a reader never sees half a file


def load_snapshot(path: Path | str) -> CentralSnapshot | None:
    try:
        return CentralSnapshot.model_validate_json(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValidationError) as e:
        logger.warning("Central snapshot unreadable at %s: %s", path, e)
        return None
