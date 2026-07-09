"""Pydantic schemas — request/response shapes for the FastAPI routes."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Tier = Literal["PLATINUM", "GOLD", "SILVER", "BRONZE", "FAILED"]
Trend = Literal["IMPROVED", "STABLE", "REGRESSED", "UNKNOWN"]


class VirtueScores(BaseModel):
    courage: float = Field(ge=0, le=10)
    wisdom: float = Field(ge=0, le=10)
    justice: float = Field(ge=0, le=10)
    temperance: float = Field(ge=0, le=10)


class AuditRequest(BaseModel):
    agent_id: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=8000)
    previous_agent_id: Optional[str] = Field(
        default=None,
        description="If set, delta is computed against this agent's most recent audit.",
    )


class AuditResponse(BaseModel):
    agent_id: str
    tier: Tier
    overall_score: float
    proposed_virtues: VirtueScores
    delta: dict
    trend: Trend
    bridge_compliant: bool
    requires_human_approval: bool
    stoic_feedback: str
    created_at: datetime


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "stoic-matrix"
    version: str = "2.0.0"
    gemini_configured: bool
