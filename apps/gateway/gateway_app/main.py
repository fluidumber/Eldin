import os, json, time, datetime, re
from typing import List, Dict, Any
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

PROVIDER_BASE = os.environ.get("PROVIDER_BASE", "http://provider:8001")
AUDIT_LOG = os.environ.get("AUDIT_LOG", "/app/data/logs/audit.jsonl")
EXCERPT_PER_SECTION = int(os.environ.get("EXCERPT_PER_SECTION", "600"))
EXCERPT_TOTAL_CAP = int(os.environ.get("EXCERPT_TOTAL_CAP", "1200"))
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "http://localhost:3000")

app = FastAPI(title="Eldin Gateway (MCP Client + Orchestrator)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[CORS_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def audit(event: Dict[str, Any]):
    try:
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception as e:
        print("Audit write error:", e)

class AskRequest(BaseModel):
    q: str
    user: str = "demo_user"
    tenant: str = "acme"

class SourceItem(BaseModel):
    doc_id: str
    title: str
    anchor: str
    citation_url: str
    excerpt: str

class AskResponse(BaseModel):
    answer: str
    sources: List[SourceItem]
    meta: Dict[str, Any]

def simple_heading_score(query: str, title: str) -> float:
    # naive token overlap score
    q_tokens = set(re.findall(r"\w+", query.lower()))
    t_tokens = set(re.findall(r"\w+", title.lower()))
    if not t_tokens: return 0.0
    return len(q_tokens & t_tokens) / (len(q_tokens) + 1e-6)

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    t0 = time.time()
    # License check (mock)
    audit({"ts": time.time(), "type": "ask", "user": req.user, "tenant": req.tenant, "q": req.q})

    # Q1: docs
    with httpx.Client(timeout=10.0) as client:
        docs = client.post(f"{PROVIDER_BASE}/mcp/search.documents", json={
            "q": req.q, "filters": {}, "topN": 8, "token": "stub"
        }).json()

    if not docs:
        return AskResponse(answer="Insufficient evidence. No relevant documents found.",
                           sources=[], meta={"ttfa_ms": int((time.time()-t0)*1000)})

    # Q2: sections (pick up to K=2 per doc by heading match)
    sections_to_fetch = []
    doc_title_map = {}
    for d in docs:
        doc_id = d["doc_id"]
        title = d["title"]
        doc_title_map[doc_id] = title
        with httpx.Client(timeout=10.0) as client:
            sec = client.post(f"{PROVIDER_BASE}/mcp/list.sections", json={"doc_id": doc_id, "token": "stub"}).json()
        # score headings
        scored = [{"score": simple_heading_score(req.q, s["title"]), **s} for s in sec]
        scored.sort(key=lambda x: x["score"], reverse=True)
        pick = [s for s in scored[:2] if s["score"] > 0]  # K=2, positive score
        for p in pick:
            sections_to_fetch.append({"doc_id": doc_id, "section_id": p["section_id"], "anchor": p["anchor"]})

    if not sections_to_fetch:
        return AskResponse(answer="Insufficient evidence. No relevant sections matched the query.",
                           sources=[], meta={"ttfa_ms": int((time.time()-t0)*1000)})

    # Excerpt caps
    total_chars = 0
    sources = []
    for item in sections_to_fetch:
        remaining = EXCERPT_TOTAL_CAP - total_chars
        if remaining <= 0:
            break
        per = min(EXCERPT_PER_SECTION, remaining)
        with httpx.Client(timeout=10.0) as client:
            ex = client.post(f"{PROVIDER_BASE}/mcp/get.excerpts", json={
                "doc_id": item["doc_id"],
                "spans": [{"section_id": item["section_id"], "start": 0, "end": per}],
                "max_chars": per,
                "token":"stub"
            }).json()
        if not ex["excerpts"]:
            continue
        e = ex["excerpts"][0]
        total_chars += len(e["text"])
        sources.append({
            "doc_id": item["doc_id"],
            "title": doc_title_map[item["doc_id"]],
            "anchor": e["anchor"],
            "citation_url": e["citation_url"],
            "excerpt": e["text"]
        })

    if not sources:
        return AskResponse(answer="Insufficient evidence after applying excerpt caps.",
                           sources=[], meta={"ttfa_ms": int((time.time()-t0)*1000)})

    # Build an extractive answer (bullet-like synthesis from excerpts)
    bullets = []
    for s in sources:
        # take first line(s) as bullet
        first = s["excerpt"].strip().splitlines()[0:2]
        bullets.append(" - " + " ".join([x.strip() for x in first if x.strip()]))

    answer = "Key findings:\n" + "\n".join(bullets) + "\n\nSee citations for exact passages."
    ttfa = int((time.time() - t0) * 1000)

    audit({
        "ts": time.time(),
        "type": "answer",
        "user": req.user,
        "tenant": req.tenant,
        "q": req.q,
        "sources": [{"doc_id": s["doc_id"], "anchor": s["anchor"], "chars": len(s["excerpt"])} for s in sources],
        "ttfa_ms": ttfa
    })

    return AskResponse(answer=answer, sources=sources, meta={"ttfa_ms": ttfa, "excerpt_total": total_chars})