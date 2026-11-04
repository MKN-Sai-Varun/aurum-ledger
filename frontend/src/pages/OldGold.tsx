import { useState } from "react";
import { useAuth } from "../auth/auth-context";
import OldGoldForm from "../components/OldGoldForm";
import OldGoldList from "../components/OldGoldList";

export default function OldGold() {
  const { state } = useAuth();
  const role = state.status === "signed-in" ? state.user.role : null;
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <div className="page-body">
      <div className="page-head no-print">
        <p className="eyebrow">Aurum / 07 Old gold</p>
        <h1 className="page-title">
          Old gold from <span className="accent">customers</span>
        </h1>
        <p className="lede">
          Each purchase is recorded once and tied to its exchange bill, with the tested
          purity, the fine gold and the value.
        </p>
      </div>

      {role === "issue_clerk" && (
        <OldGoldForm onSaved={() => setRefreshKey((n) => n + 1)} />
      )}

      <h2 className="section-heading no-print">Purchases</h2>
      <div className="no-print">
        <OldGoldList refreshKey={refreshKey} isFinance={role === "finance_head"} />
      </div>
    </div>
  );
}