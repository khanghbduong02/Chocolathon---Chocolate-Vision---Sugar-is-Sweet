import { useRef, useState } from "react";
import ItemEditor from "./ItemEditor";

export default function OrderLogCard({
  orderLog,
  flavors,
  onUpdateOrder,
  onDeleteOrder,
  onDownload,
  onClearLog,
  onOpenInsights,
}) {
  const [editingId, setEditingId] = useState(null);
  const [editItems, setEditItems] = useState([]);
  const [saving, setSaving] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteText, setDeleteText] = useState("");
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteError, setDeleteError] = useState("");

  const wrapRef = useRef(null);
  const wheelLockRef = useRef(false);

  function handleWheel(event) {
    const container = wrapRef.current;
    if (!container) return;
    event.preventDefault();
    if (wheelLockRef.current) return;

    const row = container.querySelector("tbody tr");
    const step = row ? row.offsetHeight : container.clientHeight;
    const direction = event.deltaY > 0 ? 1 : -1;

    wheelLockRef.current = true;
    container.scrollBy({ top: direction * step, behavior: "smooth" });
    setTimeout(() => {
      wheelLockRef.current = false;
    }, 300);
  }

  function handleClearClick() {
    if (orderLog.length === 0) return;
    setDeleteTarget(null);
    setDeleteOpen(true);
    setDeleteText("");
  }

  async function handleConfirmClear() {
    try {
      await onClearLog();
      closeDeleteModal();
    } catch (error) {
      setDeleteError(error.message || "Could not delete logs.");
    }
  }

  function startEdit(order) {
    setEditingId(order.id);
    setEditItems(
      (order.items || []).map((item) => ({
        slug: item.slug,
        name: item.name,
        quantity: item.quantity,
      })),
    );
  }

  async function saveEdit(order) {
    setSaving(true);
    try {
      await onUpdateOrder(order.id, editItems, order.box_size);
      setEditingId(null);
      setEditItems([]);
    } finally {
      setSaving(false);
    }
  }

  async function verifyOrder(order) {
    setSaving(true);
    try {
      await onUpdateOrder(order.id, editItems, order.box_size, "match");
      setEditingId(null);
      setEditItems([]);
    } finally {
      setSaving(false);
    }
  }

  function requestDeleteOrder(order) {
    setDeleteTarget(order);
    setDeleteOpen(true);
    setDeleteText("");
    setDeleteError("");
  }

  async function confirmDeleteOrder() {
    if (!deleteTarget) return;
    try {
      await onDeleteOrder(deleteTarget.id);
      closeDeleteModal();
    } catch (error) {
      setDeleteError(error.message || "Could not delete order.");
    }
  }

  function closeDeleteModal() {
    setDeleteOpen(false);
    setDeleteTarget(null);
    setDeleteText("");
  }

  return (
    <section className="order-log-panel">
      <button
        onClick={onOpenInsights}
        disabled={orderLog.length === 0}
        className="modal-close order-insights-button"
        aria-label="Session insights"
        title="Session insights"
      >
        📊
      </button>

      <div className="order-log-heading">
        <div>
          <span className="eyebrow">Order log</span>
        </div>
      </div>
      <p className="order-log-subtitle">
        {orderLog.length === 0
          ? "No boxes committed yet this session"
          : `${orderLog.length} box${orderLog.length === 1 ? "" : "es"} logged this session`}
      </p>

      <div className="order-table-wrap" ref={wrapRef} onWheel={handleWheel}>
        <table className="order-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Pieces</th>
              <th>Items</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {orderLog.length === 0 ? (
              <tr>
                <td colSpan="5" className="order-empty">
                  No orders yet.
                </td>
              </tr>
            ) : (
              orderLog.map((order) =>
                editingId === order.id ? (
                  <tr key={order.id}>
                    <td colSpan="5">
                      <div className="order-edit-layout">
                        <div>
                          <ItemEditor
                            items={editItems}
                            flavors={flavors}
                            expectedTotal={order.box_size}
                            onChange={setEditItems}
                            onSave={() => saveEdit(order)}
                            onVerify={() => verifyOrder(order)}
                            onCancel={() => setEditingId(null)}
                            busy={saving}
                          />
                          <div className="order-audit-summary">
                            <strong>Saved verification data</strong>
                            <span>
                              Voice: {formatItems(order.transcript_items)}
                            </span>
                            <span>
                              Camera: {formatItems(order.camera_items)}
                            </span>
                          </div>
                        </div>
                        {order.has_photo ? (
                          <div>
                            <img
                              className="saved-order-image"
                              src={`/api/orders/${order.id}/photo/annotated`}
                              alt="Saved annotated box"
                            />
                            <a
                              href={`/api/orders/${order.id}/photo/capture`}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Original photo
                            </a>
                          </div>
                        ) : (
                          <p>No photo was saved.</p>
                        )}
                      </div>
                    </td>
                  </tr>
                ) : (
                  <tr key={order.id}>
                    <td className="order-time">{order.timestamp}</td>
                    <td className="order-pieces">
                      {order.total_pieces}
                      {order.box_size ? (
                        <small> / {order.box_size}</small>
                      ) : null}
                    </td>
                    <td className="order-items">{order.items_text}</td>
                    <td className="order-status-cell">
                      <span
                        className={`order-status ${order.comparison_status === "match" ? "match" : "review"}`}
                      >
                        {order.comparison_status === "match"
                          ? "Good"
                          : "Needs verification"}
                      </span>
                    </td>
                    <td className="order-actions-cell">
                      <div className="order-row-actions">
                        <button
                          className="order-edit-link"
                          type="button"
                          onClick={() => startEdit(order)}
                        >
                          Edit
                        </button>
                        <button
                          className="order-delete-link"
                          type="button"
                          onClick={() => requestDeleteOrder(order)}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ),
              )
            )}
          </tbody>
        </table>
      </div>

      <div className="order-log-actions">
        <button
          onClick={onDownload}
          disabled={orderLog.length === 0}
          className="button secondary"
        >
          Download order log (JSON)
        </button>

        {!deleteOpen ? (
          <button
            onClick={handleClearClick}
            disabled={orderLog.length === 0}
            className="button danger"
          >
            Clear log
          </button>
        ) : (
          <button
            type="button"
            className="button danger"
            onClick={handleClearClick}
          >
            Delete logs
          </button>
        )}
      </div>
      {deleteError && <p className="inline-error">{deleteError}</p>}

      {deleteOpen && (
        <div className="delete-modal-backdrop" onClick={closeDeleteModal}>
          <div
            className="delete-modal"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="order-log-heading">
              <div>
                <span className="eyebrow">Permanent action</span>
                <h3>
                  {deleteTarget ? "Delete this order?" : "Delete all logs?"}
                </h3>
              </div>
              <button
                type="button"
                className="modal-close"
                onClick={closeDeleteModal}
                aria-label="Close"
              >
                ×
              </button>
            </div>
            <p>
              {deleteTarget
                ? `This will permanently delete order #${deleteTarget.id}.`
                : "This removes all saved orders from the order log."}{" "}
              Type <strong>DELETE</strong> to continue.
            </p>
            <input
              className="delete-input"
              value={deleteText}
              onChange={(event) => setDeleteText(event.target.value)}
              placeholder="Type DELETE"
              autoFocus
            />
            <div className="order-log-actions">
              <button
                type="button"
                className="button danger"
                disabled={deleteText !== "DELETE"}
                onClick={deleteTarget ? confirmDeleteOrder : handleConfirmClear}
              >
                Delete permanently
              </button>
              <button
                type="button"
                className="button secondary"
                onClick={closeDeleteModal}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function formatItems(items) {
  return (
    (items || [])
      .map((item) => `${item.name || item.slug} x${item.quantity}`)
      .join(", ") || "No items recorded"
  );
}
