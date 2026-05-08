import React, { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams, useNavigate, Link } from "react-router-dom";
import api, { API_BASE } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import ConfidenceBadge from "@/components/ConfidenceBadge";
import MarkdownMessage from "@/components/MarkdownMessage";
import { toast } from "sonner";
import {
    PaperPlaneRight,
    ThumbsUp,
    ThumbsDown,
    Copy,
    Plus,
    ChatCircle,
    Trash,
    PencilSimple,
    FileText,
    Lightning,
} from "@phosphor-icons/react";

function SessionList({ current, onPick, refreshKey, onDeleted }) {
    const [sessions, setSessions] = useState([]);
    useEffect(() => {
        api.get("/v2/sessions").then((r) => setSessions(r.data)).catch(() => {});
    }, [refreshKey]);

    const rename = async (s) => {
        const t = window.prompt("Rename session", s.title);
        if (!t) return;
        await api.patch(`/v2/sessions/${s.id}`, { title: t });
        setSessions((c) => c.map((x) => (x.id === s.id ? { ...x, title: t } : x)));
    };
    const del = async (s) => {
        if (!window.confirm(`Delete "${s.title}"?`)) return;
        await api.delete(`/v2/sessions/${s.id}`);
        setSessions((c) => c.filter((x) => x.id !== s.id));
        onDeleted?.(s.id);
    };

    return (
        <div className="h-full flex flex-col">
            <div className="p-3 border-b border-border">
                <Link to="/app/chat">
                    <Button variant="outline" className="w-full justify-start h-10" data-testid="new-chat-button">
                        <Plus size={16} /> New chat
                    </Button>
                </Link>
            </div>
            <div className="flex-1 overflow-auto">
                {sessions.length === 0 && (
                    <div className="p-4 text-xs text-muted-foreground">No sessions yet.</div>
                )}
                {sessions.map((s) => (
                    <div
                        key={s.id}
                        className={`group flex items-center gap-2 px-3 py-2.5 border-l-2 cursor-pointer transition-colors ${
                            current === s.id ? "border-brand-primary bg-secondary" : "border-transparent hover:bg-secondary/50"
                        }`}
                        onClick={() => onPick(s.id)}
                        data-testid={`session-row-${s.id}`}
                    >
                        <ChatCircle size={16} className="text-muted-foreground shrink-0" />
                        <div className="min-w-0 flex-1">
                            <div className="text-sm truncate">{s.title}</div>
                            <div className="text-[11px] text-muted-foreground font-mono">
                                {new Date(s.updated_at).toLocaleDateString()}
                            </div>
                        </div>
                        <div className="hidden group-hover:flex gap-1">
                            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={(e) => { e.stopPropagation(); rename(s); }} data-testid={`session-rename-${s.id}`}>
                                <PencilSimple size={13} />
                            </Button>
                            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={(e) => { e.stopPropagation(); del(s); }} data-testid={`session-delete-${s.id}`}>
                                <Trash size={13} />
                            </Button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function CitationPanel({ citation, onClose }) {
    return (
        <Dialog open={!!citation} onOpenChange={(o) => !o && onClose()}>
            <DialogContent data-testid="citation-panel">
                <DialogHeader>
                    <DialogTitle className="font-heading">{citation?.filename}</DialogTitle>
                    <DialogDescription>Page {citation?.page} · Source [{citation?.index}]</DialogDescription>
                </DialogHeader>
                <div className="border border-border p-4 bg-secondary/50 font-mono text-[13px] leading-relaxed whitespace-pre-wrap">
                    {citation?.text}
                </div>
            </DialogContent>
        </Dialog>
    );
}

export default function Chat() {
    const { sessionId: routeSessionId } = useParams();
    const [searchParams] = useSearchParams();
    const nav = useNavigate();

    const [sessionId, setSessionId] = useState(routeSessionId || null);
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState("");
    const [streaming, setStreaming] = useState(false);
    const [docIds, setDocIds] = useState(() => {
        const d = searchParams.get("docs");
        return d ? d.split(",") : null;
    });
    const [activeCite, setActiveCite] = useState(null);
    const [sessionsRefresh, setSessionsRefresh] = useState(0);
    const [followups, setFollowups] = useState([]);
    const [feedbackMap, setFeedbackMap] = useState({});
    const [docCount, setDocCount] = useState(0);
    const bottomRef = useRef(null);

    // Load docs count
    useEffect(() => {
        api.get("/v2/documents").then((r) => setDocCount(r.data.filter((d) => d.status === "ready").length)).catch(() => {});
    }, []);

    // Load messages when session changes
    useEffect(() => {
        setSessionId(routeSessionId || null);
        if (routeSessionId) {
            api.get(`/v2/sessions/${routeSessionId}/messages`).then((r) => {
                setMessages(r.data.messages || []);
                // Restore the original document scope so retrieval stays
                // bound to the same documents the user originally selected.
                const scope = r.data?.session?.scope_doc_ids;
                if (Array.isArray(scope)) {
                    setDocIds(scope.length > 0 ? scope : []);
                } else if (scope === null || scope === undefined) {
                    setDocIds(null); // null/undefined => "all accessible"
                }
            }).catch(() => nav("/app/chat"));
        } else {
            setMessages([]);
            // New chat: respect URL ?docs=… if present, otherwise null=all
            const d = searchParams.get("docs");
            setDocIds(d ? d.split(",") : null);
        }
        setFollowups([]);
    }, [routeSessionId,nav,searchParams]);

    useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, streaming]);

    const send = async (textOverride) => {
        const text = (textOverride ?? input).trim();
        if (!text || streaming) return;
        setInput("");
        setFollowups([]);

        const userMsg = { id: `u-${Date.now()}`, role: "user", content: text };
        setMessages((m) => [...m, userMsg]);

        const assistantDraft = { id: `a-${Date.now()}`, role: "assistant", content: "", citations: [], confidence: null, streaming: true };
        setMessages((m) => [...m, assistantDraft]);
        setStreaming(true);

        try {
            const token = localStorage.getItem("dc_access_token");
            const resp = await fetch(`${API_BASE}/v2/chat`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({
                    query: text,
                    session_id: sessionId,
                    document_ids: docIds,
                    stream: true,
                }),
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({}));
                throw new Error(err.detail || "Chat failed");
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            let newSessionId = sessionId;

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
                            newSessionId = payload.session_id;
                            setMessages((m) => m.map((mm) => mm.id === assistantDraft.id
                                ? { ...mm, citations: payload.citations, confidence: payload.confidence }
                                : mm));
                        } else if (eventType === "token") {
                            setMessages((m) => m.map((mm) => mm.id === assistantDraft.id
                                ? { ...mm, content: (mm.content || "") + payload.t }
                                : mm));
                        } else if (eventType === "done") {
                            setMessages((m) => m.map((mm) => mm.id === assistantDraft.id
                                ? { ...mm, id: payload.message_id, streaming: false }
                                : mm));
                            setFollowups(payload.followups || []);
                        }
                    } catch {}
                }
            }

            if (!sessionId && newSessionId) {
                setSessionId(newSessionId);
                nav(`/app/chat/${newSessionId}`, { replace: true });
            }
            setSessionsRefresh((x) => x + 1);
        } catch (e) {
            toast.error(e.message || "Chat failed");
            setMessages((m) => m.map((mm) => mm.id === assistantDraft.id
                ? { ...mm, content: `_Error: ${e.message}_`, streaming: false }
                : mm));
        } finally {
            setStreaming(false);
        }
    };

    const submitFeedback = async (msgId, rating) => {
        try {
            await api.post("/v2/feedback", { message_id: msgId, rating });
            setFeedbackMap((m) => ({ ...m, [msgId]: rating }));
            toast.success("Thanks for the feedback");
        } catch (e) {
            toast.error("Could not submit feedback");
        }
    };

    const copyMsg = (content) => {
        navigator.clipboard.writeText(content);
        toast.success("Copied to clipboard");
    };

    const pickSession = (id) => nav(`/app/chat/${id}`);

    return (
        <div className="h-screen grid grid-cols-[260px_1fr]">
            <aside className="border-r border-border">
                <SessionList current={sessionId} onPick={pickSession} refreshKey={sessionsRefresh} onDeleted={(id) => { if (id === sessionId) nav("/app/chat"); }} />
            </aside>

            <div className="flex flex-col h-screen">
                <header className="h-16 border-b border-border px-6 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <ChatCircle size={22} weight="duotone" className="text-brand-primary" />
                        <div>
                            <div className="dc-overline">Chat</div>
                            <div className="font-heading font-bold text-lg">
                                {docIds?.length ? `Scoped · ${docIds.length} docs` : `All documents · ${docCount} ready`}
                            </div>
                        </div>
                    </div>
                </header>

                <div className="flex-1 overflow-auto px-6 md:px-10 py-8">
                    <div className="max-w-3xl mx-auto space-y-6">
                        {messages.length === 0 && (
                            <div className="text-center py-16" data-testid="chat-empty-state">
                                <Lightning size={36} weight="duotone" className="mx-auto text-brand-primary" />
                                <h2 className="font-heading font-bold text-2xl mt-4">Ask anything about your documents</h2>
                                <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">
                                    Responses are grounded in your documents with inline citations and confidence scoring.
                                </p>
                                <div className="grid sm:grid-cols-2 gap-3 mt-8 max-w-2xl mx-auto">
                                    {[
                                        "Summarize the key points",
                                        "What are the main risks mentioned?",
                                        "Extract all dates and deadlines",
                                        "Compare the main arguments",
                                    ].map((s, i) => (
                                        <button
                                            key={i}
                                            onClick={() => send(s)}
                                            className="border border-border p-4 text-left text-sm hover:border-brand-primary hover:bg-secondary/50 transition-colors"
                                            data-testid={`suggestion-${i}`}
                                        >
                                            {s}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}

                        {messages.map((m) => (
                            <div key={m.id} className="animate-fade-in" data-testid={`message-${m.role}`}>
                                {m.role === "user" ? (
                                    <div className="flex justify-end">
                                        <div className="bg-secondary border border-border px-4 py-3 rounded-sm max-w-[80%] text-[15px]">
                                            {m.content}
                                        </div>
                                    </div>
                                ) : (
                                    <div className="border-l-2 border-brand-primary pl-5">
                                        <div className="flex items-center gap-2 mb-2">
                                            <div className="dc-overline">DocChat</div>
                                            {m.confidence && <ConfidenceBadge level={m.confidence} />}
                                            {(m.citations?.length ?? 0) > 0 && (
                                                <span className="text-xs text-muted-foreground font-mono">
                                                    {m.citations.length} source{m.citations.length === 1 ? "" : "s"}
                                                </span>
                                            )}
                                        </div>
                                        <MarkdownMessage content={m.content} citations={m.citations || []} onCite={setActiveCite} />
                                        {m.streaming && <span className="dc-cursor" />}

                                        {!m.streaming && m.content && (
                                            <div className="mt-3 flex items-center gap-1">
                                                <Button
                                                    size="icon"
                                                    variant="ghost"
                                                    className={`h-8 w-8 ${feedbackMap[m.id] === 1 ? "text-confidence-high" : ""}`}
                                                    onClick={() => submitFeedback(m.id, 1)}
                                                    data-testid={`feedback-up-${m.id}`}
                                                >
                                                    <ThumbsUp size={14} weight={feedbackMap[m.id] === 1 ? "fill" : "regular"} />
                                                </Button>
                                                <Button
                                                    size="icon"
                                                    variant="ghost"
                                                    className={`h-8 w-8 ${feedbackMap[m.id] === -1 ? "text-confidence-low" : ""}`}
                                                    onClick={() => submitFeedback(m.id, -1)}
                                                    data-testid={`feedback-down-${m.id}`}
                                                >
                                                    <ThumbsDown size={14} weight={feedbackMap[m.id] === -1 ? "fill" : "regular"} />
                                                </Button>
                                                <Button
                                                    size="icon"
                                                    variant="ghost"
                                                    className="h-8 w-8"
                                                    onClick={() => copyMsg(m.content)}
                                                    data-testid={`copy-message-${m.id}`}
                                                >
                                                    <Copy size={14} />
                                                </Button>
                                            </div>
                                        )}

                                        {m.citations?.length > 0 && !m.streaming && (
                                            <div className="mt-4 space-y-1 text-xs">
                                                <div className="dc-overline mb-2">Sources</div>
                                                {m.citations.map((c) => (
                                                    <button
                                                        key={c.chunk_id}
                                                        onClick={() => setActiveCite(c)}
                                                        className="flex items-center gap-2 text-left w-full py-1.5 px-2 hover:bg-secondary/50 border border-border rounded-sm transition-colors"
                                                        data-testid={`source-${c.index}`}
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
                            <div className="ml-5" data-testid="followup-suggestions">
                                <div className="dc-overline mb-2">Follow-ups</div>
                                <div className="flex flex-wrap gap-2">
                                    {followups.map((f, i) => (
                                        <button
                                            key={i}
                                            onClick={() => send(f)}
                                            className="text-sm border border-border px-3 py-1.5 hover:border-brand-primary hover:bg-secondary/50 transition-colors"
                                            data-testid={`followup-${i}`}
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

                <div className="border-t border-border p-4">
                    <form
                        onSubmit={(e) => { e.preventDefault(); send(); }}
                        className="max-w-3xl mx-auto flex items-end gap-2"
                        data-testid="chat-form"
                    >
                        <Textarea
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter" && !e.shiftKey) {
                                    e.preventDefault();
                                    send();
                                }
                            }}
                            placeholder={docCount === 0 ? "Upload a document first…" : "Ask about your documents… (Shift+Enter for newline)"}
                            rows={2}
                            disabled={streaming || docCount === 0}
                            className="resize-none font-sans"
                            data-testid="chat-input"
                        />
                        <Button type="submit" disabled={streaming || !input.trim() || docCount === 0} className="h-11" data-testid="chat-send-button">
                            <PaperPlaneRight size={16} weight="fill" />
                        </Button>
                    </form>
                </div>
            </div>

            <CitationPanel citation={activeCite} onClose={() => setActiveCite(null)} />
        </div>
    );
}
