export default function Home() {
  return (
    <div className="bg-background text-foreground flex min-h-screen flex-col items-center justify-center px-6">
      <main className="flex w-full max-w-xl flex-col items-center gap-6 text-center">
        <span className="text-muted-foreground text-sm font-medium tracking-widest uppercase">
          Phase 0 · Foundation
        </span>
        <h1 className="text-5xl font-semibold tracking-tight">Procto</h1>
        <p className="text-muted-foreground text-lg leading-relaxed">
          Real-time video meeting platform. Create a meet, join a meet, or run an exam/interview
          meet — all on one meeting core.
        </p>
        <p className="text-muted-foreground/70 text-sm">
          The design system, authentication and meeting room arrive in later phases.
        </p>
      </main>
    </div>
  );
}
