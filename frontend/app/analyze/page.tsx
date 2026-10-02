import type { Metadata } from "next";
import { Suspense } from "react";
import { AnalysisShell } from "@/components/analysis-shell";
import { Footer } from "@/components/footer";

export const metadata: Metadata = {
  title: "Repository analysis",
};

function ShellFallback() {
  return (
    <div className="flex-1">
      <div className="h-14 border-b border-line/70" />
    </div>
  );
}

export default function AnalyzePage() {
  return (
    <>
      {/* useSearchParams() inside the shell needs a Suspense boundary. */}
      <Suspense fallback={<ShellFallback />}>
        <AnalysisShell />
      </Suspense>
      <Footer />
    </>
  );
}
