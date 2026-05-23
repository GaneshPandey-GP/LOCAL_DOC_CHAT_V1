import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
    BookOpen, Plus, Trash, Globe, FileText, Stack, Robot as Spider, MagnifyingGlass,
} from "@phosphor-icons/react";
import { toast } from "sonner";

const TYPE_BADGES = {
    document: { label: "Document", color: "bg-blue-50 text-blue-700 border-blue-300" },
    web: { label: "Web Crawl", color: "bg-emerald-50 text-emerald-700 border-emerald-300" },
    hybrid: { label: "Hybrid", color: "bg-purple-50 text-purple-700 border-purple-300" },
};

const SEARCH_MODES = ["vector", "hybrid", "similarity", "bm25", "ensemble"];

export default function KnowledgeBases() {
    const [kbs, setKbs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [open, setOpen] = useState(false);
    const [pollState, setPollState] = useState({}); // {kbId: status}
    const [form, setForm] = useState({
        name: "", description: "", embedding_model: "BAAI/bge-small-en-v1.5",
        type: "document", web_root_url: "", sitemap_url: "", selector: "",
        exclude_selectors: "",
        search_mode: "hybrid", similarity_threshold: 0.5, top_k: 5,
        chunk_size: 1000, chunk_overlap: 200,
        dense_weight: 0.7, sparse_weight: 0.3,
        enable_reranking: false, enable_query_rewriting: false,
    });
    const [submitting, setSubmitting] = useState(false);

    const load = async () => {
        setLoading(true);
        try { const r = await api.get("/v2/kb"); setKbs(r.data); }
        finally { setLoading(false); }
    };
    useEffect(() => { load(); }, []);

    // Poll active crawls every 3s
    useEffect(() => {
        const active = kbs.filter(k => k.type !== "document");
        if (!active.length) return;
        let cancelled = false;
        const tick = async () => {
            for (const k of active) {
                try {
                    const r = await api.get(`/v2/kb/${k.id}/crawl/status`);
                    if (!cancelled) setPollState(s => ({ ...s, [k.id]: r.data }));
                } catch {/* swallow */}
            }
        };
        tick();
        const id = setInterval(tick, 3000);
        return () => { cancelled = true; clearInterval(id); };
    }, [kbs]);

    const create = async () => {
        if (!form.name.trim()) { toast.error("Name is required"); return; }
        setSubmitting(true);
        try {
            const body = {
                ...form,
                exclude_selectors: form.exclude_selectors
                    ? form.exclude_selectors.split(",").map(s => s.trim()).filter(Boolean) : [],
            };
            await api.post("/v2/kb", body);
            toast.success("Knowledge base created");
            setOpen(false);
            setForm({ ...form, name: "", description: "" });
            load();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Create failed");
        } finally { setSubmitting(false); }
    };

    const del = async (id) => {
        if (!window.confirm("Delete this KB and ALL its vectors? This is irreversible.")) return;
        try { await api.delete(`/v2/kb/${id}`); toast.success("KB deleted"); load(); }
        catch (e) { toast.error(e?.response?.data?.detail || "Delete failed"); }
    };

    const startCrawl = async (kb) => {
        try {
            await api.post(`/v2/kb/${kb.id}/crawl`, {
                type: kb.sitemap_url ? "sitemap" : "recursive",
                url: kb.web_root_url,
                depth: 3, max_pages: 200, respect_robots: true, rate_limit_rps: 2.0,
            });
            toast.success("Crawl queued");
        } catch (e) { toast.error(e?.response?.data?.detail || "Crawl failed"); }
    };

    const renderProgress = (kb) => {
        const j = pollState[kb.id];
        if (!j || !["queued", "running"].includes(j.status)) return null;
        const pct = j.pages_found > 0 ? Math.round((j.pages_crawled / j.pages_found) * 100) : 0;
        return (
            <div className="mt-2 text-[10px] font-mono">
                <div className="flex justify-between text-muted-foreground"><span>crawling…</span><span>{j.pages_crawled}/{j.pages_found || "?"} · skipped {j.pages_skipped || 0}</span></div>
                <div className="h-1 bg-secondary mt-1"><div className="h-full bg-brand-primary transition-all" style={{ width: `${pct}%` }} /></div>
            </div>
        );
    };

    return (
        <div>
            <header className="h-auto md:h-16 border-b border-border px-4 md:px-8 py-3 md:py-0 flex flex-col md:flex-row md:items-center justify-between gap-3 sticky top-0 bg-background z-10">
                <div className="flex items-center gap-3">
                    <BookOpen size={22} weight="duotone" className="text-brand-primary" />
                    <div>
                        <div className="dc-overline">Workspace</div>
                        <h1 className="font-heading font-bold text-lg">Knowledge Bases</h1>
                    </div>
                </div>
                <Button onClick={() => setOpen(true)} data-testid="create-kb-button" className="min-h-[44px] md:min-h-0">
                    <Plus size={16} /> Create Knowledge Base
                </Button>
            </header>

            <div className="p-4 md:p-8 max-w-7xl">
                {loading ? (
                    <div className="text-sm text-muted-foreground">Loading…</div>
                ) : kbs.length === 0 ? (
                    <div className="border border-dashed border-border p-12 text-center" data-testid="kb-empty">
                        <BookOpen size={36} weight="duotone" className="mx-auto text-muted-foreground" />
                        <div className="font-heading font-bold text-xl mt-3">No knowledge bases yet</div>
                        <div className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">
                            Knowledge bases let you ingest specific document sets or web sources and search them with hybrid retrieval.
                        </div>
                        <Button onClick={() => setOpen(true)} className="mt-4"><Plus size={14} /> Create your first KB</Button>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                        {kbs.map(kb => {
                            const t = TYPE_BADGES[kb.type] || TYPE_BADGES.document;
                            return (
                                <div key={kb.id} className="border border-border p-4 flex flex-col gap-3" data-testid={`kb-card-${kb.id}`}>
                                    <div className="flex items-start justify-between gap-2">
                                        <Link to={`/app/kb/${kb.id}`} className="min-w-0 flex-1 group">
                                            <div className="font-medium truncate group-hover:text-brand-primary transition-colors">{kb.name}</div>
                                            <div className="text-xs text-muted-foreground line-clamp-2 mt-0.5">{kb.description || "—"}</div>
                                        </Link>
                                        <button onClick={() => del(kb.id)} className="text-muted-foreground hover:text-red-500" title="Delete">
                                            <Trash size={14} />
                                        </button>
                                    </div>
                                    <div className="flex flex-wrap gap-1.5">
                                        <Badge variant="outline" className={`text-[10px] font-mono uppercase ${t.color}`}>{t.label}</Badge>
                                        <Badge variant="outline" className="text-[10px] font-mono uppercase">{kb.search_mode}</Badge>
                                        {kb.enable_reranking && <Badge variant="outline" className="text-[10px] font-mono uppercase">rerank</Badge>}
                                    </div>
                                    <div className="grid grid-cols-3 gap-2 text-[11px] font-mono text-muted-foreground">
                                        <div><div className="text-foreground font-semibold">{kb.chunk_count || 0}</div>chunks</div>
                                        <div><div className="text-foreground font-semibold">{kb.document_count || 0}</div>docs</div>
                                        <div className="truncate"><div className="text-foreground font-semibold">{kb.top_k || 5}</div>top-k</div>
                                    </div>
                                    {renderProgress(kb)}
                                    <div className="flex gap-1.5 mt-1 flex-wrap">
                                        {kb.type !== "document" && (
                                            <Button size="sm" variant="outline" onClick={() => startCrawl(kb)} className="h-8 text-xs">
                                                <Spider size={13} /> Crawl
                                            </Button>
                                        )}
                                        <Link to={`/app/kb/${kb.id}`}>
                                            <Button size="sm" variant="outline" className="h-8 text-xs">
                                                <MagnifyingGlass size={13} /> Search Test
                                            </Button>
                                        </Link>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent data-testid="create-kb-dialog" className="w-[calc(100vw-1.5rem)] max-w-2xl max-h-[85vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle className="font-heading text-2xl">Create Knowledge Base</DialogTitle>
                        <DialogDescription>Configure how documents are chunked, embedded and retrieved.</DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 mt-2">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            <div>
                                <Label>Name <span className="text-muted-foreground text-[10px]">({form.name.length}/64)</span></Label>
                                <Input value={form.name} maxLength={64} onChange={e => setForm({ ...form, name: e.target.value })} data-testid="kb-name" />
                            </div>
                            <div>
                                <Label>Embedding Model</Label>
                                <Select value={form.embedding_model} onValueChange={v => setForm({ ...form, embedding_model: v })}>
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="BAAI/bge-small-en-v1.5">Local MiniLM (BGE small, 384d)</SelectItem>
                                        <SelectItem value="text-embedding-3-small">OpenAI text-embedding-3-small</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>
                        <div>
                            <Label>Description <span className="text-muted-foreground text-[10px]">({form.description.length}/256)</span></Label>
                            <Textarea rows={2} maxLength={256} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} />
                        </div>
                        <div>
                            <Label>Knowledge Type</Label>
                            <div className="grid grid-cols-3 gap-2 mt-1">
                                {["document", "web", "hybrid"].map(t => (
                                    <button key={t} type="button" onClick={() => setForm({ ...form, type: t })}
                                        className={`border px-3 py-2 text-sm font-mono uppercase tracking-wider ${form.type === t ? "border-brand-primary bg-brand-primary text-white" : "border-border"}`}
                                        data-testid={`kb-type-${t}`}>
                                        {t === "document" ? <><FileText size={14} className="inline mr-1" />Document</> :
                                         t === "web" ? <><Globe size={14} className="inline mr-1" />Web</> :
                                         <><Stack size={14} className="inline mr-1" />Hybrid</>}
                                    </button>
                                ))}
                            </div>
                        </div>
                        {(form.type === "web" || form.type === "hybrid") && (
                            <div className="border border-border p-3 space-y-3">
                                <div><Label>Web Root URL</Label><Input placeholder="https://docs.example.com" value={form.web_root_url} onChange={e => setForm({ ...form, web_root_url: e.target.value })} /></div>
                                <div><Label>Sitemap URL <span className="text-muted-foreground text-[10px]">(optional)</span></Label><Input placeholder="https://docs.example.com/sitemap.xml" value={form.sitemap_url} onChange={e => setForm({ ...form, sitemap_url: e.target.value })} /></div>
                                <div><Label>CSS Selector <span className="text-muted-foreground text-[10px]">(optional)</span></Label><Input placeholder="article.main-content" value={form.selector} onChange={e => setForm({ ...form, selector: e.target.value })} /></div>
                                <div><Label>Exclude Selectors <span className="text-muted-foreground text-[10px]">(comma-separated)</span></Label><Input placeholder=".sidebar, footer" value={form.exclude_selectors} onChange={e => setForm({ ...form, exclude_selectors: e.target.value })} /></div>
                            </div>
                        )}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            <div>
                                <Label>Search Mode</Label>
                                <Select value={form.search_mode} onValueChange={v => setForm({ ...form, search_mode: v })}>
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>{SEARCH_MODES.map(m => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent>
                                </Select>
                            </div>
                            <div>
                                <Label>Top-K: <span className="font-mono">{form.top_k}</span></Label>
                                <Slider min={1} max={20} step={1} value={[form.top_k]} onValueChange={([v]) => setForm({ ...form, top_k: v })} />
                            </div>
                        </div>
                        {form.search_mode === "similarity" && (
                            <div><Label>Similarity Threshold: <span className="font-mono">{form.similarity_threshold.toFixed(2)}</span></Label>
                                <Slider min={0} max={1} step={0.05} value={[form.similarity_threshold]} onValueChange={([v]) => setForm({ ...form, similarity_threshold: v })} />
                            </div>
                        )}
                        {form.search_mode === "hybrid" && (
                            <div className="grid grid-cols-2 gap-3">
                                <div><Label>Dense Weight: <span className="font-mono">{form.dense_weight.toFixed(2)}</span></Label>
                                    <Slider min={0} max={1} step={0.05} value={[form.dense_weight]} onValueChange={([v]) => setForm({ ...form, dense_weight: v, sparse_weight: +(1 - v).toFixed(2) })} /></div>
                                <div><Label>Sparse Weight: <span className="font-mono">{form.sparse_weight.toFixed(2)}</span></Label>
                                    <Slider min={0} max={1} step={0.05} value={[form.sparse_weight]} onValueChange={([v]) => setForm({ ...form, sparse_weight: v, dense_weight: +(1 - v).toFixed(2) })} /></div>
                            </div>
                        )}
                        <div className="grid grid-cols-2 gap-3">
                            <div><Label>Chunk Size</Label><Input type="number" value={form.chunk_size} onChange={e => setForm({ ...form, chunk_size: +e.target.value })} /></div>
                            <div><Label>Chunk Overlap</Label><Input type="number" value={form.chunk_overlap} onChange={e => setForm({ ...form, chunk_overlap: +e.target.value })} /></div>
                        </div>
                        <div className="flex items-center justify-between border border-border p-3">
                            <div><div className="font-medium text-sm">Reranking</div><div className="text-xs text-muted-foreground">Cross-encoder rerank of top results</div></div>
                            <Switch checked={form.enable_reranking} onCheckedChange={v => setForm({ ...form, enable_reranking: v })} />
                        </div>
                        <div className="flex items-center justify-between border border-border p-3">
                            <div><div className="font-medium text-sm">Query Rewriting</div><div className="text-xs text-muted-foreground">LLM-generated alternate phrasings</div></div>
                            <Switch checked={form.enable_query_rewriting} onCheckedChange={v => setForm({ ...form, enable_query_rewriting: v })} />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
                        <Button onClick={create} disabled={submitting || !form.name.trim()} data-testid="kb-create-submit">
                            {submitting ? "Creating…" : "Create"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
