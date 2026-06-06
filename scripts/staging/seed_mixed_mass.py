#!/usr/bin/env python3
"""
Seed staging MySQL com massa mista: 1 row legacy (sem meta) + 1 row B2 (meta ISS).

Uso (após docker compose up):
  python scripts/staging/seed_mixed_mass.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from staging_env import ISS_ROOT, KERNELBOT_ROOT, UPSERT_SQL, apply_staging_env, db_connect

DISCIPLINE = "_staging"
SLUG_LEGACY = "legacy-modelagem"
SLUG_B2 = "fluencia-b2"

FRONTMATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n?", re.DOTALL)

LEGACY_MD = (
    ISS_ROOT
    / "content"
    / "sql-modelagem-relacional"
    / "aula-01-modelagem-dados-relacional-fundamentos.md"
)


def strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    stripped, count = FRONTMATTER_RE.subn("", text, count=1)
    return stripped if count else text


def load_legacy_body() -> str:
    if not LEGACY_MD.is_file():
        raise FileNotFoundError(f"Markdown legacy ausente: {LEGACY_MD}")
    raw = LEGACY_MD.read_text(encoding="utf-8")
    body = strip_frontmatter(raw).strip()
    words = len(body.split())
    if words < 1000:
        raise ValueError(f"legacy body tem só {words} palavras (mínimo 1000)")
    return body


def load_b2_content() -> str:
    import importlib.util

    ingest_path = ISS_ROOT / ".github" / "scripts" / "ingest-knowledge.py"
    if not ingest_path.is_file():
        raise FileNotFoundError(f"ISS ingest ausente: {ingest_path}")

    spec = importlib.util.spec_from_file_location("iss_ingest", ingest_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"nao foi possivel carregar modulo: {ingest_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.load_lesson_json("fluencia-ia", "introducao-fluencia-ia", 1)


def main() -> int:
    apply_staging_env()
    print(f"KernelBot: {KERNELBOT_ROOT}")
    print(f"ISS:       {ISS_ROOT}")

    try:
        legacy_body = load_legacy_body()
        b2_content = load_b2_content()
    except Exception as exc:
        print(f"ERRO ao carregar conteúdo: {exc}", file=sys.stderr)
        return 1

    legacy_words = len(legacy_body.split())
    b2_words = len(b2_content.split())
    print(f"legacy body: {legacy_words} palavras (sem meta)")
    print(f"B2 content:  {b2_words} palavras (meta + body ISS)")

    rows = [
        (
            DISCIPLINE,
            SLUG_LEGACY,
            "Staging legacy — modelagem relacional (sem meta B2)",
            1,
            legacy_body,
        ),
        (
            DISCIPLINE,
            SLUG_B2,
            "Staging B2 — introdução fluência IA (meta chunk 0)",
            2,
            b2_content,
        ),
    ]

    try:
        conn = db_connect()
    except Exception as exc:
        print(f"ERRO MySQL: {exc}", file=sys.stderr)
        print(
            "Dica: docker compose -f docker-compose.staging.yml up -d",
            file=sys.stderr,
        )
        return 1

    try:
        with conn.cursor() as cursor:
            for row in rows:
                cursor.execute(UPSERT_SQL, row)
        conn.commit()
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"ERRO UPSERT: {exc}", file=sys.stderr)
        if "doesn't exist" in str(exc).lower() or "1146" in str(exc):
            print(
                "Dica: ./bin/staging-apply-schema.sh  (tabela knowledge ausente)",
                file=sys.stderr,
            )
        return 1
    finally:
        conn.close()

    print(f"OK: {len(rows)} row(s) em knowledge ({DISCIPLINE})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
