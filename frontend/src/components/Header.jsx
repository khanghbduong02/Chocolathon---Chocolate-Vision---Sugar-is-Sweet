import { Mic, MicOff, Camera, CameraOff } from "lucide-react";

export default function Header({ micOn, cameraReady, elapsed, phase }) {
  return (
    <header className="cocoa-header w-full flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 sm:px-6">
      <div className="flex items-center gap-3">
        <div className="cocoa-mark h-10 w-10 rounded-lg flex items-center justify-center font-bold text-lg shrink-0">
          CV
        </div>
        <div className="text-left leading-tight">
          <div className="text-xl font-bold tracking-tight">Cocoa Vision</div>
          <div className="cocoa-subtitle text-xs">Bradley Fair</div>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2">
        <div
          tabIndex={0}
          aria-label={cameraReady ? "Camera ready" : "Camera off"}
          className={`icon-status-chip ${cameraReady ? "status-good" : "status-bad"}`}
        >
          <span className="chip-icon relative">
            {cameraReady && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
            )}
            {cameraReady ? <Camera size={18} /> : <CameraOff size={18} />}
          </span>
          <span className="chip-label">{cameraReady ? "Camera ready" : "Camera off"}</span>
        </div>

        <div
          tabIndex={0}
          aria-label={micOn ? "Mic on" : "Mic off"}
          className={`icon-status-chip ${micOn ? "status-good" : "status-bad"}`}
        >
          <span className="chip-icon relative">
            {micOn && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
            )}
            {micOn ? <Mic size={18} /> : <MicOff size={18} />}
          </span>
          <span className="chip-label">{micOn ? "Mic on" : "Mic off"}</span>
        </div>

        <div className="cocoa-timer flex items-center gap-1.5 px-3 py-1.5 rounded-full">
          <span className="eyebrow text-[0.6rem]">Timer</span>
          <span
            className={`font-mono text-lg font-bold tabular-nums leading-none ${
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