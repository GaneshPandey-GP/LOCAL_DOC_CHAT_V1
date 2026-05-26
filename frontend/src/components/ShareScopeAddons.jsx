import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";

/**
 * Reusable optional add-ons for any chat surface (share link, widget, …):
 *  • `kbIds`   — extends the answerable corpus with whole Knowledge Bases.
 *  • `toolIds` — augments answers with MCP tool execution.
 *  • `systemPrompt` — overrides the default agent persona.
 *
 * All three are *additive*. Pass null/empty arrays to disable.
 */
export default function ShareScopeAddons({
    kbIds, setKbIds,
    toolIds, setToolIds,
    systemPrompt, setSystemPrompt,
    maxPromptLen = 2000,
}) {
    const [kbs, setKbs] = useState([]);
    const [tools, setTools] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        Promise.all([api.get("/v2/kb"), api.get("/v2/mcp/tools")])
            .then(([k, t]) => { setKbs(k.data || []); setTools(t.data || []); })
            .catch(() => {/* silently — these are optional */})
            .finally(() => setLoading(false));
    }, []);

    const toggleKb = (id) => setKbIds(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);
    const toggleTool = (id) => setToolIds(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);

    const promptLen = (systemPrompt || "").length;
    const needsKey = tools.filter(t => toolIds.includes(t.id) && t.is_builtin && (t.id === "builtin-github" || t.id === "builtin-sql-query"));

    return (
        <div className="space-y-4" data-testid="share-scope-addons">
            <details className="border border-border">
                <summary className="px-3 py-2 text-sm font-medium cursor-pointer select-none">Advanced — KBs, MCP tools, system prompt</summary>
                <div className="p-3 space-y-4 border-t border-border">
                    {/* KBs */}
                    <div>
                        <Label className="dc-overline">Knowledge Bases (optional)</Label>
                        <div className="text-[11px] text-muted-foreground mb-1">All ready documents in the selected KBs are added to the answer scope.</div>
                        <div className="border border-border max-h-32 overflow-auto">
                            {loading && <div className="p-2 text-xs text-muted-foreground">Loading…</div>}
                            {!loading && kbs.length === 0 && <div className="p-2 text-xs text-muted-foreground">No KBs yet.</div>}
                            {kbs.map(k => (
                                <label key={k.id} className="flex items-center gap-2 px-2 py-1.5 border-b border-border last:border-b-0 hover:bg-secondary/50 cursor-pointer">
                                    <input type="checkbox" checked={(kbIds || []).includes(k.id)} onChange={() => toggleKb(k.id)} className="w-4 h-4 accent-brand-primary" data-testid={`addon-kb-${k.id}`} />
                                    <span className="text-sm truncate flex-1">{k.name}</span>
                                    <Badge variant="outline" className="text-[10px] font-mono">{k.type}</Badge>
                                </label>
                            ))}
                        </div>
                        <div className="text-[11px] text-muted-foreground mt-1 font-mono">{(kbIds || []).length} selected</div>
                    </div>

                    {/* MCP Tools */}
                    <div>
                        <Label className="dc-overline">MCP Tools (optional)</Label>
                        <div className="text-[11px] text-muted-foreground mb-1">The assistant may call these tools to answer questions.</div>
                        <div className="border border-border max-h-32 overflow-auto">
                            {loading && <div className="p-2 text-xs text-muted-foreground">Loading…</div>}
                            {!loading && tools.length === 0 && <div className="p-2 text-xs text-muted-foreground">No tools registered.</div>}
                            {tools.map(t => (
                                <label key={t.id} className="flex items-center gap-2 px-2 py-1.5 border-b border-border last:border-b-0 hover:bg-secondary/50 cursor-pointer">
                                    <input type="checkbox" checked={(toolIds || []).includes(t.id)} onChange={() => toggleTool(t.id)} className="w-4 h-4 accent-brand-primary" data-testid={`addon-tool-${t.id}`} />
                                    <span className="text-sm truncate flex-1">{t.name}</span>
                                    <Badge variant="outline" className="text-[10px] font-mono">{t.is_builtin ? "Built-in" : "Custom"}</Badge>
                                </label>
                            ))}
                        </div>
                        <div className="text-[11px] text-muted-foreground mt-1 font-mono">{(toolIds || []).length} selected</div>
                        {needsKey.length > 0 && (
                            <div className="mt-2 text-[11px] text-amber-700 border border-amber-300 bg-amber-50/60 px-2 py-1.5">
                                ⚠ {needsKey.map(t => t.name).join(", ")} require server-side API keys (GITHUB_TOKEN, DATABASE_URL). Check backend env.
                            </div>
                        )}
                    </div>

                    {/* System prompt */}
                    <div>
                        <div className="flex items-center justify-between">
                            <Label className="dc-overline">System prompt (optional)</Label>
                            <button type="button" className="text-[11px] text-brand-primary hover:underline" onClick={() => setSystemPrompt("")} data-testid="reset-system-prompt">Reset to default</button>
                        </div>
                        <Textarea
                            rows={4}
                            placeholder="Leave blank to use the default DocChat assistant persona."
                            value={systemPrompt || ""}
                            maxLength={maxPromptLen}
                            onChange={e => setSystemPrompt(e.target.value)}
                            className="font-mono text-xs"
                            data-testid="addon-system-prompt"
                        />
                        <div className="text-[11px] text-muted-foreground text-right font-mono">{promptLen}/{maxPromptLen}</div>
                    </div>
                </div>
            </details>
        </div>
    );
}
