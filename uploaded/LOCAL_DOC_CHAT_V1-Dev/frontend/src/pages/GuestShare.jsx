import React, { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import axios from "axios";
import { API_BASE } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import ConfidenceBadge from "@/components/ConfidenceBadge";
import MarkdownMessage from "@/components/MarkdownMessage";
import { toast } from "sonner";
import {
    Lock,
    Clock,
    Globe,
    PaperPlaneRight,
    FileText,
    WarningCircle,
    Lightning,
    ArrowSquareOut,
} from "@phosphor-icons/react";

export default function GuestShare() {
    const { token } = useParams();
    const [info, setInfo] = useState(null);
    const [stage, setStage] = useState("loading"); // loading | gate | chat | error
    const [error, setError] = useState(null);
    const [password, setPassword] = useState("");
    const [email, setEmail] = useState("");
    const [verifying, setVerifying] = useState(false);
    const [guestToken, setGuestToken] = useState(null);
    const [documents, setDocuments] = useState([]);
    const [sessionId, setSessionId] = useState(null);
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState("");
    const [streaming, setStreaming] = useState(false);
    const [followups, setFollowups] = useState([]);
    const [activeCite, setActiveCite] = useState(null);
    const bottomRef = useRef(null);

    useEffect(() => {
        axios
            .get(`${API_BASE}/v2/share-links/${token}/info`)
            .then((r) => {
                setInfo(r.data);
                setStage("gate");
            })
            .catch((e) => {
                setError(e?.response?.data?.detail || "Link not found");
                setStage("error");
            });
    }, [token]);

    const verify = async (e) => {
        e?.preventDefault?.();
        setVerifying(true);
        try {
            const r = await axios.post(`${API_BASE}/v2/share-links/${token}/verify`, { password, email });
            setGuestToken(r.data.guest_token);
            setDocuments(r.data.documents);
            setStage("chat");
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Verification failed");
        } finally {
            setVerifying(false);
        }
    };

    useEffect(() => {
        if (stage === "chat" && info && !info.requires_password && !info.requires_email) {
            verify();
        }
        // eslint-disable-next-line
    }, [stage]);

    useEffect(() => {
        if (stage === "gate" && info && !info.requires_password && !info.requires_email) {
            verify();
        }
        // eslint-disable-next-line
    }, [info]);

    useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, streaming]);

    const openSource = async (docId, filename) => {
        if (!guestToken || !docId) return;
        try {
            const res = await fetch(
                `${API_BASE}/v2/share-links/${token}/document/${docId}/file`,
                { headers: { "x-guest-token": guestToken } }
            );
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const w = window.open(url, "_blank");
            if (!w) {
                const a = document.createElement("a");
                a.href = url;
                a.download = filename || "document";
                a.click();
            }
            setTimeout(() => URL.revokeObjectURL(url), 60_000);
        } catch (e) {
            toast.error("Could not open source");
        }
    };

    const send = async (textOverride) => {
        const text = (textOverride ?? input).trim();
        if (!text || streaming || !guestToken) return;
        setInput("");
        setFollowups([]);

        const userMsg = { id: `u-${Date.now()}`, role: "user", content: text };
        setMessages((m) => [...m, userMsg]);
        const assistantDraft = { id: `a-${Date.now()}`, role: "assistant", content: "", citations: [], confidence: null, streaming: true };
        setMessages((m) => [...m, assistantDraft]);
        setStreaming(true);

        try {
            const resp = await fetch(`${API_BASE}/v2/chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query: text, session_id: sessionId, guest_token: guestToken, stream: true }),
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.detail || "Chat failed");
            }
            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const events = buffer.split("\n\n");
                buffer = events.pop() || "";
                for (const ev of events) {
                    const lines = ev.split("\n");
                    let eventType = "message";
                    let data = "";
                    for (const line of lines) {
                        if (line.startsWith("event:")) eventType = line.slice(6).trim();
                        else if (line.startsWith("data:")) data += line.slice(5).trim();
                    }
                    if (!data) continue;
                    try {
                        const payload = JSON.parse(data);
                        if (eventType === "meta") {
                            setSessionId(payload.session_id);
                            setMessages((m) => m.map((mm) => mm.id === assistantDraft.id
                                ? { ...mm, citations: payload.citations, confidence: payload.confidence } : mm));
                        } else if (eventType === "token") {
                            setMessages((m) => m.map((mm) => mm.id === assistantDraft.id
                                ? { ...mm, content: (mm.content || "") + payload.t } : mm));
                        } else if (eventType === "done") {
                            setMessages((m) => m.map((mm) => mm.id === assistantDraft.id
                                ? { ...mm, streaming: false } : mm));
                            setFollowups(payload.followups || []);
                        }
                    } catch {}
                }
            }
        } catch (e) {
            toast.error(e.message || "Chat failed");
            setMessages((m) => m.map((mm) => mm.id === assistantDraft.id
                ? { ...mm, content: `_Error: ${e.message}_`, streaming: false } : mm));
        } finally {
            setStreaming(false);
        }
    };

    if (stage === "loading") {
        return <div className="min-h-screen grid place-items-center text-sm text-muted-foreground">Loading…</div>;
    }

    if (stage === "error") {
        return (
            <div className="min-h-screen grid place-items-center px-6">
                <div className="max-w-md text-center" data-testid="share-error-state">
                    <WarningCircle size={40} weight="duotone" className="mx-auto text-confidence-low" />
                    <h1 className="font-heading font-bold text-2xl mt-4">Link unavailable</h1>
                    <p className="text-sm text-muted-foreground mt-2">{error}</p>
                    <Link to="/"><Button className="mt-6" variant="outline" data-testid="share-error-home-button">Go to home</Button></Link>
                </div>
            </div>
        );
    }

    const ModeIcon = info?.mode === "password" ? Lock : info?.mode === "expiring" ? Clock : Globe;

    if (stage === "gate" && (info?.requires_password || info?.requires_email)) {
        return (
            <div className="min-h-screen grid place-items-center px-6">
                <form onSubmit={verify} className="w-full max-w-md" data-testid="share-gate-form">
                    <div className="dc-overline mb-2 flex items-center gap-2"><ModeIcon size={14} /> Secure share</div>
                    <h1 className="font-heading font-black text-3xl tracking-tighter">{info?.title || "Shared documents"}</h1>
                    <p className="text-sm text-muted-foreground mt-2">
                        {info?.requires_password && "Passphrase required. "}
                        {info?.requires_email && `Restricted to ${info.domain_restriction}`}
                    </p>

                    <div className="mt-6 space-y-4">
                        {info?.requires_email && (
                            <div>
                                <Label className="dc-overline">Email</Label>
                                <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 h-11" required data-testid="share-gate-email" />
                            </div>
                        )}
                        {info?.requires_password && (
                            <div>
                                <Label className="dc-overline">Passphrase</Label>
                                <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1 h-11" required data-testid="share-gate-password" />
                            </div>
                        )}
                    </div>

                    <Button type="submit" disabled={verifying} className="w-full h-11 mt-6" data-testid="share-gate-submit">
                        {verifying ? "Unlocking…" : "Unlock access"}
                    </Button>

                    <div className="mt-8 text-xs text-muted-foreground font-mono">
                        {info?.documents?.length || 0} document{info?.documents?.length === 1 ? "" : "s"} scoped to this link
                    </div>
                </form>
            </div>
        );
    }

    // Chat view (after verify)
    return (
        <div className="min-h-screen grid grid-rows-[auto_1fr_auto]">
            <header className="h-16 border-b border-border px-6 flex items-center justify-between">
                <div className="flex items-center gap-3 min-w-0">
                    <div className="w-7 h-7 bg-brand-primary grid place-items-center shrink-0">
                        <span className="text-white font-heading font-black text-sm">D</span>
                    </div>
                    <div className="min-w-0">
                        <div className="dc-overline">Shared view</div>
                        <div className="font-heading font-bold text-base truncate">{info?.title || "Scoped chat"}</div>
                    </div>
                </div>
                <div className="text-xs text-muted-foreground font-mono hidden sm:block">
                    {documents.length} document{documents.length === 1 ? "" : "s"}
                </div>
            </header>

            <div className="overflow-auto px-6 md:px-10 py-8">
                <div className="max-w-3xl mx-auto">
                    <div className="border border-border bg-secondary/30 p-4 mb-6" data-testid="share-scope-list">
                        <div className="dc-overline mb-2">Accessible documents</div>
                        <div className="flex flex-wrap gap-2">
                            {documents.map((d) => (
                                <div key={d.id} className="flex items-center gap-1.5 border border-border bg-card px-2 py-1 text-xs">
                                    <FileText size={12} />{d.filename}
                                </div>
                            ))}
                        </div>
                    </div>

                    {messages.length === 0 && (
                        <div className="text-center py-8" data-testid="share-chat-empty">
                            <Lightning size={32} weight="duotone" className="mx-auto text-brand-primary" />
                            <h2 className="font-heading font-bold text-xl mt-3">Ask a question about these documents</h2>
                            <p className="text-sm text-muted-foreground mt-2">Answers are grounded with inline citations.</p>
                        </div>
                    )}

                    <div className="space-y-6">
                        {messages.map((m) => (
                            <div key={m.id} className="animate-fade-in" data-testid={`share-message-${m.role}`}>
                                {m.role === "user" ? (
                                    <div className="flex justify-end">
                                        <div className="bg-secondary border border-border px-4 py-3 rounded-sm max-w-[80%] text-[15px]">{m.content}</div>
                                    </div>
                                ) : (
                                    <div className="border-l-2 border-brand-primary pl-5">
                                        <div className="flex items-center gap-2 mb-2">
                                            <div className="dc-overline">DocChat</div>
                                            {m.confidence && <ConfidenceBadge level={m.confidence} />}
                                        </div>
                                        <MarkdownMessage content={m.content} citations={m.citations || []} onCite={setActiveCite} />
                                        {m.streaming && <span className="dc-cursor" />}
                                        {m.citations?.length > 0 && !m.streaming && (
                                            <div className="mt-4 space-y-1 text-xs">
                                                <div className="dc-overline mb-2">Sources</div>
                                                {m.citations.map((c) => (
                                                    <button
                                                        type="button"
                                                        key={c.chunk_id}
                                                        onClick={() => setActiveCite(c)}
                                                        className="w-full flex items-center gap-2 py-1.5 px-2 border border-border rounded-sm hover:bg-secondary/50 transition-colors text-left"
                                                        data-testid={`share-source-${c.chunk_id}`}
                                                        title="Preview source snippet"
                                                    >
                                                        <span className="font-mono text-[11px] bg-secondary border border-border px-1.5 py-0.5 rounded-sm">[{c.index}]</span>
                                                        <FileText size={13} className="text-muted-foreground" />
                                                        <span className="truncate flex-1">{c.filename}</span>
                                                        <span className="text-muted-foreground font-mono">p.{c.page}</span>
                                                    </button>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}

                        {followups.length > 0 && !streaming && (
                            <div className="ml-5" data-testid="share-followup-suggestions">
                                <div className="dc-overline mb-2">Follow-ups</div>
                                <div className="flex flex-wrap gap-2">
                                    {followups.map((f, i) => (
                                        <button
                                            key={i}
                                            type="button"
                                            onClick={() => send(f)}
                                            className="text-xs px-3 py-1.5 border border-border bg-card hover:bg-secondary/60 transition-colors rounded-sm"
                                            data-testid={`share-followup-${i}`}
                                        >
                                            {f}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}
                        <div ref={bottomRef} />
                    </div>
                </div>
            </div>

            <div className="border-t border-border p-4">
                <form onSubmit={(e) => { e.preventDefault(); send(); }} className="max-w-3xl mx-auto flex items-end gap-2" data-testid="share-chat-form">
                    <Textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                        placeholder="Ask about the shared documents…"
                        rows={2}
                        disabled={streaming}
                        className="resize-none"
                        data-testid="share-chat-input"
                    />
                    <Button type="submit" disabled={streaming || !input.trim()} className="h-11" data-testid="share-chat-send">
                        <PaperPlaneRight size={16} weight="fill" />
                    </Button>
                </form>
            </div>

            <Dialog open={!!activeCite} onOpenChange={(o) => !o && setActiveCite(null)}>
                <DialogContent data-testid="share-citation-panel">
                    <DialogHeader>
                        <DialogTitle className="font-heading">{activeCite?.filename}</DialogTitle>
                        <DialogDescription>
                            Page {activeCite?.page} · Source [{activeCite?.index}]
                        </DialogDescription>
                    </DialogHeader>
                    <div className="border border-border p-4 bg-secondary/50 font-mono text-[13px] leading-relaxed whitespace-pre-wrap max-h-[50vh] overflow-auto">
                        {activeCite?.text}
                    </div>
                    <Button
                        variant="outline"
                        onClick={() => activeCite && openSource(activeCite.document_id, activeCite.filename)}
                        className="self-end gap-2"
                        data-testid="share-citation-open-file"
                    >
                        <ArrowSquareOut size={14} /> Open original document
                    </Button>
                </DialogContent>
            </Dialog>
        </div>
    );
}
