import { useRef, useState } from "react";
import ItemEditor from "./ItemEditor";
import { API_BASE_URL, apiFetch } from "../constants/config";

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
  const [photoError, setPhotoError] = useState("");

  const wrapRef = useRef(null);

  // Fetch the photo with the ngrok header (plain <a href> can't send it, and
  // a relative href would hit the Vercel domain instead of the backend),
  // then open the blob in a new tab. The tab is opened synchronously on click
  // so popup blockers allow it, then pointed at the blob once it loads.
  async function openPhoto(event, order, kind) {
    event.preventDefault();
    setPhotoError("");
    const win = window.open("", "_blank");
    try {
      const response = await apiFetch(
        `${API_BASE_URL}/api/orders/${order.id}/photo/${kind}`,
      );
      if (!response.ok) throw new Error("Photo not found.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      if (win) win.location.href = url;
      else window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (error) {
      if (win) win.close();
      setPhotoError(error.message || "Could not load photo.");
    }
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
    setPhotoError("");
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

      <div className={`order-table-wrap${editingId ? " is-editing" : ""}`} ref={wrapRef}>
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
                          <div className="order-photo-links">
                            <a
                              href="#"
                              onClick={(event) => openPhoto(event, order, "capture")}
                            >
                              Original photo
                            </a>
                            <a
                              href="#"
                              onClick={(event) => openPhoto(event, order, "annotated")}
                            >
                              Annotated photo (with classifications)
                            </a>
                            {photoError && <p className="inline-error">{photoError}</p>}
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