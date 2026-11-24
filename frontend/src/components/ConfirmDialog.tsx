import { useState } from "react";
import { ApiError } from "../api/errors";
import { Modal } from "./Modal";

interface Props {
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => Promise<unknown>;
  onClose: () => void;
  /** Called after a successful action (the dialog then closes itself). */
  onDone?: () => void;
  /** Called when the API answers 409, so the page can refetch and show the real state. */
  onConflict?: () => void;
}

/**
 * Confirm-then-run dialog for stock-changing actions. A 409 from the backend (order
 * already completed or received, not enough stock) is shown as a distinct conflict
 * notice carrying the server's own message, and the dialog stays open so it is read.
 */
export function ConfirmDialog({ title, message, confirmLabel, onConfirm, onClose, onDone, onConflict }: Props) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const conflict = error instanceof ApiError && error.isConflict;

  async function run() {
    setPending(true);
    setError(null);
    try {
      await onConfirm();
      onDone?.();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e : new Error("Something went wrong."));
      if (e instanceof ApiError && e.isConflict) onConflict?.();
      setPending(false);
    }
  }

  return (
    <Modal title={title} onClose={onClose}>
      <p>{message}</p>
      {error && (
        <div role="alert" className={conflict ? "notice notice-conflict" : "notice notice-error"}>
          {conflict ? (
            <>
              <strong>Conflict (409): nothing was changed.</strong>
              <p>{error.message}</p>
              <p className="muted">The list has been refreshed so you can see the current state of this record.</p>
            </>
          ) : (
            <p>{error.message}</p>
          )}
        </div>
      )}
      <div className="form-actions">
        <button type="button" className="btn" onClick={onClose}>
          {conflict ? "Close" : "Cancel"}
        </button>
        {!conflict && (
          <button type="button" className="btn btn-primary" onClick={() => void run()} disabled={pending} data-autofocus>
            {pending ? "Working…" : confirmLabel}
          </button>
        )}
      </div>
    </Modal>
  );
}
