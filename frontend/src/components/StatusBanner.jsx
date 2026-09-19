import { getBannerCopy, getBannerIcon, getBannerClass } from "../utils/statusStyles";

export default function StatusBanner({ phase, boxLocked, remaining, voicePieces, scalePieces, elapsed }) {
  const copy = getBannerCopy(phase, { boxLocked, remaining, voicePieces, scalePieces, elapsed });
  const icon = getBannerIcon(phase);
  const cls = getBannerClass(phase, boxLocked);

  return (
    <div className="w-full px-4 flex justify-center">
      <div className={`inline-flex items-center gap-2 rounded-full border py-1.5 px-4 text-sm font-semibold transition-colors ${cls}`}>
        <span className="text-base leading-none">{icon}</span>
        <span>{copy}</span>
      </div>
    </div>
  );
}