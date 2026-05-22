import React, { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Renders assistant markdown and replaces inline citations like [1], [2]
 * with clickable badges.
 */
export default function MarkdownMessage({ content, citations = [], onCite }) {
    // Replace [n] with a marker we can render as a span
    const transformed = useMemo(() => {
        if (!content) return "";
        // Replace all [n] where n is 1..N with placeholder
        return content.replace(/\[(\d+)\]/g, (m, n) => `\u200B[[CITE:${n}]]\u200B`);
    }, [content]);

    const renderText = (text) => {
        const parts = String(text).split(/(\u200B\[\[CITE:\d+\]\]\u200B)/g);
        return parts.map((p, i) => {
            const m = p.match(/\u200B\[\[CITE:(\d+)\]\]\u200B/);
            if (m) {
                const idx = parseInt(m[1], 10);
                const c = citations.find((x) => x.index === idx);
                return (
                    <span
                        key={i}
                        className="dc-cite"
                        data-testid={`citation-${idx}`}
                        onClick={() => c && onCite?.(c)}
                        role="button"
                        tabIndex={0}
                        title={c ? `${c.filename} · p.${c.page}` : `Source ${idx}`}
                    >
                        {idx}
                    </span>
                );
            }
            return <React.Fragment key={i}>{p}</React.Fragment>;
        });
    };

    return (
        <div className="dc-prose" data-testid="markdown-message">
            <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                    p: ({ children }) => <p>{React.Children.map(children, (c) => typeof c === "string" ? renderText(c) : c)}</p>,
                    li: ({ children }) => <li>{React.Children.map(children, (c) => typeof c === "string" ? renderText(c) : c)}</li>,
                    td: ({ children }) => <td>{React.Children.map(children, (c) => typeof c === "string" ? renderText(c) : c)}</td>,
                    a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
                }}
            >
                {transformed}
            </ReactMarkdown>
        </div>
    );
}
