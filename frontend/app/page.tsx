import { BookOpen, Flag, Quote, Route } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Footer } from "@/components/footer";
import { Hero } from "@/components/hero";
import { Navbar } from "@/components/navbar";

const FEATURES: { icon: LucideIcon; title: string; text: string }[] = [
  {
    icon: Route,
    title: "Guided reading path",
    text: "A short, ordered list of the files that explain the project, starting from where the code runs.",
  },
  {
    icon: Quote,
    title: "Evidence-based answers",
    text: "Ask where things live and get answers that cite real files and line ranges—or an honest “not sure”.",
  },
  {
    icon: BookOpen,
    title: "README onboarding review",
    text: "A transparent check of what the README covers for a newcomer, and what it leaves out.",
  },
  {
    icon: Flag,
    title: "First contribution idea",
    text: "One small, concrete task grounded in the actual code, sized for a first pull request.",
  },
];

const STEPS = [
  { title: "Paste repository", text: "Any public GitHub repository URL." },
  { title: "RepoLens analyses structure", text: "Files, imports, entry points and framework, read statically." },
  { title: "Learn with a clear path", text: "What to read first, what to skip, and why." },
];

export default function HomePage() {
  return (
    <>
      <Navbar />
      <main className="flex-1">
        <Hero />

        <section aria-labelledby="features-heading" className="border-t border-line/70">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
            <h2 id="features-heading" className="text-[13px] font-medium tracking-[0.08em] text-faint uppercase">
              What you get
            </h2>
            <ul className="mt-8 grid gap-x-10 gap-y-10 sm:grid-cols-2 lg:grid-cols-4">
              {FEATURES.map(({ icon: Icon, title, text }) => (
                <li key={title} className="border-l border-line pl-5">
                  <Icon aria-hidden="true" className="size-4 text-accent" strokeWidth={1.75} />
                  <h3 className="mt-4 text-[15px] font-medium text-fg">{title}</h3>
                  <p className="mt-2 text-[14px] leading-relaxed text-muted">{text}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section aria-labelledby="how-heading" className="border-t border-line/70">
          <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
            <h2 id="how-heading" className="text-[13px] font-medium tracking-[0.08em] text-faint uppercase">
              How it works
            </h2>
            <ol className="mt-8 flex flex-col gap-6 md:flex-row md:gap-4">
              {STEPS.map((step, index) => (
                <li key={step.title} className="flex flex-1 gap-4 md:gap-4">
                  <div className="flex flex-1 gap-4 md:block">
                    <span className="font-mono text-[12px] text-faint">0{index + 1}</span>
                    <div className="md:mt-3">
                      <p className="text-[15px] font-medium text-fg">{step.title}</p>
                      <p className="mt-1 text-[14px] leading-relaxed text-muted">{step.text}</p>
                    </div>
                  </div>
                  {index < STEPS.length - 1 && (
                    <span aria-hidden="true" className="hidden pt-7 font-mono text-faint md:block">
                      →
                    </span>
                  )}
                </li>
              ))}
            </ol>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
