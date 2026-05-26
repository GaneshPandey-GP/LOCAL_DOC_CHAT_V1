import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Wrench, Plus, Trash, Play, Globe, CodeBlock, GithubLogo, Database, Plug as Webhooks } from "@phosphor-icons/react";
import { toast } from "sonner";

const ICONS = {
    "builtin-web-search": Globe,
    "builtin-http-request": CodeBlock,
    "builtin-github": GithubLogo,
    "builtin-sql-query": Database,
    "builtin-webhook": Webhooks,
};

export default function MCPTools() {
    const [tools, setTools] = useState([]);
    const [open, setOpen] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [testFor, setTestFor] = useState(null);
    const [testInput, setTestInput] = useState("{}");
    const [testFields, setTestFields] = useState({}); // structured form for builtins
    const [testResult, setTestResult] = useState(null);
    const [form, setForm] = useState({ name: "", description: "", endpoint_type: "http", endpoint_url: "", timeout_ms: 30000, input_schema: "{}" });
    const [executions, setExecutions] = useState({}); // toolId -> [last 5 executions]

    const load = async () => {
        const r = await api.get("/v2/mcp/tools");
        setTools(r.data);
    };
    useEffect(() => { load(); }, []);

    const loadExecutions = async (toolId) => {
        try {
            const r = await api.get(`/v2/mcp/tools/${toolId}/executions`, { params: { limit: 5 } });
            setExecutions(s => ({ ...s, [toolId]: r.data || [] }));
        } catch { /* ignore — only editors see this */ }
    };

    const submit = async () => {
        try {
            let schema = {};
            if (form.input_schema && form.input_schema.trim()) {
                try { schema = JSON.parse(form.input_schema); }
                catch { toast.error("Invalid JSON in input schema"); return; }
            }
            setSubmitting(true);
            await api.post("/v2/mcp/tools", { ...form, input_schema: schema });
            toast.success("Tool registered");
            setOpen(false);
            setForm({ name: "", description: "", endpoint_type: "http", endpoint_url: "", timeout_ms: 30000, input_schema: "{}" });
            load();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Register failed");
        } finally { setSubmitting(false); }
    };

    const del = async (id) => {
        if (!window.confirm("Delete this tool?")) return;
        try { await api.delete(`/v2/mcp/tools/${id}`); toast.success("Deleted"); load(); }
        catch (e) { toast.error(e?.response?.data?.detail || "Delete failed"); }
    };

    const toggleEnabled = async (tool) => {
        try {
            await api.patch(`/v2/mcp/tools/${tool.id}`, { enabled: !tool.enabled });
            load();
        } catch (e) { toast.error("Update failed"); }
    };

    const openTest = (tool) => {
        setTestFor(tool);
        setTestResult(null);
        // Seed structured fields for builtins from input_schema.properties
        const props = (tool.input_schema && tool.input_schema.properties) || {};
        const seed = {};
        Object.keys(props).forEach(k => { seed[k] = ""; });
        setTestFields(seed);
        setTestInput("{}");
    };

    const runTest = async () => {
        let input;
        // Builtin tools with structured fields → build payload from form
        if (testFor?.is_builtin && testFor?.input_schema?.properties && Object.keys(testFor.input_schema.properties).length) {
            input = {};
            Object.entries(testFields).forEach(([k, v]) => {
                if (v === "" || v === null || v === undefined) return;
                const schemaType = testFor.input_schema.properties[k]?.type;
                if (schemaType === "object" || schemaType === "array") {
                    try { input[k] = JSON.parse(v); } catch { input[k] = v; }
                } else if (schemaType === "number" || schemaType === "integer") {
                    const n = Number(v);
                    input[k] = Number.isFinite(n) ? n : v;
                } else if (schemaType === "boolean") {
                    input[k] = v === "true" || v === true;
                } else {
                    input[k] = v;
                }
            });
        } else {
            try { input = JSON.parse(testInput || "{}"); }
            catch { toast.error("Invalid JSON"); return; }
        }
        try {
            const r = await api.post(`/v2/mcp/tools/${testFor.id}/test`, input);
            setTestResult(r.data);
            loadExecutions(testFor.id);
        } catch (e) {
            setTestResult({ ok: false, error: e?.response?.data?.detail || String(e) });
        }
    };

    const builtins = tools.filter(t => t.is_builtin);
    const customs = tools.filter(t => !t.is_builtin);

    return (
        <div>
            <header className="h-auto md:h-16 border-b border-border px-4 md:px-8 py-3 md:py-0 flex flex-col md:flex-row md:items-center justify-between gap-3 sticky top-0 bg-background z-10">
                <div className="flex items-center gap-3">
                    <Wrench size={22} weight="duotone" className="text-brand-primary" />
                    <div><div className="dc-overline">AI Studio</div><h1 className="font-heading font-bold text-lg">MCP Tools</h1></div>
                </div>
                <Button onClick={() => setOpen(true)} data-testid="register-tool" className="min-h-[44px] md:min-h-0">
                    <Plus size={16} /> Register Tool
                </Button>
            </header>

            <div className="p-4 md:p-8 max-w-6xl space-y-8">
                <section>
                    <div className="dc-overline mb-3">Built-in Tools</div>
                    {builtins.length === 0 && (
                        <div className="border border-yellow-300 bg-yellow-50/60 p-3 text-xs text-yellow-900 mb-3" data-testid="builtins-missing">
                            Built-in tools are not seeded yet. Check backend startup logs (`docker compose logs backend`).
                        </div>
                    )}
                    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                        {builtins.map(t => {
                            const I = ICONS[t.id] || Wrench;
                            return (
                                <div key={t.id} className="border border-border p-4" data-testid={`tool-${t.id}`}>
                                    <div className="flex items-start gap-3">
                                        <I size={22} weight="duotone" className="text-brand-primary shrink-0" />
                                        <div className="min-w-0 flex-1">
                                            <div className="font-medium">{t.name}</div>
                                            <div className="text-xs text-muted-foreground line-clamp-2 mt-0.5">{t.description}</div>
                                        </div>
                                    </div>
                                    <div className="mt-3 flex gap-2">
                                        <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => openTest(t)} data-testid={`test-tool-${t.id}`}>
                                            <Play size={12} /> Test
                                        </Button>
                                        <Button size="sm" variant="ghost" className="h-8 text-xs" onClick={() => loadExecutions(t.id)} data-testid={`history-tool-${t.id}`}>History</Button>
                                        <Badge variant="outline" className="text-[10px] font-mono">{t.endpoint_type}</Badge>
                                    </div>
                                    {executions[t.id] && (
                                        <div className="mt-3 border-t border-border pt-2 space-y-1" data-testid={`exec-list-${t.id}`}>
                                            <div className="dc-overline">Recent executions</div>
                                            {executions[t.id].length === 0 && <div className="text-[11px] text-muted-foreground">No runs yet.</div>}
                                            {executions[t.id].map(ex => (
                                                <div key={ex.id} className="flex items-center justify-between text-[11px] font-mono">
                                                    <Badge variant="outline" className={`text-[9px] uppercase ${ex.status === "completed" ? "border-green-500 text-green-700" : ex.status === "failed" ? "border-red-500 text-red-700" : ""}`}>{ex.status}</Badge>
                                                    <span>{ex.elapsed_ms || 0}ms</span>
                                                    <span className="text-muted-foreground">{ex.created_at ? new Date(ex.created_at).toLocaleTimeString() : ""}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </section>

                <section>
                    <div className="dc-overline mb-3">Custom Tools</div>
                    {customs.length === 0 ? (
                        <div className="border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
                            No custom tools yet. Register an HTTP endpoint to invoke from any workflow or MCP-aware agent.
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                            {customs.map(t => (
                                <div key={t.id} className="border border-border p-4">
                                    <div className="flex items-start justify-between gap-2">
                                        <div className="min-w-0 flex-1">
                                            <div className="font-medium truncate">{t.name}</div>
                                            <div className="text-[10px] font-mono text-muted-foreground truncate">{t.endpoint_url}</div>
                                            <div className="text-xs text-muted-foreground line-clamp-2 mt-1">{t.description}</div>
                                        </div>
                                        <button onClick={() => del(t.id)} className="text-muted-foreground hover:text-red-500"><Trash size={14} /></button>
                                    </div>
                                    <div className="flex items-center justify-between mt-3 flex-wrap gap-2">
                                        <Badge variant="outline" className="text-[10px] font-mono">{t.call_count || 0} calls</Badge>
                                        <div className="flex items-center gap-2">
                                            <Switch checked={!!t.enabled} onCheckedChange={() => toggleEnabled(t)} />
                                            <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => openTest(t)}>
                                                <Play size={12} /> Test
                                            </Button>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </section>
            </div>

            {/* Register modal */}
            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="w-[calc(100vw-1.5rem)] max-w-lg">
                    <DialogHeader><DialogTitle>Register Tool</DialogTitle><DialogDescription>Add a custom HTTP MCP tool that workflows and agents can call.</DialogDescription></DialogHeader>
                    <div className="space-y-3 mt-2">
                        <div><Label>Name</Label><Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} /></div>
                        <div><Label>Description</Label><Textarea rows={2} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} /></div>
                        <div className="grid grid-cols-2 gap-3">
                            <div><Label>Endpoint Type</Label>
                                <Select value={form.endpoint_type} onValueChange={v => setForm({ ...form, endpoint_type: v })}>
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="http">HTTP</SelectItem>
                                        <SelectItem value="builtin">Builtin</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <div><Label>Timeout (ms)</Label><Input type="number" value={form.timeout_ms} onChange={e => setForm({ ...form, timeout_ms: +e.target.value })} /></div>
                        </div>
                        {form.endpoint_type === "http" && <div><Label>Endpoint URL</Label><Input value={form.endpoint_url} onChange={e => setForm({ ...form, endpoint_url: e.target.value })} placeholder="https://api.example.com/tool" /></div>}
                        <div><Label>Input JSON Schema</Label><Textarea rows={5} className="font-mono text-xs" value={form.input_schema} onChange={e => setForm({ ...form, input_schema: e.target.value })} /></div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
                        <Button onClick={submit} disabled={submitting || !form.name.trim()}>{submitting ? "Registering…" : "Register"}</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Test panel */}
            <Dialog open={!!testFor} onOpenChange={o => !o && setTestFor(null)}>
                <DialogContent className="w-[calc(100vw-1.5rem)] max-w-2xl">
                    <DialogHeader><DialogTitle>Test: {testFor?.name}</DialogTitle><DialogDescription className="font-mono text-xs">{testFor?.id}</DialogDescription></DialogHeader>
                    <div className="space-y-3 mt-2">
                        {testFor?.is_builtin && testFor?.input_schema?.properties && Object.keys(testFor.input_schema.properties).length > 0 ? (
                            <div className="space-y-2" data-testid="structured-inputs">
                                {Object.entries(testFor.input_schema.properties).map(([key, spec]) => {
                                    const required = (testFor.input_schema.required || []).includes(key);
                                    const desc = spec.description || "";
                                    return (
                                        <div key={key}>
                                            <Label className="flex items-center gap-2">
                                                <span className="font-mono">{key}</span>
                                                <span className="text-[10px] font-mono text-muted-foreground">{spec.type}{required ? " · required" : ""}</span>
                                            </Label>
                                            {spec.enum ? (
                                                <Select value={String(testFields[key] ?? "")} onValueChange={v => setTestFields(s => ({ ...s, [key]: v }))}>
                                                    <SelectTrigger><SelectValue placeholder="Choose…" /></SelectTrigger>
                                                    <SelectContent>
                                                        {spec.enum.map(o => <SelectItem key={o} value={String(o)}>{String(o)}</SelectItem>)}
                                                    </SelectContent>
                                                </Select>
                                            ) : spec.type === "boolean" ? (
                                                <Select value={String(testFields[key] ?? "false")} onValueChange={v => setTestFields(s => ({ ...s, [key]: v === "true" }))}>
                                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                                    <SelectContent>
                                                        <SelectItem value="true">true</SelectItem>
                                                        <SelectItem value="false">false</SelectItem>
                                                    </SelectContent>
                                                </Select>
                                            ) : (spec.type === "object" || spec.type === "array") ? (
                                                <Textarea rows={3} className="font-mono text-xs" placeholder={spec.type === "array" ? "[]" : "{}"} value={String(testFields[key] ?? "")} onChange={e => setTestFields(s => ({ ...s, [key]: e.target.value }))} />
                                            ) : (
                                                <Input value={String(testFields[key] ?? "")} onChange={e => setTestFields(s => ({ ...s, [key]: e.target.value }))} placeholder={desc} data-testid={`field-${key}`} />
                                            )}
                                            {desc && <div className="text-[10px] text-muted-foreground mt-0.5">{desc}</div>}
                                        </div>
                                    );
                                })}
                            </div>
                        ) : (
                            <div><Label>Input (JSON)</Label><Textarea rows={6} className="font-mono text-xs" value={testInput} onChange={e => setTestInput(e.target.value)} /></div>
                        )}
                        <Button onClick={runTest} data-testid="send-test"><Play size={13} /> Send</Button>
                        {testResult && (
                            <div className={`border p-3 ${testResult.ok ? "border-green-300 bg-green-50" : "border-red-300 bg-red-50"}`} data-testid="test-result">
                                <div className="text-xs font-mono uppercase mb-1">{testResult.ok ? "ok" : "error"}</div>
                                <pre className="text-xs font-mono whitespace-pre-wrap break-words max-h-72 overflow-auto">{JSON.stringify(testResult.ok ? testResult.result : testResult.error, null, 2)}</pre>
                            </div>
                        )}
                    </div>
                    <DialogFooter><Button variant="outline" onClick={() => setTestFor(null)}>Close</Button></DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
