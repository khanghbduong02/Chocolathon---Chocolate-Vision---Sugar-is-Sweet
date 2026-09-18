function pieceCount(items) {
  return items.reduce((sum, item) => sum + Number(item.quantity || 0), 0);
}

export default function ItemEditor({ items, flavors, expectedTotal, onChange, onSave, onVerify, onCancel, busy, saveLabel = "Save changes" }) {
  const unused = flavors.filter((flavor) => !items.some((item) => item.slug === flavor.slug));
  const total = pieceCount(items);

  function setQuantity(slug, value) {
    const quantity = Math.max(0, Number(value) || 0);
    onChange(items.map((item) => item.slug === slug ? { ...item, quantity } : item).filter((item) => item.quantity > 0));
  }

  function replaceFlavor(oldSlug, newSlug) {
    const flavor = flavors.find((entry) => entry.slug === newSlug);
    if (flavor) onChange(items.map((item) => item.slug === oldSlug ? { ...item, slug: flavor.slug, name: flavor.name } : item));
  }

  return (
    <div className="order-editor">
      <div className={`order-editor-total ${expectedTotal && total !== expectedTotal ? "is-mismatch" : ""}`}>
        <span>Total pieces</span><strong>{total}</strong>
        {expectedTotal && <small>Expected {expectedTotal}</small>}
      </div>
      {items.map((item) => (
        <div className="order-editor-row" key={item.slug}>
          <select value={item.slug} onChange={(event) => replaceFlavor(item.slug, event.target.value)}>
            <option value={item.slug}>{item.name}</option>
            {unused.map((flavor) => <option key={flavor.slug} value={flavor.slug}>{flavor.name}</option>)}
          </select>
          <button type="button" onClick={() => setQuantity(item.slug, item.quantity - 1)}>−</button>
          <input type="number" min="1" value={item.quantity} onChange={(event) => setQuantity(item.slug, event.target.value)} />
          <button type="button" onClick={() => setQuantity(item.slug, item.quantity + 1)}>+</button>
          <button type="button" className="editor-remove" onClick={() => setQuantity(item.slug, 0)}>Remove</button>
        </div>
      ))}
      <div className="order-editor-actions">
        <button type="button" className="button primary" disabled={busy || !items.length} onClick={onSave}>{busy ? "Saving..." : saveLabel}</button>
        {onVerify && <button type="button" className="button gold" disabled={busy || !items.length} onClick={onVerify}>Verify order</button>}
        <button type="button" className="button secondary editor-cancel" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}
