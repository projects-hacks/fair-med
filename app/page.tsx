"use client";

import { useState, useCallback, useRef } from "react";
import { Header } from "@/components/header";
import { BillInput } from "@/components/bill-input";
import { AgentWorkflow } from "@/components/agent-workflow";
import { ResultsPanel } from "@/components/results-panel";
import { AgentEvent, AgentName, AnalysisResult, DisputeLetterStatus } from "@/lib/types";

const BACKEND_URL = "http://23.239.6.35";

// Agent sequence for visualization
const AGENT_SEQUENCE: AgentName[] = ["triage", "parser", "pricing", "auditor", "researcher", "factchecker", "writer"];

export default function Home() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [agentEvents, setAgentEvents] = useState<AgentEvent[]>([]);
  const [currentAgent, setCurrentAgent] = useState<AgentName | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [disputeStatus, setDisputeStatus] = useState<DisputeLetterStatus | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // Simulate agent progression based on poll status
  const updateAgentProgress = useCallback((status: string, agentsUsed?: AgentName[]) => {
    if (status === "pending") {
      // Starting - show triage as running
      setCurrentAgent("triage");
      setAgentEvents([{ agent: "triage", status: "running", timestamp: new Date().toISOString() }]);
    } else if (status === "running") {
      // Progress through agents based on time/status
      setAgentEvents(prev => {
        const completed = prev.filter(e => e.status === "complete").length;
        const nextIdx = Math.min(completed + 1, AGENT_SEQUENCE.length - 1);
        const nextAgent = AGENT_SEQUENCE[nextIdx];
        
        // Mark previous as complete, current as running
        const updated = AGENT_SEQUENCE.slice(0, nextIdx).map(agent => ({
          agent,
          status: "complete" as const,
          timestamp: new Date().toISOString()
        }));
        
        updated.push({ agent: nextAgent, status: "running", timestamp: new Date().toISOString() });
        setCurrentAgent(nextAgent);
        return updated;
      });
    } else if (status === "completed" && agentsUsed) {
      // All done - mark all used agents as complete
      setCurrentAgent(null);
      setAgentEvents(agentsUsed.map(agent => ({
        agent,
        status: "complete",
        timestamp: new Date().toISOString()
      })));
    }
  }, []);

  const handleAnalyze = useCallback(async (data: { text?: string; file?: File }) => {
    setIsAnalyzing(true);
    setAgentEvents([]);
    setCurrentAgent(null);
    setResult(null);
    setDisputeStatus(null);
    setJobId(null);

    // Clear any existing polling
    if (pollingRef.current) {
      clearTimeout(pollingRef.current);
    }

    try {
      // Start analysis - POST /api/analyze
      const response = await fetch(`${BACKEND_URL}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bill_text: data.text || "" }),
      });

      if (!response.ok) {
        throw new Error(`Analysis failed: ${response.statusText}`);
      }

      const { job_id } = await response.json();
      setJobId(job_id);
      updateAgentProgress("pending");

      // Poll for results - GET /api/analyze/{job_id}
      const pollResults = async () => {
        try {
          const statusResponse = await fetch(`${BACKEND_URL}/api/analyze/${job_id}`);
          const statusData = await statusResponse.json();

          if (statusData.status === "completed") {
            // Transform backend response to our format
            const analysisResult: AnalysisResult = {
              session_id: job_id,
              status: "complete",
              total_billed: statusData.total_billed || 0,
              total_fair: statusData.total_fair || 0,
              total_overcharge: statusData.total_overcharge || 0,
              error_count: statusData.error_count || 0,
              parsed_charges: statusData.parsed_charges || [],
              pricing_results: statusData.pricing_results || [],
              audit_findings: statusData.audit_findings || statusData.errors_found || [],
              agents_used: statusData.agents_used || AGENT_SEQUENCE,
            };
            
            setResult(analysisResult);
            updateAgentProgress("completed", analysisResult.agents_used);
            setIsAnalyzing(false);
          } else if (statusData.status === "error" || statusData.status === "failed") {
            console.error("Analysis failed:", statusData.error);
            setIsAnalyzing(false);
          } else {
            // Still running - update progress and continue polling
            updateAgentProgress(statusData.status);
            pollingRef.current = setTimeout(pollResults, 1500);
          }
        } catch (pollError) {
          console.error("Polling error:", pollError);
          pollingRef.current = setTimeout(pollResults, 2000);
        }
      };

      // Start polling
      pollingRef.current = setTimeout(pollResults, 1000);

    } catch (error) {
      console.error("Analysis error:", error);
      setIsAnalyzing(false);
    }
  }, [updateAgentProgress]);

  const handleGenerateDispute = useCallback(async () => {
    if (!jobId) return;

    setDisputeStatus({ session_id: jobId, status: "pending" });

    try {
      // Trigger letter generation - POST /api/letter/{job_id}
      const response = await fetch(`${BACKEND_URL}/api/letter/${jobId}`, {
        method: "POST",
      });

      if (!response.ok) {
        throw new Error("Failed to start dispute generation");
      }

      // Poll for letter status - GET /api/letter/{job_id}
      const pollStatus = async () => {
        try {
          const statusResponse = await fetch(`${BACKEND_URL}/api/letter/${jobId}`);
          const statusData = await statusResponse.json();
          
          if (statusData.status === "ready" || statusData.status === "completed") {
            setDisputeStatus({
              session_id: jobId,
              status: "ready",
              download_url: statusData.download_url || statusData.letter_url || `${BACKEND_URL}/api/letter/${jobId}/download`,
            });
          } else if (statusData.status === "error" || statusData.status === "failed") {
            setDisputeStatus({
              session_id: jobId,
              status: "error",
              error: statusData.error || "Letter generation failed",
            });
          } else {
            setDisputeStatus({ session_id: jobId, status: "generating" });
            setTimeout(pollStatus, 2000);
          }
        } catch (pollError) {
          setTimeout(pollStatus, 2000);
        }
      };

      pollStatus();
    } catch (error) {
      setDisputeStatus({ 
        session_id: jobId, 
        status: "error", 
        error: error instanceof Error ? error.message : "Unknown error" 
      });
    }
  }, [jobId]);

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <Header />
      
      <main className="flex-1 container mx-auto px-4 py-6">
        <div className="grid lg:grid-cols-3 gap-6 h-[calc(100vh-8rem)]">
          {/* Left: Bill Input */}
          <div className="lg:col-span-1">
            <BillInput onSubmit={handleAnalyze} isLoading={isAnalyzing} />
          </div>

          {/* Middle: Agent Workflow */}
          <div className="lg:col-span-1">
            <AgentWorkflow events={agentEvents} currentAgent={currentAgent} />
          </div>

          {/* Right: Results */}
          <div className="lg:col-span-1">
            {result ? (
              <ResultsPanel 
                result={result} 
                disputeStatus={disputeStatus}
                onGenerateDispute={handleGenerateDispute}
              />
            ) : (
              <div className="h-full border rounded-lg bg-card flex items-center justify-center">
                <div className="text-center text-muted-foreground">
                  <p className="text-lg font-medium mb-1">No results yet</p>
                  <p className="text-sm">Upload a bill to start analysis</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
