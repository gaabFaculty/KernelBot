#!/usr/bin/env python3
"""Smoke da matriz de aceite: sempre LLM (plano be366700)."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8001/chat"

CASES = [
    (
        "vaga_1_palavra",
        {"message": "transformers"},
        {"reason": "underspecified_query"},
    ),
    (
        "off_corpus",
        {"message": "protocolo zetaquantum inexistente no material"},
        {
            "reason_in": (
                "insufficient_context",
                "context_misaligned",
                "low_confidence",
                "ambiguous_retrieval",
            )
        },
    ),
    (
        "ambigua_sem_disambiguation",
        {"message": "níveis integridade relacional transformers"},
        {
            "reason_in": (
                "ambiguous_retrieval",
                "context_misaligned",
                "low_confidence",
            ),
            "min_sources": 2,
        },
    ),
    (
        "doc_vazio",
        {"message": "/doc protocolo inexistente xyz"},
        {"decision": "answer", "not_hard_stop": True},
    ),
]


def stream_chat(payload: dict) -> tuple[dict | None, dict | None, list[str], bool]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        BASE,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    first_meta: dict | None = None
    last_meta: dict | None = None
    deltas: list[str] = []
    llm_stream = False
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            buf = ""
            for raw in resp:
                line = raw.decode("utf-8", errors="replace")
                buf += line
                while "\n" in buf:
                    part, buf = buf.split("\n", 1)
                    part = part.strip()
                    if not part.startswith("data:"):
                        continue
                    data = part[5:].strip()
                    if data == "[DONE]":
                        continue
                    if data.startswith("[ACL_META]"):
                        meta = json.loads(data[len("[ACL_META]") :])
                        if first_meta is None:
                            first_meta = meta
                        last_meta = meta
                        continue
                    llm_stream = True
                    deltas.append(data.replace("\\n", "\n"))
    except urllib.error.HTTPError as exc:
        return None, None, [f"HTTP {exc.code}: {exc.read().decode()[:500]}"], False
    except Exception as exc:
        return None, None, [str(exc)], False
    return first_meta, last_meta, deltas, llm_stream


def main() -> int:
    print(f"POST {BASE}\n")
    failed = 0
    for name, payload, expect in CASES:
        first, last, deltas, llm_stream = stream_chat(payload)
        ok = True
        notes: list[str] = []

        if first is None:
            ok = False
            notes.append("sem ACL_META inicial")
        else:
            if first.get("allow_generation") is not True:
                ok = False
                notes.append(f"inicial allow_generation={first.get('allow_generation')!r}")
            if first.get("decision") != "answer":
                ok = False
                notes.append(f"inicial decision={first.get('decision')!r}")
            exp_reason = expect.get("reason")
            if exp_reason and first.get("reason") != exp_reason:
                ok = False
                notes.append(
                    f"inicial reason={first.get('reason')!r} esperado {exp_reason}"
                )
            reason_in = expect.get("reason_in")
            if reason_in and first.get("reason") not in reason_in:
                ok = False
                notes.append(f"inicial reason={first.get('reason')!r} not in {reason_in}")
            min_src = expect.get("min_sources")
            if min_src and len(first.get("sources") or []) < min_src:
                ok = False
                notes.append(f"fontes={len(first.get('sources') or [])} < {min_src}")
            if expect.get("not_hard_stop") and first.get("decision") == "hard_stop":
                ok = False
                notes.append("hard_stop no meta inicial")

        if not llm_stream:
            ok = False
            notes.append("sem stream LLM")

        if last and last.get("post_generation_override"):
            notes.append(
                f"pós-geração override (ok): reason_final={last.get('reason')}"
            )

        text_len = sum(len(d) for d in deltas)
        status = "OK" if ok else "FALHA"
        if not ok:
            failed += 1
        print(f"[{status}] {name}")
        print(f"  message: {payload['message'][:70]}")
        if first:
            print(
                f"  meta_inicial: allow_generation={first.get('allow_generation')} "
                f"decision={first.get('decision')} reason={first.get('reason')} "
                f"sources={len(first.get('sources') or [])} llm_called={first.get('llm_called')}"
            )
        print(f"  stream_chars={text_len} notes={notes or ['—']}")
        print()

    print(f"Resumo: {len(CASES) - failed}/{len(CASES)} OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
