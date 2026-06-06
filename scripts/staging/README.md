# Staging local (MySQL offline)

Massa mista para validar **legacy** (markdown sem meta) + **B2** (meta só no chunk 0) no pipeline `fetch_db_chunks` → `SearchEngine.rebuild()` → BM25.

Credenciais em `docker-compose.staging.yml` (comentários) e `.env.staging.example` — **não** usar em produção/Aiven.

## Pré-requisitos

- Docker + Docker Compose
- Python 3 + venv KernelBot (`pip install -r requirements.txt`)
- Repo ISS ao lado: `../ISS` (ou `ISS_ROOT=/caminho/ISS`)

## 5 comandos

```bash
cd /home/gaab/Documentos/gitHub/KernelBot

# 1) Subir MySQL 8 na porta 3307
docker compose -f docker-compose.staging.yml up -d

# 2) Esperar healthy (opcional)
docker compose -f docker-compose.staging.yml ps

# 3) (Opcional) copiar env staging — ou usar defaults inline nos scripts
cp .env.staging.example .env.staging.local

# 4) Seed: legacy sql-modelagem + B2 fluencia-ia/01
.venv/bin/python scripts/staging/seed_mixed_mass.py

# 5) E2E: fetch + rebuild + queries BM25
.venv/bin/python scripts/staging/run_e2e_reload.py
```

## Sem Docker

Se `docker` não estiver instalado, use MySQL/MariaDB nativo na porta **3307** com o schema em `init-knowledge.sql` e as mesmas credenciais do compose. Depois execute os passos 4–5.

## O que o E2E valida

| Check | Critério |
|-------|----------|
| `fetch_db_chunks` | `chunk_count > 0` |
| `rebuild` | silos incluem `_staging` |
| Query A | `modelo hierárquico…` acerta `db:_staging/legacy-modelagem` |
| Query B | `transformers` — score chunk 0 > chunk 1; meta só no chunk 0 |
| Legacy | sem `ERROR` fatal de meta malformado |

## Parar

```bash
docker compose -f docker-compose.staging.yml down
```
