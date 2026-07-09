#!/usr/bin/env python3
"""
L7 Memory Exporter v2.0 — Angel Guardian Technologies
======================================================
Converts Perplexity / any conversation text to structured L7 Memory JSON
and optionally syncs to Git repository.

ZMIANY vs v1.0:
  - Usunięto pyperclip (brak obsługi headless CI)
  - Dodano @dataclass + Config centralny
  - Naprawiono datetime.utcnow() → datetime.now(UTC)
  - Poprawiona obsługa błędów git
  - Dodano TAG_RULES oparte na regułach
  - Input: stdin | --file | --text

Usage:
  # Ze stdin (pipe)
  cat conversation.txt | python l7_memory_exporter.py

  # Z pliku
  python l7_memory_exporter.py --file conversation.txt

  # Z tekstu inline
  python l7_memory_exporter.py --text "User: ...\nAssistant: ..."

  # Bez auto-push do git
  python l7_memory_exporter.py --file conv.txt --no-git-push
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("L7-Memory")


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG (centralny — brak rozproszonych stałych)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Config:
    repo_memory_path: str = ".github/memory"
    export_local_path: str = "./exports"
    auto_git_push: bool = True
    git_remote: str = "origin"
    git_branch: str = "main"
    max_block_length_for_user: int = 400  # > N chars → likely assistant
    max_content_chars: int = 50_000       # truncate huge inputs


# ═══════════════════════════════════════════════════════════════════════════════
# TAG RULES (rule-based, nie heurystyczne słowa kluczowe w kodzie)
# ═══════════════════════════════════════════════════════════════════════════════

TAG_RULES: list[tuple[str, re.Pattern]] = [
    ("L7_Bridge",        re.compile(r"\bL7\b|\bBridge\b|\bL7Bridge\b")),
    ("Memory5",          re.compile(r"\bMemory5\b|\bperplexity memory\b", re.I)),
    ("PRAWO_ZERO",       re.compile(r"\bPRAWO\b|\bPRAWO.ZERO\b|\bPrawoZero\b")),
    ("philosophy",       re.compile(r"\bSeneca\b|\bStoic\b|\bAurelius\b|\bEpiktet\b|\bstoicyz\b", re.I)),
    ("deployment",       re.compile(r"\bdeploy(ment)?\b|\bdeploy\b|\bHugging.Face\b", re.I)),
    ("virtue_protocol",  re.compile(r"\bPhantom\b|\bSolana\b|\bNFT\b|\bCnota\b|\bvirtue\b", re.I)),
    ("blockchain",       re.compile(r"\bblockchain\b|\bweb3\b|\bSepolia\b|\bcontract\b", re.I)),
    ("governance",       re.compile(r"\bgovernan\b|\bAssembly\b|\bMetaJury\b|\bDAO\b", re.I)),
    ("AI",               re.compile(r"\bGemini\b|\bOpenAI\b|\bLLM\b|\bAgent\b|\bHSA\b")),
    ("ciobchodzitm_lab", re.compile(r"\bcieobchodzitm\b|\bAngel.Guardian\b|\bL7.CNOTA\b", re.I)),
]


def extract_tags(text: str) -> list[str]:
    """Apply TAG_RULES and return matched tags (deduplicated, sorted)."""
    return sorted({tag for tag, pattern in TAG_RULES if pattern.search(text)})


# ═══════════════════════════════════════════════════════════════════════════════
# PARSER
# ═══════════════════════════════════════════════════════════════════════════════

def parse_conversation(raw_text: str, cfg: Config) -> list[dict]:
    """
    Heuristic parser — splits on double newlines, assigns roles.
    Longer/code blocks → assistant; shorter queries → user.
    """
    raw_text = raw_text[:cfg.max_content_chars]
    blocks = re.split(r"\n{2,}", raw_text.strip())
    messages = []

    for i, block in enumerate(blocks):
        block = block.strip()
        if not block:
            continue

        # Role heuristics
        is_long = len(block) > cfg.max_block_length_for_user
        has_code = "```" in block or block.startswith("    ")
        is_url = block.startswith(("http://", "https://", "curl"))

        if is_url:
            role = "user"
        elif is_long or has_code:
            role = "assistant"
        else:
            # Alternating fallback
            role = "user" if i % 2 == 0 else "assistant"

        messages.append({
            "index": len(messages),
            "role": role,
            "content": block,
        })

    return messages


# ═══════════════════════════════════════════════════════════════════════════════
# MEMORY JSON BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def build_l7_memory(
    messages: list[dict],
    source_url: Optional[str] = None,
    source_file: Optional[str] = None,
) -> dict:
    """Builds L7 Memory JSON structure."""
    now = datetime.now(timezone.utc)
    all_text = " ".join(m["content"] for m in messages)
    tags = extract_tags(all_text)

    return {
        "meta": {
            "id": f"mem-{int(now.timestamp())}",
            "source": source_file or "stdin",
            "url": source_url or "unknown",
            "exported_at": now.isoformat(),
            "version": "2.0",
            "status": "RAW_EXPORT",
            "tags": tags,
        },
        "conversation": messages,
        "summary": {
            "total_messages": len(messages),
            "user_messages": sum(1 for m in messages if m["role"] == "user"),
            "assistant_messages": sum(1 for m in messages if m["role"] == "assistant"),
            "export_method": "l7_memory_exporter.py v2.0",
            "timestamp": now.isoformat(),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# FILE I/O
# ═══════════════════════════════════════════════════════════════════════════════

def save_json(data: dict, filename: str, directory: str) -> Path:
    """Save JSON to file, creating directories as needed."""
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    filepath = out_dir / filename
    filepath.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return filepath


# ═══════════════════════════════════════════════════════════════════════════════
# GIT SYNC
# ═══════════════════════════════════════════════════════════════════════════════

def git_sync(filepath: Path, cfg: Config) -> bool:
    """
    Copies file to repo memory path, commits and pushes.
    Returns True on success, False on failure (non-fatal).
    """
    repo_file = Path(cfg.repo_memory_path) / filepath.name
    try:
        repo_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(filepath, repo_file)

        def run(cmd: list[str]) -> subprocess.CompletedProcess:
            return subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )

        run(["git", "add", str(repo_file)])
        run(["git", "commit", "-m", f"[MEMORY] L7 Export: {filepath.name}"])
        run(["git", "push", cfg.git_remote, cfg.git_branch])

        log.info(
            "Git push OK → %s/%s: %s",
            cfg.git_remote, cfg.git_branch, repo_file,
        )
        return True

    except FileNotFoundError:
        log.error("git nie jest dostępny w PATH.")
        return False
    except subprocess.CalledProcessError as exc:
        log.error(
            "Błąd git (kod %d):\n  stdout: %s\n  stderr: %s",
            exc.returncode,
            exc.stdout.strip() if exc.stdout else "",
            exc.stderr.strip() if exc.stderr else "",
        )
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="l7_memory_exporter.py",
        description="L7 Memory Exporter v2.0 — Angel Guardian Technologies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Przykłady:
  # Ze stdin
  cat conversation.txt | python l7_memory_exporter.py

  # Z pliku
  python l7_memory_exporter.py --file conversation.txt

  # Bez git push
  python l7_memory_exporter.py --file conv.txt --no-git-push

  # Z podaniem URL źródłowego
  python l7_memory_exporter.py --file conv.txt --source-url "https://perplexity.ai/..."
        """,
    )

    source = p.add_mutually_exclusive_group()
    source.add_argument("--file", metavar="PATH", help="Plik z rozmową (txt, md, json)")
    source.add_argument("--text", metavar="TEXT", help="Tekst rozmowy inline")

    p.add_argument("--source-url", metavar="URL", help="URL źródłowy (opcjonalny)")
    p.add_argument("--output-dir", default="./exports", help="Katalog wyjściowy (domyślnie: ./exports)")
    p.add_argument("--repo-memory-path", default=".github/memory", help="Ścieżka w repo")
    p.add_argument("--no-git-push", action="store_true", help="Wyłącz auto git push")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    return p


def read_input(args: argparse.Namespace) -> tuple[str, Optional[str]]:
    """Returns (raw_text, source_label)."""
    if args.text:
        return args.text, "cli --text"

    if args.file:
        fp = Path(args.file)
        if not fp.exists():
            log.error("Plik nie istnieje: %s", args.file)
            sys.exit(1)
        return fp.read_text(encoding="utf-8"), str(fp)

    # stdin fallback
    if not sys.stdin.isatty():
        log.info("Czytam ze stdin…")
        return sys.stdin.read(), "stdin"

    log.error(
        "Brak źródła danych. Podaj --file, --text, lub przekaż dane przez stdin.\n"
        "Użyj -h dla pomocy."
    )
    sys.exit(1)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    cfg = Config(
        export_local_path=args.output_dir,
        repo_memory_path=args.repo_memory_path,
        auto_git_push=not args.no_git_push,
    )

    log.info("L7 Memory Exporter v2.0 — start")

    # Read input
    raw_text, source_label = read_input(args)

    if not raw_text or len(raw_text) < 20:
        log.error("Tekst zbyt krótki lub pusty. Anulowano.")
        return 1

    log.info("Przetwarzam %d znaków z: %s", len(raw_text), source_label)

    # Parse & build
    messages = parse_conversation(raw_text, cfg)
    memory_data = build_l7_memory(
        messages,
        source_url=args.source_url,
        source_file=source_label,
    )

    filename = memory_data["meta"]["id"] + ".json"
    filepath = save_json(memory_data, filename, cfg.export_local_path)

    log.info("Zapisano: %s (%d wiadomości, tagi: %s)",
             filepath,
             len(messages),
             memory_data["meta"]["tags"])

    # Git sync
    if cfg.auto_git_push:
        success = git_sync(filepath, cfg)
        if not success:
            log.warning("Git sync nieudany — plik dostępny lokalnie: %s", filepath)

    # Output JSON path to stdout (CI-friendly)
    print(str(filepath))
    return 0


if __name__ == "__main__":
    sys.exit(main())
