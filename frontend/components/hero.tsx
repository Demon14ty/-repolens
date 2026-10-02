import { RepositoryInput } from "./repository-input";

export function Hero() {
  return (
    <section id="analyze" aria-labelledby="hero-heading" className="scroll-mt-8">
      <div className="mx-auto max-w-6xl px-4 pt-20 pb-20 sm:px-6 sm:pt-28 sm:pb-24">
        <div className="max-w-2xl">
          <p className="font-mono text-[12px] tracking-[0.14em] text-accent uppercase">
            Understand unfamiliar codebases
          </p>
          <h1
            id="hero-heading"
            className="mt-5 text-[34px] leading-[1.12] font-semibold tracking-[-0.02em] text-balance text-fg sm:text-[44px]"
          >
            Find your way through any Python repository.
          </h1>
          <p className="mt-5 max-w-xl text-[16px] leading-relaxed text-muted sm:text-[17px]">
            RepoLens turns a public GitHub repository into an evidence-based learning path—showing what to read
            first, what to skip, and how the code fits together.
          </p>
        </div>
        <div className="mt-10 max-w-2xl">
          <RepositoryInput />
        </div>
      </div>
    </section>
  );
}
