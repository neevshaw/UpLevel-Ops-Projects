from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field, validator

class Criterion(BaseModel):
    id: str
    label: str
    levels: Dict[int, str]  # keys 1..4
    keywords: List[str] = Field(default_factory=list)

    @validator("levels")
    @classmethod
    def _check_levels(cls, v: Dict[int, str]):
        missing = {1,2,3,4} - set(v.keys())
        if missing:
            raise ValueError(f"levels must include 1..4, missing: {missing}")
        return v

class Category(BaseModel):
    id: str
    name: str
    criteria: List[Criterion]
    rollup: Literal["median","mean"] = "median"

class MaturityModel(BaseModel):
    categories: List[Category]

    def index(self) -> Dict[str, Category]:
        return {c.id: c for c in self.categories}
