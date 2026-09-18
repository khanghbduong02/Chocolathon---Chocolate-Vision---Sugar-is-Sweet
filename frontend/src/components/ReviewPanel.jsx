const statusLabel = {
  exact_match: "Matches",
  quantity_mismatch: "Quantity differs",
  voice_only: "Voice only",
};

export default function ReviewPanel({ comparison, items, itemsEditable, onAdjustQty, onRemoveItem, onSave, saving, saveError }) {
  if (!comparison) {
    return (
      <section className="review-panel">
        <div className="panel-heading">
          <div><span className="eyebrow">Human review</span><h2>Confirm the final list</h2></div>
        </div>
        <p className="review-intro">Comparing the spoken flavors against the camera scan...</p>
      </section>
    );
  }

  const voiceIndexes = new Map(items.map((item, index) => [item.slug, index]));
  const reviewRows = comparison.byFlavor.filter((row) => row.voiceQty > 0);

  return (
    <section className="review-panel">
      <div className="panel-heading">
        <div><span className="eyebrow">Human review</span><h2>Confirm the final list</h2></div>
        <span className={`comparison-badge ${comparison.match ? "match" : "mismatch"}`}>{comparison.match ? "Match" : "Review needed"}</span>
      </div>
      <p className="review-intro">Camera quantities stay read-only. Edit the spoken list before saving the confirmed order.</p>
      <div className="review-list">
        {reviewRows.length ? reviewRows.map((row) => {
          const index = voiceIndexes.get(row.slug);
          const editable = index !== undefined;
          return (
            <div className="review-row" key={row.slug}>
              <div className="review-name"><strong>{row.name}</strong><span className={`status-text ${row.status === "exact_match" ? "status-text-good" : "status-text-warn"}`}>{statusLabel[row.status]}</span></div>
              <span className="camera-quantity">Camera: {row.cameraQty}</span>
              <button className="icon-button" disabled={!itemsEditable || !editable} onClick={() => onAdjustQty(index, -1)} aria-label={`Decrease ${row.name}`}>−</button>
              <span className="review-quantity">{row.voiceQty}</span>
              <button className="icon-button" disabled={!itemsEditable || !editable} onClick={() => onAdjustQty(index, 1)} aria-label={`Increase ${row.name}`}>+</button>
              <button className="remove-button" disabled={!itemsEditable || !editable} onClick={() => onRemoveItem(index)} aria-label={`Remove ${row.name}`}>×</button>
            </div>
          );
        }) : (
          <p className="panel-hint">No spoken flavors were recorded. The saved order will use the camera-classified quantities below.</p>
        )}
      </div>
      <div className="camera-only-callout"><strong>All camera classifications</strong><span>{comparison.byFlavor.filter((entry) => entry.cameraQty > 0).map((entry) => `${entry.name} x${entry.cameraQty}`).join(", ") || "No classified items"}</span></div>
      {saveError && <p className="inline-error">{saveError}</p>}
      <button className="button primary save-button" disabled={saving || !items.length} onClick={onSave}>{saving ? "Saving order..." : "Save confirmed order"}</button>
    </section>
  );
}