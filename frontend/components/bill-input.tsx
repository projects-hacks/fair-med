"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DEMO_BILL_TEXT } from "@/lib/types";
import { FileText, Sparkles } from "lucide-react";

interface BillInputProps {
  onAnalyze: (billText: string) => void;
  isAnalyzing: boolean;
}

export function BillInput({ onAnalyze, isAnalyzing }: BillInputProps) {
  const [billText, setBillText] = useState("");

  const handleAnalyze = () => {
    if (billText.trim()) {
      onAnalyze(billText);
    }
  };

  const handleLoadDemo = () => {
    setBillText(DEMO_BILL_TEXT);
  };

  return (
    <Card className="h-full">
      <CardHeader className="pb-4">
        <CardTitle className="flex items-center gap-2 text-lg">
          <FileText className="h-5 w-5 text-primary" />
          Medical Bill Input
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <Textarea
          placeholder="Paste your itemized medical bill or EOB text here..."
          value={billText}
          onChange={(e) => setBillText(e.target.value)}
          className="min-h-[280px] font-mono text-sm"
          disabled={isAnalyzing}
        />
        <div className="flex flex-col gap-3 sm:flex-row">
          <Button
            onClick={handleAnalyze}
            disabled={!billText.trim() || isAnalyzing}
            className="flex-1"
            size="lg"
          >
            {isAnalyzing ? (
              <>
                <Sparkles className="mr-2 h-4 w-4 animate-spin" />
                Analyzing...
              </>
            ) : (
              <>
                <Sparkles className="mr-2 h-4 w-4" />
                Analyze Bill
              </>
            )}
          </Button>
          <Button
            variant="outline"
            onClick={handleLoadDemo}
            disabled={isAnalyzing}
          >
            Try Demo Bill
          </Button>
        </div>
        <p className="text-xs text-muted-foreground text-center">
          Your data is processed securely and never shared with third parties.
        </p>
      </CardContent>
    </Card>
  );
}
