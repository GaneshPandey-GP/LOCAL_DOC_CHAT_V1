import React, { useCallback, useEffect, useRef, useState } from "react";
import api, { BACKEND_URL } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import {
    Plus,
    ArrowLeft,
    Copy,
    Check,
    Code,
    Eye,
    ToggleLeft,
    ToggleRight,
    Trash,
    ChartBar,
    Globe,
    Lightning,
    ShieldCheck,
    ChatDots,
    PaintBucket,
    Sliders,
    Link,
    WarningCircle,
} from "@phosphor-icons/react";

// ─── Default widget config ───────────────────────────────────────────────────
const DEFAULT_CFG = {
    title: "Ask our Knowledge Base",
    subtitle: "Ask me anything about our docs…",
    brand_color: "#2563EB",
    logo_url: "",
    position: "bottom-right",
    launcher_style: "icon",
    dark_mode: false,
    welcome_message: "Hi! How can I help you today?",
    fallback_message: "I don't have enough information in the provided documents to answer that.",
    max_questions_per_session: 0,
    show_citations: true,
    show_confidence: true,
    allow_copy: true,
    email_collection: "off",
};

// ─── Copy-to-clipboard button ─────────────────────────────────────────────────
function CopyBtn({ text, className = "" }) {
    const [done, setDone] = useState(false);
    const copy = () => {
        navigator.clipboard.writeText(text);
        setDone(true);
        toast.success("Copied to clipboard");
        setTimeout(() => setDone(false), 2000);
    };
    return (
        <Button size="sm" variant="outline" onClick={copy} className={className}>
            {done ? <Check size={14} /> : <Copy size={14} />}
            <span className="ml-1">{done ? "Copied" : "Copy"}</span>
        </Button>
    );
}

// ─── Live Widget Preview ──────────────────────────────────────────────────────
function WidgetPreview({ cfg }) {
    const isDark = cfg.dark_mode;
    const bg = isDark ? "#18181b" : "#ffffff";
    const textC = isDark ? "#fafafa" : "#18181b";
    const surface = isDark ? "#27272a" : "#f4f4f5";
    const borderC = isDark ? "#3f3f46" : "#e4e4e7";
    const muted = isDark ? "#a1a1aa" : "#71717a";
    const bc = cfg.brand_color || "#2563EB";

    return (
        <div className="flex flex-col items-center gap-4">
            <div className="text-xs font-mono text-muted-foreground uppercase tracking-wider">Live Preview</div>

            {/* Phone frame with widget panel open */}
            <div
                className="relative flex flex-col overflow-hidden"
                style={{
                    width: 300,
                    height: 480,
                    borderRadius: 16,
                    border: `1px solid ${borderC}`,
                    background: bg,
                    boxShadow: "0 8px 32px rgba(0,0,0,.14)",
                }}
            >
                {/* Widget header */}
                <div style={{ background: bc, color: "#fff", padding: "12px 14px", flexShrink: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>{cfg.title || "Ask our Knowledge Base"}</div>
                    <div style={{ fontSize: 11, opacity: 0.85 }}>{cfg.subtitle || "Ask me anything…"}</div>
                </div>

                {/* Messages area */}
                <div style={{ flex: 1, padding: "12px 12px 8px", overflowY: "auto", display: "flex", flexDirection: "column", gap: 8 }}>
                    {/* Welcome message bubble */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 3, maxWidth: "88%", alignSelf: "flex-start" }}>
                        <div style={{
                            padding: "8px 12px", borderRadius: "12px 12px 12px 3px",
                            background: surface, color: textC, fontSize: 12, lineHeight: 1.5,
                        }}>
                            {cfg.welcome_message || "Hi! How can I help you today?"}
                        </div>
                        {cfg.show_confidence && (
                            <span style={{
                                fontSize: 9, padding: "1px 5px", borderRadius: 99, fontWeight: 700,
                                background: "#dcfce7", color: "#166534", display: "inline-block", alignSelf: "flex-start",
                            }}>HIGH</span>
                        )}
                    </div>

                    {/* Mock user question */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 3, maxWidth: "88%", alignSelf: "flex-end" }}>
                        <div style={{
                            padding: "8px 12px", borderRadius: "12px 12px 3px 12px",
                            background: bc, color: "#fff", fontSize: 12, lineHeight: 1.5,
                        }}>
                            What topics are covered?
                        </div>
                    </div>

                    {/* Mock answer with citation */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 3, maxWidth: "88%", alignSelf: "flex-start" }}>
                        <div style={{
                            padding: "8px 12px", borderRadius: "12px 12px 12px 3px",
                            background: surface, color: textC, fontSize: 12, lineHeight: 1.5,
                        }}>
                            The documents cover several key topics including <strong>setup</strong>, <strong>configuration</strong>, and <strong>best practices</strong>. [1]
                        </div>
                        {cfg.show_citations && (
                            <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                                <span style={{
                                    fontSize: 9, padding: "2px 5px", borderRadius: 3,
                                    background: surface, border: `1px solid ${borderC}`, color: muted,
                                }}>[1] document.pdf</span>
                            </div>
                        )}
                    </div>
                </div>

                {/* Input area */}
                <div style={{ padding: "8px 10px", borderTop: `1px solid ${borderC}`, flexShrink: 0, background: bg }}>
                    <div style={{ display: "flex", gap: 6, alignItems: "flex-end" }}>
                        <div style={{
                            flex: 1, padding: "7px 10px", border: `1px solid ${borderC}`, borderRadius: 8,
                            fontSize: 11, color: muted, background: bg,
                        }}>
                            Type your question…
                        </div>
                        <div style={{
                            background: bc, color: "#fff", borderRadius: 8,
                            width: 32, height: 32, display: "flex", alignItems: "center", justifyContent: "center",
                        }}>
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                                <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
                            </svg>
                        </div>
                    </div>
                </div>
            </div>

            {/* Launcher button preview */}
            <div className="flex items-center gap-3">
                <div
                    style={{
                        background: bc, color: "#fff", borderRadius: cfg.launcher_style === "icon-label" ? 28 : "50%",
                        width: cfg.launcher_style === "icon-label" ? "auto" : 44,
                        height: 44, display: "flex", alignItems: "center", justifyContent: "center",
                        padding: cfg.launcher_style === "icon-label" ? "0 16px 0 12px" : undefined,
                        gap: 8, boxShadow: "0 4px 12px rgba(0,0,0,.2)", cursor: "pointer",
                    }}
                >
                    <ChatDots size={20} weight="fill" />
                    {cfg.launcher_style === "icon-label" && (
                        <span style={{ fontSize: 13, fontWeight: 600, whiteSpace: "nowrap" }}>{cfg.title || "Chat"}</span>
                    )}
                </div>
                <span className="text-xs text-muted-foreground">Launcher button</span>
            </div>
        </div>
    );
}

// ─── Analytics dialog ─────────────────────────────────────────────────────────
function AnalyticsDialog({ widget, open, onClose }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!open || !widget) return;
        setLoading(true);
        api.get(`/v2/widgets/${widget.widget_id}/analytics`)
            .then((r) => setData(r.data))
            .catch(() => toast.error("Failed to load analytics"))
            .finally(() => setLoading(false));
    }, [open, widget]);

    return (
        <Dialog open={open} onOpenChange={onClose}>
            <DialogContent className="max-w-xl">
                <DialogHeader>
                    <DialogTitle className="font-heading text-xl">Widget Analytics</DialogTitle>
                    <DialogDescription className="font-mono text-xs">{widget?.name}</DialogDescription>
                </DialogHeader>

                {loading && <div className="py-8 text-center text-sm text-muted-foreground">Loading…</div>}

                {!loading && data && (
                    <div className="space-y-5">
                        {/* Stat cards */}
                        <div className="grid grid-cols-2 gap-3">
                            {[
                                { label: "Total Sessions", val: data.total_sessions },
                                { label: "Unique Visitors", val: data.unique_visitors },
                                { label: "Total Queries", val: data.total_queries },
                                { label: "Avg Queries/Session", val: data.avg_queries_per_session },
                                { label: "Rate Limit Hits", val: data.rate_limit_hits },
                                { label: "Domain Blocks", val: data.domain_blocks },
                            ].map(({ label, val }) => (
                                <div key={label} className="border border-border p-3">
                                    <div className="text-xs font-mono text-muted-foreground uppercase">{label}</div>
                                    <div className="text-2xl font-heading font-bold mt-1">{val}</div>
                                </div>
                            ))}
                        </div>

                        {/* Top questions */}
                        {data.top_questions?.length > 0 && (
                            <div>
                                <div className="dc-overline mb-2">Top Questions</div>
                                <div className="border border-border divide-y divide-border">
                                    {data.top_questions.slice(0, 5).map((q, i) => (
                                        <div key={i} className="px-3 py-2 flex justify-between items-center gap-4">
                                            <span className="text-sm truncate flex-1">{q.query}</span>
                                            <Badge variant="secondary" className="font-mono text-xs shrink-0">{q.count}×</Badge>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Domain breakdown */}
                        {data.domain_breakdown?.length > 0 && (
                            <div>
                                <div className="dc-overline mb-2">Traffic by Domain</div>
                                <div className="border border-border divide-y divide-border">
                                    {data.domain_breakdown.slice(0, 5).map((d, i) => (
                                        <div key={i} className="px-3 py-2 flex justify-between items-center">
                                            <span className="font-mono text-sm">{d.domain}</span>
                                            <Badge variant="secondary" className="font-mono text-xs">{d.count}</Badge>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {data.total_sessions === 0 && (
                            <div className="text-center py-4 text-sm text-muted-foreground">
                                No traffic yet. Embed the widget on your site to start collecting data.
                            </div>
                        )}
                    </div>
                )}

                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Close</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

// ─── Install snippets ─────────────────────────────────────────────────────────
function InstallTab({ widgetId, cfg }) {
    const baseUrl = BACKEND_URL || window.location.origin;

    const scriptSnippet =
        `<script>\n  window.DochatConfig = { widgetId: "${widgetId}" };\n</script>\n<script src="${baseUrl}/api/widget/loader.js" async></script>`;

    const iframeSnippet =
        `<iframe\n  src="${baseUrl}/api/widget/${widgetId}/iframe"\n  width="400"\n  height="600"\n  frameborder="0"\n  allow="clipboard-write"\n></iframe>`;

    const npmSnippet =
        `// npm install @docchat/chat-widget\nimport { DochatWidget } from '@docchat/chat-widget';\n\n<DochatWidget widgetId="${widgetId}" />`;

    return (
        <div className="space-y-5">
            <div className="border border-border bg-secondary/30 px-4 py-3 flex items-start gap-3 text-sm">
                <ShieldCheck size={18} weight="duotone" className="text-brand-primary shrink-0 mt-0.5" />
                <div>
                    <div className="font-medium">Secure &amp; isolated</div>
                    <div className="text-xs text-muted-foreground mt-0.5">
                        All queries are strictly scoped to your selected documents. Domain whitelist is enforced server-side.
                    </div>
                </div>
            </div>

            {/* Option 1 */}
            <div>
                <div className="flex items-center justify-between mb-2">
                    <div>
                        <div className="font-medium text-sm">Option 1 — Script Tag <Badge className="ml-1 text-[10px]">Recommended</Badge></div>
                        <div className="text-xs text-muted-foreground mt-0.5">Paste before &lt;/body&gt; on any website</div>
                    </div>
                    <CopyBtn text={scriptSnippet} />
                </div>
                <pre className="bg-secondary text-foreground text-xs p-4 rounded-sm overflow-x-auto border border-border font-mono leading-relaxed">
                    {scriptSnippet}
                </pre>
            </div>

            {/* Option 2 */}
            <div>
                <div className="flex items-center justify-between mb-2">
                    <div>
                        <div className="font-medium text-sm">Option 2 — iFrame Embed</div>
                        <div className="text-xs text-muted-foreground mt-0.5">For CMS platforms, Webflow, Notion</div>
                    </div>
                    <CopyBtn text={iframeSnippet} />
                </div>
                <pre className="bg-secondary text-foreground text-xs p-4 rounded-sm overflow-x-auto border border-border font-mono leading-relaxed">
                    {iframeSnippet}
                </pre>
            </div>

            {/* Option 3 */}
            <div>
                <div className="flex items-center justify-between mb-2">
                    <div>
                        <div className="font-medium text-sm">Option 3 — React / Next.js</div>
                        <div className="text-xs text-muted-foreground mt-0.5">npm package for React-based apps</div>
                    </div>
                    <CopyBtn text={npmSnippet} />
                </div>
                <pre className="bg-secondary text-foreground text-xs p-4 rounded-sm overflow-x-auto border border-border font-mono leading-relaxed">
                    {npmSnippet}
                </pre>
            </div>

            {/* Test link */}
            <div className="border border-border px-4 py-3 flex items-center justify-between">
                <div>
                    <div className="text-sm font-medium">Test your widget</div>
                    <div className="text-xs text-muted-foreground mt-0.5">Open the iframe in a new tab to preview</div>
                </div>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => window.open(`${baseUrl}/api/widget/${widgetId}/iframe`, "_blank")}
                >
                    <Eye size={14} className="mr-1" /> Preview
                </Button>
            </div>
        </div>
    );
}

// ─── Widget Builder ───────────────────────────────────────────────────────────
function WidgetBuilder({ initial, onSaved, onBack }) {
    const isEdit = !!initial;
    const [name, setName] = useState(initial?.name || "");
    const [cfg, setCfg] = useState(initial?.config || { ...DEFAULT_CFG });
    const [allowedDomains, setAllowedDomains] = useState((initial?.allowed_domains || []).join("\n"));
    const [docIds, setDocIds] = useState(initial?.document_ids || []);
    const [rateHour, setRateHour] = useState(initial?.rate_limit_hour ?? 20);
    const [rateDay, setRateDay] = useState(initial?.rate_limit_day ?? 500);
    const [docs, setDocs] = useState([]);
    const [busy, setBusy] = useState(false);
    const [tab, setTab] = useState("appearance");

    useEffect(() => {
        api.get("/v2/documents").then((r) => setDocs(r.data.filter((d) => d.status === "ready")));
    }, []);

    const patchCfg = (key, val) => setCfg((c) => ({ ...c, [key]: val }));

    const toggleDoc = (id) => setDocIds((ids) => ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]);

    const save = async () => {
        if (!name.trim()) { toast.error("Widget name is required"); return; }
        if (!docIds.length) { toast.error("Select at least one document"); return; }
        setBusy(true);
        try {
            const domains = allowedDomains.split("\n").map((d) => d.trim()).filter(Boolean);
            const payload = {
                name: name.trim(),
                config: cfg,
                document_ids: docIds,
                allowed_domains: domains,
                rate_limit_hour: parseInt(rateHour, 10) || 0,
                rate_limit_day: parseInt(rateDay, 10) || 0,
            };
            if (isEdit) {
                await api.patch(`/v2/widgets/${initial.widget_id}`, payload);
                toast.success("Widget updated");
            } else {
                await api.post("/v2/widgets", payload);
                toast.success("Widget created");
            }
            onSaved();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Save failed");
        } finally {
            setBusy(false);
        }
    };

    return (
        <div>
            {/* Header */}
            <header className="h-16 border-b border-border px-8 flex items-center justify-between sticky top-0 bg-background z-10">
                <div className="flex items-center gap-4">
                    <Button variant="ghost" size="icon" onClick={onBack}><ArrowLeft size={18} /></Button>
                    <div>
                        <div className="dc-overline">Embed Widget</div>
                        <h1 className="font-heading font-bold text-lg">{isEdit ? "Edit widget" : "Create widget"}</h1>
                    </div>
                </div>
                <Button onClick={save} disabled={busy}>{busy ? "Saving…" : isEdit ? "Save changes" : "Create widget"}</Button>
            </header>

            <div className="p-8">
                <div className="grid grid-cols-[1fr_300px] gap-8 max-w-7xl">
                    {/* Left: form */}
                    <div className="space-y-6">
                        {/* Name */}
                        <div>
                            <Label className="dc-overline">Widget name <span className="text-red-500">*</span></Label>
                            <Input
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                placeholder="My Support Widget"
                                className="mt-1"
                            />
                        </div>

                        {/* Document scope */}
                        <div>
                            <Label className="dc-overline">Document scope <span className="text-red-500">*</span></Label>
                            <div className="text-xs text-muted-foreground mt-0.5 mb-2">
                                Widget can only answer from these documents. Changes take effect instantly.
                            </div>
                            <div className="border border-border max-h-48 overflow-auto">
                                {docs.length === 0 && (
                                    <div className="p-3 text-xs text-muted-foreground">No ready documents. Upload and process documents first.</div>
                                )}
                                {docs.map((d) => (
                                    <label
                                        key={d.id}
                                        className="flex items-center gap-3 px-3 py-2 border-b border-border last:border-b-0 hover:bg-secondary/50 cursor-pointer"
                                    >
                                        <input
                                            type="checkbox"
                                            checked={docIds.includes(d.id)}
                                            onChange={() => toggleDoc(d.id)}
                                            className="w-4 h-4 accent-brand-primary"
                                        />
                                        <span className="text-sm truncate">{d.filename}</span>
                                    </label>
                                ))}
                            </div>
                            <div className="text-[11px] text-muted-foreground mt-1 font-mono">{docIds.length} selected</div>
                        </div>

                        {/* Tabs */}
                        <Tabs value={tab} onValueChange={setTab}>
                            <TabsList className="mb-4">
                                <TabsTrigger value="appearance" className="flex items-center gap-1.5">
                                    <PaintBucket size={14} /> Appearance
                                </TabsTrigger>
                                <TabsTrigger value="behaviour" className="flex items-center gap-1.5">
                                    <Sliders size={14} /> Behaviour
                                </TabsTrigger>
                                <TabsTrigger value="security" className="flex items-center gap-1.5">
                                    <ShieldCheck size={14} /> Security
                                </TabsTrigger>
                                {isEdit && (
                                    <TabsTrigger value="install" className="flex items-center gap-1.5">
                                        <Code size={14} /> Install
                                    </TabsTrigger>
                                )}
                            </TabsList>

                            {/* ─── Appearance ─── */}
                            <TabsContent value="appearance" className="space-y-4">
                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <Label className="dc-overline">Widget title</Label>
                                        <Input value={cfg.title} onChange={(e) => patchCfg("title", e.target.value)} className="mt-1" />
                                    </div>
                                    <div>
                                        <Label className="dc-overline">Subtitle / placeholder</Label>
                                        <Input value={cfg.subtitle} onChange={(e) => patchCfg("subtitle", e.target.value)} className="mt-1" />
                                    </div>
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <Label className="dc-overline">Brand color</Label>
                                        <div className="flex items-center gap-2 mt-1">
                                            <input
                                                type="color"
                                                value={cfg.brand_color}
                                                onChange={(e) => patchCfg("brand_color", e.target.value)}
                                                className="w-10 h-10 rounded border border-border cursor-pointer p-0.5"
                                            />
                                            <Input
                                                value={cfg.brand_color}
                                                onChange={(e) => patchCfg("brand_color", e.target.value)}
                                                className="font-mono"
                                                maxLength={7}
                                            />
                                        </div>
                                    </div>
                                    <div>
                                        <Label className="dc-overline">Widget position</Label>
                                        <Select value={cfg.position} onValueChange={(v) => patchCfg("position", v)}>
                                            <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="bottom-right">Bottom Right</SelectItem>
                                                <SelectItem value="bottom-left">Bottom Left</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>

                                <div>
                                    <Label className="dc-overline">Launcher style</Label>
                                    <Select value={cfg.launcher_style} onValueChange={(v) => patchCfg("launcher_style", v)}>
                                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="icon">Icon only</SelectItem>
                                            <SelectItem value="icon-label">Icon + Label</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="flex items-center justify-between border border-border px-3 py-2.5">
                                    <div>
                                        <div className="text-sm font-medium">Dark mode</div>
                                        <div className="text-xs text-muted-foreground">Widget uses dark color scheme</div>
                                    </div>
                                    <Switch checked={cfg.dark_mode} onCheckedChange={(v) => patchCfg("dark_mode", v)} />
                                </div>
                            </TabsContent>

                            {/* ─── Behaviour ─── */}
                            <TabsContent value="behaviour" className="space-y-4">
                                <div>
                                    <Label className="dc-overline">Welcome message</Label>
                                    <Textarea
                                        value={cfg.welcome_message}
                                        onChange={(e) => patchCfg("welcome_message", e.target.value)}
                                        rows={2}
                                        className="mt-1"
                                    />
                                </div>

                                <div>
                                    <Label className="dc-overline">Fallback message (when no answer found)</Label>
                                    <Textarea
                                        value={cfg.fallback_message}
                                        onChange={(e) => patchCfg("fallback_message", e.target.value)}
                                        rows={2}
                                        className="mt-1"
                                    />
                                </div>

                                <div>
                                    <Label className="dc-overline">Max questions per session (0 = unlimited)</Label>
                                    <Input
                                        type="number"
                                        min={0}
                                        value={cfg.max_questions_per_session}
                                        onChange={(e) => patchCfg("max_questions_per_session", parseInt(e.target.value, 10) || 0)}
                                        className="mt-1 w-32"
                                    />
                                </div>

                                <div>
                                    <Label className="dc-overline">Visitor email collection</Label>
                                    <Select value={cfg.email_collection} onValueChange={(v) => patchCfg("email_collection", v)}>
                                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="off">Off — no email asked</SelectItem>
                                            <SelectItem value="optional">Optional — skip allowed</SelectItem>
                                            <SelectItem value="required">Required — must enter email</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>

                                <div className="space-y-2">
                                    {[
                                        { key: "show_citations", label: "Show source citations", desc: "Inline citation badges below answers" },
                                        { key: "show_confidence", label: "Show confidence score", desc: "HIGH / MEDIUM / LOW badge" },
                                        { key: "allow_copy", label: "Allow copy / export", desc: "Copy-to-clipboard button on answers" },
                                    ].map(({ key, label, desc }) => (
                                        <div key={key} className="flex items-center justify-between border border-border px-3 py-2.5">
                                            <div>
                                                <div className="text-sm font-medium">{label}</div>
                                                <div className="text-xs text-muted-foreground">{desc}</div>
                                            </div>
                                            <Switch checked={cfg[key]} onCheckedChange={(v) => patchCfg(key, v)} />
                                        </div>
                                    ))}
                                </div>
                            </TabsContent>

                            {/* ─── Security ─── */}
                            <TabsContent value="security" className="space-y-4">
                                <div>
                                    <Label className="dc-overline">Allowed domains (one per line)</Label>
                                    <div className="text-xs text-muted-foreground mt-0.5 mb-1">
                                        Widget only renders on these domains. Wildcard supported: <code>*.company.com</code>. Leave empty to allow all.
                                    </div>
                                    <Textarea
                                        value={allowedDomains}
                                        onChange={(e) => setAllowedDomains(e.target.value)}
                                        placeholder={"docs.company.com\n*.support.company.com"}
                                        rows={4}
                                        className="mt-1 font-mono text-sm"
                                    />
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <Label className="dc-overline">Max queries per visitor per hour</Label>
                                        <div className="text-xs text-muted-foreground mt-0.5 mb-1">0 = unlimited</div>
                                        <Input
                                            type="number"
                                            min={0}
                                            value={rateHour}
                                            onChange={(e) => setRateHour(e.target.value)}
                                            className="mt-1"
                                        />
                                    </div>
                                    <div>
                                        <Label className="dc-overline">Max queries per day (all visitors)</Label>
                                        <div className="text-xs text-muted-foreground mt-0.5 mb-1">0 = unlimited</div>
                                        <Input
                                            type="number"
                                            min={0}
                                            value={rateDay}
                                            onChange={(e) => setRateDay(e.target.value)}
                                            className="mt-1"
                                        />
                                    </div>
                                </div>

                                <div className="border border-border bg-secondary/30 px-4 py-3 flex items-start gap-3">
                                    <ShieldCheck size={18} weight="duotone" className="text-brand-primary shrink-0 mt-0.5" />
                                    <div className="text-sm">
                                        <div className="font-medium">Server-side enforcement</div>
                                        <div className="text-xs text-muted-foreground mt-1">
                                            Domain whitelist and rate limits are validated on every request by the backend — not just the client.
                                            Widget tokens carry no user identity and are strictly read-only.
                                        </div>
                                    </div>
                                </div>
                            </TabsContent>

                            {/* ─── Install (edit only) ─── */}
                            {isEdit && (
                                <TabsContent value="install">
                                    <InstallTab widgetId={initial.widget_id} cfg={cfg} />
                                </TabsContent>
                            )}
                        </Tabs>
                    </div>

                    {/* Right: live preview */}
                    <div className="sticky top-24 self-start">
                        <WidgetPreview cfg={cfg} />
                    </div>
                </div>
            </div>
        </div>
    );
}

// ─── Widget list ──────────────────────────────────────────────────────────────
export default function EmbedWidget() {
    const [widgets, setWidgets] = useState([]);
    const [loading, setLoading] = useState(true);
    const [view, setView] = useState("list"); // 'list' | 'create' | 'edit'
    const [editTarget, setEditTarget] = useState(null);
    const [analyticsWidget, setAnalyticsWidget] = useState(null);
    const [toggling, setToggling] = useState({});

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const r = await api.get("/v2/widgets");
            setWidgets(r.data);
        } catch (e) {
            if (e?.response?.status !== 403 && e?.response?.status !== 404) {
                toast.error("Failed to load widgets");
            }
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    const handleToggle = async (w) => {
        setToggling((t) => ({ ...t, [w.widget_id]: true }));
        try {
            await api.patch(`/v2/widgets/${w.widget_id}`, { is_active: !w.is_active });
            toast.success(w.is_active ? "Widget paused" : "Widget activated");
            setWidgets((ws) => ws.map((x) => x.widget_id === w.widget_id ? { ...x, is_active: !w.is_active } : x));
        } catch {
            toast.error("Toggle failed");
        } finally {
            setToggling((t) => ({ ...t, [w.widget_id]: false }));
        }
    };

    const handleDelete = async (w) => {
        if (!window.confirm(`Deactivate "${w.name}"? Existing embeds will stop working immediately.`)) return;
        try {
            await api.delete(`/v2/widgets/${w.widget_id}`);
            toast.success("Widget deactivated");
            load();
        } catch {
            toast.error("Delete failed");
        }
    };

    const handleSaved = () => {
        setView("list");
        setEditTarget(null);
        load();
    };

    // ─── Edit / Create views ───
    if (view === "create") {
        return <WidgetBuilder initial={null} onSaved={handleSaved} onBack={() => setView("list")} />;
    }
    if (view === "edit" && editTarget) {
        return <WidgetBuilder initial={editTarget} onSaved={handleSaved} onBack={() => { setView("list"); setEditTarget(null); }} />;
    }

    // ─── List view ────────────────────────────────────────────────────────────
    return (
        <div>
            <header className="h-16 border-b border-border px-8 flex items-center justify-between sticky top-0 bg-background z-10">
                <div>
                    <div className="dc-overline">Workspace</div>
                    <h1 className="font-heading font-bold text-lg">Embed Widget</h1>
                </div>
                <Button onClick={() => setView("create")}>
                    <Plus size={16} /> New widget
                </Button>
            </header>

            <div className="p-8 max-w-7xl">
                {/* Info banner */}
                <div className="border border-border bg-secondary/30 px-4 py-3 mb-6 flex items-start gap-3 text-sm">
                    <Lightning size={18} weight="duotone" className="text-brand-primary shrink-0 mt-0.5" />
                    <div>
                        <div className="font-medium">One script tag, powered by your documents</div>
                        <div className="text-xs text-muted-foreground mt-0.5">
                            Embed a fully AI-powered chat widget on any website. Queries are strictly scoped to your
                            selected documents with domain-whitelist and rate-limit protection.
                        </div>
                    </div>
                </div>

                {loading && <div className="text-sm text-muted-foreground py-8">Loading…</div>}

                {!loading && widgets.length === 0 && (
                    <div className="border border-dashed border-border p-16 text-center">
                        <Code size={40} weight="duotone" className="mx-auto text-muted-foreground" />
                        <h2 className="font-heading font-bold text-xl mt-4">No widgets yet</h2>
                        <p className="text-sm text-muted-foreground mt-2 max-w-sm mx-auto">
                            Create an embeddable chat widget scoped to your documents. Install on any website with a single script tag.
                        </p>
                        <Button className="mt-6" onClick={() => setView("create")}>
                            <Plus size={16} /> Create first widget
                        </Button>
                    </div>
                )}

                {!loading && widgets.length > 0 && (
                    <div className="border border-border">
                        <div className="hidden md:grid grid-cols-[1fr_140px_120px_100px_80px_180px] gap-4 px-4 py-3 bg-secondary/50 border-b border-border text-xs font-mono uppercase tracking-wider text-muted-foreground">
                            <div>Widget</div>
                            <div>Domains</div>
                            <div>Documents</div>
                            <div>Rate/hr</div>
                            <div>Status</div>
                            <div>Actions</div>
                        </div>
                        {widgets.map((w) => (
                            <div
                                key={w.widget_id}
                                className="md:grid md:grid-cols-[1fr_140px_120px_100px_80px_180px] gap-4 px-4 py-3 border-b border-border last:border-b-0 items-center"
                            >
                                <div className="min-w-0">
                                    <div className="font-medium truncate">{w.name}</div>
                                    <div className="text-[11px] font-mono text-muted-foreground truncate">{w.widget_id}</div>
                                </div>
                                <div className="text-sm font-mono">
                                    {w.allowed_domains?.length > 0
                                        ? <span title={w.allowed_domains.join(", ")}>{w.allowed_domains.length} domain{w.allowed_domains.length !== 1 ? "s" : ""}</span>
                                        : <span className="text-muted-foreground">Any domain</span>
                                    }
                                </div>
                                <div className="text-sm font-mono">{w.document_ids?.length || 0} doc{w.document_ids?.length !== 1 ? "s" : ""}</div>
                                <div className="text-sm font-mono">{w.rate_limit_hour || "∞"}</div>
                                <div>
                                    {w.is_active
                                        ? <Badge className="text-[10px] font-mono bg-confidence-high text-white">ACTIVE</Badge>
                                        : <Badge variant="secondary" className="text-[10px] font-mono">PAUSED</Badge>
                                    }
                                </div>
                                <div className="flex gap-1 flex-wrap">
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        onClick={() => { setEditTarget(w); setView("edit"); }}
                                        title="Edit"
                                    >
                                        Edit
                                    </Button>
                                    <Button
                                        size="icon"
                                        variant="ghost"
                                        onClick={() => setAnalyticsWidget(w)}
                                        title="Analytics"
                                    >
                                        <ChartBar size={14} />
                                    </Button>
                                    <Button
                                        size="icon"
                                        variant="ghost"
                                        onClick={() => handleToggle(w)}
                                        disabled={toggling[w.widget_id]}
                                        title={w.is_active ? "Pause" : "Activate"}
                                    >
                                        {w.is_active ? <ToggleRight size={16} weight="fill" className="text-brand-primary" /> : <ToggleLeft size={16} />}
                                    </Button>
                                    <Button
                                        size="icon"
                                        variant="ghost"
                                        onClick={() => handleDelete(w)}
                                        title="Deactivate"
                                        className="text-destructive hover:text-destructive"
                                    >
                                        <Trash size={14} />
                                    </Button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <AnalyticsDialog
                widget={analyticsWidget}
                open={!!analyticsWidget}
                onClose={() => setAnalyticsWidget(null)}
            />
        </div>
    );
}
