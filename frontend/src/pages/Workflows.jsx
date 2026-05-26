import React from "react";
import { Lightning, Cpu, GitBranch } from "@phosphor-icons/react";
import { Badge } from "@/components/ui/badge";

/**
 * Coming-soon stub for the Workflow engine.
 * The backend tables (workflows, workflow_runs, tool_executions) already exist;
 * only the UI canvas + engine wiring is pending — tracked as P2 in ROADMAP.md.
 */
export default function Workflows() {
    return (
        <div data-testid="workflows-coming-soon">
            <header className="h-16 border-b border-border px-8 flex items-center justify-between sticky top-0 bg-background z-10">
                <div className="flex items-center gap-3">
                    <GitBranch size={22} weight="duotone" className="text-brand-primary" />
                    <div><div className="dc-overline">AI Studio</div><h1 className="font-heading font-bold text-lg">Workflows</h1></div>
                </div>
                <Badge variant="outline" className="text-[10px] font-mono">COMING SOON</Badge>
            </header>
            <div className="p-8 max-w-3xl">
                <div className="border border-dashed border-border p-12 text-center">
                    <Lightning size={42} weight="duotone" className="mx-auto text-brand-primary" />
                    <h2 className="font-heading font-bold text-2xl mt-4">Workflow Builder is coming soon</h2>
                    <p className="text-sm text-muted-foreground mt-2 max-w-md mx-auto">
                        Compose multi-step agents with MCP tools, retrieval, and human approvals.
                        The backend tables and the underlying graph engine are scaffolded — the visual
                        canvas + run orchestrator are next on the roadmap.
                    </p>
                    <div className="grid sm:grid-cols-3 gap-3 mt-8 text-left">
                        {[
                            { i: Lightning, t: "DAG Engine", d: "Sequential & parallel steps with retry policies." },
                            { i: Cpu, t: "MCP Tools", d: "Already live — use them from chat or share links." },
                            { i: GitBranch, t: "Approvals", d: "Pause & resume runs on human review." },
                        ].map(({ i: Icon, t, d }) => (
                            <div key={t} className="border border-border p-4">
                                <Icon size={20} weight="duotone" className="text-brand-primary" />
                                <div className="font-medium mt-2 text-sm">{t}</div>
                                <div className="text-xs text-muted-foreground mt-1">{d}</div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
