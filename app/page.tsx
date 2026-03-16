"use client";

import { useState } from "react";
import { Header } from "@/components/header";
import { BillInput } from "@/components/bill-input";
import { AnalysisPipeline } from "@/components/analysis-pipeline";
import { ResultsSummary } from "@/components/results-summary";
import { PricingTable } from "@/components/pricing-table";
import { ErrorFindings } from "@/components/error-findings";
import { DisputeLetter } from "@/components/dispute-letter";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import type { AnalysisResult, AgentStep } from "@/lib/types";
import { Shield, Zap, Lock, FileCheck } from "lucide-react";

const INITIAL_STEPS: AgentStep[] = [
  { name: "Triage", status: "pending" },
  { name: "Parser", status: "pending" },
  { name: "Pricing", status: "pending" },
  { name: "Auditor", status: "pending" },
  { name: "Researcher", status: "pending" },
  { name: "Fact-Checker", status: "pending" },
  { name: "Writer", status: "pending" },
];

export default function HomePage() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [steps, setSteps] = useState<AgentStep[]>(INITIAL_STEPS);
  const [result, setResult] = useState<AnalysisResult | null>(null);

  const handleAnalyze = async (billText: string) => {
    setIsAnalyzing(true);
    setSteps(INITIAL_STEPS);
    setResult(null);

    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bill_text: billText }),
      });

      if (!response.ok) {
        throw new Error("Analysis failed");
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No reader available");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));

              if (data.type === "step_start") {
                setSteps((prev) =>
                  prev.map((step) =>
                    step.name === data.step
                      ? { ...step, status: "running" }
                      : step
                  )
                );
              } else if (data.type === "step_complete") {
                setSteps((prev) =>
                  prev.map((step) =>
                    step.name === data.step
                      ? { ...step, status: "complete", duration: data.duration }
                      : step
                  )
                );
              } else if (data.type === "result") {
                setResult(data.result);
              } else if (data.type === "error") {
                console.error("Analysis error:", data.message);
              }
            } catch {
              // Skip malformed JSON
            }
          }
        }
      }
    } catch (error) {
      console.error("Analysis failed:", error);
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-background">
      <Header />

      <main className="flex-1 container mx-auto px-4 py-8">
        {/* Hero Section */}
        {!result && (
          <section className="text-center mb-12 animate-fade-in">
            <h1 className="text-4xl md:text-5xl font-bold mb-4 text-balance">
              AI-Powered Medical Bill Analysis
            </h1>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto text-pretty">
              Detect billing errors, compare against Medicare fair rates, and
              generate dispute letters with our multi-agent AI system.
            </p>

            {/* Feature Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-8 max-w-4xl mx-auto">
              <Card className="bg-card/50">
                <CardContent className="p-6 text-center">
                  <Zap className="h-8 w-8 text-primary mx-auto mb-3" />
                  <h3 className="font-semibold mb-1">7 AI Agents</h3>
                  <p className="text-sm text-muted-foreground">
                    Specialized agents work together to analyze your bill
                  </p>
                </CardContent>
              </Card>
              <Card className="bg-card/50">
                <CardContent className="p-6 text-center">
                  <FileCheck className="h-8 w-8 text-primary mx-auto mb-3" />
                  <h3 className="font-semibold mb-1">Real CMS Data</h3>
                  <p className="text-sm text-muted-foreground">
                    Compare prices against official Medicare rates
                  </p>
                </CardContent>
              </Card>
              <Card className="bg-card/50">
                <CardContent className="p-6 text-center">
                  <Lock className="h-8 w-8 text-primary mx-auto mb-3" />
                  <h3 className="font-semibold mb-1">Secure & Private</h3>
                  <p className="text-sm text-muted-foreground">
                    Your data is never shared or stored permanently
                  </p>
                </CardContent>
              </Card>
            </div>
          </section>
        )}

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column - Input */}
          <div className="lg:col-span-1 space-y-6">
            <BillInput onAnalyze={handleAnalyze} isAnalyzing={isAnalyzing} />

            {isAnalyzing && (
              <Card>
                <CardContent className="p-6">
                  <AnalysisPipeline steps={steps} />
                </CardContent>
              </Card>
            )}
          </div>

          {/* Right Column - Results */}
          <div className="lg:col-span-2 space-y-6">
            {result ? (
              <>
                <ResultsSummary result={result} />

                <Tabs defaultValue="pricing" className="w-full">
                  <TabsList className="w-full justify-start">
                    <TabsTrigger value="pricing">Pricing</TabsTrigger>
                    <TabsTrigger value="errors">
                      Errors ({result.error_count})
                    </TabsTrigger>
                    <TabsTrigger value="letter">Dispute Letter</TabsTrigger>
                  </TabsList>
                  <TabsContent value="pricing">
                    <PricingTable results={result.pricing_results} />
                  </TabsContent>
                  <TabsContent value="errors">
                    <ErrorFindings errors={result.errors_found} />
                  </TabsContent>
                  <TabsContent value="letter">
                    <DisputeLetter letter={result.dispute_letter} />
                  </TabsContent>
                </Tabs>
              </>
            ) : (
              <Card className="flex flex-col items-center justify-center py-20">
                <Shield className="h-16 w-16 text-muted-foreground/30 mb-6" />
                <h2 className="text-xl font-semibold text-muted-foreground mb-2">
                  Ready to Analyze
                </h2>
                <p className="text-muted-foreground text-center max-w-sm">
                  Paste your medical bill on the left to start the AI-powered
                  analysis. Try the demo bill to see how it works.
                </p>
              </Card>
            )}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border py-6 mt-auto">
        <div className="container mx-auto px-4 text-center text-sm text-muted-foreground">
          <p>
            FairMed uses CMS RVU26B Medicare rates and NCCI 2026Q2 billing rules
          </p>
          <p className="mt-1">
            Built for NVIDIA Agents for Impact Hackathon | SJSU | March 2026
          </p>
        </div>
      </footer>
    </div>
  );
}
