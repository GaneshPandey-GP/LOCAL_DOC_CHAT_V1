import React from "react";

const variants = {
    HIGH: { label: "High Confidence", cls: "dc-confidence-high", dot: "bg-confidence-high" },
    MEDIUM: { label: "Medium Confidence", cls: "dc-confidence-medium", dot: "bg-confidence-medium" },
    LOW: { label: "Low Confidence", cls: "dc-confidence-low", dot: "bg-confidence-low" },
};

export default function ConfidenceBadge({ level = "MEDIUM" }) {
    const v = variants[level] || variants.MEDIUM;
    return (
        <span
            className={`inline-flex items-center gap-1.5 border px-2 py-0.5 rounded-sm text-[11px] font-mono font-semibold uppercase tracking-wider ${v.cls}`}
            title={v.label}
            data-testid={`confidence-badge-${level.toLowerCase()}`}
        >
            <span className={`w-1.5 h-1.5 rounded-full ${v.dot}`} />
            {level}
        </span>
    );
}
