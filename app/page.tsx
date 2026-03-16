"use client";

import { useState } from "react";
import { Header } from "@/components/header";
import { BillInput } from "@/components/bill-input";
import { ResultsSummary } from "@/components/results-summary";
import { PricingTable } from "@/components/pricing-table";
import { ErrorFindings } from "@/components/error-findings";
import { DisputeLetter } from "@/components/dispute-letter";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import type { AnalysisResult } from "@/lib/types";
import { Shield, Zap, FileCheck, Loader2 } from "lucide-react";

export default function HomePage() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleAnalyze = async (billText: string) => {
    setIsAnalyzing(true);
    setResult(null);
    setError(null);

    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bill_text: billText }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || "Analysis failed");
      }

      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
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
          <section className="text-center mb-12">
            <h1 className="text-4xl md:text-5xl font-bold mb-4 text-balance">
              AI-Powered Medical Bill Analysis
            </h1>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto text-pretty">
              Detect billing errors, compare against Medicare fair rates, and
              generate dispute letters with our multi-agent AI system.
            </p>

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
                  <Shield className="h-8 w-8 text-primary mx-auto mb-3" />
                  <h3 className="font-semibold mb-1">NCCI Compliance</h3>
                  <p className="text-sm text-muted-foreground">
                    Checks against official billing rules
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
                <CardContent className="p-6 flex flex-col items-center gap-4">
                  <Loader2 className="h-8 w-8 animate-spin text-primary" />
                  <p className="text-sm text-muted-foreground">
                    Running 7 AI agents...
                  </p>
                </CardContent>
              </Card>
            )}

            {error && (
              <Card className="border-destructive">
                <CardContent className="p-4 text-destructive text-sm">
                  {error}
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

      <footer className="border-t border-border py-6 mt-auto">
        <div className="container mx-auto px-4 text-center text-sm text-muted-foreground">
          <p>FairMed - CMS RVU26B Medicare rates | NCCI 2026Q2 billing rules</p>
        </div>
      </footer>
    </div>
  );
}
