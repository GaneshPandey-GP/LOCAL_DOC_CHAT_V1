import React, { useEffect, useState } from "react";
import api, { API_BASE } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
    Database,
    Play,
    FileXls,
    Lightning,
    ShieldCheck,
    Spinner,
    DownloadSimple,
    Warning,
    ClockCounterClockwise,
} from "@phosphor-icons/react";
import { toast } from "sonner";

function RowsTable({ result }) {
    if (!result || !result.rows?.length) {
        return (
            <div className="border border-dashed border-border p-8 text-sm text-center text-muted-foreground">
                No rows.
            </div>
        );
    }
    return (
        <div className="border border-border overflow-x-auto">
            <table className="w-full text-sm" data-testid="db-agent-result-table">
                <thead className="bg-secondary/50">
                    <tr>
                        {result.columns.map((c) => (
                            <th key={c} className="text-left px-3 py-2 font-mono text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border">
                                {c}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {result.rows.slice(0, 200).map((row, i) => (
                        <tr key={i} className="border-b border-border last:border-b-0 hover:bg-secondary/30">
                            {result.columns.map((c) => (
                                <td key={c} className="px-3 py-2 align-top font-mono text-xs">
                                    {row[c] === null || row[c] === undefined ? <span className="text-muted-foreground">—</span> : String(row[c])}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
            {result.rows.length > 200 && (
                <div className="px-3 py-2 text-[11px] text-muted-foreground border-t border-border">
                    Showing first 200 rows of {result.row_count}. Use Export to Excel for the full dataset.
                </div>
            )}
        </div>
    );
}

export default function DBAgent() {
    const { user } = useAuth();
    const [status, setStatus] = useState(null);
    const [query, setQuery] = useState("");
    const [busy, setBusy] = useState(false);
    const [response, setResponse] = useState(null);
    const [history, setHistory] = useState([]);

    useEffect(() => {
        api.get("/v2/db-agent/status").then((r) => setStatus(r.data)).catch(() => setStatus({ enabled: false }));
        api.get("/v2/reports/history").then((r) => setHistory(r.data)).catch(() => {});
    }, []);

    const run = async (mode) => {
        if (!query.trim()) { toast.error("Enter a question first"); return; }
        setBusy(true);
        setResponse(null);
        try {
            const url = mode === "explain" ? "/v2/db-agent/explain" : "/v2/db-agent/query";
            const r = await api.post(url, { query, execute: mode !== "explain" });
            setResponse(r.data);
            if (r.data?.blocked) toast.error("Blocked by safety guard");
            else if (r.data?.error) toast.error(r.data.error);
            else toast.success(mode === "explain" ? "Plan generated" : "Query executed");
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Request failed");
        } finally {
            setBusy(false);
        }
    };

    const exportExcel = async () => {
        if (!query.trim()) { toast.error("Enter a question first"); return; }
        setBusy(true);
        try {
            const r = await api.post("/v2/db-agent/report", { query });
            if (r.data?.blocked || r.data?.error) {
                toast.error(r.data.error || "Blocked");
                return;
            }
            toast.success("Report generated");
            // Refresh history then trigger download
            const id = r.data?.report?.id;
            if (id) downloadReport(id);
            const hist = await api.get("/v2/reports/history");
            setHistory(hist.data);
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Report failed");
        } finally {
            setBusy(false);
        }
    };

    const downloadReport = async (id) => {
        try {
            const token = localStorage.getItem("dc_access_token");
            const res = await fetch(`${API_BASE}/v2/reports/${id}/download`, {
                headers: token ? { Authorization: `Bearer ${token}` } : {},
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `docchat-report-${id}.xlsx`;
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 60_000);
        } catch (e) {
            toast.error("Download failed");
        }
    };

    const disabled = !status?.enabled;

    return (
        <div>
            <header className="h-auto md:h-16 border-b border-border px-4 md:px-8 py-3 md:py-0 flex flex-col md:flex-row md:items-center justify-between gap-3 sticky top-0 bg-background z-10">
                <div className="flex items-center gap-3">
                    <Database size={22} weight="duotone" className="text-brand-primary" />
                    <div>
                        <div className="dc-overline">Analytics</div>
                        <h1 className="font-heading font-bold text-lg">DB Agent</h1>
                    </div>
                </div>
                <div className="flex items-center gap-2 text-xs">
                    {status?.enabled ? (
                        <Badge className="font-mono uppercase" variant="outline" data-testid="db-agent-status">
                            <ShieldCheck size={12} /> Enabled
                        </Badge>
                    ) : (
                        <Badge className="font-mono uppercase" variant="outline" data-testid="db-agent-status">
                            <Warning size={12} /> Disabled
                        </Badge>
                    )}
                </div>
            </header>

            <div className="p-4 md:p-8 max-w-6xl space-y-6">
                {disabled && (
                    <div className="border border-amber-300 bg-amber-50 p-4 text-sm" data-testid="db-agent-disabled-banner">
                        <div className="font-semibold mb-1">DB Agent is disabled</div>
                        <div className="text-muted-foreground">
                            Ask an admin to enable it in <span className="font-mono">Settings → DB Agent</span> and provide PostgreSQL credentials.
                        </div>
                    </div>
                )}

                {/* Stream 7 — query input + results stack vertically on md */}
                <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6">
                    <div className="space-y-4">
                        <div>
                            <label className="dc-overline" htmlFor="db-agent-input">Natural-language question</label>
                            <Textarea
                                id="db-agent-input"
                                placeholder="e.g. Top 5 customers by revenue in the last 30 days, grouped by region"
                                rows={4}
                                className="mt-1 font-mono text-sm"
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                disabled={busy || disabled}
                                data-testid="db-agent-input"
                            />
                        </div>
                        <div className="flex flex-wrap gap-2">
                            <Button onClick={() => run("query")} disabled={busy || disabled} data-testid="db-agent-run-button">
                                {busy ? <Spinner size={14} className="animate-spin" /> : <Play size={14} />} Run query
                            </Button>
                            <Button variant="outline" onClick={() => run("explain")} disabled={busy || disabled} data-testid="db-agent-explain-button">
                                <Lightning size={14} /> Explain only
                            </Button>
                            <Button variant="outline" onClick={exportExcel} disabled={busy || disabled} data-testid="db-agent-export-button">
                                <FileXls size={14} /> Export to Excel
                            </Button>
                        </div>

                        {response?.blocked && (
                            <div className="border border-red-300 bg-red-50 p-4 text-sm">
                                <div className="font-semibold mb-2">Blocked by guard</div>
                                <ul className="list-disc list-inside text-muted-foreground space-y-0.5">
                                    {response.reasons?.map((r, i) => <li key={i}>{r}</li>)}
                                </ul>
                                {response.sql && (
                                    <pre className="mt-3 text-xs font-mono bg-white border border-border p-2 overflow-x-auto whitespace-pre-wrap">{response.sql}</pre>
                                )}
                            </div>
                        )}

                        {response?.error && (
                            <div className="border border-red-300 bg-red-50 p-4 text-sm">
                                <div className="font-semibold">{response.error}</div>
                                {response.detail && <div className="text-muted-foreground mt-1">{response.detail}</div>}
                                {response.sql && (
                                    <pre className="mt-3 text-xs font-mono bg-white border border-border p-2 overflow-x-auto whitespace-pre-wrap">{response.sql}</pre>
                                )}
                            </div>
                        )}

                        {response?.sql && !response?.blocked && !response?.error && (
                            <div className="space-y-3">
                                <div>
                                    <div className="dc-overline mb-1">Generated SQL</div>
                                    <pre
                                        className="text-xs font-mono bg-secondary/40 border border-border p-3 overflow-x-auto whitespace-pre-wrap"
                                        data-testid="db-agent-sql"
                                    >
                                        {response.sql}
                                    </pre>
                                </div>
                                {response.explanation && (
                                    <div className="text-sm text-muted-foreground">{response.explanation}</div>
                                )}
                                {response.plan && (
                                    <div>
                                        <div className="dc-overline mb-1">EXPLAIN plan</div>
                                        <pre className="text-xs font-mono bg-secondary/40 border border-border p-3 overflow-x-auto whitespace-pre-wrap">
                                            {response.plan.join("\n")}
                                        </pre>
                                    </div>
                                )}
                                {response.result && (
                                    <div>
                                        <div className="flex items-center justify-between mb-1">
                                            <div className="dc-overline">
                                                Results ({response.result.row_count} row{response.result.row_count === 1 ? "" : "s"} ·
                                                {" "}{response.result.elapsed_ms} ms{response.result.truncated ? " · truncated" : ""})
                                            </div>
                                        </div>
                                        <RowsTable result={response.result} />
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* History panel */}
                    <aside className="border border-border bg-background">
                        <div className="px-4 py-3 border-b border-border flex items-center gap-2">
                            <ClockCounterClockwise size={14} />
                            <div className="dc-overline">Report history</div>
                        </div>
                        {history.length === 0 ? (
                            <div className="p-4 text-xs text-muted-foreground">No reports yet.</div>
                        ) : (
                            <div className="divide-y divide-border max-h-[420px] overflow-y-auto">
                                {history.map((h) => (
                                    <div key={h.id} className="px-4 py-3 text-xs hover:bg-secondary/30" data-testid={`report-row-${h.id}`}>
                                        <div className="font-medium truncate" title={h.query}>{h.query}</div>
                                        <div className="text-muted-foreground mt-0.5 flex items-center justify-between">
                                            <span>{new Date(h.created_at).toLocaleString()}</span>
                                            <button
                                                className="text-brand-primary hover:underline flex items-center gap-1"
                                                onClick={() => downloadReport(h.id)}
                                            >
                                                <DownloadSimple size={12} /> .xlsx
                                            </button>
                                        </div>
                                        <div className="text-[10px] text-muted-foreground mt-0.5">
                                            {h.row_count} rows · {h.elapsed_ms} ms
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </aside>
                </div>
            </div>
        </div>
    );
}
