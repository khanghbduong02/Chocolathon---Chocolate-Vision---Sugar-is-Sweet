import { BOX_SIZE_OPTIONS } from "../constants/config";

// `locked` should be true whenever a box is actively being packed
// (i.e. the same condition as `itemsEditable` from useBoxPacking) —
// size can't change mid-pack.
export default function BoxSizeSelector({ boxSize, setBoxSize, locked }) {
  return (
    <div className="w-full px-4">
      <div className="cocoa-size-panel max-w-3xl mx-auto rounded-xl px-4 py-2 flex items-center justify-center gap-3 flex-wrap">
        <span className="cocoa-subtitle text-xs font-medium shrink-0">Box size</span>
        <div className="flex flex-wrap items-center justify-center gap-2">
          {BOX_SIZE_OPTIONS.map((size) => {
            const selected = size === boxSize;
            return (
              <button
                key={size}
                onClick={() => !locked && setBoxSize(size)}
                disabled={locked}
                className={`box-size-button ${selected ? "selected" : ""}`}
              >
                {size}pc
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}