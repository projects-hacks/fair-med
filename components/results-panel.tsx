"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { 
  DollarSign, 
  AlertTriangle, 
  TrendingUp, 
  Scale,
  Download,
  FileText,
  Bell,
  Loader2,
  CheckCircle
} from "lucide-react";
import { cn, formatCurrency, formatPercent } from "@/lib/utils";
import { AnalysisResult, PricingResult, BillingError, DisputeLetterStatus } from "@/lib/types";

interface ResultsPanelProps {
  result: AnalysisResult;
  disputeStatus: DisputeLetterStatus | null;
  onGenerateDispute: () => void;
}

function MetricCard({ 
  label, 
  value, 
  icon: Icon, 
  variant = "default" 
}: { 
  label: string; 
  value: string; 
  icon: React.ElementType;
  variant?: "default" | "success" | "warning" | "destructive";
}) {
  const colors = {
    default: "text-foreground bg-secondary",
    success: "text-success bg-success/10",
    warning: "text-warning bg-warning/10",
    destructive: "text-destructive bg-destructive/10",
  };

  return (
    <div className="flex items-center gap-3 p-3 rounded-lg border">
      <div className={cn("h-10 w-10 rounded-md flex items-center justify-center", colors[variant])}>
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className={cn("text-lg font-semibold", variant !== "default" && colors[variant].split(" ")[0])}>
          {value}
        </p>
      </div>
    </div>
  );
}

function PricingTable({ results }: { results: PricingResult[] }) {
  if (!results || results.length === 0) {
    return <p className="text-muted-foreground text-sm">No pricing data available.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left">
            <th className="pb-3 font-medium text-muted-foreground">CPT Code</th>
            <th className="pb-3 font-medium text-muted-foreground">Description</th>
            <th className="pb-3 font-medium text-muted-foreground text-right">Billed</th>
            <th className="pb-3 font-medium text-muted-foreground text-right">Fair Rate</th>
            <th className="pb-3 font-medium text-muted-foreground text-right">Difference</th>
          </tr>
        </thead>
        <tbody>
          {results.map((item, idx) => (
            <tr key={idx} className="border-b border-border/50">
              <td className="py-3 font-mono text-primary">{item.cpt_code}</td>
              <td className="py-3 text-foreground/80 max-w-[200px] truncate">{item.description}</td>
              <td className="py-3 text-right">{formatCurrency(item.billed_amount)}</td>
              <td className="py-3 text-right text-info">{formatCurrency(item.fair_estimate)}</td>
              <td className={cn(
                "py-3 text-right font-medium",
                item.difference > 0 ? "text-destructive" : "text-success"
              )}>
                {item.difference > 0 ? "+" : ""}{formatCurrency(item.difference)}
                <span className="text-xs ml-1 text-muted-foreground">
                  ({formatPercent(item.difference_percent)})
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ErrorFindings({ errors }: { errors: BillingError[] }) {
  if (!errors || errors.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-center">
        <CheckCircle className="h-12 w-12 text-success mb-3" />
        <p className="font-medium">No billing errors detected</p>
        <p className="text-sm text-muted-foreground">Your bill appears to be accurate.</p>
      </div>
    );
  }

  const severityColors = {
    low: "border-l-info bg-info/5",
    medium: "border-l-warning bg-warning/5",
    high: "border-l-destructive bg-destructive/5",
  };

  const typeLabels: Record<string, string> = {
    duplicate: "Duplicate Charge",
    upcoding: "Upcoding",
    unbundling: "Unbundling",
    overcharge: "Overcharge",
    other: "Other Issue",
  };

  return (
    <div className="space-y-3">
      {errors.map((error, idx) => (
        <div 
          key={idx} 
          className={cn(
            "p-4 rounded-lg border-l-4",
            severityColors[error.severity]
          )}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="font-medium">{typeLabels[error.type] || error.type}</span>
                <span className={cn(
                  "text-xs px-2 py-0.5 rounded-full",
                  error.severity === "high" && "bg-destructive/20 text-destructive",
                  error.severity === "medium" && "bg-warning/20 text-warning",
                  error.severity === "low" && "bg-info/20 text-info"
                )}>
                  {error.severity}
                </span>
              </div>
              <p className="text-sm text-foreground/80">{error.description}</p>
              {error.cpt_codes.length > 0 && (
                <div className="flex gap-1.5 mt-2">
                  {error.cpt_codes.map((code, i) => (
                    <span key={i} className="text-xs font-mono bg-muted px-2 py-0.5 rounded">
                      {code}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="text-right shrink-0">
              <p className="text-xs text-muted-foreground">Potential Savings</p>
              <p className="font-semibold text-success">{formatCurrency(error.potential_savings)}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function DisputeSection({ 
  status, 
  onGenerate 
}: { 
  status: DisputeLetterStatus | null;
  onGenerate: () => void;
}) {
  if (!status) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <FileText className="h-12 w-12 text-muted-foreground mb-4" />
        <h3 className="font-medium mb-2">Generate Dispute Letter</h3>
        <p className="text-sm text-muted-foreground mb-4 max-w-md">
          Based on the errors found, we can generate a professional dispute letter 
          citing relevant regulations and patient rights.
        </p>
        <Button onClick={onGenerate}>
          Generate Letter
        </Button>
      </div>
    );
  }

  if (status.status === "pending" || status.status === "generating") {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <Loader2 className="h-12 w-12 text-primary animate-spin mb-4" />
        <h3 className="font-medium mb-2">Generating Dispute Letter</h3>
        <p className="text-sm text-muted-foreground">
          Our AI agents are researching regulations and drafting your letter...
        </p>
      </div>
    );
  }

  if (status.status === "error") {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <AlertTriangle className="h-12 w-12 text-destructive mb-4" />
        <h3 className="font-medium mb-2">Generation Failed</h3>
        <p className="text-sm text-muted-foreground mb-4">{status.error}</p>
        <Button onClick={onGenerate} variant="outline">
          Try Again
        </Button>
      </div>
    );
  }

  if (!status.download_url) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <AlertTriangle className="h-12 w-12 text-warning mb-4" />
        <h3 className="font-medium mb-2">Letter Ready, Link Missing</h3>
        <p className="text-sm text-muted-foreground mb-4">
          The letter was generated, but download URL was not returned. Try regenerating once.
        </p>
        <Button onClick={onGenerate} variant="outline">
          Regenerate Link
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="h-16 w-16 rounded-full bg-success/10 flex items-center justify-center mb-4">
        <Bell className="h-8 w-8 text-success" />
      </div>
      <h3 className="font-medium mb-2">Dispute Letter Ready</h3>
      <p className="text-sm text-muted-foreground mb-4">
        Your personalized dispute letter has been generated.
      </p>
      <Button asChild>
        <a href={status.download_url} download>
          <Download className="h-4 w-4 mr-2" />
          Download Letter
        </a>
      </Button>
    </div>
  );
}

export function ResultsPanel({ result, disputeStatus, onGenerateDispute }: ResultsPanelProps) {
  const fairRate = result.total_fair ?? (result.total_billed - result.total_overcharge);

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">Analysis Results</CardTitle>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col gap-4 overflow-hidden">
        <div className="grid grid-cols-2 gap-3">
          <MetricCard 
            label="Total Billed" 
            value={formatCurrency(result.total_billed)} 
            icon={DollarSign}
          />
          <MetricCard 
            label="Fair Rate" 
            value={formatCurrency(fairRate)} 
            icon={Scale}
            variant="success"
          />
          <MetricCard 
            label="Overcharge" 
            value={formatCurrency(result.total_overcharge)} 
            icon={TrendingUp}
            variant="warning"
          />
          <MetricCard 
            label="Errors Found" 
            value={result.error_count.toString()} 
            icon={AlertTriangle}
            variant={result.error_count > 0 ? "destructive" : "success"}
          />
        </div>

        <Tabs defaultValue="pricing" className="flex-1 flex flex-col overflow-hidden">
          <TabsList className="w-full justify-start shrink-0">
            <TabsTrigger value="pricing">Pricing</TabsTrigger>
            <TabsTrigger value="errors">
              Errors ({result.error_count})
            </TabsTrigger>
            <TabsTrigger value="dispute">Dispute Letter</TabsTrigger>
          </TabsList>
          <TabsContent value="pricing" className="flex-1 overflow-y-auto">
            <PricingTable results={result.pricing_results} />
          </TabsContent>
          <TabsContent value="errors" className="flex-1 overflow-y-auto">
            <ErrorFindings errors={result.audit_findings} />
          </TabsContent>
          <TabsContent value="dispute" className="flex-1 overflow-y-auto">
            <DisputeSection status={disputeStatus} onGenerate={onGenerateDispute} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
