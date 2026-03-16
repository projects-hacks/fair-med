"use client";

import { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FileText, Upload, X, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface BillInputProps {
  onSubmit: (data: { text?: string; file?: File }) => void;
  isLoading: boolean;
}

export function BillInput({ onSubmit, isLoading }: BillInputProps) {
  const [inputMode, setInputMode] = useState<"text" | "file">("text");
  const [billText, setBillText] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = () => {
    if (inputMode === "text" && billText.trim()) {
      onSubmit({ text: billText });
    } else if (inputMode === "file" && selectedFile) {
      onSubmit({ file: selectedFile });
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (file.type === "application/pdf" || file.type.startsWith("image/")) {
        setSelectedFile(file);
        setInputMode("file");
      }
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
    }
  };

  const clearFile = () => {
    setSelectedFile(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const isValid = (inputMode === "text" && billText.trim().length > 0) || 
                  (inputMode === "file" && selectedFile !== null);

  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          <FileText className="h-5 w-5 text-primary" />
          Upload Medical Bill
        </CardTitle>
        <div className="flex gap-2 mt-3">
          <Button
            variant={inputMode === "text" ? "default" : "outline"}
            size="sm"
            onClick={() => setInputMode("text")}
            disabled={isLoading}
          >
            Paste Text
          </Button>
          <Button
            variant={inputMode === "file" ? "default" : "outline"}
            size="sm"
            onClick={() => setInputMode("file")}
            disabled={isLoading}
          >
            Upload PDF
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col gap-4">
        {inputMode === "text" ? (
          <textarea
            value={billText}
            onChange={(e) => setBillText(e.target.value)}
            placeholder="Paste your medical bill text here...

Include details like:
- CPT codes and descriptions
- Dates of service
- Billed amounts
- Provider information"
            className="flex-1 min-h-[300px] w-full rounded-md border border-input bg-muted/50 px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary resize-none font-mono"
            disabled={isLoading}
          />
        ) : (
          <div
            className={cn(
              "flex-1 min-h-[300px] border-2 border-dashed rounded-lg flex flex-col items-center justify-center gap-4 transition-colors",
              dragActive ? "border-primary bg-primary/5" : "border-border",
              selectedFile ? "bg-muted/30" : "hover:border-muted-foreground"
            )}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
          >
            {selectedFile ? (
              <div className="flex flex-col items-center gap-3">
                <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center">
                  <FileText className="h-6 w-6 text-primary" />
                </div>
                <div className="text-center">
                  <p className="font-medium">{selectedFile.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {(selectedFile.size / 1024).toFixed(1)} KB
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={clearFile}
                  disabled={isLoading}
                >
                  <X className="h-4 w-4 mr-1" />
                  Remove
                </Button>
              </div>
            ) : (
              <>
                <div className="h-12 w-12 rounded-lg bg-muted flex items-center justify-center">
                  <Upload className="h-6 w-6 text-muted-foreground" />
                </div>
                <div className="text-center">
                  <p className="font-medium">Drop your bill here</p>
                  <p className="text-sm text-muted-foreground">PDF or image files supported</p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isLoading}
                >
                  Browse Files
                </Button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,image/*"
                  onChange={handleFileSelect}
                  className="hidden"
                />
              </>
            )}
          </div>
        )}
        
        <Button 
          onClick={handleSubmit} 
          disabled={!isValid || isLoading}
          className="w-full"
          size="lg"
        >
          {isLoading ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Analyzing...
            </>
          ) : (
            "Analyze Bill"
          )}
        </Button>
      </CardContent>
    </Card>
  );
}
