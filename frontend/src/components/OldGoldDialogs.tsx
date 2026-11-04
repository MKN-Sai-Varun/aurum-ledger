import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, api } from "../lib/api";
import { showDate } from "../lib/dates";
import { groupRupees } from "../lib/money";
import { tidyName } from "../lib/text";
import type { OldGold } from "../lib/types";
import Dialog from "./Dialog";

export function PurchaseDetails({ ogNo, onClose }: { ogNo: string; onClose: () => void }) {
  const [state, setState] = useState<
    | { status: "loading" }
    | { status: "error"; message: string }
    | { status: "ready"; purchase: OldGold }
  >({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    api
      .get<OldGold>(`/api/old-gold/${ogNo}`)
      .then((purchase) => {
        if (!cancelled) setState({ status: "ready", purchase });
      })
      .catch((e) => {
        if (!cancelled) {
          setState({
            status: "error",
            message: e instanceof ApiError ? e.message : "Something went wrong.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [ogNo]);

  return (
    <Dialog title={`Purchase ${ogNo}`} onClose={onClose}>
      {state.status === "loading" && (
        <p className="muted" role="status">
          Loading...
        </p>
      )}
      {state.status === "error" && (
        <p className="banner" role="alert">
          {state.message}
        </p>
      )}
      {state.status === "ready" && (
        <>
          <dl className="slip-rows">
            <div className="slip-row">
              <dt>Bill</dt>
              <dd className="figure">{state.purchase.bill_no}</dd>
            </div>
            <div className="slip-row">
              <dt>Customer</dt>
              <dd>{state.purchase.customer_name}</dd>
            </div>
            <div className="slip-row">
              <dt>Date</dt>
              <dd>{showDate(state.purchase.entry_date)}</dd>
            </div>
            <div className="slip-row">
              <dt>Gross weight</dt>
              <dd className="figure">{state.purchase.gross_weight_g} g</dd>
            </div>
            <div className="slip-row">
              <dt>Deduction</dt>
              <dd className="figure">{state.purchase.deduction_g} g</dd>
            </div>
            <div className="slip-row">
              <dt>Net weight</dt>
              <dd className="figure">{state.purchase.net_weight_g} g</dd>
            </div>
            <div className="slip-row">
              <dt>Tested purity</dt>
              <dd className="figure">{state.purchase.purity_pct} %</dd>
            </div>
            <div className="slip-row slip-key">
              <dt>Fine gold</dt>
              <dd className="figure">{state.purchase.fine_weight_g} g</dd>
            </div>
            <div className="slip-row">
              <dt>Rate per gram</dt>
              <dd className="figure">Rs {groupRupees(state.purchase.rate_per_g)}</dd>
            </div>
            <div className="slip-row slip-key">
              <dt>Value</dt>
              <dd className="figure">Rs {groupRupees(state.purchase.value)}</dd>
            </div>
            <div className="slip-row">
              <dt>Payment</dt>
              <dd>{state.purchase.payment_label}</dd>
            </div>
            <div className="slip-row">
              <dt>PAN</dt>
              <dd className="figure">{state.purchase.pan ?? "Not recorded"}</dd>
            </div>
            <div className="slip-row">
              <dt>Recorded by</dt>
              <dd>{state.purchase.recorded_by}</dd>
            </div>
            {state.purchase.note && (
              <div className="slip-row">
                <dt>Note</dt>
                <dd>{state.purchase.note}</dd>
              </div>
            )}
            {state.purchase.voided && (
              <div className="slip-row">
                <dt>Voided</dt>
                <dd>{state.purchase.void_reason}</dd>
              </div>
            )}
          </dl>
          {state.purchase.pan_masked && state.purchase.pan && (
            <p className="muted manage-note">
              The full PAN is visible to the finance head only.
            </p>
          )}
        </>
      )}
    </Dialog>
  );
}

export function VoidPurchase({
  purchase,
  onDone,
  onClose,
}: {
  purchase: OldGold;
  onDone: (updated: OldGold) => void;
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cleaned = tidyName(reason);
  const valid = cleaned.length >= 5 && cleaned.length <= 150;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !valid) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await api.post<OldGold>(`/api/old-gold/${purchase.og_no}/void`, {
        reason: cleaned,
      });
      onDone(updated);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
      setBusy(false);
    }
  }

  return (
    <Dialog title={`Void ${purchase.og_no}`} onClose={() => !busy && onClose()}>
      <dl className="slip-rows">
        <div className="slip-row">
          <dt>Bill</dt>
          <dd className="figure">{purchase.bill_no}</dd>
        </div>
        <div className="slip-row">
          <dt>Fine gold</dt>
          <dd className="figure">{purchase.fine_weight_g} g</dd>
        </div>
        <div className="slip-row">
          <dt>Value</dt>
          <dd className="figure">Rs {groupRupees(purchase.value)}</dd>
        </div>
      </dl>
      <p className="muted manage-note">
        The purchase stays in the list, marked as voided. The gold comes out of the stock
        statement from today, and earlier statements don't change.
      </p>
      <form onSubmit={(e) => void submit(e)} noValidate>
        <div className="field">
          <label htmlFor="void-reason">Reason</label>
          <input
            id="void-reason"
            className="input"
            type="text"
            autoComplete="off"
            maxLength={150}
            placeholder="For example: recorded against the wrong bill"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <p className="field-count muted">{cleaned.length} / 150, at least 5</p>
        </div>
        {error && (
          <p className="banner" role="alert">
            {error}
          </p>
        )}
        <div className="inline">
          <button className="btn btn-danger" type="submit" disabled={busy || !valid}>
            {busy ? "Voiding..." : "Void purchase"}
          </button>
          <button className="btn" type="button" disabled={busy} onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Dialog>
  );
}