# Eldin MVP — HRM-lite + MCP Gateway + Mock Provider + Next.js UI

This is a runnable starter kit that demonstrates:
- **MCP Tool Bus (gateway)** calling a **mock provider** via well-defined endpoints
- **HRM-lite retrieval** (Q0 fixed provider → Q1 documents (BM25) → Q2 section selection by heading match)
- **Citation-first answers** with excerpt caps and **audit logging**
- A simple **Next.js** UI to ask questions and view answers + citations

## Quick Start

```bash
# 1) Build & run
docker compose up --build

# 2) Open the UI
# http://localhost:3000

# 3) Ask a question (e.g.):
# "How do I remediate call recording failures in Region X?"
```

### Services
- **gateway** (FastAPI): http://localhost:8000
- **provider_analystco** (FastAPI): http://localhost:8001
- **web** (Next.js): http://localhost:3000

### Data
- Docs live in `data/provider_analystco/docs/` as Markdown.
- Index is built on provider startup under `data/provider_analystco/index/` (Whoosh).
- Audit logs written to `data/logs/audit.jsonl` by the gateway.

### Contracts (MCP-like)
POST endpoints on provider:
- `/mcp/license.check`
- `/mcp/search.documents`
- `/mcp/list.sections`
- `/mcp/get.excerpts`
- `/mcp/get.citation_url`

### Env
- See `infra/docker-compose.yml` for ports/env.
- CORS for UI → gateway is allowed by default.

> NOTE: This is a minimal MVP: auth is stubbed, budgets and scopes are enforced in-process for clarity.