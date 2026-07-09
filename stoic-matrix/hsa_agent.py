#!/usr/bin/env python3
"""
HSA-001 Virtue Audit Agent — Angel Guardian Technologies
=========================================================
Stoic assessment engine for L7 / Rzeczpospolita governance system.

Tryby działania:
  --action "tekst"          → ocenia tekst akcji/commitu
  --file path.json          → wczytuje plik (event JSON, diff, dowolny tekst)
  --previous-json path.json → poprzedni result.json (prawdziwy delta diff)

Output JSON schema:
  tier, overall_score, proposed_virtues, delta, previous_audit,
  requires_human_approval, trend

Backendy:
  AI   → Gemini 2.0 Flash (google-genai)  ← UNIFIED
  Obs  → AgentOps (opcjonalny)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Gemini (unified backend) ─────────────────────────────────────────────────
try:
    from google import genai
    from google.genai import types as genai_types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# ── AgentOps (optional monitoring) ───────────────────────────────────────────
try:
    import agentops
    AGENTOPS_AVAILABLE = True
except ImportError:
    AGENTOPS_AVAILABLE = False

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("HSA-001")


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class HSAConfig:
    gemini_model: str = "gemini-2.0-flash-001"
    gemini_temperature: float = 0.3
    max_output_tokens: int = 1024

    # Virtue thresholds
    score_tier_platinum: float = 9.0
    score_tier_gold: float = 7.5
    score_tier_silver: float = 6.0
    score_tier_bronze: float = 4.5

    # Human approval triggers
    approval_threshold_score: float = 5.0     # below → requires approval
    approval_threshold_courage: float = 4.0   # courage too low → flag

    # L7 Bridge compliance thresholds (mirror L7BridgeGuard.sol)
    arete_min: float = 7.0      # ≥70%
    logos_min: float = 8.0      # ≥80%
    koinonia_min: float = 6.0   # ≥60%


CONFIG = HSAConfig()


# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class VirtueScores:
    courage: float    # Fortitudo / Arete   — odwaga działania
    wisdom: float     # Prudentia / Logos   — mądrość decyzji
    justice: float    # Iustitia / Koinonia — sprawiedliwość / dobro wspólne
    temperance: float # Temperantia         — umiar


@dataclass
class HSAResult:
    agent_id: str
    timestamp: str
    action_assessed: str
    tier: str                     # PLATINUM | GOLD | SILVER | BRONZE | FAILED
    overall_score: float          # 0.0 – 10.0
    proposed_virtues: dict        # {courage, wisdom, justice, temperance}
    delta: dict                   # prawdziwy diff vs poprzedni audit
    requires_human_approval: bool
    bridge_compliant: bool        # czy spełnia L7BridgeGuard.sol thresholds
    stoic_feedback: str           # komentarz Marcus (Gemini)
    trend: str = "UNKNOWN"        # IMPROVED | STABLE | REGRESSED | UNKNOWN
    previous_audit: Optional[dict] = None  # snapshot poprzedniego audytu
    raw_gemini_response: Optional[str] = None

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=indent)


@dataclass
class PreviousAudit:
    """Snapshot of a previous result.json — used for delta computation."""
    source_path: str
    agent_id: str
    timestamp: str
    tier: str
    overall_score: float
    virtues: dict   # {courage, wisdom, justice, temperance}

    @classmethod
    def load(cls, path: str) -> "PreviousAudit":
        """
        Load and validate a previous result.json.
        Raises FileNotFoundError or ValueError on bad data.
        """
        fp = Path(path)
        if not fp.exists():
            raise FileNotFoundError(f"Poprzedni wynik nie istnieje: {path}")

        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Niepoprawny JSON w {path}: {exc}") from exc

        required = {"agent_id", "timestamp", "tier", "overall_score", "proposed_virtues"}
        missing = required - data.keys()
        if missing:
            raise ValueError(
                f"Brak wymaganych pól w poprzednim wyniku: {missing}"
            )

        virtues = data["proposed_virtues"]
        for key in ("courage", "wisdom", "justice", "temperance"):
            if key not in virtues:
                raise ValueError(f"Brak cnoty '{key}' w proposed_virtues poprzedniego wyniku.")

        return cls(
            source_path=str(fp),
            agent_id=data["agent_id"],
            timestamp=data["timestamp"],
            tier=data["tier"],
            overall_score=float(data["overall_score"]),
            virtues={k: float(v) for k, v in virtues.items()},
        )


# Tier ordering for regression detection
_TIER_RANK: dict[str, int] = {
    "PLATINUM": 4,
    "GOLD": 3,
    "SILVER": 2,
    "BRONZE": 1,
    "FAILED": 0,
}


def _tier_trend(current: str, previous: str) -> str:
    """Returns IMPROVED | STABLE | REGRESSED based on tier ranks."""
    delta = _TIER_RANK.get(current, 0) - _TIER_RANK.get(previous, 0)
    if delta > 0:
        return "IMPROVED"
    if delta < 0:
        return "REGRESSED"
    return "STABLE"


# ═══════════════════════════════════════════════════════════════════════════════
# GEMINI ENGINE (replaces OpenAI evaluate_stoic_reflection)
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
Jesteś HSA-001 (Hierarchical Stoic Assessor), strażnikiem cnót w Rzeczypospolitej L7.
Oceniasz akcje/decyzje/commity według czterech Kardynalnych Cnót Stoickich.

SKALA: 1.0 – 10.0 (1=katastrofa, 5=neutralne, 10=doskonałość)

CNOTY:
- courage    (Fortitudo / Arete)   — odwaga działania, proaktywność, brak prokrastynacji
- wisdom     (Prudentia / Logos)   — trafność decyzji, zgodność z kontrolowanym
- justice    (Iustitia / Koinonia) — dobro wspólne, transparentność, uczciwość  
- temperance (Temperantia)         — umiar, brak nadmiernej złożoności, ekonomia

ZWRÓĆ WYŁĄCZNIE POPRAWNY JSON (bez markdown, bez backticks):
{
  "courage": <float>,
  "wisdom": <float>,
  "justice": <float>,
  "temperance": <float>,
  "feedback": "<stoicka rada, max 3 zdania, po polsku>"
}

WAŻNE: feedback musi być konstruktywny i filozoficznie zakorzeniony w Stoicyzmie.
Marcus Aurelius, Seneca, Epiktet — cytuj koncepcje, nie osoby wprost.
"""


def _build_user_prompt(action_text: str, agent_id: str) -> str:
    return (
        f"Agent-ID: {agent_id}\n"
        f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n"
        f"Akcja do oceny:\n\n{action_text}\n\n"
        f"Oceń powyższą akcję zgodnie z systemem."
    )


def call_gemini(action_text: str, agent_id: str) -> tuple[VirtueScores, str]:
    """
    Calls Gemini 2.0 Flash and returns parsed VirtueScores + raw feedback.
    Raises RuntimeError on failure.
    """
    if not GEMINI_AVAILABLE:
        raise RuntimeError(
            "google-genai nie jest zainstalowany. "
            "Uruchom: pip install google-genai"
        )

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Brak GEMINI_API_KEY w zmiennych środowiskowych.")

    client = genai.Client(api_key=api_key)

    log.info("Wysyłam zapytanie do Gemini (%s)…", CONFIG.gemini_model)
    start = time.monotonic()

    response = client.models.generate_content(
        model=CONFIG.gemini_model,
        contents=_build_user_prompt(action_text, agent_id),
        config=genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=CONFIG.gemini_temperature,
            max_output_tokens=CONFIG.max_output_tokens,
        ),
    )

    elapsed = time.monotonic() - start
    log.info("Gemini odpowiedział w %.2fs", elapsed)

    raw_text = response.text.strip()

    # Strip accidental markdown fences
    if raw_text.startswith("```"):
        raw_text = "\n".join(
            line for line in raw_text.splitlines()
            if not line.strip().startswith("```")
        ).strip()

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Gemini zwrócił niepoprawny JSON: {exc}\n---\n{raw_text}"
        ) from exc

    scores = VirtueScores(
        courage=float(parsed["courage"]),
        wisdom=float(parsed["wisdom"]),
        justice=float(parsed["justice"]),
        temperance=float(parsed["temperance"]),
    )
    feedback = parsed.get("feedback", "Brak feedbacku.")

    return scores, feedback


# ═══════════════════════════════════════════════════════════════════════════════
# SCORING & TIER LOGIC
# ═══════════════════════════════════════════════════════════════════════════════

def compute_overall_score(v: VirtueScores) -> float:
    """
    Weighted composite score — mirrors cnota_engine.py CNOTA weights:
      Prudentia 35%, Iustitia 25%, Fortitudo 20%, Temperantia 20%
    Mapped to our fields:
      wisdom=35%, justice=25%, courage=20%, temperance=20%
    """
    return round(
        v.wisdom * 0.35
        + v.justice * 0.25
        + v.courage * 0.20
        + v.temperance * 0.20,
        2,
    )


def score_to_tier(score: float) -> str:
    if score >= CONFIG.score_tier_platinum:
        return "PLATINUM"
    if score >= CONFIG.score_tier_gold:
        return "GOLD"
    if score >= CONFIG.score_tier_silver:
        return "SILVER"
    if score >= CONFIG.score_tier_bronze:
        return "BRONZE"
    return "FAILED"


def check_requires_approval(score: float, v: VirtueScores) -> bool:
    """Human approval required if overall score low OR courage critically low."""
    return (
        score < CONFIG.approval_threshold_score
        or v.courage < CONFIG.approval_threshold_courage
    )


def check_bridge_compliance(v: VirtueScores) -> bool:
    """
    Mirror of L7BridgeGuard.sol thresholds:
      Arete ≥70% (courage ≥7.0)
      Logos ≥80% (wisdom ≥8.0)
      Koinonia ≥60% (justice ≥6.0)
    """
    return (
        v.courage >= CONFIG.arete_min
        and v.wisdom >= CONFIG.logos_min
        and v.justice >= CONFIG.koinonia_min
    )


def compute_delta(
    current: VirtueScores,
    current_overall: float,
    previous: Optional[PreviousAudit],
) -> dict:
    """
    Real delta: current − previous dla każdej cnoty i overall.
    Zwraca dict z kluczami: courage, wisdom, justice, temperance, overall,
    has_baseline, previous_agent_id, previous_timestamp.

    Jeśli brak poprzedniego audytu → delta = 0.0 (brak baseline).
    """
    if previous is None:
        return {
            "has_baseline": False,
            "courage": 0.0,
            "wisdom": 0.0,
            "justice": 0.0,
            "temperance": 0.0,
            "overall": 0.0,
            "previous_agent_id": None,
            "previous_timestamp": None,
        }

    def diff(field: str) -> float:
        cur_val = getattr(current, field)
        prev_val = previous.virtues.get(field, 0.0)
        return round(cur_val - prev_val, 2)

    overall_delta = round(current_overall - previous.overall_score, 2)

    return {
        "has_baseline": True,
        "courage": diff("courage"),
        "wisdom": diff("wisdom"),
        "justice": diff("justice"),
        "temperance": diff("temperance"),
        "overall": overall_delta,
        "previous_agent_id": previous.agent_id,
        "previous_timestamp": previous.timestamp,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# AGENTOPS INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════

def init_agentops() -> bool:
    """Initialize AgentOps monitoring if API key present."""
    if not AGENTOPS_AVAILABLE:
        log.debug("agentops nie zainstalowany — pomijam monitoring.")
        return False

    api_key = os.environ.get("AGENTOPS_API_KEY")
    if not api_key:
        log.debug("Brak AGENTOPS_API_KEY — pomijam monitoring.")
        return False

    try:
        agentops.init(api_key=api_key, tags=["HSA-001", "L7", "stoic-audit"])
        log.info("AgentOps monitoring aktywny.")
        return True
    except Exception as exc:
        log.warning("AgentOps init failed (non-fatal): %s", exc)
        return False


def record_agentops_event(result: HSAResult, agentops_active: bool) -> None:
    """Record assessment result to AgentOps."""
    if not agentops_active or not AGENTOPS_AVAILABLE:
        return
    try:
        agentops.record(agentops.ActionEvent(
            action_type="HSA-001-ASSESSMENT",
            params={
                "agent_id": result.agent_id,
                "action": result.action_assessed[:200],
            },
            returns={
                "tier": result.tier,
                "overall_score": result.overall_score,
                "bridge_compliant": result.bridge_compliant,
                "requires_human_approval": result.requires_human_approval,
            },
        ))
    except Exception as exc:
        log.warning("AgentOps record failed (non-fatal): %s", exc)


# ═══════════════════════════════════════════════════════════════════════════════
# ACTION TEXT EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def load_action_from_file(path: str) -> str:
    """
    Load action text from file.
    Supports:
      - GitHub event JSON  → extract key fields
      - Plain text / diff  → use as-is
      - Any JSON           → serialize for assessment
    """
    fp = Path(path)
    if not fp.exists():
        raise FileNotFoundError(f"Plik nie istnieje: {path}")

    raw = fp.read_text(encoding="utf-8")

    # Try to parse as JSON (GitHub event format)
    try:
        data = json.loads(raw)
        # Extract meaningful fields from GitHub event
        parts = []
        if "commits" in data:
            for c in data["commits"][:5]:  # max 5 commits
                parts.append(f"Commit: {c.get('message', '')} by {c.get('author', {}).get('name', 'unknown')}")
        if "pull_request" in data:
            pr = data["pull_request"]
            parts.append(f"PR #{pr.get('number')}: {pr.get('title', '')} — {pr.get('body', '')[:500]}")
        if "head_commit" in data:
            hc = data["head_commit"]
            parts.append(f"Head commit: {hc.get('message', '')} by {hc.get('author', {}).get('name', 'unknown')}")
        if "ref" in data:
            parts.append(f"Branch: {data['ref']}")

        if parts:
            return "\n".join(parts)
        else:
            # Generic JSON — serialize with indent
            return json.dumps(data, ensure_ascii=False, indent=2)[:3000]

    except json.JSONDecodeError:
        # Plain text / diff
        return raw[:3000]


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ASSESS FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def assess(
    agent_id: str,
    action_text: str,
    previous: Optional[PreviousAudit] = None,
) -> HSAResult:
    """Core assessment pipeline."""

    # Call Gemini
    virtues, feedback = call_gemini(action_text, agent_id)

    # Compute metrics
    overall = compute_overall_score(virtues)
    tier = score_to_tier(overall)
    approval = check_requires_approval(overall, virtues)
    bridge_ok = check_bridge_compliance(virtues)
    delta = compute_delta(virtues, overall, previous)
    trend = _tier_trend(tier, previous.tier) if previous else "UNKNOWN"

    log.info(
        "Wynik: %s | %.2f/10 | Trend: %s | Bridge: %s | Approval: %s",
        tier, overall, trend, bridge_ok, approval,
    )

    # Previous audit snapshot (compact) for output JSON
    prev_snapshot: Optional[dict] = None
    if previous:
        prev_snapshot = {
            "agent_id": previous.agent_id,
            "timestamp": previous.timestamp,
            "tier": previous.tier,
            "overall_score": previous.overall_score,
            "virtues": previous.virtues,
        }

    return HSAResult(
        agent_id=agent_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        action_assessed=action_text[:500],
        tier=tier,
        overall_score=overall,
        proposed_virtues={
            "courage": virtues.courage,
            "wisdom": virtues.wisdom,
            "justice": virtues.justice,
            "temperance": virtues.temperance,
        },
        delta=delta,
        requires_human_approval=approval,
        bridge_compliant=bridge_ok,
        stoic_feedback=feedback,
        trend=trend,
        previous_audit=prev_snapshot,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hsa_agent.py",
        description="HSA-001 Virtue Audit Agent — Angel Guardian Technologies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Przykłady:
  # Lokalny test z tekstem akcji
  python hsa_agent.py --agent-id test-001 \\
    --action "Deployed L7 Bridge commit a1b2c3d to mainnet" \\
    --output-json ./hsa_assessments/result.json

  # Z prawdziwą deltą vs poprzedni audit
  python hsa_agent.py --agent-id test-002 \\
    --action "Merged PR #42: virtue scoring refactor" \\
    --previous-json ./hsa_assessments/result.json \\
    --output-json ./hsa_assessments/result.json

  # GitHub CI (event file + delta)
  python hsa_agent.py --agent-id "GitHub-${GITHUB_RUN_NUMBER}" \\
    --file "${GITHUB_EVENT_PATH}" \\
    --previous-json ./hsa_assessments/result.json \\
    --output-json ./hsa_assessments/result.json
        """,
    )
    p.add_argument("--agent-id", required=True, help="Identyfikator agenta (np. GitHub-42)")

    # Unified action source: either --action OR --file
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--action", metavar="TEXT", help="Tekst akcji do oceny (lokalny test)")
    source.add_argument("--file", metavar="PATH", help="Ścieżka do pliku (GitHub event JSON, diff, tekst)")

    p.add_argument(
        "--previous-json",
        metavar="PATH",
        default=None,
        help=(
            "Ścieżka do poprzedniego result.json. "
            "Jeśli pominięty — delta=0 (brak baseline). "
            "Może wskazywać ten sam plik co --output-json (odczyt przed nadpisaniem)."
        ),
    )

    p.add_argument(
        "--output-json",
        metavar="PATH",
        default="./hsa_assessments/result.json",
        help="Ścieżka do pliku wyjściowego JSON (domyślnie: ./hsa_assessments/result.json)",
    )
    p.add_argument("--no-agentops", action="store_true", help="Wyłącz AgentOps monitoring")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # AgentOps init
    agentops_active = False
    if not args.no_agentops:
        agentops_active = init_agentops()

    # Resolve action text
    if args.action:
        action_text = args.action
        log.info("Tryb: --action (tekst bezpośredni)")
    else:
        log.info("Tryb: --file (%s)", args.file)
        try:
            action_text = load_action_from_file(args.file)
        except FileNotFoundError as exc:
            log.error("%s", exc)
            return 1

    if not action_text.strip():
        log.error("Pusta treść akcji — brak danych do oceny.")
        return 1

    # Load previous audit for delta computation
    previous: Optional[PreviousAudit] = None
    if args.previous_json:
        try:
            previous = PreviousAudit.load(args.previous_json)
            log.info(
                "Poprzedni audit załadowany: %s | %s | %.2f/10",
                previous.agent_id,
                previous.tier,
                previous.overall_score,
            )
        except FileNotFoundError:
            log.info(
                "Brak poprzedniego wyniku (%s) — delta=0 (pierwszy audit).",
                args.previous_json,
            )
        except ValueError as exc:
            log.warning("Nieprawidłowy poprzedni wynik (delta=0): %s", exc)

    # Run assessment
    try:
        result = assess(args.agent_id, action_text, previous)
    except RuntimeError as exc:
        log.error("Błąd asesmentu: %s", exc)
        return 2

    # Save output
    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.to_json(), encoding="utf-8")
    log.info("Wynik zapisany: %s", output_path)

    # AgentOps event
    record_agentops_event(result, agentops_active)

    # Print summary to stdout
    print(result.to_json())

    # Exit code: 1 if human approval required (for CI gate)
    return 1 if result.requires_human_approval else 0


if __name__ == "__main__":
    sys.exit(main())
