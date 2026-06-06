"""Variáveis e paths comuns para staging local (sem tocar .env de produção)."""
from __future__ import annotations

import os
from pathlib import Path

KERNELBOT_ROOT = Path(__file__).resolve().parents[2]
ISS_ROOT = Path(os.environ.get("ISS_ROOT", KERNELBOT_ROOT.parent / "ISS")).resolve()

STAGING_DEFAULTS: dict[str, str] = {
    "OPENROUTER_API_KEY": "staging-dummy-not-used-for-e2e",
    "DB_HOST": "127.0.0.1",
    "DB_PORT": "3307",
    "DB_NAME": "kernelbot_staging",
    "DB_USER": "kb_staging",
    "DB_PASSWORD": "kb_staging_pw",
    "ACL_GLOBAL_CONTEXT": "geral",
    "ACL_CATALOG_ENABLED": "false",
}

UPSERT_SQL = """
INSERT INTO knowledge (discipline, slug, title, `order`, content, active)
VALUES (%s, %s, %s, %s, %s, 1)
ON DUPLICATE KEY UPDATE
  title = VALUES(title),
  `order` = VALUES(`order`),
  content = VALUES(content),
  active = 1
"""


def apply_staging_env() -> Path:
    """Carrega .env.staging.local se existir; senão defaults inline (sem Aiven)."""
    from dotenv import load_dotenv

    local = KERNELBOT_ROOT / ".env.staging.local"
    if local.is_file():
        load_dotenv(local, override=True)
    for key, value in STAGING_DEFAULTS.items():
        os.environ.setdefault(key, value)
    return KERNELBOT_ROOT


def db_connect():
    import pymysql

    apply_staging_env()
    return pymysql.connect(
        host=os.environ["DB_HOST"].strip(),
        port=int(os.environ.get("DB_PORT", "3307")),
        database=os.environ["DB_NAME"].strip(),
        user=os.environ["DB_USER"].strip(),
        password=os.environ.get("DB_PASSWORD", ""),
        charset="utf8mb4",
        autocommit=False,
    )
