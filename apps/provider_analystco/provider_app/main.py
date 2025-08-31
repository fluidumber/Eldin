import os, json, re, glob, uuid, io, datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from whoosh import index
from whoosh.fields import Schema, TEXT, ID, STORED
from whoosh.qparser import MultifieldParser
import markdown2
import yaml
from slugify import slugify

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
DOCS_DIR = os.path.join(DATA_DIR, "provider_analystco", "docs")
INDEX_DIR = os.path.join(DATA_DIR, "provider_analystco", "index")
HOST = os.environ.get("HOST", "http://provider:8001")

app = FastAPI(title="AnalystCo Provider (MCP Server)")

class SearchRequest(BaseModel):
    q: str
    filters: Optional[Dict[str, Any]] = None
    topN: int = 10
    token: Optional[str] = None

class LicenseRequest(BaseModel):
    user: str
    scope: str
    tenant: str

class SectionsRequest(BaseModel):
    doc_id: str
    token: Optional[str] = None

class ExcerptSpan(BaseModel):
    section_id: str
    start: int = 0
    end: int = 600

class ExcerptsRequest(BaseModel):
    doc_id: str
    spans: List[ExcerptSpan]
    max_chars: int = 600
    token: Optional[str] = None

class CitationURLRequest(BaseModel):
    doc_id: str
    section_id: Optional[str] = None
    anchor: Optional[str] = None

# ---------- Utilities ----------
def ensure_index():
    os.makedirs(INDEX_DIR, exist_ok=True)
    schema = Schema(doc_id=ID(stored=True, unique=True),
                    title=TEXT(stored=True),
                    summary=TEXT(stored=True),
                    date=STORED,
                    authority=STORED,
                    fulltext=TEXT)
    if not index.exists_in(INDEX_DIR):
        ix = index.create_in(INDEX_DIR, schema)
    else:
        ix = index.open_dir(INDEX_DIR)

    # Determine if docs changed by simple heuristic: count files vs index doc count
    md_files = sorted(glob.glob(os.path.join(DOCS_DIR, "*.md")))
    writer = ix.writer()
    # Clear and rebuild for simplicity
    try:
        ix.reader().close()
    except:
        pass
    writer.mergetype = writing.CLEAR  # type: ignore

    # Simple parser for frontmatter + markdown sections
    for p in md_files:
        with open(p, "r", encoding="utf-8") as f:
            raw = f.read()
        m = re.match(r"---\n(.*?)\n---\n(.*)$", raw, re.S)
        if m:
            fm = yaml.safe_load(m.group(1))
            body = m.group(2).strip()
        else:
            fm = {}
            body = raw
        doc_id = fm.get("id") or os.path.splitext(os.path.basename(p))[0]
        title = fm.get("title") or doc_id
        date = fm.get("date") or ""
        authority = fm.get("authority") or 0.5

        # Summary = first paragraph
        summary = ""
        for para in body.split("\n\n"):
            if para.strip():
                summary = re.sub(r"\s+", " ", para.strip())
                break

        writer.add_document(doc_id=str(doc_id),
                            title=title,
                            summary=summary,
                            date=str(date),
                            authority=float(authority),
                            fulltext=body)
    writer.commit()
    return True

def parse_sections(md_text: str):
    # Return list of (section_id, title, text, anchor)
    sections = []
    current_title = None
    current_text = []
    for line in md_text.splitlines():
        if line.startswith("#"):
            # flush prev
            if current_title is not None:
                title = current_title.strip("# ").strip()
                anchor = "#" + slugify(title)
                section_id = slugify(title).upper()[:8]
                sections.append({
                    "section_id": section_id,
                    "title": title,
                    "anchor": anchor,
                    "text": "\n".join(current_text).strip()
                })
                current_text = []
            current_title = line
        else:
            current_text.append(line)
    if current_title is not None:
        title = current_title.strip("# ").strip()
        anchor = "#" + slugify(title)
        section_id = slugify(title).upper()[:8]
        sections.append({
            "section_id": section_id,
            "title": title,
            "anchor": anchor,
            "text": "\n".join(current_text).strip()
        })
    return sections

def read_doc(doc_id: str):
    path = os.path.join(DOCS_DIR, f"{doc_id}.md")
    if not os.path.exists(path):
        # try fallback search by filename prefix
        candidates = glob.glob(os.path.join(DOCS_DIR, f"{doc_id}*.md"))
        if not candidates:
            return None, None, None, None
        path = candidates[0]
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    m = re.match(r"---\n(.*?)\n---\n(.*)$", raw, re.S)
    if m:
        fm = yaml.safe_load(m.group(1))
        body = m.group(2).strip()
    else:
        fm, body = {}, raw
    title = fm.get("title") or doc_id
    date = fm.get("date") or ""
    authority = fm.get("authority") or 0.5
    sections = parse_sections(body)
    return title, date, authority, sections

# Build index on startup
try:
    ensure_index()
except Exception as e:
    print("Index build error:", e)

# ---------- Portal (HTML rendering) ----------
@app.get("/portal/doc/{doc_id}")
def portal_doc(doc_id: str):
    title, date, authority, sections = read_doc(doc_id)
    if title is None:
        raise HTTPException(status_code=404, detail="Doc not found")
    # Build a simple HTML with anchors
    html = [f"<html><head><title>{title}</title></head><body>"]
    html.append(f"<h1>{title}</h1>")
    html.append(f"<p><em>Date: {date} • Authority: {authority}</em></p>")
    for s in sections:
        html.append(f"<h2 id='{s['anchor'].lstrip('#')}'>{s['title']}</h2>")
        html.append("<pre>" + (s["text"] or "").replace("<","&lt;").replace(">","&gt;") + "</pre>")
    html.append("</body></html>")
    return html[0] + "\n".join(html[1:])

# ---------- MCP endpoints ----------
@app.post("/mcp/license.check")
def license_check(req: LicenseRequest):
    # MVP: allow basic scopes
    allowed_scopes = {"read:metadata", "read:excerpts"}
    return {"allowed": req.scope in allowed_scopes, "reason": "mock-policy"}

@app.post("/mcp/search.documents")
def search_documents(req: SearchRequest):
    from whoosh import index
    from whoosh.qparser import MultifieldParser
    ix = index.open_dir(INDEX_DIR)
    parser = MultifieldParser(["title", "summary", "fulltext"], schema=ix.schema)
    q = parser.parse(req.q)
    out = []
    with ix.searcher() as s:
        res = s.search(q, limit=req.topN)
        for hit in res:
            out.append({
                "doc_id": hit["doc_id"],
                "title": hit["title"],
                "summary": hit["summary"],
                "recency": hit.get("date", ""),
                "authority": hit.get("authority", 0.5)
            })
    return out

@app.post("/mcp/list.sections")
def list_sections(req: SectionsRequest):
    title, date, authority, sections = read_doc(req.doc_id)
    if title is None:
        raise HTTPException(status_code=404, detail="Doc not found")
    return [{"section_id": s["section_id"], "title": s["title"], "anchor": s["anchor"]} for s in sections]

@app.post("/mcp/get.excerpts")
def get_excerpts(req: ExcerptsRequest):
    title, date, authority, sections = read_doc(req.doc_id)
    if title is None:
        raise HTTPException(status_code=404, detail="Doc not found")
    sec_map = {s["section_id"]: s for s in sections}
    excerpts = []
    consumed = 0
    for span in req.spans:
        sec = sec_map.get(span.section_id)
        if not sec:
            continue
        text = sec["text"]
        start = max(0, span.start)
        end = min(len(text), span.end, start + req.max_chars)
        chunk = text[start:end]
        consumed += len(chunk)
        excerpts.append({
            "section_id": span.section_id,
            "text": chunk,
            "anchor": sec["anchor"],
            "citation_url": f"{HOST}/portal/doc/{req.doc_id}{sec['anchor']}"
        })
    return {"excerpts": excerpts, "consumed_chars": consumed}

@app.post("/mcp/get.citation_url")
def get_citation_url(req: CitationURLRequest):
    anchor = req.anchor or ""
    return {"url": f"{HOST}/portal/doc/{req.doc_id}{anchor}"}