import { HeartPulse } from "lucide-react";

export function Header() {
  return (
    <header className="border-b bg-card/50 backdrop-blur-sm sticky top-0 z-50">
      <div className="container mx-auto px-4 h-14 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="h-8 w-8 rounded-md bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-sm shadow-primary/20">
            <HeartPulse className="h-5 w-5 text-primary-foreground" />
          </div>
          <span className="font-semibold text-lg tracking-tight">Fair-Med</span>
        </div>
        <p className="text-sm text-muted-foreground hidden sm:block">
          AI-Powered Medical Bill Analysis
        </p>
      </div>
    </header>
  );
}
