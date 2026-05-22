import React, { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    UploadSimple,
    FilePdf,
    FileDoc,
    FileText,
    FileXls,
    FilePpt,
    Image as ImageIcon,
} from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";

const FORMAT_MAP = {
    pdf: { icon: FilePdf, label: "PDF", flag: null },
    docx: { icon: FileDoc, label: "DOCX", flag: null },
    txt: { icon: FileText, label: "Text", flag: null },
    md: { icon: FileText, label: "Markdown", flag: null },
    pptx: { icon: FilePpt, label: "PowerPoint", flag: "ENABLE_PPTX_SUPPORT" },
    xlsx: { icon: FileXls, label: "Excel", flag: "ENABLE_EXCEL_SUPPORT" },
    csv: { icon: FileXls, label: "CSV", flag: "ENABLE_EXCEL_SUPPORT" },
    png: { icon: ImageIcon, label: "Image (OCR)", flag: "ENABLE_IMAGE_OCR" },
    jpg: { icon: ImageIcon, label: "Image (OCR)", flag: "ENABLE_IMAGE_OCR" },
    jpeg: { icon: ImageIcon, label: "Image (OCR)", flag: "ENABLE_IMAGE_OCR" },
};

export default function UploadDialog({ open, onOpenChange, onUploaded }) {
    const [file, setFile] = useState(null);
    const [tags, setTags] = useState("");
    const [busy, setBusy] = useState(false);
    const [flags, setFlags] = useState({});

    useEffect(() => {
        if (!open) return;
        api.get("/v2/flags").then((r) => setFlags(r.data)).catch(() => {});
    }, [open]);

    const reset = () => { setFile(null); setTags(""); };
    const handleClose = (o) => { if (!o) reset(); onOpenChange(o); };

    const enabledFormats = Object.entries(FORMAT_MAP).filter(([ext, m]) => !m.flag || flags[m.flag]);
    const acceptStr = enabledFormats.map(([ext]) => `.${ext}`).join(",");

    const submit = async () => {
        if (!file) { toast.error("Choose a file"); return; }
        setBusy(true);
        try {
            const fd = new FormData();
            fd.append("file", file);
            fd.append("tags", tags);
            await api.post("/v2/documents/ingest", fd, { headers: { "Content-Type": "multipart/form-data" } });
            toast.success("Upload started — indexing in background");
            reset();
            onOpenChange(false);
            onUploaded?.();
        } catch (e) {
            const detail = e?.response?.data?.detail;
            if (e?.response?.status === 409 && detail?.code === "DUPLICATE") {
                toast.error("Document already exists", { duration: 6000 });
            } else {
                toast.error(typeof detail === "string" ? detail : "Upload failed");
            }
        } finally {
            setBusy(false);
        }
    };

    const ext = file ? file.name.split(".").pop().toLowerCase() : "";
    const meta = FORMAT_MAP[ext] || { icon: FileText, label: ext.toUpperCase() };
    const Icon = meta.icon;

    // Group enabled formats for display
    const uniqueLabels = [];
    const seen = new Set();
    enabledFormats.forEach(([, m]) => {
        if (!seen.has(m.label)) { seen.add(m.label); uniqueLabels.push(m.label); }
    });

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent data-testid="upload-dialog">
                <DialogHeader>
                    <DialogTitle className="font-heading text-2xl">Ingest Document</DialogTitle>
                    <DialogDescription>
                        Processing runs in the background. OCR-based formats take a bit longer.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4">
                    <label
                        htmlFor="file-input"
                        className="flex flex-col items-center justify-center border-2 border-dashed border-border hover:border-brand-primary transition-colors p-10 cursor-pointer"
                        data-testid="upload-dropzone"
                    >
                        {file ? (
                            <>
                                <Icon size={36} className="text-brand-primary" weight="duotone" />
                                <div className="mt-3 font-medium">{file.name}</div>
                                <div className="text-xs text-muted-foreground mt-1">
                                    {meta.label} · {(file.size / 1024).toFixed(1)} KB
                                </div>
                            </>
                        ) : (
                            <>
                                <UploadSimple size={36} className="text-muted-foreground" weight="duotone" />
                                <div className="mt-3 font-medium">Click to choose a file</div>
                                <div className="text-xs text-muted-foreground mt-1 font-mono max-w-md text-center">
                                    {uniqueLabels.join(" · ") || "Loading supported formats…"}
                                </div>
                            </>
                        )}
                        <input
                            id="file-input"
                            type="file"
                            accept={acceptStr || ".pdf,.docx,.txt,.md"}
                            className="hidden"
                            data-testid="upload-file-input"
                            onChange={(e) => setFile(e.target.files?.[0] || null)}
                        />
                    </label>

                    <div>
                        <Label htmlFor="tags" className="dc-overline">Tags (optional)</Label>
                        <Input
                            id="tags"
                            placeholder="legal, q4-2025, finance"
                            value={tags}
                            onChange={(e) => setTags(e.target.value)}
                            className="mt-1"
                            data-testid="upload-tags-input"
                        />
                    </div>

                    {ext && FORMAT_MAP[ext]?.flag && !flags[FORMAT_MAP[ext].flag] && (
                        <div className="text-xs bg-secondary border border-border p-3 text-muted-foreground" data-testid="upload-flag-warning">
                            This format requires <span className="dc-kbd">{FORMAT_MAP[ext].flag}</span> to be enabled. Ask an admin to flip the feature flag in <span className="font-mono">backend/.env</span>.
                        </div>
                    )}
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => handleClose(false)} data-testid="upload-cancel-button">Cancel</Button>
                    <Button onClick={submit} disabled={busy || !file} data-testid="upload-submit-button">
                        {busy ? "Uploading…" : "Ingest"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
