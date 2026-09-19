import { useState } from "react";

const statusLabel = {
  exact_match: "Matches",
  quantity_mismatch: "Quantity differs",
  voice_only: "Voice only",
};

// Keeps a local draft so the field can be emptied while typing.
// Only commits on blur/Enter, and only if the value is a valid number >= 1.
function QuantityInput({ value, disabled, label, onCommit }) {
  // null = not editing, show the prop value. A string = the user's in-progress text.
  const [draft, setDraft] = useState(null);

  const commit = () => {
    if (draft !== null) {
      const next = parseInt(draft, 10);
      if (!Number.isNaN(next) && next >= 1 && next !== value) onCommit(next);
    }
    setDraft(null);
  };

  return (
    <input
      type="number"
      min="1"
      inputMode="numeric"
      className="review-quantity-input"
      disabled={disabled}
      value={draft ?? String(value)}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter") event.currentTarget.blur();
      }}
      aria-label={label}
    />
  );
}

function AddFlavorRow({ flavors, items, onAdd }) {
  const [name, setName] = useState("");
  const [qty, setQty] = useState(1);

  const taken = new Set(items.map((item) => item.name.toLowerCase()));
  const available = flavors.filter((f) => !taken.has(f.name.toLowerCase()));

  const handleAdd = () => {
    if (!name) return;
    onAdd(name, qty);
    setName("");
    setQty(1);
  };

  return (
    <div className="review-row">
      <div className="review-name">
        <select
          className="add-flavor-select"
          style={{ font: "inherit" }}
          value={name}
          onChange={(event) => setName(event.target.value)}
          aria-label="Missing flavor"
        >
          <option value="">Add a missing flavor…</option>
          {available.map((flavor) => (
            <option key={flavor.slug || flavor.name} value={flavor.name}>
              {flavor.name}
            </option>
          ))}
        </select>
      </div>
      <span className="camera-quantity">Missing</span>
      <button
        className="icon-button"
        disabled={qty <= 1}
        onClick={() => setQty((q) => Math.max(1, q - 1))}
        aria-label="Decrease quantity to add"
      >
        −
      </button>
      <QuantityInput
        value={qty}
        label="Quantity to add"
        onCommit={setQty}
      />
      <button
        className="icon-button"
        onClick={() => setQty((q) => q + 1)}
        aria-label="Increase quantity to add"
      >
        +
      </button>
      <button
        type="button"
        className="button"
        disabled={!name}
        onClick={handleAdd}
      >
        Add
      </button>
    </div>
  );
}

export default function ReviewPanel({
  comparison,
  items,
  itemsEditable,
  flavors = [],
  onAdjustQty,
  onRemoveItem,
  onAddItem,
  onSave,
  saving,
  saveError,
}) {
  if (!comparison) {
    return (
      <section className="review-panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Human review</span>
          </div>
        </div>
        <p className="review-intro">
          Comparing the spoken flavors against the camera scan...
        </p>
      </section>
    );
  }

  const voiceIndexes = new Map(items.map((item, index) => [item.slug, index]));
  const reviewRows = comparison.byFlavor.filter((row) => row.voiceQty > 0);

  return (
    <section className="review-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Human review</span>
        </div>
        <span
          className={`comparison-badge ${comparison.match ? "match" : "mismatch"}`}
        >
          {comparison.match ? "Match" : "Review needed"}
        </span>
      </div>
      <p className="review-intro">
        Camera quantities stay read-only. Edit the spoken list before saving the
        confirmed order.
      </p>
      <div className="review-list">
        {reviewRows.length ? (
          reviewRows.map((row) => {
            const index = voiceIndexes.get(row.slug);
            const editable = index !== undefined;
            return (
              <div className="review-row" key={row.slug}>
                <div className="review-name">
                  <strong>{row.name}</strong>
                  <span
                    className={`status-text ${row.status === "exact_match" ? "status-text-good" : "status-text-warn"}`}
                  >
                    {statusLabel[row.status]}
                  </span>
                </div>
                <span className="camera-quantity">Camera: {row.cameraQty}</span>
                <button
                  className="icon-button"
                  disabled={!itemsEditable || !editable || row.voiceQty <= 1}
                  onClick={() => onAdjustQty(index, -1)}
                  aria-label={`Decrease ${row.name}`}
                >
                  −
                </button>
                <QuantityInput
                  value={row.voiceQty}
                  disabled={!itemsEditable || !editable}
                  label={`Quantity for ${row.name}`}
                  onCommit={(next) => onAdjustQty(index, next - row.voiceQty)}
                />
                <button
                  className="icon-button"
                  disabled={!itemsEditable || !editable}
                  onClick={() => onAdjustQty(index, 1)}
                  aria-label={`Increase ${row.name}`}
                >
                  +
                </button>
                <button
                  className="remove-button"
                  disabled={!itemsEditable || !editable}
                  onClick={() => onRemoveItem(index)}
                  aria-label={`Remove ${row.name}`}
                >
                  ×
                </button>
              </div>
            );
          })
        ) : (
          <p className="panel-hint">
            No spoken flavors were recorded. The saved order will use the
            camera-classified quantities below.
          </p>
        )}

        {itemsEditable && (
          <AddFlavorRow flavors={flavors} items={items} onAdd={onAddItem} />
        )}

        <div className="camera-only-callout">
          <strong>All camera classifications</strong>
          <span>
            {comparison.byFlavor
              .filter((entry) => entry.cameraQty > 0)
              .map((entry) => `${entry.name} x${entry.cameraQty}`)
              .join(", ") || "No classified items"}
          </span>
        </div>
      </div>
      {saveError && <p className="inline-error">{saveError}</p>}
      <button
        className="button primary save-button"
        disabled={saving || !items.length}
        onClick={onSave}
      >
        {saving ? "Saving order..." : "Save confirmed order"}
      </button>
    </section>
  );
}