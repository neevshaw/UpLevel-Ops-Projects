from pathlib import Path
import yaml as yaml
from typing import Tuple
from ..schemas.maturity import MaturityModel

BASE_DIR = Path(__file__).parent.parent.parent  # services -> app -> src
DEFAULT_YAML = BASE_DIR / "assets" / "maturity_model.yaml"

def load_maturity_model(path: str | None = None) -> Tuple[MaturityModel, dict]:
    p = Path(path) if path else DEFAULT_YAML
    if not p.exists():
        raise FileNotFoundError(f"Maturity model not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    model = MaturityModel(**data)
    return model, data  # return raw too, if you want to inspect
