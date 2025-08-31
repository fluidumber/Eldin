import { useState } from "react";

const GATEWAY = process.env.NEXT_PUBLIC_GATEWAY || "http://localhost:8000";

export default function Home() {
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [resp, setResp] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const ask = async () => {
    setError(null);
    setLoading(true);
    setResp(null);
    try {
      const r = await fetch(`${GATEWAY}/ask`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ q, user: "demo_user", tenant: "acme" })
      });
      if (!r.ok) {
        throw new Error(`Gateway error: ${r.status}`);
      }
      const data = await r.json();
      setResp(data);
    } catch (e:any) {
      setError(e.message || "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main style={{maxWidth: 900, margin: "40px auto", fontFamily: "system-ui, Arial"}}>
      <h1>Eldin MVP — License‑Aware Answers</h1>
      <p>Ask a question and get excerpt‑cited answers across your licensed provider.</p>
      <div style={{display:"flex", gap: 8, marginTop: 16}}>
        <input
          value={q}
          onChange={e=>setQ(e.target.value)}
          placeholder="e.g., How do I remediate call recording failures in Region X?"
          style={{flex: 1, padding: 10, border: "1px solid #ccc", borderRadius: 6}}
        />
        <button onClick={ask} disabled={loading || !q.trim()} style={{padding: "10px 16px"}}>
          {loading ? "Asking..." : "Ask"}
        </button>
      </div>
      {error && <p style={{color:"red"}}>{error}</p>}
      {resp && (
        <section style={{marginTop: 24}}>
          <h2>Answer</h2>
          <pre style={{whiteSpace:"pre-wrap"}}>{resp.answer}</pre>
          <h3>Sources</h3>
          <ul>
            {resp.sources?.map((s:any, idx:number)=> (
              <li key={idx} style={{marginBottom: 12}}>
                <div><strong>{s.title}</strong> — <code>{s.doc_id}</code></div>
                <div style={{fontSize:13, color:"#555"}}>{s.excerpt.slice(0,200)}{s.excerpt.length>200?"...":""}</div>
                <div><a href={s.citation_url} target="_blank">Open citation</a></div>
              </li>
            ))}
          </ul>
          <div style={{fontSize:12, color:"#666"}}>
            <div>Latency: {resp.meta?.ttfa_ms} ms</div>
            <div>Excerpt total: {resp.meta?.excerpt_total}</div>
          </div>
        </section>
      )}
    </main>
  );
}