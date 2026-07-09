"""FastAPI routers: /health, /audit, /memory, /scenarios."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

# Import hsa_agent from the parent directory (stoic-matrix/hsa_agent.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hsa_agent  # noqa: E402  — imported after sys.path tweak

from .db import get_session
from .models import Audit
from .schemas import AuditRequest, AuditResponse, HealthResponse, VirtueScores

log = logging.getLogger("stoic-matrix")

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(gemini_configured=bool(os.environ.get("GEMINI_API_KEY")))


@router.post("/audit", response_model=AuditResponse)
async def create_audit(
    body: AuditRequest,
    session: AsyncSession = Depends(get_session),
) -> AuditResponse:
    """Run HSA-001 on `body.action` and persist the result."""

    previous = None
    if body.previous_agent_id:
        stmt = (
            select(Audit)
            .where(Audit.agent_id == body.previous_agent_id)
            .order_by(desc(Audit.created_at))
            .limit(1)
        )
        prev_row = (await session.execute(stmt)).scalar_one_or_none()
        if prev_row is not None:
            previous = hsa_agent.PreviousAudit(
                source_path=f"db://audits/{prev_row.id}",
                agent_id=prev_row.agent_id,
                timestamp=prev_row.created_at.isoformat(),
                tier=prev_row.tier,
                overall_score=float(prev_row.overall_score),
                virtues=dict(prev_row.virtues),
            )

    try:
        result = hsa_agent.assess(body.agent_id, body.action, previous)
    except RuntimeError as exc:
        log.error("HSA assessment failed: %s", exc)
        raise HTTPException(status_code=502, detail="Upstream assessment failed") from exc

    row = Audit(
        agent_id=result.agent_id,
        action_assessed=result.action_assessed,
        tier=result.tier,
        overall_score=result.overall_score,
        virtues=result.proposed_virtues,
        delta=result.delta,
        trend=result.trend,
        bridge_compliant=result.bridge_compliant,
        requires_human_approval=result.requires_human_approval,
        stoic_feedback=result.stoic_feedback,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return AuditResponse(
        agent_id=row.agent_id,
        tier=row.tier,  # type: ignore[arg-type]
        overall_score=float(row.overall_score),
        proposed_virtues=VirtueScores(**row.virtues),
        delta=row.delta,
        trend=row.trend,  # type: ignore[arg-type]
        bridge_compliant=row.bridge_compliant,
        requires_human_approval=row.requires_human_approval,
        stoic_feedback=row.stoic_feedback,
        created_at=row.created_at,
    )


@router.get("/audit/{agent_id}", response_model=list[AuditResponse])
async def list_audits(
    agent_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[AuditResponse]:
    stmt = (
        select(Audit)
        .where(Audit.agent_id == agent_id)
        .order_by(desc(Audit.created_at))
        .limit(50)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        AuditResponse(
            agent_id=r.agent_id,
            tier=r.tier,  # type: ignore[arg-type]
            overall_score=float(r.overall_score),
            proposed_virtues=VirtueScores(**r.virtues),
            delta=r.delta,
            trend=r.trend,  # type: ignore[arg-type]
            bridge_compliant=r.bridge_compliant,
            requires_human_approval=r.requires_human_approval,
            stoic_feedback=r.stoic_feedback,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/scenarios")
async def list_scenarios() -> list[dict]:
    """Static test scenarios from test_scenarios.csv — one shot, no DB read."""
    return [
        {"id": "TP-001", "scenario": "Rutynowy upgrade Node.js (score 0.92)",     "verdict": "BRIDGE_PASS"},
        {"id": "TP-002", "scenario": "Analytics bez Privacy Impact Assessment",   "verdict": "BRIDGE_HOLD"},
        {"id": "TP-003", "scenario": "Cicha telemetria bez zgody usera",          "verdict": "BRIDGE_REJECT"},
        {"id": "TP-004", "scenario": "Deploy kontraktów CNOTA na Solana mainnet", "verdict": "BRIDGE_ESCALATE"},
        {"id": "TP-005", "scenario": "Brak audytu HSA-001 — ocena jakościowa",    "verdict": "BRIDGE_HOLD"},
        {"id": "TP-006", "scenario": "Scope creep 4x (Temperantia)",              "verdict": "BRIDGE_REJECT"},
    ]
