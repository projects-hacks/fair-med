"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency, cn } from "@/lib/utils";
import type { BillingError } from "@/lib/types";
import { AlertTriangle, AlertCircle, Info } from "lucide-react";

interface ErrorFindingsProps {
  errors: BillingError[];
}

export function ErrorFindings({ errors }: ErrorFindingsProps) {
  if (!errors || errors.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <AlertTriangle className="h-5 w-5 text-primary" />
            Audit Findings
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <div className="rounded-full bg-success/10 p-4 mb-4">
              <Info className="h-8 w-8 text-success" />
            </div>
            <p className="text-lg font-medium text-success">
              No billing errors detected
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              Your bill appears to be accurately coded.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case "HIGH":
        return <AlertTriangle className="h-5 w-5 text-destructive" />;
      case "MEDIUM":
        return <AlertCircle className="h-5 w-5 text-warning" />;
      default:
        return <Info className="h-5 w-5 text-info" />;
    }
  };

  const getSeverityStyles = (severity: string) => {
    switch (severity) {
      case "HIGH":
        return "border-destructive/30 bg-destructive/5";
      case "MEDIUM":
        return "border-warning/30 bg-warning/5";
      default:
        return "border-info/30 bg-info/5";
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <AlertTriangle className="h-5 w-5 text-primary" />
          Audit Findings
          <span className="ml-auto text-sm font-normal text-muted-foreground">
            {errors.length} issue{errors.length !== 1 ? "s" : ""} found
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {errors.map((error, index) => (
          <div
            key={index}
            className={cn(
              "rounded-lg border p-4 space-y-3",
              getSeverityStyles(error.severity)
            )}
          >
            <div className="flex items-start gap-3">
              {getSeverityIcon(error.severity)}
              <div className="flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-foreground">
                    {error.type.replace(/_/g, " ")}
                  </span>
                  <span
                    className={cn(
                      "text-xs px-2 py-0.5 rounded-full font-medium",
                      error.severity === "HIGH" &&
                        "bg-destructive/20 text-destructive",
                      error.severity === "MEDIUM" &&
                        "bg-warning/20 text-warning",
                      error.severity === "LOW" && "bg-info/20 text-info"
                    )}
                  >
                    {error.severity}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground mt-1">
                  {error.description}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-4 text-xs">
              {error.cpt_codes && error.cpt_codes.length > 0 && (
                <div>
                  <span className="text-muted-foreground">CPT Codes: </span>
                  <span className="font-mono font-medium">
                    {error.cpt_codes.join(", ")}
                  </span>
                </div>
              )}
              {(error.potential_savings_low > 0 ||
                error.potential_savings_high > 0) && (
                <div>
                  <span className="text-muted-foreground">
                    Potential Savings:{" "}
                  </span>
                  <span className="font-medium text-success">
                    {formatCurrency(error.potential_savings_low)} -{" "}
                    {formatCurrency(error.potential_savings_high)}
                  </span>
                </div>
              )}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
