"""The snapshot on disk: written whole (temp file + rename), read on every page view."""

import logging
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from geral.central.models import CentralSnapshot

logger = logging.getLogger(__name__)


def save_snapshot(path: Path | str, snapshot: CentralSnapshot) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # One temp file per writer (the thread and `geral central` may overlap), synced before the
    # rename: a reader never sees half a file.
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(snapshot.model_dump_json())
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def load_snapshot(path: Path | str) -> CentralSnapshot | None:
    try:
        return CentralSnapshot.model_validate_json(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, ValidationError) as e:  # ValueError: broken UTF-8
        logger.warning("Central snapshot unreadable at %s: %s", path, e)
        return None
