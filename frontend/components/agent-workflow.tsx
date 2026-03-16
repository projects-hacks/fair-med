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
  Wrench
} from "lucide-react";
import { cn } from "@/lib/utils";
import { AgentName, AgentStatus, AgentEvent, ToolCall } from "@/lib/types";
import { useState } from "react";

const AGENT_CONFIG: Record<AgentName, { label: string; icon: React.ElementType; description: string }> = {
  triage: { 
    label: "Triage", 
    icon: Search, 
    description: "Initial bill review and red flag detection" 
  },
  parser: { 
    label: "Parser", 
    icon: FileSearch, 
    description: "Extract CPT codes, diagnoses, and charges" 
  },
  pricing: { 
    label: "Pricing", 
    icon: DollarSign, 
    description: "Compare against Medicare fair rates" 
  },
  auditor: { 
    label: "Auditor", 
    icon: ShieldAlert, 
    description: "Detect billing errors and fraud patterns" 
  },
  researcher: { 
    label: "Researcher", 
    icon: BookOpen, 
    description: "Research patient rights and regulations" 
  },
  factchecker: { 
    label: "Fact Checker", 
    icon: CheckCircle2, 
    description: "Verify legal references and claims" 
  },
  writer: { 
    label: "Writer", 
    icon: PenTool, 
    description: "Generate dispute letter" 
  },
};

const AGENT_ORDER: AgentName[] = ["triage", "parser", "pricing", "auditor", "researcher", "factchecker", "writer"];

interface AgentWorkflowProps {
  events: AgentEvent[];
  currentAgent: AgentName | null;
}

function StatusIcon({ status }: { status: AgentStatus }) {
  switch (status) {
    case "running":
      return <Loader2 className="h-4 w-4 animate-spin text-primary" />;
    case "complete":
      return <CheckCircle className="h-4 w-4 text-success" />;
    case "error":
      return <XCircle className="h-4 w-4 text-destructive" />;
    case "skipped":
      return <Circle className="h-4 w-4 text-muted-foreground/50" />;
    default:
      return <Circle className="h-4 w-4 text-muted-foreground" />;
  }
}

function ToolCallDisplay({ toolCall }: { toolCall: ToolCall }) {
  const [expanded, setExpanded] = useState(false);
  
  return (
    <div className="border-l-2 border-accent/30 pl-3 py-1">
      <button 
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors w-full text-left"
      >
        <Wrench className="h-3 w-3 text-accent" />
        <span className="font-mono">{toolCall.name}</span>
        {expanded ? <ChevronDown className="h-3 w-3 ml-auto" /> : <ChevronRight className="h-3 w-3 ml-auto" />}
      </button>
      {expanded && (
        <div className="mt-2 space-y-2 text-xs">
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

function AgentCard({ 
  agent, 
  event, 
  isActive 
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

  return (
    <div 
      className={cn(
        "border rounded-lg p-3 transition-all",
        isActive && "border-primary bg-primary/5",
        status === "complete" && "border-success/30 bg-success/5",
        status === "error" && "border-destructive/30 bg-destructive/5",
        status === "skipped" && "opacity-50"
      )}
    >
      <div className="flex items-start gap-3">
        <div className={cn(
          "h-8 w-8 rounded-md flex items-center justify-center shrink-0",
          isActive ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground"
        )}>
          <Icon className="h-4 w-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm">{config.label}</span>
            <StatusIcon status={status} />
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">{config.description}</p>
          
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
        <div className="mt-3 space-y-3 pl-11">
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
                <ToolCallDisplay key={i} toolCall={tc} />
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
  const progress = AGENT_ORDER.length > 0 ? (completedCount / AGENT_ORDER.length) * 100 : 0;

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Agent Workflow</CardTitle>
          <span className="text-sm text-muted-foreground">
            {completedCount}/{AGENT_ORDER.length} complete
          </span>
        </div>
        <div className="h-1.5 bg-muted rounded-full mt-3 overflow-hidden">
          <div 
            className="h-full bg-primary transition-all duration-500 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
      </CardHeader>
      <CardContent className="flex-1 overflow-y-auto">
        <div className="space-y-2">
          {AGENT_ORDER.map((agent) => (
            <AgentCard
              key={agent}
              agent={agent}
              event={eventMap.get(agent)}
              isActive={currentAgent === agent}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
