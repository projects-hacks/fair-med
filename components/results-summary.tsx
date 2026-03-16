"use client";

import { Card, CardContent } from "@/components/ui/card";
import { formatCurrency } from "@/lib/utils";
import type { AnalysisResult } from "@/lib/types";
import { DollarSign, TrendingUp, AlertTriangle, Scale } from "lucide-react";

interface ResultsSummaryProps {
  result: AnalysisResult;
}

export function ResultsSummary({ result }: ResultsSummaryProps) {
  const fairRate = result.total_billed - result.total_overcharge;
  
  const metrics = [
    {
      label: "Total Billed",
      value: formatCurrency(result.total_billed),
      icon: DollarSign,
      color: "text-foreground",
      bgColor: "bg-secondary",
    },
    {
      label: "Medicare Fair Rate",
      value: formatCurrency(fairRate),
      icon: Scale,
      color: "text-info",
      bgColor: "bg-info/10",
    },
    {
      label: "Potential Overcharge",
      value: formatCurrency(result.total_overcharge),
      icon: TrendingUp,
      color: "text-warning",
      bgColor: "bg-warning/10",
    },
    {
      label: "Errors Found",
      value: result.errors_found.toString(),
      icon: AlertTriangle,
      color:
        result.errors_found > 0 ? "text-destructive" : "text-success",
      bgColor:
        result.errors_found > 0 ? "bg-destructive/10" : "bg-success/10",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {metrics.map((metric) => (
        <Card key={metric.label} className="relative overflow-hidden">
          <CardContent className="p-4">
            <div className="flex items-start justify-between">
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground uppercase tracking-wide">
                  {metric.label}
                </p>
                <p className={`text-2xl font-bold ${metric.color}`}>
                  {metric.value}
                </p>
              </div>
              <div className={`rounded-lg p-2 ${metric.bgColor}`}>
                <metric.icon className={`h-5 w-5 ${metric.color}`} />
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
