import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { ArrowLeft, Robot as Spider, ArrowClockwise, Play, FloppyDisk, Trash, Eye, Warning, X as XIcon, CaretDown, CaretRight, Info } from "@phosphor-icons/react";
import { toast } from "sonner";

const STATUS_COLORS = {
    queued: "border-amber-500 text-amber-700 bg-amber-50",
    running: "border-blue-500 text-blue-700 bg-blue-50",
    completed: "border-green-600 text-green-700 bg-green-50",
    failed: "border-red-500 text-red-700 bg-red-50",
    cancelled: "border-yellow-500 text-yellow-700 bg-yellow-50",
};

export default function KnowledgeBaseCrawl() {
    const { kbId } = useParams();
    const [kb, setKb] = useState(null);
    const [active, setActive] = useState(null);
    const [history, setHistory] = useState([]);
    // schedule state (kept for completeness even though the existing UI
    // mostly relies on the inline cron form below)
    const [cfg, setCfg] = useState({
        type: "recursive", url: "", depth: 3, max_pages: 200,
        respect_robots: true, rate_limit_rps: 2.0, selector: "", use_playwright: false,
    });
    const [cronForm, setCronForm] = useState({ cron_expr: "0 3 * * *", enabled: true });
    const [flags, setFlags] = useState({});
    const [preview, setPreview] = useState(null); // {url,title,content_preview,word_count,status_code}
    const [previewLoading, setPreviewLoading] = useState(false);
    const [expandedFailed, setExpandedFailed] = useState({}); // jobId -> bool

    const load = async () => {
        const [k, st, h] = await Promise.all([
            api.get(`/v2/kb/${kbId}`),
            api.get(`/v2/kb/${kbId}/crawl/status`),
            api.get(`/v2/kb/${kbId}/crawl/history`),
        ]);
        setKb(k.data);
        setActive(st.data && st.data.status !== "none" ? st.data : null);
        setHistory(h.data || []);
        if (!cfg.url && k.data?.web_root_url) setCfg(c => ({ ...c, url: k.data.web_root_url }));
    };
    useEffect(() => { load(); api.get("/v2/flags").then(r => setFlags(r.data)).catch(() => {}); }, [kbId]);

    // Live refresh while running/queued; stop on completed/failed/cancelled.
    useEffect(() => {
        if (!active || !["queued", "running"].includes(active.status)) return;
        const id = setInterval(load, 3000);
        return () => clearInterval(id);
    }, [active]);

    const start = async () => {
        try {
            await api.post(`/v2/kb/${kbId}/crawl`, cfg);
            toast.success("Crawl queued");
            load();
        } catch (e) {
            const status = e?.response?.status;
            const detail = e?.response?.data?.detail || "Crawl failed";
            if (status === 422) toast.error(`Cannot start crawl: ${detail}`, { duration: 6000 });
            else toast.error(detail);
        }
    };
    const cancel = async () => {
        if (!window.confirm("Cancel the active crawl? Already-ingested pages stay in the KB.")) return;
        try { await api.post(`/v2/kb/${kbId}/crawl/cancel`); toast.success("Cancel signal sent"); load(); }
        catch (e) { toast.error(e?.response?.data?.detail || "Cancel failed"); }
    };
    const retry = async (job) => {
        try { await api.post(`/v2/kb/${kbId}/crawl/retry`); toast.success("Re-queued"); load(); }
        catch (e) { toast.error(e?.response?.data?.detail || "Retry failed"); }
    };
    const previewUrl = async () => {
        if (!cfg.url) { toast.error("Enter a URL first"); return; }
        setPreviewLoading(true);
        try {
            const r = await api.post(`/v2/kb/${kbId}/crawl/preview`, { ...cfg, type: "single" });
            setPreview(r.data);
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Preview failed");
        } finally { setPreviewLoading(false); }
    };
    const saveSchedule = async () => {
        try { await api.post(`/v2/kb/${kbId}/schedule`, { ...cronForm, crawl_config: cfg }); toast.success("Schedule saved"); }
        catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
    };
    const delSchedule = async () => {
        try { await api.delete(`/v2/kb/${kbId}/schedule`); toast.success("Schedule deleted"); }
        catch (e) { toast.error("Delete failed"); }
    };

    if (!kb) return <div className="p-8">Loading…</div>;
    const showPlaywright = !!flags.ENABLE_PLAYWRIGHT_CRAWLER;
    const elapsed = active?.started_at ? Math.round((Date.now() - new Date(active.started_at).getTime()) / 1000) : 0;
    const isRunning = !!active && ["queued", "running"].includes(active.status);

    return (
        <div>
            <header className="h-auto md:h-16 border-b border-border px-4 md:px-8 py-3 md:py-0 flex items-center gap-4 sticky top-0 bg-background z-10">
                <Link to={`/app/kb/${kbId}`} className="text-muted-foreground hover:text-foreground"><ArrowLeft size={18} /></Link>
                <Spider size={20} weight="duotone" className="text-brand-primary" />
                <div>
                    <div className="dc-overline">Crawl Manager</div>
                    <h1 className="font-heading font-bold text-lg truncate max-w-[60vw]">{kb.name}</h1>
                </div>
            </header>
            <div className="p-4 md:p-8 max-w-5xl space-y-6">
                {active && (
                    <div className={`border p-4 ${
                        active.status === "failed" ? "border-red-300 bg-red-50/40" :
                        active.status === "cancelled" ? "border-yellow-300 bg-yellow-50/40" :
                        active.status === "completed" ? "border-green-300 bg-green-50/40" :
                        "border-blue-300 bg-blue-50/40"
                    }`} data-testid="crawl-active">
                        <div className="flex items-center justify-between flex-wrap gap-2">
                            <div className="flex items-center gap-2"><Badge className={`text-[10px] font-mono uppercase ${STATUS_COLORS[active.status] || ""}`}>{active.status}</Badge>
                                <span className="text-xs text-muted-foreground">started {active.started_at ? new Date(active.started_at).toLocaleString() : "—"} · {elapsed}s elapsed</span></div>
                            {isRunning && (
                                <Button size="sm" variant="outline" onClick={cancel} data-testid="cancel-crawl">
                                    <XIcon size={13} /> Cancel Crawl
                                </Button>
                            )}
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3 text-xs">
                            <div><div className="dc-overline">Found</div><div className="font-mono text-lg">{active.pages_found || 0}</div></div>
                            <div><div className="dc-overline">Crawled</div><div className="font-mono text-lg">{active.pages_crawled || 0}</div></div>
                            <div><div className="dc-overline">Skipped</div><div className="font-mono text-lg">{active.pages_skipped || 0}</div></div>
                            <div><div className="dc-overline">Failed</div><div className="font-mono text-lg">{active.pages_failed || 0}</div></div>
                        </div>
                        <div className="h-1 bg-secondary mt-3">
                            <div className="h-full bg-brand-primary transition-all" style={{ width: active.pages_found ? `${Math.min(100, Math.round(100 * active.pages_crawled / active.pages_found))}%` : "0%" }} />
                        </div>
                        {active.status === "failed" && active.error && (
                            <div className="mt-3 text-xs flex gap-2 items-start text-red-700" data-testid="crawl-error">
                                <Warning size={14} className="shrink-0 mt-0.5" />
                                <span className="break-all">{active.error}</span>
                            </div>
                        )}
                        {active.status === "cancelled" && (
                            <div className="mt-3 text-xs text-yellow-800 flex items-center gap-2" data-testid="crawl-cancelled-banner">
                                <Info size={14} /> This crawl was cancelled. Already-ingested pages remain in the KB.
                            </div>
                        )}
                        {active.status === "completed" && active.pages_found === 0 && (
                            <div className="mt-3 text-xs text-yellow-800 flex items-center gap-2" data-testid="crawl-zero-pages">
                                <Warning size={14} /> Crawl completed but no pages were found. Verify the URL, robots.txt, or selector configuration.
                            </div>
                        )}
                    </div>
                )}

                <div className="border border-border p-4 space-y-3">
                    <div className="dc-overline">Crawl Config</div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div><Label>Type</Label>
                            <Select value={cfg.type} onValueChange={v => setCfg({ ...cfg, type: v })}>
                                <SelectTrigger><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="recursive">Recursive</SelectItem>
                                    <SelectItem value="sitemap">Sitemap</SelectItem>
                                    <SelectItem value="single">Single Page</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="md:col-span-2"><Label>URL</Label>
                            <div className="flex gap-2">
                                <Input value={cfg.url} onChange={e => setCfg({ ...cfg, url: e.target.value })} placeholder="https://docs.example.com" />
                                <Button variant="outline" onClick={previewUrl} disabled={previewLoading || !cfg.url} data-testid="preview-url-btn">
                                    <Eye size={14} /> {previewLoading ? "…" : "Preview"}
                                </Button>
                            </div>
                        </div>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div><Label>Depth: <span className="font-mono">{cfg.depth}</span></Label>
                            <Slider min={1} max={10} value={[cfg.depth]} onValueChange={([v]) => setCfg({ ...cfg, depth: v })} /></div>
                        <div><Label>Max Pages</Label>
                            <Select value={String(cfg.max_pages)} onValueChange={v => setCfg({ ...cfg, max_pages: +v })}>
                                <SelectTrigger><SelectValue /></SelectTrigger>
                                <SelectContent>{[50, 200, 500, 2000].map(n => <SelectItem key={n} value={String(n)}>{n}</SelectItem>)}</SelectContent>
                            </Select>
                        </div>
                        <div><Label>Rate (req/sec): <span className="font-mono">{cfg.rate_limit_rps.toFixed(1)}</span></Label>
                            <Slider min={0.5} max={10} step={0.5} value={[cfg.rate_limit_rps]} onValueChange={([v]) => setCfg({ ...cfg, rate_limit_rps: v })} /></div>
                    </div>
                    <div className="flex flex-wrap gap-3 items-center">
                        <div className="flex items-center gap-2"><Switch checked={cfg.respect_robots} onCheckedChange={v => setCfg({ ...cfg, respect_robots: v })} /><span className="text-sm">Respect robots.txt</span></div>
                        {showPlaywright && (
                            <div className="flex items-center gap-2"><Switch checked={cfg.use_playwright} onCheckedChange={v => setCfg({ ...cfg, use_playwright: v })} /><span className="text-sm">Use Playwright (JS render)</span></div>
                        )}
                    </div>
                    <div className="flex justify-end">
                        <Button onClick={start} disabled={!!active && ["queued", "running"].includes(active.status)} data-testid="start-crawl"><Play size={14} /> Start Crawl</Button>
                    </div>
                </div>

                <div className="border border-border">
                    <div className="px-4 py-3 dc-overline border-b border-border">Crawl History</div>
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead className="bg-secondary/50 text-xs font-mono uppercase text-muted-foreground">
                                <tr><th className="text-left px-3 py-2">Started</th><th className="text-left px-3 py-2">Found</th><th className="text-left px-3 py-2">Crawled</th><th className="text-left px-3 py-2">Skipped</th><th className="text-left px-3 py-2">Failed</th><th className="text-left px-3 py-2">Status</th><th className="text-right px-3 py-2"></th></tr>
                            </thead>
                            <tbody>
                                {history.length === 0 && <tr><td colSpan={7} className="px-3 py-6 text-center text-muted-foreground">No history yet</td></tr>}
                                {history.map(j => {
                                    const hasFailed = (j.failed_urls || []).length > 0;
                                    const expanded = !!expandedFailed[j.id];
                                    return (
                                        <React.Fragment key={j.id}>
                                            <tr className="border-t border-border" data-testid={`crawl-row-${j.id}`}>
                                                <td className="px-3 py-2 text-xs">{new Date(j.queued_at).toLocaleString()}</td>
                                                <td className="px-3 py-2 font-mono">{j.pages_found || 0}</td>
                                                <td className="px-3 py-2 font-mono">{j.pages_crawled || 0}</td>
                                                <td className="px-3 py-2 font-mono">{j.pages_skipped || 0}</td>
                                                <td className="px-3 py-2 font-mono">
                                                    {hasFailed ? (
                                                        <button
                                                            className="flex items-center gap-1 text-red-600 hover:underline"
                                                            onClick={() => setExpandedFailed(s => ({ ...s, [j.id]: !s[j.id] }))}
                                                            data-testid={`failed-toggle-${j.id}`}
                                                        >
                                                            {expanded ? <CaretDown size={12} /> : <CaretRight size={12} />}
                                                            {j.pages_failed || 0}
                                                        </button>
                                                    ) : (j.pages_failed || 0)}
                                                </td>
                                                <td className="px-3 py-2"><Badge variant="outline" className={`text-[10px] font-mono ${STATUS_COLORS[j.status] || ""}`}>{j.status}</Badge></td>
                                                <td className="px-3 py-2 text-right">{j.status === "failed" && <Button size="sm" variant="ghost" onClick={() => retry(j)}><ArrowClockwise size={12} /></Button>}</td>
                                            </tr>
                                            {expanded && hasFailed && (
                                                <tr className="border-t border-border bg-red-50/30">
                                                    <td colSpan={7} className="px-4 py-3" data-testid={`failed-list-${j.id}`}>
                                                        <div className="dc-overline mb-1.5">Failed URLs ({(j.failed_urls || []).length})</div>
                                                        <ul className="space-y-1 max-h-48 overflow-auto">
                                                            {(j.failed_urls || []).map((fu, idx) => (
                                                                <li key={idx} className="text-xs font-mono flex flex-wrap gap-2">
                                                                    <span className="truncate text-foreground max-w-[55%]">{fu.url}</span>
                                                                    <span className="text-red-700">{fu.reason}</span>
                                                                </li>
                                                            ))}
                                                        </ul>
                                                    </td>
                                                </tr>
                                            )}
                                        </React.Fragment>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div className="border border-border p-4 space-y-3">
                    <div className="dc-overline">Sync Schedule</div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div><Label>Cron Expression</Label><Input value={cronForm.cron_expr} onChange={e => setCronForm({ ...cronForm, cron_expr: e.target.value })} placeholder="0 3 * * *" /></div>
                        <div className="flex items-end gap-2"><Switch checked={cronForm.enabled} onCheckedChange={v => setCronForm({ ...cronForm, enabled: v })} /><span className="text-sm">Enabled</span></div>
                    </div>
                    <div className="flex justify-end gap-2">
                        <Button variant="outline" onClick={delSchedule}><Trash size={13} /> Delete Schedule</Button>
                        <Button onClick={saveSchedule}><FloppyDisk size={13} /> Save Schedule</Button>
                    </div>
                </div>
            </div>

            <Dialog open={!!preview} onOpenChange={(o) => !o && setPreview(null)}>
                <DialogContent className="w-[calc(100vw-1.5rem)] max-w-2xl" data-testid="preview-modal">
                    <DialogHeader>
                        <DialogTitle className="font-heading text-xl">Preview: {preview?.title}</DialogTitle>
                        <DialogDescription className="font-mono text-xs break-all">{preview?.url}</DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3 mt-1">
                        <div className="flex flex-wrap gap-2">
                            <Badge variant="outline" className="text-[10px] font-mono">HTTP {preview?.status_code}</Badge>
                            <Badge variant="outline" className="text-[10px] font-mono">{preview?.word_count ?? 0} words</Badge>
                        </div>
                        <div className="border border-border p-3 max-h-[50vh] overflow-auto">
                            <pre className="text-xs whitespace-pre-wrap font-mono">{preview?.content_preview}</pre>
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setPreview(null)}>Close</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
