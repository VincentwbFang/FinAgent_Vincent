from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)
    horizon_days: int = Field(default=365, ge=30, le=1825)
    depth: str = Field(default="standard", pattern="^(quick|standard|deep)$")
    include_macro: bool = True
    valuation_modes: list[str] = Field(default_factory=lambda: ["dcf", "multiples", "scenarios"])


class JobCreated(BaseModel):
    job_id: str
    status: str


class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int = Field(ge=0, le=100)
    error: str | None = None
    updated_at: datetime


class Citation(BaseModel):
    source: str
    url: str
    retrieved_at: datetime


class ScenarioSet(BaseModel):
    bull: float
    base: float
    bear: float


class TargetRange(BaseModel):
    low: float
    high: float


class AnalysisReport(BaseModel):
    symbol: str
    timestamp_utc: datetime
    thesis: str
    key_points: list[str] = Field(default_factory=list)
    scenarios: ScenarioSet
    target_range: TargetRange
    risk_flags: list[str]
    confidence: float
    reliability: dict[str, Any] = Field(default_factory=dict)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    deep_dive: dict[str, Any] = Field(default_factory=dict)
    narrative: str = ""
    narrative_en: str = ""
    narrative_zh: str = ""
    citations: list[Citation] = Field(default_factory=list)


class PriceBar(BaseModel):
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class LLMMessage(BaseModel):
    role: str
    content: str
