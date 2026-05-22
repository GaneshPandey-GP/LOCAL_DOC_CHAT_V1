import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const FLAG_DESCRIPTIONS = {
    ENABLE_HYBRID_SEARCH: "Combine vector + keyword (BM25) search for better recall",
    ENABLE_RERANKING: "Re-rank retrieved chunks with a cross-encoder for higher precision",
    ENABLE_QUERY_REWRITING: "LLM rewrites ambiguous queries before retrieval",
    ENABLE_MULTI_QUERY_EXPANSION: "Generate multiple query variants and union results",
    ENABLE_STREAMING: "Stream LLM tokens to the UI in real time",
    ENABLE_CONFIDENCE_SCORING: "Show HIGH / MEDIUM / LOW confidence badge on answers",
    ENABLE_HALLUCINATION_DETECTION: "Post-generation grounding check against retrieved context",
    ENABLE_OCR: "Basic OCR on image-only pages",
    ENABLE_TABLE_EXTRACTION: "Structured table parsing from PDF, DOCX, and PPTX",
    ENABLE_ENTITY_EXTRACTION: "Extract named entities and index them as metadata",
    ENABLE_PII_MASKING: "Redact PII (names, emails, phone numbers) before indexing",
    ENABLE_RBAC: "Role-based access control on documents",
    ENABLE_SHARE_LINKS: "Allow users to create shareable chat links",
    ENABLE_EMBEDDING_CACHE: "Cache embedding vectors to reduce API calls",
    ENABLE_QUERY_CACHE: "Semantic cache for repeated / similar queries",
    ENABLE_BACKGROUND_INGESTION: "Process uploaded documents asynchronously in background",
    ENABLE_ANALYTICS_DASHBOARD: "Show usage analytics in admin panel",
    ENABLE_AUDIT_LOG: "Log every query, retrieval, and response for compliance",
    ENABLE_PPTX_SUPPORT: "Support PowerPoint (.pptx) file ingestion",
    ENABLE_EXCEL_SUPPORT: "Support Excel (.xlsx) and CSV file ingestion",
    ENABLE_IMAGE_OCR: "OCR on standalone image files (.png, .jpg)",
    ENABLE_SCANNED_PDF_OCR: "Full-page OCR fallback for scanned/image-only PDFs",
    ENABLE_GOOGLE_SLIDES: "Google Slides ingestion (requires API credentials)",
    ENABLE_ADVANCED_OCR: "Multi-pass OCR with preprocessing for better accuracy",
    ENABLE_IMAGE_IN_PDF_OCR: "Extract and OCR images embedded inside PDF pages",
    ENABLE_PPTX_IMAGE_OCR: "OCR images embedded in PowerPoint slides",
    ENABLE_VISION_LLM_FOR_PDF_IMAGES:
        "Use Claude Vision to describe charts/diagrams in PDFs (requires ANTHROPIC_API_KEY)",
    ENABLE_EMBED_WIDGET: "Allow embedding the chat widget in external websites",
};

const FLAG_GROUPS = {
    "Retrieval & Search": [
        "ENABLE_HYBRID_SEARCH",
        "ENABLE_RERANKING",
        "ENABLE_QUERY_REWRITING",
        "ENABLE_MULTI_QUERY_EXPANSION",
    ],
    "Answer Quality": [
        "ENABLE_STREAMING",
        "ENABLE_CONFIDENCE_SCORING",
        "ENABLE_HALLUCINATION_DETECTION",
    ],
    "Document Extraction": [
        "ENABLE_OCR",
        "ENABLE_TABLE_EXTRACTION",
        "ENABLE_ENTITY_EXTRACTION",
        "ENABLE_IMAGE_OCR",
        "ENABLE_SCANNED_PDF_OCR",
        "ENABLE_ADVANCED_OCR",
        "ENABLE_IMAGE_IN_PDF_OCR",
        "ENABLE_PPTX_IMAGE_OCR",
        "ENABLE_VISION_LLM_FOR_PDF_IMAGES",
    ],
    "File Format Support": [
        "ENABLE_PPTX_SUPPORT",
        "ENABLE_EXCEL_SUPPORT",
        "ENABLE_GOOGLE_SLIDES",
    ],
    "Security & Compliance": [
        "ENABLE_PII_MASKING",
        "ENABLE_RBAC",
        "ENABLE_AUDIT_LOG",
    ],
    Performance: [
        "ENABLE_EMBEDDING_CACHE",
        "ENABLE_QUERY_CACHE",
        "ENABLE_BACKGROUND_INGESTION",
    ],
    Platform: [
        "ENABLE_SHARE_LINKS",
        "ENABLE_ANALYTICS_DASHBOARD",
        "ENABLE_EMBED_WIDGET",
    ],
};

export default function AdminFlags() {
    const [flags, setFlags] = useState({});
    const [overrides, setOverrides] = useState({});
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(null);

    const fetchFlags = useCallback(async () => {
        try {
            const res = await api.get("/admin/flags/");
            setFlags(res.data.flags || {});
            setOverrides(res.data.overrides || {});
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Failed to load feature flags");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchFlags();
    }, [fetchFlags]);

    const toggleFlag = async (flagName, newValue) => {
        setSaving(flagName);
        try {
            await api.patch(`/admin/flags/${flagName}`, { value: newValue });
            setFlags((prev) => ({ ...prev, [flagName]: newValue }));
            setOverrides((prev) => ({ ...prev, [flagName]: newValue }));
            toast.success(`${flagName} ${newValue ? "enabled" : "disabled"}`);
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Failed to update flag");
        } finally {
            setSaving(null);
        }
    };

    const resetAll = async () => {
        try {
            await api.post("/admin/flags/reset");
            toast.success("All overrides cleared — defaults restored");
            fetchFlags();
        } catch (err) {
            toast.error(err?.response?.data?.detail || "Reset failed");
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-primary" />
            </div>
        );
    }

    return (
        <div className="p-8 max-w-4xl mx-auto space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <div className="dc-overline">Admin</div>
                    <h1 className="font-heading font-bold text-2xl">Feature Flags</h1>
                    <p className="text-sm text-muted-foreground mt-1">
                        Toggle features at runtime. Changes take effect immediately but reset on
                        server restart unless persisted to{" "}
                        <code className="bg-secondary px-1 rounded text-xs">.env</code>.
                    </p>
                </div>
                <Button variant="outline" size="sm" onClick={resetAll}>
                    Reset all to defaults
                </Button>
            </div>

            {/* Groups */}
            {Object.entries(FLAG_GROUPS).map(([groupName, flagKeys]) => {
                const visibleKeys = flagKeys.filter((k) => k in flags);
                if (!visibleKeys.length) return null;
                return (
                    <div key={groupName} className="border border-border">
                        <div className="px-4 py-2.5 bg-secondary/50 border-b border-border">
                            <h2 className="dc-overline">{groupName}</h2>
                        </div>
                        <div className="divide-y divide-border">
                            {visibleKeys.map((flagName) => {
                                const isOn = flags[flagName];
                                const isOverridden = flagName in overrides;
                                const isSaving = saving === flagName;
                                return (
                                    <div
                                        key={flagName}
                                        className="flex items-center justify-between px-4 py-3 gap-4"
                                    >
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <span className="font-mono text-sm font-medium">
                                                    {flagName}
                                                </span>
                                                {isOverridden && (
                                                    <Badge
                                                        variant="outline"
                                                        className="text-[10px] text-amber-600 border-amber-400"
                                                    >
                                                        runtime override
                                                    </Badge>
                                                )}
                                            </div>
                                            <p className="text-xs text-muted-foreground mt-0.5">
                                                {FLAG_DESCRIPTIONS[flagName] ||
                                                    "No description available"}
                                            </p>
                                        </div>
                                        <Switch
                                            checked={!!isOn}
                                            disabled={isSaving}
                                            onCheckedChange={(val) => toggleFlag(flagName, val)}
                                            aria-label={flagName}
                                        />
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                );
            })}

            {/* Footer note */}
            <p className="text-xs text-muted-foreground text-center pb-4">
                ⚠ Some flags (e.g. ENABLE_VISION_LLM_FOR_PDF_IMAGES) require environment
                variables to be set before they take effect. Enabling them without the required
                keys causes graceful failures, not crashes.
            </p>
        </div>
    );
}
