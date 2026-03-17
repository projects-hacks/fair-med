"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Search,
  FileSearch,
  DollarSign,
  ShieldAlert,
  BookOpen,
  CheckCircle2,
  PenTool,
  Circle,
  CheckCircle,
  XCircle,
  Loader2,
  ChevronDown,
  ChevronRight,
  Wrench,
  Zap,
  Clock,
  ArrowDown,
  AlertTriangle,
  Ban,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { AgentName, AgentStatus, AgentEvent, ToolCall } from "@/lib/types";
import { useState, useEffect, useRef } from "react";

const AGENT_CONFIG: Record<AgentName, { label: string; icon: React.ElementType; description: string; phase: 1 | 2 }> = {
  triage: {
    label: "Triage",
    icon: Search,
    description: "Initial bill review and red flag detection",
    phase: 1,
  },
  parser: {
    label: "Parser",
    icon: FileSearch,
    description: "Extract CPT codes, diagnoses, and charges",
    phase: 1,
  },
  pricing: {
    label: "Pricing",
    icon: DollarSign,
    description: "Compare against Medicare fair rates",
    phase: 1,
  },
  auditor: {
    label: "Auditor",
    icon: ShieldAlert,
    description: "Detect billing errors and fraud patterns",
    phase: 1,
  },
  researcher: {
    label: "Researcher",
    icon: BookOpen,
    description: "Research patient rights and regulations",
    phase: 2,
  },
  factchecker: {
    label: "Fact Checker",
    icon: CheckCircle2,
    description: "Verify legal references and claims",
    phase: 2,
  },
  writer: {
    label: "Writer",
    icon: PenTool,
    description: "Generate dispute letter",
    phase: 2,
  },
};

const AGENT_ORDER: AgentName[] = ["triage", "parser", "pricing", "auditor", "researcher", "factchecker", "writer"];

interface AgentWorkflowProps {
  events: AgentEvent[];
  currentAgent: AgentName | null;
}

function ElapsedTimer({ startTime }: { startTime: string }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = new Date(startTime).getTime();
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [startTime]);

  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;

  return (
    <span className="text-xs font-mono text-primary tabular-nums flex items-center gap-1">
      <Clock className="h-3 w-3" />
      {mins > 0 ? `${mins}m ` : ""}{secs}s
      <span className="animate-cursor">|</span>
    </span>
  );
}

function StatusIcon({ status }: { status: AgentStatus }) {
  switch (status) {
    case "running":
      return (
        <div className="relative">
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
          <div className="absolute inset-0 animate-ripple rounded-full" />
        </div>
      );
    case "complete":
      return <CheckCircle className="h-4 w-4 text-success animate-check-pop" />;
    case "error":
      return <XCircle className="h-4 w-4 text-destructive" />;
    case "skipped":
      return <Circle className="h-4 w-4 text-muted-foreground/30" />;
    default:
      return <Circle className="h-4 w-4 text-muted-foreground/50" />;
  }
}

function ToolCallDisplay({ toolCall, index }: { toolCall: ToolCall; index: number }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="border-l-2 border-accent/30 pl-3 py-1 animate-slide-in"
      style={{ animationDelay: `${index * 100}ms` }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors w-full text-left"
      >
        <Wrench className="h-3 w-3 text-accent" />
        <span className="font-mono">{toolCall.name}</span>
        {expanded ? <ChevronDown className="h-3 w-3 ml-auto" /> : <ChevronRight className="h-3 w-3 ml-auto" />}
      </button>
      {expanded && (
        <div className="mt-2 space-y-2 text-xs animate-fade-in-up">
          <div>
            <span className="text-muted-foreground">Input:</span>
            <pre className="mt-1 p-2 bg-muted rounded text-xs overflow-x-auto font-mono">
              {JSON.stringify(toolCall.input, null, 2)}
            </pre>
          </div>
          {toolCall.output && (
            <div>
              <span className="text-muted-foreground">Output:</span>
              <pre className="mt-1 p-2 bg-muted rounded text-xs overflow-x-auto font-mono max-h-32 overflow-y-auto">
                {toolCall.output}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PipelineConnector({
  fromStatus,
  toStatus
}: {
  fromStatus: AgentStatus;
  toStatus: AgentStatus;
}) {
  const isFlowing = fromStatus === "complete" && toStatus === "running";
  const isComplete = fromStatus === "complete" && (toStatus === "complete" || toStatus === "skipped");

  return (
    <div className="flex justify-center py-0.5">
      <div className={cn(
        "w-0.5 h-5 rounded-full transition-all duration-500",
        isFlowing && "animate-flow w-0.5",
        isComplete && "bg-success/40",
        !isFlowing && !isComplete && "bg-border/50"
      )} />
    </div>
  );
}

function AgentCard({
  agent,
  event,
  isActive,
}: {
  agent: AgentName;
  event?: AgentEvent;
  isActive: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const config = AGENT_CONFIG[agent];
  const Icon = config.icon;
  const status = event?.status || "idle";
  const hasDetails = event?.reasoning || (event?.tool_calls && event.tool_calls.length > 0);
  const cardRef = useRef<HTMLDivElement>(null);

  // Auto-scroll into view when agent becomes active
  useEffect(() => {
    if (isActive && cardRef.current) {
      cardRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [isActive]);

  // Auto-expand when running
  useEffect(() => {
    if (isActive) setExpanded(true);
  }, [isActive]);

  return (
    <div
      ref={cardRef}
      className={cn(
        "border rounded-lg p-3 transition-all duration-300 relative overflow-hidden",
        isActive && "border-primary/60 animate-glow",
        isActive && "animate-shimmer",
        status === "complete" && "border-success/30 bg-success/5",
        status === "error" && "border-destructive/30 bg-destructive/5",
        status === "skipped" && "opacity-40",
        status === "idle" && "opacity-60"
      )}
    >
      {/* Active indicator bar */}
      {isActive && (
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-primary to-transparent" />
      )}

      <div className="flex items-start gap-3">
        {/* Agent icon with status ring */}
        <div className={cn(
          "h-9 w-9 rounded-lg flex items-center justify-center shrink-0 transition-all duration-300 relative",
          isActive && "bg-primary/20 text-primary scale-110",
          status === "complete" && "bg-success/15 text-success",
          status === "error" && "bg-destructive/15 text-destructive",
          status === "idle" && "bg-muted text-muted-foreground",
          status === "skipped" && "bg-muted/50 text-muted-foreground/50"
        )}>
          <Icon className="h-4 w-4" />
          {isActive && (
            <span className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-primary animate-pulse-dot" />
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={cn(
              "font-medium text-sm transition-colors",
              isActive && "text-primary",
              status === "complete" && "text-success",
            )}>{config.label}</span>
            <StatusIcon status={status} />

            {/* Live elapsed time for running agent */}
            {isActive && event?.timestamp && (
              <div className="ml-auto">
                <ElapsedTimer startTime={event.timestamp} />
              </div>
            )}

            {/* Completion badge */}
            {status === "complete" && !isActive && (
              <span className="ml-auto text-xs text-success/70 font-mono">done</span>
            )}
          </div>
          <p className={cn(
            "text-xs mt-0.5 transition-colors",
            isActive ? "text-foreground/70" : "text-muted-foreground"
          )}>{config.description}</p>

          {/* Live reasoning preview (shows while running) */}
          {isActive && event?.reasoning && !expanded && (
            <p className="text-xs text-primary/70 mt-2 line-clamp-2 italic">
              {event.reasoning.slice(0, 120)}...
            </p>
          )}

          {hasDetails && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 text-xs text-primary mt-2 hover:underline"
            >
              {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              {expanded ? "Hide details" : "Show reasoning"}
            </button>
          )}
        </div>
      </div>

      {expanded && hasDetails && (
        <div className="mt-3 space-y-3 pl-12 animate-fade-in-up">
          {event?.reasoning && (
            <div className="text-xs">
              <span className="text-muted-foreground font-medium">Reasoning:</span>
              <p className="mt-1 text-foreground/80 leading-relaxed">{event.reasoning}</p>
            </div>
          )}
          {event?.tool_calls && event.tool_calls.length > 0 && (
            <div className="space-y-2">
              <span className="text-xs text-muted-foreground font-medium">Tool Calls:</span>
              {event.tool_calls.map((tc, i) => (
                <ToolCallDisplay key={i} toolCall={tc} index={i} />
              ))}
            </div>
          )}
          {event?.error && (
            <div className="text-xs text-destructive">
              <span className="font-medium">Error:</span> {event.error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function AgentWorkflow({ events, currentAgent }: AgentWorkflowProps) {
  const eventMap = new Map(events.map(e => [e.agent, e]));

  const completedCount = events.filter(e => e.status === "complete").length;
  const skippedCount = events.filter(e => e.status === "skipped").length;
  const totalActive = AGENT_ORDER.length - skippedCount;
  const progress = totalActive > 0 ? (completedCount / totalActive) * 100 : 0;
  const isRunning = currentAgent !== null;
  const isComplete = completedCount + skippedCount === AGENT_ORDER.length && events.length > 0;

  // Phase tracking
  const phase1Agents: AgentName[] = ["triage", "parser", "pricing", "auditor"];
  const phase2Agents: AgentName[] = ["researcher", "factchecker", "writer"];
  const phase1Done = phase1Agents.every(a => {
    const ev = eventMap.get(a);
    return ev && (ev.status === "complete" || ev.status === "skipped");
  });
  const phase2Started = phase2Agents.some(a => eventMap.has(a));
  const phase2Skipped = phase2Agents.every(a => eventMap.get(a)?.status === "skipped");
  const phase2Done = phase2Agents.every(a => {
    const ev = eventMap.get(a);
    return ev && (ev.status === "complete" || ev.status === "skipped");
  });

  // Extract error count from auditor's completed output
  const auditorEvent = eventMap.get("auditor");
  const errorsFound = auditorEvent?.status === "complete"
    ? (auditorEvent.output?.error_count as number ?? 0)
    : -1; // -1 means auditor hasn't finished yet

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <Zap className={cn(
              "h-4 w-4 transition-colors",
              isRunning ? "text-primary animate-pulse-dot" : isComplete ? "text-success" : "text-muted-foreground"
            )} />
            Agent Pipeline
          </CardTitle>
          <span className={cn(
            "text-sm font-mono tabular-nums",
            isComplete ? "text-success" : "text-muted-foreground"
          )}>
            {completedCount}/{totalActive}
          </span>
        </div>

        {/* Animated progress bar */}
        <div className="h-2 bg-muted rounded-full mt-3 overflow-hidden relative">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-700 ease-out relative",
              isComplete
                ? "bg-success"
                : "bg-gradient-to-r from-primary to-accent"
            )}
            style={{ width: `${progress}%` }}
          >
            {isRunning && (
              <div className="absolute inset-0 animate-progress-stripe rounded-full" />
            )}
          </div>
        </div>

        {/* Status text */}
        {isRunning && currentAgent && (
          <p className="text-xs text-primary mt-2 flex items-center gap-1.5">
            <Loader2 className="h-3 w-3 animate-spin" />
            {AGENT_CONFIG[currentAgent].label} is analyzing...
          </p>
        )}
        {isComplete && (
          <p className="text-xs text-success mt-2 flex items-center gap-1.5 animate-fade-in-up">
            <CheckCircle className="h-3 w-3" />
            Analysis pipeline complete
          </p>
        )}
      </CardHeader>

      <CardContent className="flex-1 overflow-y-auto">
        <div>
          {/* Phase 1: Analysis */}
          <div className="mb-1">
            <div className="flex items-center gap-2 mb-2">
              <span className={cn(
                "text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full",
                phase1Done
                  ? "bg-success/15 text-success"
                  : isRunning && !phase2Started
                    ? "bg-primary/15 text-primary"
                    : "bg-muted text-muted-foreground"
              )}>
                Phase 1 — Analysis
              </span>
              {phase1Done && <CheckCircle className="h-3 w-3 text-success animate-check-pop" />}
            </div>

            {phase1Agents.map((agent, idx) => (
              <div key={agent}>
                <AgentCard
                  agent={agent}
                  event={eventMap.get(agent)}
                  isActive={currentAgent === agent}
                />
                {idx < phase1Agents.length - 1 && (
                  <PipelineConnector
                    fromStatus={eventMap.get(phase1Agents[idx])?.status || "idle"}
                    toStatus={eventMap.get(phase1Agents[idx + 1])?.status || "idle"}
                  />
                )}
              </div>
            ))}
          </div>

          {/* Phase transition banner */}
          {phase1Done && errorsFound > 0 && !phase2Skipped && (
            <div className="my-3 animate-fade-in-up">
              <div className="rounded-lg border border-warning/30 bg-warning/5 p-3">
                <div className="flex items-center gap-2 mb-1">
                  <AlertTriangle className="h-4 w-4 text-warning" />
                  <span className="text-sm font-medium text-warning">
                    {errorsFound} billing error{errorsFound > 1 ? "s" : ""} detected
                  </span>
                </div>
                <p className="text-xs text-muted-foreground pl-6">
                  Proceeding to Phase 2 to research your rights and generate a dispute letter.
                </p>
              </div>
            </div>
          )}

          {phase1Done && errorsFound === 0 && phase2Skipped && (
            <div className="my-3 animate-fade-in-up">
              <div className="rounded-lg border border-success/30 bg-success/5 p-3">
                <div className="flex items-center gap-2 mb-1">
                  <CheckCircle className="h-4 w-4 text-success" />
                  <span className="text-sm font-medium text-success">
                    No billing errors found
                  </span>
                </div>
                <p className="text-xs text-muted-foreground pl-6">
                  Your bill appears accurate. Skipping dispute phase.
                </p>
              </div>
            </div>
          )}

          {!phase1Done && (
            <div className="flex items-center gap-2 my-3">
              <div className="flex-1 h-px bg-border" />
              <ArrowDown className="h-3.5 w-3.5 text-muted-foreground/30" />
              <div className="flex-1 h-px bg-border" />
            </div>
          )}

          {/* Phase 2: Dispute */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className={cn(
                "text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full",
                phase2Skipped
                  ? "bg-muted text-muted-foreground/40"
                  : phase2Done
                    ? "bg-success/15 text-success"
                    : phase2Started
                      ? "bg-primary/15 text-primary"
                      : "bg-muted text-muted-foreground/50"
              )}>
                Phase 2 — Dispute
              </span>
              {phase2Skipped && (
                <Ban className="h-3 w-3 text-muted-foreground/40" />
              )}
            </div>

            {phase2Agents.map((agent, idx) => (
              <div key={agent}>
                <AgentCard
                  agent={agent}
                  event={eventMap.get(agent)}
                  isActive={currentAgent === agent}
                />
                {idx < phase2Agents.length - 1 && (
                  <PipelineConnector
                    fromStatus={eventMap.get(phase2Agents[idx])?.status || "idle"}
                    toStatus={eventMap.get(phase2Agents[idx + 1])?.status || "idle"}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
