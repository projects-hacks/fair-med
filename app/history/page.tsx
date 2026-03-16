import { Header } from "@/components/header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { History, FileText, ArrowRight } from "lucide-react";
import Link from "next/link";

export default function HistoryPage() {
  return (
    <div className="min-h-screen flex flex-col bg-background">
      <Header />

      <main className="flex-1 container mx-auto px-4 py-8">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center gap-3 mb-8">
            <History className="h-8 w-8 text-primary" />
            <div>
              <h1 className="text-3xl font-bold">Analysis History</h1>
              <p className="text-muted-foreground">
                View your previous medical bill analyses
              </p>
            </div>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Recent Analyses</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <div className="rounded-full bg-muted p-6 mb-6">
                  <FileText className="h-12 w-12 text-muted-foreground" />
                </div>
                <h3 className="text-xl font-semibold mb-2">No analyses yet</h3>
                <p className="text-muted-foreground max-w-sm mb-6">
                  Start by analyzing a medical bill. Your analysis history will
                  appear here for easy reference.
                </p>
                <Link href="/">
                  <Button>
                    Analyze a Bill
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                </Link>
              </div>
            </CardContent>
          </Card>

          {/* Info Card */}
          <Card className="mt-6 bg-card/50">
            <CardContent className="p-6">
              <h3 className="font-semibold mb-2">About Analysis History</h3>
              <p className="text-sm text-muted-foreground">
                Analysis history is stored locally in your browser. To enable
                persistent storage and access your history across devices,
                connect your Supabase database. All analyses include pricing
                comparisons, error detection, and generated dispute letters.
              </p>
            </CardContent>
          </Card>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border py-6 mt-auto">
        <div className="container mx-auto px-4 text-center text-sm text-muted-foreground">
          <p>
            FairMed uses CMS RVU26B Medicare rates and NCCI 2026Q2 billing rules
          </p>
        </div>
      </footer>
    </div>
  );
}
