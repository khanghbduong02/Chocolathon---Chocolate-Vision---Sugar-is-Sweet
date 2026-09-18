export default function Header({ micOn, cameraReady, elapsed, phase }) {
  return (
    <header className="cocoa-header w-full flex flex-col items-center gap-4 px-6 py-7 text-center">
      <div className="flex flex-col items-center gap-3">
        <div className="cocoa-mark h-16 w-16 rounded-xl flex items-center justify-center font-bold text-3xl">
          CV
        </div>
        <div>
          <div className="text-3xl font-bold tracking-tight">Cocoa Vision</div>
          <div className="cocoa-subtitle text-sm">Bradley Fair</div>
        </div>
      </div>

      <div className="flex flex-wrap items-stretch justify-center gap-3">
        <div
          className={`flex items-center justify-center gap-3 px-5 py-3 min-w-[180px] rounded-full border ${
            cameraReady
              ? "status-chip status-good"
              : "status-chip status-bad"
          }`}
        >
          <span className={`status-dot ${cameraReady ? "good" : "bad"}`} />
          <span className="text-base font-semibold">
            {cameraReady ? "Camera ready" : "Camera off"}
          </span>
        </div>

        <div
          className={`flex items-center justify-center gap-3 px-5 py-3 min-w-[180px] rounded-full border ${
            micOn
              ? "status-chip status-good"
              : "status-chip status-bad"
          }`}
        >
          <span className="relative flex h-3.5 w-3.5 shrink-0">
            {micOn && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
            )}
            <span
              className={`status-dot ${micOn ? "good" : "bad"}`}
            />
          </span>
          <span className="text-base font-semibold">
            {micOn ? "Mic on" : "Mic off"}
          </span>
        </div>

        <div className="cocoa-timer flex flex-col items-center justify-center gap-0.5 px-5 py-2 min-w-[110px] rounded-full">
          <span className="eyebrow text-[0.65rem]">Timer</span>
          <span
            className={`font-mono text-2xl font-bold tabular-nums leading-none ${
              phase === "saved" ? "timer-good" : "timer-default"
            }`}
          >
            {elapsed.toFixed(2)}s
          </span>
        </div>
      </div>
    </header>
  );
}