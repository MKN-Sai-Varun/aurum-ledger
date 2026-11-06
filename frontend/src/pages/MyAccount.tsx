import { useEffect, useState } from "react";
import { ApiError, api } from "../lib/api";
import { showDateIn } from "../lib/dates";
import { CATEGORY_TEXT, KIND_TEXT, TEXT, pick } from "../lib/i18n";
import type { TextKey } from "../lib/i18n";
import type { MySummary } from "../lib/types";
import { useLang } from "../lib/useLang";

type Load =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: MySummary };

export default function MyAccount() {
  const [lang, setLang] = useLang();
  const t = (key: TextKey) => TEXT[key][lang];

  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .get<MySummary>("/api/me/summary")
      .then((data) => {
        if (!cancelled) setLoad({ status: "ready", data });
      })
      .catch((e) => {
        if (!cancelled) {
          setLoad({
            status: "error",
            message: e instanceof ApiError ? e.message : "Something went wrong.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  return (
    <div className={`page-body my-page${lang === "ta" ? " tamil" : ""}`} lang={lang}>
      <div className="my-head">
        <h1 className="my-title">{t("title")}</h1>
        <div className="tabs" role="group" aria-label={t("language")}>
          <button
            type="button"
            className="tab"
            aria-pressed={lang === "ta"}
            lang="ta"
            onClick={() => setLang("ta")}
          >
            தமிழ்
          </button>
          <button
            type="button"
            className="tab"
            aria-pressed={lang === "en"}
            lang="en"
            onClick={() => setLang("en")}
          >
            English
          </button>
        </div>
      </div>

      {load.status === "loading" && (
        <div className="stack" aria-busy="true" role="status">
          <span className="sr-only">{t("loading")}</span>
          <div className="card skeleton" />
          <div className="card skeleton" />
        </div>
      )}

      {load.status === "error" && (
        <section className="card">
          <p className="status-line">{load.message}</p>
          <button
            className="btn btn-primary"
            onClick={() => {
              setLoad({ status: "loading" });
              setAttempt((n) => n + 1);
            }}
          >
            {t("retry")}
          </button>
        </section>
      )}

      {load.status === "ready" && (
        <div className="stack">
          <section className="card my-balance">
            <p className="eyebrow">{load.data.karigar}</p>
            <p className="my-label">{t("balanceLabel")}</p>
            <p className="my-number figure">{load.data.balance_g}</p>
            <p className="muted">{t("unit")}</p>
            <p className="my-open">
              {t("openJobs")}: <span className="figure">{load.data.open_jobs}</span>
            </p>
          </section>

          <h2 className="my-heading">{t("jobsHeading")}</h2>
          {load.data.jobs.length === 0 ? (
            <section className="card">
              <p className="status-line">{t("noJobs")}</p>
            </section>
          ) : (
            load.data.jobs.map((job) => (
              <article className="card" key={job.job_no}>
                <header className="job-head">
                  <div>
                    <p className="eyebrow figure">{job.job_no}</p>
                    <h3 className="my-item">{pick(CATEGORY_TEXT, job.category, lang)}</h3>
                    <p className="karigar-meta">{showDateIn(job.opened_on, lang)}</p>
                  </div>
                  <span className={`chip ${job.status === "OPEN" ? "chip-ok" : "chip-muted"}`}>
                    {job.status === "OPEN" ? t("open") : t("closed")}
                  </span>
                </header>
                <dl className="slip-rows">
                  <div className="slip-row">
                    <dt>{t("issued")}</dt>
                    <dd className="figure">{job.issued_fine_g}</dd>
                  </div>
                  <div className="slip-row">
                    <dt>{t("returned")}</dt>
                    <dd className="figure">{job.returned_fine_g}</dd>
                  </div>
                  <div className="slip-row slip-key">
                    <dt>{t("outstanding")}</dt>
                    <dd className="figure">{job.outstanding_g}</dd>
                  </div>
                </dl>
              </article>
            ))
          )}

          <h2 className="my-heading">{t("entriesHeading")}</h2>
          {load.data.entries.length === 0 ? (
            <section className="card">
              <p className="status-line">{t("noEntries")}</p>
            </section>
          ) : (
            load.data.entries.map((entry) => (
              <article className="card" key={entry.txn_no}>
                <header className="job-head">
                  <div>
                    <p className="my-kind">{pick(KIND_TEXT, entry.kind, lang)}</p>
                    <p className="karigar-meta">
                      {showDateIn(entry.entry_date, lang)} - {pick(CATEGORY_TEXT, entry.category, lang)}
                    </p>
                  </div>
                  <span
                    className={`chip ${entry.kind === "ISSUE" ? "chip-gold" : entry.kind === "REVERSAL" ? "chip-muted" : "chip-ok"}`}
                  >
                    <span className="figure">{entry.change_g}</span>
                  </span>
                </header>
                <dl className="slip-rows">
                  <div className="slip-row">
                    <dt>{t("slipNo")}</dt>
                    <dd className="figure">{entry.txn_no}</dd>
                  </div>
                  <div className="slip-row">
                    <dt>{t("job")}</dt>
                    <dd className="figure">{entry.job_no}</dd>
                  </div>
                  <div className="slip-row">
                    <dt>{t("gross")}</dt>
                    <dd className="figure">{entry.gross_weight_g}</dd>
                  </div>
                  <div className="slip-row">
                    <dt>{t("purity")}</dt>
                    <dd className="figure">{entry.purity_pct} %</dd>
                  </div>
                  <div className="slip-row slip-key">
                    <dt>{t("fine")}</dt>
                    <dd className="figure">{entry.fine_weight_g}</dd>
                  </div>
                  {entry.huid && (
                    <div className="slip-row">
                      <dt>HUID</dt>
                      <dd className="figure">{entry.huid}</dd>
                    </div>
                  )}
                </dl>
              </article>
            ))
          )}

          {load.data.truncated && <p className="muted manage-note">{t("latestOnly")}</p>}
          <p className="muted manage-note">{t("readOnly")}</p>
        </div>
      )}
    </div>
  );
}