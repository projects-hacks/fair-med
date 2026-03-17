"use client";

import { useState, useCallback } from "react";
import { Header } from "@/components/header";
import { BillInput } from "@/components/bill-input";
import { AgentWorkflow } from "@/components/agent-workflow";
import { ResultsPanel } from "@/components/results-panel";
import { AgentEvent, AgentName, AnalysisResult, DisputeLetterStatus } from "@/lib/types";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "/api";

function getBackendCandidates(): string[] {
  if (typeof window !== "undefined" && window.location.protocol === "https:") {
    return ["/api"];
  }

  const candidates: string[] = [];
  if (BACKEND_URL) {
    candidates.push(BACKEND_URL.replace(/\/$/, ""));
  }
  if (!candidates.includes("/api")) {
    candidates.push("/api");
  }
  return candidates;
}

async function fetchFromBackend(path: string, init?: RequestInit): Promise<Response> {
  const bases = getBackendCandidates();
  let lastError: unknown = null;

  for (const base of bases) {
    try {
      const url = `${base}${path.startsWith("/") ? "" : "/"}${path}`;
      const response = await fetch(url, init);
      return response;
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError instanceof Error ? lastError : new Error("Failed to reach backend");
}

function toAbsoluteDownloadUrl(url?: string): string | undefined {
  if (!url) return url;

  const normalizePath = (path: string): string => {
    if (path.startsWith("/api/")) return path;
    if (path.startsWith("/dispute/")) return `/api${path}`;
    return path;
  };

  if (typeof window !== "undefined") {
    try {
      const parsed = new URL(url, window.location.origin);
      if (parsed.origin === window.location.origin) {
        return normalizePath(`${parsed.pathname}${parsed.search}`);
      }
    } catch {
      // keep fallback behavior below
    }
  }

  if (url.startsWith("/")) {
    return normalizePath(url);
  }

  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  const candidates = getBackendCandidates();
  const absoluteBase = candidates.find((c) => c.startsWith("http://") || c.startsWith("https://"));
  if (absoluteBase) {
    return `${absoluteBase.replace(/\/$/, "")}${url.startsWith("/") ? "" : "/"}${url}`;
  }
  return url;
}

export default function Home() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [agentEvents, setAgentEvents] = useState<AgentEvent[]>([]);
  const [currentAgent, setCurrentAgent] = useState<AgentName | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [disputeStatus, setDisputeStatus] = useState<DisputeLetterStatus | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const handleAnalyze = useCallback(async (data: { text?: string; file?: File }) => {
    setIsAnalyzing(true);
    setAgentEvents([]);
    setCurrentAgent(null);
    setResult(null);
    setDisputeStatus(null);

    try {
      // Create form data for file upload or text
      const formData = new FormData();
      if (data.file) {
        formData.append("file", data.file);
      } else if (data.text) {
        formData.append("bill_text", data.text);
      }

      // Use SSE endpoint for real-time updates
      const response = await fetchFromBackend(`/analyze/stream`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Analysis failed: ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error("No response body");
      }

      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const jsonStr = line.slice(6);
            if (jsonStr === "[DONE]") continue;

            try {
              const event = JSON.parse(jsonStr);
              
              switch (event.type) {
                case "session_start":
                  setSessionId(event.session_id);
                  break;
                  
                case "agent_start":
                  setCurrentAgent(event.agent);
                  setAgentEvents(prev => [
                    ...prev.filter(e => e.agent !== event.agent),
                    { agent: event.agent, status: "running", timestamp: new Date().toISOString() }
                  ]);
                  break;
                  
                case "agent_reasoning":
                  setAgentEvents(prev => prev.map(e => 
                    e.agent === event.agent 
                      ? { ...e, reasoning: event.reasoning }
                      : e
                  ));
                  break;
                  
                case "agent_tool_call":
                  setAgentEvents(prev => prev.map(e => 
                    e.agent === event.agent 
                      ? { ...e, tool_calls: [...(e.tool_calls || []), event.tool_call] }
                      : e
                  ));
                  break;
                  
                case "agent_complete":
                  setAgentEvents(prev => prev.map(e => 
                    e.agent === event.agent 
                      ? { ...e, status: "complete", output: event.output }
                      : e
                  ));
                  setCurrentAgent(null);
                  break;
                  
                case "agent_error":
                  setAgentEvents(prev => prev.map(e => 
                    e.agent === event.agent 
                      ? { ...e, status: "error", error: event.error }
                      : e
                  ));
                  setCurrentAgent(null);
                  break;
                  
                case "agent_skipped":
                  setAgentEvents(prev => [
                    ...prev.filter(e => e.agent !== event.agent),
                    { agent: event.agent, status: "skipped", timestamp: new Date().toISOString() }
                  ]);
                  break;
                  
                case "analysis_complete":
                  setResult(event.result);
                  setCurrentAgent(null);
                  break;
              }
            } catch (parseError) {
              console.error("Failed to parse SSE event:", parseError);
            }
          }
        }
      }
    } catch (error) {
      console.error("Analysis error:", error);
    } finally {
      setIsAnalyzing(false);
    }
  }, []);

  const handleDownloadLetter = useCallback(async (url: string) => {
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error("Download failed");
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = downloadUrl;
      a.download = "fairmed_dispute_letter.txt";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(downloadUrl);
    } catch (err) {
      console.error("Download error:", err);
      window.open(url, "_blank");
    }
  }, []);

  const handleGenerateDispute = useCallback(async () => {
    if (!sessionId) return;

    setDisputeStatus({ session_id: sessionId, status: "pending" });

    try {
      const response = await fetchFromBackend(`/dispute/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });

      if (!response.ok) {
        throw new Error("Failed to start dispute generation");
      }

      // Poll for status
      const pollStatus = async () => {
        const statusResponse = await fetchFromBackend(`/dispute/status/${sessionId}`);
        const statusData = await statusResponse.json();
        if (statusData?.download_url) {
          statusData.download_url = toAbsoluteDownloadUrl(statusData.download_url);
        }
        setDisputeStatus(statusData);

        if (statusData.status === "pending" || statusData.status === "generating") {
          setTimeout(pollStatus, 2000);
        }
      };

      pollStatus();
    } catch (error) {
      setDisputeStatus({ 
        session_id: sessionId, 
        status: "error", 
        error: error instanceof Error ? error.message : "Unknown error" 
      });
    }
  }, [sessionId]);

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
                onDownloadLetter={handleDownloadLetter}
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
