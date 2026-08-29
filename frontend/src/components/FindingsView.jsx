import { useState } from "react";

const VERDICT_LABELS = {
  CONFIRMED: "Confirmed",
  REJECTED: "Rejected",
  NEEDS_TESTING: "Needs Testing",
};

export default function FindingsView({ scan, findings }) {
  const [selected, setSelected] = useState(null);

  if (!scan) {
    return <div className="findings-view muted">Select or start a scan to see results.</div>;
  }

  return (
    <div className="findings-view">
      <div className="scan-header">
        <h2>{scan.source}</h2>
        <span className={`status-badge ${scan.status.toLowerCase()}`}>{scan.status}</span>
      </div>

      {scan.status === "FAILED" && <p className="error">{scan.error}</p>}
      {scan.status !== "FAILED" && scan.status !== "COMPLETED" && (
        <p className="muted">Scan in progress — this page refreshes automatically.</p>
      )}

      {scan.languages && (
        <p className="muted">Languages: {formatLanguages(scan.languages)}</p>
      )}

      {scan.status === "COMPLETED" && findings.length === 0 && (
        <p className="muted">No findings — Semgrep did not flag anything.</p>
      )}

      <table className="findings-table">
        <thead>
          <tr>
            <th>Severity</th>
            <th>Type</th>
            <th>Location</th>
            <th>AI Verdict</th>
          </tr>
        </thead>
        <tbody>
          {findings.map((f) => (
            <tr key={f.id} onClick={() => setSelected(f)} className="clickable">
              <td>
                <span className={`severity ${f.severity.toLowerCase()}`}>{f.severity}</span>
              </td>
              <td>{f.type}</td>
              <td>
                {f.file}:{f.line}
              </td>
              <td>
                <span className={`verdict ${(f.ai_verdict || "").toLowerCase()}`}>
                  {VERDICT_LABELS[f.ai_verdict] ?? f.ai_verdict ?? "—"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {selected && <FindingDetail finding={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function formatLanguages(languagesJson) {
  try {
    const langs = typeof languagesJson === "string" ? JSON.parse(languagesJson) : languagesJson;
    return Object.entries(langs)
      .map(([lang, count]) => `${lang} (${count})`)
      .join(", ");
  } catch {
    return "";
  }
}

function FindingDetail({ finding, onClose }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose}>
          ×
        </button>
        <h3>{finding.type}</h3>
        <p className="muted">
          {finding.file}:{finding.line} · rule: {finding.rule} · confidence: {finding.confidence}
        </p>

        <h4>Evidence</h4>
        <pre>{finding.evidence}</pre>

        <h4>AI Analysis — {VERDICT_LABELS[finding.ai_verdict] ?? finding.ai_verdict}</h4>
        <p>{finding.ai_explanation}</p>
      </div>
    </div>
  );
}
