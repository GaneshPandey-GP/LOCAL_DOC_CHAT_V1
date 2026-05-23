import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { ArrowLeft, MagnifyingGlass, FloppyDisk, FileText, ChartLine, Robot as Spider } from "@phosphor-icons/react";
import { toast } from "sonner";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

const TABS = [
    { id: "settings", label: "Settings" },
    { id: "search", label: "Search Test" },
    { id: "docs", label: "Documents" },
    { id: "analytics", label: "Analytics" },
];

export default function KnowledgeBaseDetail() {
    const { kbId } = useParams();
    const [tab, setTab] = useState("settings");
    const [kb, setKb] = useState(null);
    const [docs, setDocs] = useState([]);
    const [analytics, setAnalytics] = useState(null);

    const [q, setQ] = useState("");
    const [mode, setMode] = useState(null);
    const [thr, setThr] = useState(null);
    const [topK, setTopK] = useState(null);
    const [hits, setHits] = useState([]);
    const [searching, setSearching] = useState(false);
    const [saving, setSaving] = useState(false);

    const load = async () => {
        const r = await api.get(`/v2/kb/${kbId}`);
        setKb(r.data);
        setMode(r.data.search_mode || "hybrid");
        setThr(r.data.similarity_threshold ?? 0.5);
        setTopK(r.data.top_k ?? 5);
    };
    useEffect(() => { load(); }, [kbId]);

    useEffect(() => {
        if (tab === "docs") {
            api.get(`/v2/documents`).then(r => {
                setDocs(r.data.filter(d => d.kb_id === kbId));
            });
        } else if (tab === "analytics") {
            api.get(`/v2/kb/${kbId}/analytics`).then(r => setAnalytics(r.data));
        }
    }, [tab, kbId]);

    const save = async () => {
        setSaving(true);
        try {
            await api.patch(`/v2/kb/${kbId}`, {
                name: kb.name, description: kb.description, embedding_model: kb.embedding_model,
                search_mode: kb.search_mode, similarity_threshold: kb.similarity_threshold,
                top_k: kb.top_k, chunk_size: kb.chunk_size, chunk_overlap: kb.chunk_overlap,
                dense_weight: kb.dense_weight, sparse_weight: kb.sparse_weight,
                enable_reranking: kb.enable_reranking, enable_query_rewriting: kb.enable_query_rewriting,
                web_root_url: kb.web_root_url, sitemap_url: kb.sitemap_url, selector: kb.selector,
            });
            toast.success("Saved");
        } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
        finally { setSaving(false); }
    };

    const search = async () => {
        if (!q.trim()) { toast.error("Enter a query"); return; }
        setSearching(true);
        try {
            const r = await api.post(`/v2/kb/${kbId}/search`, { query: q, mode, top_k: topK, similarity_threshold: thr });
            setHits(r.data || []);
        } catch (e) { toast.error(e?.response?.data?.detail || "Search failed"); }
        finally { setSearching(false); }
    };

    if (!kb) return <div className="p-8">Loading…</div>;

    return (
        <div>
            <header className="h-auto md:h-16 border-b border-border px-4 md:px-8 py-3 md:py-0 flex items-center gap-4 sticky top-0 bg-background z-10">
                <Link to="/app/kb" className="text-muted-foreground hover:text-foreground"><ArrowLeft size={18} /></Link>
                <div>
                    <div className="dc-overline">Knowledge Base</div>
                    <h1 className="font-heading font-bold text-lg truncate max-w-[60vw]">{kb.name}</h1>
                </div>
            </header>
            <div className="px-4 md:px-8 border-b border-border flex gap-1 overflow-x-auto">
                {TABS.map(t => (
                    <button key={t.id} onClick={() => setTab(t.id)} data-testid={`kb-tab-${t.id}`}
                        className={`px-4 py-3 text-sm font-mono uppercase tracking-wider border-b-2 transition-colors ${tab === t.id ? "border-brand-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
                        {t.label}
                    </button>
                ))}
            </div>

            <div className="p-4 md:p-8 max-w-5xl">
                {tab === "settings" && (
                    <div className="space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            <div><Label>Name</Label><Input value={kb.name || ""} onChange={e => setKb({ ...kb, name: e.target.value })} /></div>
                            <div><Label>Embedding Model</Label>
                                <Select value={kb.embedding_model} onValueChange={v => setKb({ ...kb, embedding_model: v })}>
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="BAAI/bge-small-en-v1.5">Local MiniLM</SelectItem>
                                        <SelectItem value="text-embedding-3-small">OpenAI text-embedding-3-small</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>
                        <div><Label>Description</Label><Textarea rows={2} value={kb.description || ""} onChange={e => setKb({ ...kb, description: e.target.value })} /></div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            <div><Label>Search Mode</Label>
                                <Select value={kb.search_mode} onValueChange={v => setKb({ ...kb, search_mode: v })}>
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>{["vector", "hybrid", "similarity", "bm25", "ensemble"].map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent>
                                </Select>
                            </div>
                            <div><Label>Top-K: <span className="font-mono">{kb.top_k}</span></Label>
                                <Slider min={1} max={20} value={[kb.top_k || 5]} onValueChange={([v]) => setKb({ ...kb, top_k: v })} />
                            </div>
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <div><Label>Chunk Size</Label><Input type="number" value={kb.chunk_size || 1000} onChange={e => setKb({ ...kb, chunk_size: +e.target.value })} /></div>
                            <div><Label>Chunk Overlap</Label><Input type="number" value={kb.chunk_overlap || 200} onChange={e => setKb({ ...kb, chunk_overlap: +e.target.value })} /></div>
                        </div>
                        <div className="flex items-center justify-between border border-border p-3"><div><div className="font-medium text-sm">Reranking</div></div>
                            <Switch checked={!!kb.enable_reranking} onCheckedChange={v => setKb({ ...kb, enable_reranking: v })} /></div>
                        <div className="flex items-center justify-between border border-border p-3"><div><div className="font-medium text-sm">Query Rewriting</div></div>
                            <Switch checked={!!kb.enable_query_rewriting} onCheckedChange={v => setKb({ ...kb, enable_query_rewriting: v })} /></div>
                        <div className="flex justify-end gap-2">
                            {kb.type !== "document" && <Link to={`/app/kb/${kb.id}/crawl`}><Button variant="outline"><Spider size={14} /> Crawl Manager</Button></Link>}
                            <Button onClick={save} disabled={saving}><FloppyDisk size={14} /> {saving ? "Saving…" : "Save"}</Button>
                        </div>
                    </div>
                )}

                {tab === "search" && (
                    <div className="space-y-4">
                        <div className="border border-border p-4 space-y-3">
                            <Label>Query</Label>
                            <Textarea rows={2} value={q} onChange={e => setQ(e.target.value)} placeholder="What do you want to find?" data-testid="kb-search-input" />
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                <div><Label>Mode</Label>
                                    <Select value={mode} onValueChange={setMode}>
                                        <SelectTrigger><SelectValue /></SelectTrigger>
                                        <SelectContent>{["vector", "hybrid", "similarity", "bm25", "ensemble"].map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent>
                                    </Select>
                                </div>
                                <div><Label>Threshold: <span className="font-mono">{thr?.toFixed(2)}</span></Label>
                                    <Slider min={0} max={1} step={0.05} value={[thr || 0]} onValueChange={([v]) => setThr(v)} /></div>
                                <div><Label>Top-K: <span className="font-mono">{topK}</span></Label>
                                    <Slider min={1} max={20} value={[topK || 5]} onValueChange={([v]) => setTopK(v)} /></div>
                            </div>
                            <Button onClick={search} disabled={searching} data-testid="kb-search-run"><MagnifyingGlass size={14} /> {searching ? "Searching…" : "Search"}</Button>
                        </div>
                        <div className="space-y-3">
                            {hits.length === 0 && !searching && <div className="text-sm text-muted-foreground">No results yet — run a query.</div>}
                            {hits.map((h, i) => (
                                <div key={h.chunk_id} className="border border-border p-3" data-testid={`kb-search-hit-${i}`}>
                                    <div className="flex items-center justify-between text-xs font-mono mb-1">
                                        <span className="text-muted-foreground truncate"><FileText size={11} className="inline" /> {h.filename} {h.page ? `· p.${h.page}` : ""} · chunk {h.chunk_index}</span>
                                        <div className="flex gap-1.5 shrink-0">
                                            <Badge variant="outline">score {h.score?.toFixed(3)}</Badge>
                                            {h.confidence && <Badge variant="outline">{h.confidence}</Badge>}
                                        </div>
                                    </div>
                                    <div className="text-sm whitespace-pre-wrap line-clamp-6">{h.text}</div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {tab === "docs" && (
                    <div className="border border-border">
                        <div className="grid grid-cols-[1fr_120px_100px_140px_100px] gap-3 px-3 py-2 bg-secondary/50 border-b border-border text-xs font-mono uppercase tracking-wider text-muted-foreground">
                            <div>File</div><div>Type</div><div>Chunks</div><div>Indexed</div><div>Status</div>
                        </div>
                        {docs.length === 0 ? <div className="p-6 text-center text-sm text-muted-foreground">No documents in this KB</div> :
                            docs.map(d => (
                                <div key={d.id} className="grid grid-cols-[1fr_120px_100px_140px_100px] gap-3 px-3 py-2 border-b border-border last:border-b-0 text-sm">
                                    <div className="truncate">{d.filename}</div>
                                    <div className="text-xs font-mono">{d.file_type}</div>
                                    <div className="font-mono">{d.chunk_count}</div>
                                    <div className="text-xs text-muted-foreground">{d.indexed_at ? new Date(d.indexed_at).toLocaleDateString() : "—"}</div>
                                    <Badge variant="outline" className="text-[10px]">{d.status}</Badge>
                                </div>
                            ))}
                    </div>
                )}

                {tab === "analytics" && analytics && (
                    <div className="space-y-5">
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                            {[
                                ["Documents", analytics.document_count],
                                ["Chunks", analytics.chunk_count],
                                ["Pages", analytics.page_count],
                                ["Jobs", analytics.job_count],
                            ].map(([l, v]) => (
                                <div key={l} className="border border-border p-3"><div className="dc-overline">{l}</div><div className="font-heading font-bold text-2xl">{v}</div></div>
                            ))}
                        </div>
                        <div className="border border-border p-3">
                            <div className="dc-overline mb-2 flex items-center gap-2"><ChartLine size={12} /> Recent Crawl Jobs</div>
                            <ResponsiveContainer width="100%" height={220}>
                                <BarChart data={(analytics.recent_jobs || []).slice().reverse()}>
                                    <CartesianGrid strokeDasharray="3 3" />
                                    <XAxis dataKey="queued_at" tickFormatter={d => d?.slice(5, 10)} fontSize={10} />
                                    <YAxis fontSize={10} />
                                    <Tooltip />
                                    <Bar dataKey="pages_crawled" fill="#0033A0" />
                                    <Bar dataKey="pages_skipped" fill="#94a3b8" />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
