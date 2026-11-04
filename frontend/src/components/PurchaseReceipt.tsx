import { showDate } from "../lib/dates";
import { groupRupees } from "../lib/money";
import type { OldGold } from "../lib/types";

export default function PurchaseReceipt({
  purchase,
  onNew,
}: {
  purchase: OldGold;
  onNew: () => void;
}) {
  return (
    <div>
      <p className="banner banner-ok no-print" role="status">
        Purchase saved as {purchase.og_no}.
      </p>

      <article className="slip" aria-label={`Old gold receipt ${purchase.og_no}`}>
        <header className="slip-head">
          <div>
            <p className="eyebrow">Aurum / Old gold receipt</p>
            <h2 className="slip-title">{purchase.customer_name}</h2>
          </div>
          <div className="slip-ref figure">
            <div>{purchase.og_no}</div>
            <div>{purchase.bill_no}</div>
          </div>
        </header>

        <dl className="slip-rows">
          <div className="slip-row">
            <dt>Date</dt>
            <dd>{showDate(purchase.entry_date)}</dd>
          </div>
          <div className="slip-row">
            <dt>Gross weight</dt>
            <dd className="figure">{purchase.gross_weight_g} g</dd>
          </div>
          <div className="slip-row">
            <dt>Deduction</dt>
            <dd className="figure">{purchase.deduction_g} g</dd>
          </div>
          <div className="slip-row">
            <dt>Net weight</dt>
            <dd className="figure">{purchase.net_weight_g} g</dd>
          </div>
          <div className="slip-row">
            <dt>Tested purity</dt>
            <dd className="figure">{purchase.purity_pct} %</dd>
          </div>
          <div className="slip-row slip-key">
            <dt>Fine gold</dt>
            <dd className="figure">{purchase.fine_weight_g} g</dd>
          </div>
          <div className="slip-row">
            <dt>Rate per gram</dt>
            <dd className="figure">Rs {groupRupees(purchase.rate_per_g)}</dd>
          </div>
          <div className="slip-row slip-key">
            <dt>Value</dt>
            <dd className="figure">Rs {groupRupees(purchase.value)}</dd>
          </div>
          <div className="slip-row">
            <dt>Payment</dt>
            <dd>{purchase.payment_label}</dd>
          </div>
          {purchase.pan && (
            <div className="slip-row">
              <dt>PAN</dt>
              <dd className="figure">{purchase.pan}</dd>
            </div>
          )}
          {purchase.note && (
            <div className="slip-row">
              <dt>Note</dt>
              <dd>{purchase.note}</dd>
            </div>
          )}
        </dl>

        <footer className="slip-foot">Recorded by {purchase.recorded_by}</footer>
      </article>

      <div className="slip-actions no-print">
        <button className="btn btn-primary" onClick={() => window.print()}>
          Print receipt
        </button>
        <button className="btn" onClick={onNew}>
          Record another purchase
        </button>
      </div>
    </div>
  );
}