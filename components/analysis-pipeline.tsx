"use client";

import { cn } from "@/lib/utils";
import type { AgentStep } from "@/lib/types";
import { CheckCircle, Circle, Loader2 } from "lucide-react";

interface AnalysisPipelineProps {
  steps: AgentStep[];
}

export function AnalysisPipeline({ steps }: AnalysisPipelineProps) {
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium text-muted-foreground">
        Analysis Pipeline
      </h3>
      <div className="space-y-2">
        {steps.map((step, index) => (
          <div
            key={step.name}
            className={cn(
              "flex items-center gap-3 rounded-lg border px-4 py-3 transition-all",
              step.status === "complete" && "border-success/30 bg-success/5",
              step.status === "running" &&
                "border-primary/50 bg-primary/5 animate-pulse-glow",
              step.status === "pending" && "border-border bg-muted/30",
              step.status === "error" && "border-destructive/30 bg-destructive/5"
            )}
          >
            <div className="flex-shrink-0">
              {step.status === "complete" && (
                <CheckCircle className="h-5 w-5 text-success" />
              )}
              {step.status === "running" && (
                <Loader2 className="h-5 w-5 text-primary animate-spin" />
              )}
              {step.status === "pending" && (
                <Circle className="h-5 w-5 text-muted-foreground" />
              )}
              {step.status === "error" && (
                <Circle className="h-5 w-5 text-destructive" />
              )}
            </div>
            <div className="flex-1">
              <span
                className={cn(
                  "text-sm font-medium",
                  step.status === "pending" && "text-muted-foreground",
                  step.status === "running" && "text-primary",
                  step.status === "complete" && "text-success",
                  step.status === "error" && "text-destructive"
                )}
              >
                {step.name}
              </span>
            </div>
            {step.duration && (
              <span className="text-xs text-muted-foreground">
                {step.duration.toFixed(1)}s
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
