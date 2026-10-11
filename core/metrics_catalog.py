"""Loader for metrics/metrics.yml, the single source of metric definitions."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

METRICS_PATH = Path(__file__).resolve().parent.parent / "metrics" / "metrics.yml"


class Metric(BaseModel):
    id: str
    label: str
    short: str | None = None
    definition: str
    formula: str
    model: str
    unit: str
    caveats: list[str] = []


class Catalog(BaseModel):
    metrics: list[Metric]
    rules: dict[str, str] = {}

    def ids(self) -> set[str]:
        return {m.id for m in self.metrics}


@lru_cache
def load_catalog(path: Path = METRICS_PATH) -> Catalog:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Catalog.model_validate(raw)
