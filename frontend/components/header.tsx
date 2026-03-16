import { Shield } from "lucide-react";

export function Header() {
  return (
    <header className="border-b bg-card/50 backdrop-blur-sm sticky top-0 z-50">
      <div className="container mx-auto px-4 h-14 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-md bg-primary flex items-center justify-center">
            <Shield className="h-5 w-5 text-primary-foreground" />
          </div>
          <span className="font-semibold text-lg">BillShield</span>
        </div>
        <p className="text-sm text-muted-foreground hidden sm:block">
          AI-Powered Medical Bill Analysis
        </p>
      </div>
    </header>
  );
}
