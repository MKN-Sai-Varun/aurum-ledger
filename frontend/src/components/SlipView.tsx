import { showDate } from "../lib/dates";
import type { Slip } from "../lib/types";

export default function SlipView({ slip, onNew }: { slip: Slip; onNew: () => void }) {
  return (
    <div>
      <p className="banner banner-ok no-print" role="status">
        Issue saved as {slip.txn_no}.
      </p>

      <article className="slip" aria-label={`Issue slip ${slip.txn_no}`}>
        <header className="slip-head">
          <div>
            <p className="eyebrow">Aurum / Issue slip</p>
            <h2 className="slip-title">{slip.karigar}</h2>
          </div>
          <div className="slip-ref figure">
            <div>{slip.txn_no}</div>
            <div>{slip.job_no}</div>
          </div>
        </header>

        <dl className="slip-rows">
          <div className="slip-row">
            <dt>Date</dt>
            <dd>{showDate(slip.entry_date)}</dd>
          </div>
          <div className="slip-row">
            <dt>Item category</dt>
            <dd>{slip.category}</dd>
          </div>
          <div className="slip-row">
            <dt>Gross weight</dt>
            <dd className="figure">{slip.gross_weight_g} g</dd>
          </div>
          <div className="slip-row">
            <dt>Purity</dt>
            <dd className="figure">{slip.purity_pct} %</dd>
          </div>
          <div className="slip-row slip-key">
            <dt>Fine gold issued</dt>
            <dd className="figure">{slip.fine_weight_g} g</dd>
          </div>
          <div className="slip-row">
            <dt>Allowed wastage</dt>
            <dd className="figure">
              {slip.allowed_wastage_g} g ({slip.allowed_wastage_pct} %)
            </dd>
          </div>
          <div className="slip-row slip-key">
            <dt>Balance with karigar</dt>
            <dd className="figure">{slip.balance_g} g</dd>
          </div>
          {slip.note && (
            <div className="slip-row">
              <dt>Note</dt>
              <dd>{slip.note}</dd>
            </div>
          )}
        </dl>

        <footer className="slip-foot">Issued by {slip.issued_by}</footer>
      </article>

      <div className="slip-actions no-print">
        <button className="btn btn-primary" onClick={() => window.print()}>
          Print slip
        </button>
        <button className="btn" onClick={onNew}>
          Record another issue
        </button>
      </div>
    </div>
  );
}