import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CheckCircle, XCircle } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Settings() {
    const { user } = useAuth();
    const [flags, setFlags] = useState({});
    const [providers, setProviders] = useState(null);
    const [adminProviders, setAdminProviders] = useState(null);
    const [form, setForm] = useState({ llm_provider: "", llm_model: "", embedding_provider: "", embedding_model: "" });
    const [saving, setSaving] = useState(false);

    const isOwner = user?.role === "owner";

    useEffect(() => {
        api.get("/v2/flags").then((r) => setFlags(r.data)).catch(() => {});
        api.get("/v2/providers").then((r) => setProviders(r.data)).catch(() => {});
        if (isOwner) {
            api.get("/admin/providers").then((r) => {
                setAdminProviders(r.data);
                setForm({
                    llm_provider: r.data.llm.provider,
                    llm_model: r.data.llm.model,
                    embedding_provider: r.data.embedding.provider,
                    embedding_model: r.data.embedding.model,
                });
            }).catch(() => {});
        }
    }, [isOwner]);

    const saveProviders = async () => {
        setSaving(true);
        try {
            const r = await api.patch("/admin/providers", form);
            toast.success(r?.data?.note || "Providers updated");
            setProviders({ llm: r.data.llm, embedding: r.data.embedding });
            setAdminProviders((cur) => cur ? {
                llm: { ...cur.llm, provider: r.data.llm.provider, model: r.data.llm.model },
                embedding: { ...cur.embedding, provider: r.data.embedding.provider, model: r.data.embedding.model },
            } : cur);
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Update failed");
        } finally {
            setSaving(false);
        }
    };

    return (
        <div>
            <header className="h-16 border-b border-border px-8 flex items-center sticky top-0 bg-background z-10">
                <div>
                    <div className="dc-overline">Account</div>
                    <h1 className="font-heading font-bold text-lg">Settings</h1>
                </div>
            </header>
            <div className="p-8 max-w-4xl space-y-8">
                <section>
                    <div className="dc-overline mb-3">Profile</div>
                    <div className="border border-border p-6 grid md:grid-cols-3 gap-4">
                        <div>
                            <div className="text-xs text-muted-foreground">Name</div>
                            <div className="font-medium mt-1" data-testid="settings-name">{user?.name}</div>
                        </div>
                        <div>
                            <div className="text-xs text-muted-foreground">Email</div>
                            <div className="font-mono text-sm mt-1" data-testid="settings-email">{user?.email}</div>
                        </div>
                        <div>
                            <div className="text-xs text-muted-foreground">Role</div>
                            <div className="mt-1"><Badge className="font-mono uppercase" data-testid="settings-role">{user?.role}</Badge></div>
                        </div>
                    </div>
                </section>

                <section>
                    <div className="dc-overline mb-3">Active providers</div>
                    {isOwner ? (
                        <>
                            <p className="text-xs text-muted-foreground mb-4">
                                As an Owner you can switch the LLM and Embedding providers at runtime. Changes are saved to <span className="dc-kbd">backend/.env</span> and persist across restarts.
                            </p>
                            <div className="border border-border p-6 space-y-6" data-testid="provider-edit-form">
                                <div className="grid md:grid-cols-2 gap-6">
                                    <div className="space-y-2">
                                        <Label className="dc-overline">LLM provider</Label>
                                        <Select
                                            value={form.llm_provider}
                                            onValueChange={(v) => setForm({ ...form, llm_provider: v })}
                                        >
                                            <SelectTrigger data-testid="llm-provider-select">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {(adminProviders?.llm?.allowed_providers || ["emergent", "openrouter"]).map((p) => (
                                                    <SelectItem key={p} value={p}>{p}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-2">
                                        <Label className="dc-overline" htmlFor="llm-model">LLM model</Label>
                                        <Input
                                            id="llm-model"
                                            value={form.llm_model}
                                            onChange={(e) => setForm({ ...form, llm_model: e.target.value })}
                                            placeholder="gpt-4o-mini"
                                            className="font-mono"
                                            data-testid="llm-model-input"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label className="dc-overline">Embedding provider</Label>
                                        <Select
                                            value={form.embedding_provider}
                                            onValueChange={(v) => setForm({ ...form, embedding_provider: v })}
                                        >
                                            <SelectTrigger data-testid="embedding-provider-select">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {(adminProviders?.embedding?.allowed_providers || ["local", "openai"]).map((p) => (
                                                    <SelectItem key={p} value={p}>{p}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-2">
                                        <Label className="dc-overline" htmlFor="emb-model">Embedding model</Label>
                                        <Input
                                            id="emb-model"
                                            value={form.embedding_model}
                                            onChange={(e) => setForm({ ...form, embedding_model: e.target.value })}
                                            placeholder="text-embedding-3-small"
                                            className="font-mono"
                                            data-testid="embedding-model-input"
                                        />
                                    </div>
                                </div>
                                <div className="flex justify-end pt-2 border-t border-border">
                                    <Button onClick={saveProviders} disabled={saving} data-testid="save-providers-button">
                                        {saving ? "Saving…" : "Save providers"}
                                    </Button>
                                </div>
                            </div>
                        </>
                    ) : (
                        <>
                            <p className="text-xs text-muted-foreground mb-4">Read-only. Ask an Owner to change providers.</p>
                            {providers && (
                                <div className="grid md:grid-cols-2 gap-0 border-l border-t border-border">
                                    <div className="border-r border-b border-border p-6" data-testid="provider-llm">
                                        <div className="dc-overline mb-2">LLM (chat)</div>
                                        <div className="font-heading font-bold text-2xl">{providers.llm.provider}</div>
                                        <div className="text-xs font-mono text-muted-foreground mt-1">{providers.llm.model}</div>
                                    </div>
                                    <div className="border-r border-b border-border p-6" data-testid="provider-embedding">
                                        <div className="dc-overline mb-2">Embeddings</div>
                                        <div className="font-heading font-bold text-2xl">{providers.embedding.provider}</div>
                                        <div className="text-xs font-mono text-muted-foreground mt-1">{providers.embedding.model}</div>
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </section>

                <section>
                    <div className="dc-overline mb-3">Feature flags</div>
                    <p className="text-xs text-muted-foreground mb-4">Toggled server-side via env vars. Read-only view.</p>
                    <div className="border border-border">
                        {Object.entries(flags).map(([k, v], i) => (
                            <div
                                key={k}
                                className={`grid grid-cols-[1fr_100px] items-center px-4 py-2.5 ${i < Object.keys(flags).length - 1 ? "border-b border-border" : ""}`}
                                data-testid={`flag-row-${k}`}
                            >
                                <div className="font-mono text-[13px]">{k}</div>
                                <div className="flex items-center gap-1.5 text-xs font-mono justify-end">
                                    {v ? (
                                        <span className="text-confidence-high flex items-center gap-1"><CheckCircle size={14} weight="fill" /> ON</span>
                                    ) : (
                                        <span className="text-muted-foreground flex items-center gap-1"><XCircle size={14} weight="fill" /> OFF</span>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </section>
            </div>
        </div>
    );
}
