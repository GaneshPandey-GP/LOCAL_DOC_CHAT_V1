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
    const [testResult, setTestResult] = useState(null);
    const [form, setForm] = useState({ name: "", description: "", endpoint_type: "http", endpoint_url: "", timeout_ms: 30000, input_schema: "{}" });

    const load = async () => {
        const r = await api.get("/v2/mcp/tools");
        setTools(r.data);
    };
    useEffect(() => { load(); }, []);

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

    const runTest = async () => {
        let input = {};
        try { input = JSON.parse(testInput || "{}"); }
        catch { toast.error("Invalid JSON"); return; }
        try {
            const r = await api.post(`/v2/mcp/tools/${testFor.id}/test`, input);
            setTestResult(r.data);
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
                                        <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => { setTestFor(t); setTestInput("{}"); setTestResult(null); }} data-testid={`test-tool-${t.id}`}>
                                            <Play size={12} /> Test
                                        </Button>
                                        <Badge variant="outline" className="text-[10px] font-mono">{t.endpoint_type}</Badge>
                                    </div>
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
                                            <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => { setTestFor(t); setTestInput("{}"); setTestResult(null); }}>
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
                        <div><Label>Input (JSON)</Label><Textarea rows={6} className="font-mono text-xs" value={testInput} onChange={e => setTestInput(e.target.value)} /></div>
                        <Button onClick={runTest}><Play size={13} /> Send</Button>
                        {testResult && (
                            <div className={`border p-3 ${testResult.ok ? "border-green-300 bg-green-50" : "border-red-300 bg-red-50"}`}>
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
