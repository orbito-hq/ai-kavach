const STATUS_LABELS = {
  PENDING: "Pending",
  RUNNING: "Running",
  COMPLETED: "Completed",
  FAILED: "Failed",
};

export default function ScanList({ scans, activeScanId, onSelect }) {
  return (
    <div className="scan-list">
      <h2>Scans</h2>
      {scans.length === 0 && <p className="muted">No scans yet.</p>}
      <ul>
        {scans.map((scan) => (
          <li
            key={scan.id}
            className={scan.id === activeScanId ? "active" : ""}
            onClick={() => onSelect(scan.id)}
          >
            <span className={`status-dot ${scan.status.toLowerCase()}`} />
            <div className="scan-info">
              <span className="scan-source">{scan.source}</span>
              <span className="scan-status">{STATUS_LABELS[scan.status] ?? scan.status}</span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
