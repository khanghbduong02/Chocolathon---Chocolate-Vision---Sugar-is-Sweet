// Shown only while a mismatch is still open for correction. Editing the
// box log can auto-resolve this to "saved"; the button here is the
// explicit override to log it as-is.
export default function MismatchPanel({ visible, onConfirmMismatch }) {
  if (!visible) return null;

  return (
    <div className="w-full px-4 pt-3 flex justify-center">
      <div className="panel-warn max-w-3xl w-full rounded-xl p-4 flex flex-col items-center gap-3 text-center">
        <p className="status-text-warn text-sm">
          Fix it by adjusting quantities or removing items in the box log below — it'll
          auto-save once the counts match. Or confirm to log it as a mismatch.
        </p>
        <button
          onClick={onConfirmMismatch}
          className="button danger"
        >
          Confirm &amp; log as mismatch
        </button>
      </div>
    </div>
  );
}