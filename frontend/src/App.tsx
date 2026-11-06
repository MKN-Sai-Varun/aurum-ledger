import AuthProvider from "./auth/AuthProvider";
import { useAuth } from "./auth/auth-context";
import Layout from "./components/Layout";
import { useRoute } from "./lib/useRoute";
import Issue from "./pages/Issue";
import Jobs from "./pages/Jobs";
import Karigars from "./pages/Karigars";
import Ledger from "./pages/Ledger";
import Alerts from "./pages/Alerts";
import Stock from "./pages/Stock";
import OldGold from "./pages/OldGold";
import Login from "./pages/Login";
import MyAccount from "./pages/MyAccount";
import Aging from "./pages/Aging";

const KNOWN_ROUTES = ["/karigars", "/jobs", "/ledger", "/oldgold", "/issue", "/alerts", "/stock","/aging"];

function Notice({ text }: { text: string }) {
  return (
    <section className="card">
      <p className="status-line">{text}</p>
      <a className="btn btn-primary" href="#/karigars">
        Go to karigars
      </a>
    </section>
  );
}

function Screen() {
  const { state, retry } = useAuth();
  const route = useRoute();

  if (state.status === "loading") {
    return (
      <div className="boot" role="status">
        <span className="sr-only">Loading</span>
        <span className="boot-dot" aria-hidden="true" />
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="boot">
        <section className="card boot-card">
          <p className="status-line">{state.message}</p>
          <button className="btn btn-primary" onClick={retry}>
            Try again
          </button>
        </section>
      </div>
    );
  }

  if (state.status === "anonymous") return <Login />;
  if (state.user.role === "karigar") {
    return (
      <Layout>
        <MyAccount />
      </Layout>
    );
  }

  const isClerk = state.user.role === "issue_clerk";
  const isFinance = state.user.role === "finance_head";

  return (
    <Layout>
      {route === "/karigars" && <Karigars />}
      {route === "/jobs" && <Jobs />}
      {route === "/ledger" && <Ledger />}
      {route === "/oldgold" && <OldGold />}
      {route === "/aging" && (isFinance ? <Aging /> : <Notice text="Only the finance head can see aging." />)}

      {route === "/alerts" &&
        (isFinance ? <Alerts /> : <Notice text="Only the finance head can see alerts." />)}
      {route === "/stock" &&
        (isFinance ? <Stock /> : <Notice text="Only the finance head can see stock." />)}
      {route === "/issue" &&
        (isClerk ? <Issue /> : <Notice text="Only the issue clerk can record issues." />)}
      {!KNOWN_ROUTES.includes(route) && <Notice text="That page doesn't exist." />}
    </Layout>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Screen />
    </AuthProvider>
  );
}