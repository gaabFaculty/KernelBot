#!/usr/bin/env python3
"""
E2E staging: fetch_db_chunks → SearchEngine.rebuild() → queries BM25.

Uso:
  python scripts/staging/run_e2e_reload.py
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
KERNELBOT_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(KERNELBOT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from staging_env import apply_staging_env  # noqa: E402

META_START = "[CONCEITOS E KEYWORDS DA AULA PARA INDEXAÇÃO LÉXICA]"

# Query A: termo no corpo legacy (modelagem relacional aula-01)
QUERY_LEGACY = "modelo hierárquico rede relacional"
# Query B: keyword só no meta B2 (ISS fluencia-ia/01)
QUERY_B2 = "transformers"

DISCIPLINE = "_staging"
SOURCE_LEGACY = f"db:{DISCIPLINE}/legacy-modelagem"
SOURCE_B2 = f"db:{DISCIPLINE}/fluencia-b2"


def _setup_logging() -> None:
    from core.logging_config import configure_logging

    apply_staging_env()
    configure_logging()


def _load_settings():
    from core.config import Settings

    return Settings.load()


def _chunks_for_source(chunks: list[dict], source: str) -> list[dict]:
    return [c for c in chunks if c.get("source") == source]


def main() -> int:
    _setup_logging()
    log = logging.getLogger("kernelbots.staging.e2e")

    print("=== E2E staging reload ===")
    print(f"DB: {__import__('os').environ.get('DB_HOST')}:{__import__('os').environ.get('DB_PORT')}")
    print(f"DB_NAME: {__import__('os').environ.get('DB_NAME')}")

    try:
        settings = _load_settings()
    except Exception as exc:
        print(f"FALHA Settings.load(): {exc}", file=sys.stderr)
        return 1

    from engine.database import fetch_db_chunks
    from engine.search import SearchEngine

    t0 = time.perf_counter()
    try:
        chunks = fetch_db_chunks(settings)
    except Exception as exc:
        print(f"FALHA fetch_db_chunks: {exc}", file=sys.stderr)
        return 1
    fetch_ms = (time.perf_counter() - t0) * 1000

    sources = {c.get("source") for c in chunks}
    row_sources = {s for s in sources if s and s.startswith("db:")}
    print(f"fetch_db_chunks: chunk_count={len(chunks)} fetch_ms={fetch_ms:.2f}")
    print(f"  sources: {sorted(row_sources)}")

    if not chunks:
        print("FALHA: chunk_count=0 (MySQL inacessível ou sem seed?)", file=sys.stderr)
        return 1

    t1 = time.perf_counter()
    engine = SearchEngine(score_threshold=0.7, settings=settings)
    rebuild_ms = (time.perf_counter() - t1) * 1000

    all_chunks = engine.chunks
    silos = sorted(engine._silos.keys())  # noqa: SLF001 — diagnóstico E2E
    print(f"SearchEngine.rebuild: chunk_total={len(all_chunks)} silos={silos}")
    print(f"  rebuild_ms={rebuild_ms:.2f}")

    ok = True

    # --- Query A (legacy) ---
    cands_a = engine.search_candidates(QUERY_LEGACY, candidate_k=8, discipline_filter=DISCIPLINE)
    top_a = cands_a[0] if cands_a else None
    print(f"\nQuery A ({QUERY_LEGACY!r}):")
    if not top_a:
        print("  FALHA: sem candidatos")
        ok = False
    else:
        print(f"  top source={top_a.source} raw_score={top_a.raw_score:.4f}")
        if SOURCE_LEGACY not in top_a.source:
            print(f"  FALHA: esperado hit em {SOURCE_LEGACY}")
            ok = False
        legacy_chunks = _chunks_for_source(all_chunks, SOURCE_LEGACY)
        meta_in_legacy = any(META_START in c.get("text", "") for c in legacy_chunks)
        if meta_in_legacy:
            print("  FALHA: legacy não deve conter bloco meta B2")
            ok = False
        else:
            print("  OK: legacy sem meta B2 nos chunks")

    # --- Query B (transformers → chunk 0 > chunk 1) ---
    cands_b = engine.search_candidates(QUERY_B2, candidate_k=8, discipline_filter=DISCIPLINE)
    b2_chunks = _chunks_for_source(all_chunks, SOURCE_B2)
    print(f"\nQuery B ({QUERY_B2!r}) — chunks B2: {len(b2_chunks)}")
    if len(b2_chunks) < 2:
        print("  AVISO: menos de 2 chunks B2 (body curto?)")
    chunk0_has_meta = META_START in (b2_chunks[0]["text"] if b2_chunks else "")
    chunk1_has_meta = META_START in (b2_chunks[1]["text"] if len(b2_chunks) > 1 else "")
    print(f"  meta no chunk0: {chunk0_has_meta} | meta no chunk1+: {chunk1_has_meta}")
    if not chunk0_has_meta:
        print("  FALHA: chunk 0 B2 deve ter meta_header")
        ok = False
    if chunk1_has_meta:
        print("  FALHA: meta só deve aparecer no chunk 0 (B2)")
        ok = False

    with engine._lock:  # noqa: SLF001
        silo_chunks = list(engine._silos.get(DISCIPLINE, {}).get("chunks", []))
    b2_positions = [
        i for i, ch in enumerate(silo_chunks) if ch.get("source") == SOURCE_B2
    ]
    score_by_pos: dict[int, float] = {}
    for c in cands_b:
        if SOURCE_B2 not in c.source:
            continue
        try:
            pos = int(c.chunk_id.split(":", 1)[1])
        except (IndexError, ValueError):
            continue
        score_by_pos[pos] = c.raw_score

    if len(b2_positions) >= 2:
        p0, p1 = b2_positions[0], b2_positions[1]
        s0 = score_by_pos.get(p0, 0.0)
        s1 = score_by_pos.get(p1, 0.0)
        print(f"  B2 pos{p0} raw={s0:.4f} pos{p1} raw={s1:.4f} margin={s0 - s1:.4f}")
        if s0 <= s1:
            print("  FALHA: chunk0 B2 deve ter score > chunk1 para transformers")
            ok = False
        elif s0 <= 0:
            print("  FALHA: score chunk0 B2 deve ser positivo")
            ok = False
        else:
            print("  OK: chunk0 > chunk1 (meta só no primeiro chunk B2)")
    elif b2_positions:
        p0 = b2_positions[0]
        s0 = score_by_pos.get(p0, 0.0)
        print(f"  AVISO: um único chunk B2 (pos{p0} raw={s0:.4f})")
        if s0 <= 0:
            print("  FALHA: score B2 deve ser positivo")
            ok = False
    else:
        print("  FALHA: sem chunks B2 no silo")
        ok = False

    print("\n=== Veredito ===")
    if ok:
        print(f"E2E: SIM | fetch_ms={fetch_ms:.2f} rebuild_ms={rebuild_ms:.2f}")
        log.info("staging e2e passou")
        return 0
    print(f"E2E: NÃO | fetch_ms={fetch_ms:.2f} rebuild_ms={rebuild_ms:.2f}")
    log.error("staging e2e falhou")
    return 1


if __name__ == "__main__":
    sys.exit(main())
