"""Read the shipped demo without a database session or simulation execution."""

import gzip
from functools import lru_cache
from pathlib import Path

from app.core.errors import ApiProblem
from app.database.hashing import canonical_json_hash
from app.schemas.demo import DemoPlaybackResponse

DEMO_PATH = Path(__file__).resolve().parents[1] / "demo" / "baja-launch.json.gz"


@lru_cache(maxsize=1)
def playback():
    try:
        with gzip.open(DEMO_PATH, "rt", encoding="utf-8") as stream:
            demo = DemoPlaybackResponse.model_validate_json(stream.read())
        if (
            canonical_json_hash(demo.input_document_snapshot) != demo.input_hash
            or canonical_json_hash(demo.result) != demo.result_hash
            or demo.result.get("metrics", {}).get("completed") is not True
        ):
            raise ValueError("Invalid retained demo evidence")
        return demo
    except (OSError, ValueError, EOFError) as exc:
        raise ApiProblem(
            503,
            "demo_unavailable",
            "The recorded demo is unavailable on this installation. Restore the bundled demo artifact and restart the API.",
        ) from exc
