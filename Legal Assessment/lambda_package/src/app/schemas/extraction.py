from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class SourceRef(BaseModel):
    file: str
    locator: str                  # e.g., "p12" or "s4"
    excerpt: Optional[str] = None

class PainPoint(BaseModel):
    text: str
    category: Optional[str] = None
    impact_hint: Literal["low","med","high"] = "med"
    effort_hint: Literal["low","med","high"] = "med"
    evidence: Optional[str] = None
    source_ref: SourceRef

class CurrentTool(BaseModel):
    name: str
    purpose: Optional[str] = None
    adoption_level: Optional[Literal["pilot","partial","full"]] = None
    issues: List[str] = Field(default_factory=list)
    source_ref: SourceRef

class ProcessStep(BaseModel):
    process_name: str
    step: str
    owners: List[str] = Field(default_factory=list)
    systems: List[str] = Field(default_factory=list)
    slas: Optional[str] = None
    risks: List[str] = Field(default_factory=list)
    source_ref: SourceRef

class Metric(BaseModel):
    name: str
    value: Optional[str] = None
    timeframe: Optional[str] = None
    owner: Optional[str] = None
    source_ref: SourceRef

class Opportunity(BaseModel):
    area: str
    description: str
    impact_hint: Literal["low","med","high"] = "med"
    effort_hint: Literal["low","med","high"] = "med"
    dependencies: List[str] = Field(default_factory=list)
    source_ref: SourceRef

class ExtractionResult(BaseModel):
    chunks_used: List[str] = Field(default_factory=list)
    pain_points: List[PainPoint] = Field(default_factory=list)
    current_tools: List[CurrentTool] = Field(default_factory=list)
    processes: List[ProcessStep] = Field(default_factory=list)
    metrics: List[Metric] = Field(default_factory=list)
    opportunities: List[Opportunity] = Field(default_factory=list)
