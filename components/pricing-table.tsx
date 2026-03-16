"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency, formatPercentage, cn } from "@/lib/utils";
import type { PricingResult } from "@/lib/types";
import { TrendingUp } from "lucide-react";

interface PricingTableProps {
  results: PricingResult[];
}

export function PricingTable({ results }: PricingTableProps) {
  if (!results || results.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <TrendingUp className="h-5 w-5 text-primary" />
            Pricing Comparison
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground text-center py-8">
            No pricing data available yet.
          </p>
        </CardContent>
      </Card>
    );
  }

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case "EXTREME":
        return "text-destructive bg-destructive/10";
      case "MAJOR":
        return "text-warning bg-warning/10";
      case "MINOR":
        return "text-info bg-info/10";
      case "UNDER":
        return "text-success bg-success/10";
      default:
        return "text-muted-foreground bg-muted";
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <TrendingUp className="h-5 w-5 text-primary" />
          Pricing Comparison
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-3 px-2 text-muted-foreground font-medium">
                  CPT Code
                </th>
                <th className="text-left py-3 px-2 text-muted-foreground font-medium">
                  Description
                </th>
                <th className="text-right py-3 px-2 text-muted-foreground font-medium">
                  Billed
                </th>
                <th className="text-right py-3 px-2 text-muted-foreground font-medium">
                  Medicare
                </th>
                <th className="text-right py-3 px-2 text-muted-foreground font-medium">
                  Difference
                </th>
                <th className="text-center py-3 px-2 text-muted-foreground font-medium">
                  Status
                </th>
              </tr>
            </thead>
            <tbody>
              {results.map((row, index) => (
                <tr
                  key={`${row.cpt_code}-${index}`}
                  className="border-b border-border/50 hover:bg-muted/30 transition-colors"
                >
                  <td className="py-3 px-2 font-mono font-medium">
                    {row.cpt_code || "N/A"}
                  </td>
                  <td className="py-3 px-2 text-muted-foreground max-w-[200px] truncate">
                    {row.description || "Unknown"}
                  </td>
                  <td className="py-3 px-2 text-right font-medium">
                    {formatCurrency(row.billed)}
                  </td>
                  <td className="py-3 px-2 text-right text-info">
                    {row.found
                      ? formatCurrency(row.medicare_rate)
                      : "Not Found"}
                  </td>
                  <td
                    className={cn(
                      "py-3 px-2 text-right font-medium",
                      row.overcharge_amount > 0
                        ? "text-warning"
                        : "text-success"
                    )}
                  >
                    {row.overcharge_amount > 0 ? "+" : ""}
                    {formatCurrency(row.overcharge_amount)}
                    <span className="text-xs ml-1 text-muted-foreground">
                      ({formatPercentage(row.overcharge_pct)})
                    </span>
                  </td>
                  <td className="py-3 px-2 text-center">
                    <span
                      className={cn(
                        "inline-flex items-center px-2 py-1 rounded-full text-xs font-medium",
                        getSeverityColor(row.severity)
                      )}
                    >
                      {row.severity}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
