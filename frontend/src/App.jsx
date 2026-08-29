import { useEffect, useState, useCallback } from "react";
import UploadForm from "./components/UploadForm.jsx";
import ScanList from "./components/ScanList.jsx";
import FindingsView from "./components/FindingsView.jsx";
import { listScans, getScan, getFindings } from "./api.js";

const ACTIVE_STATUSES = new Set(["PENDING", "RUNNING"]);

export default function App() {
  const [scans, setScans] = useState([]);
  const [activeScanId, setActiveScanId] = useState(null);
  const [activeScan, setActiveScan] = useState(null);
  const [findings, setFindings] = useState([]);

  const refreshScans = useCallback(async () => {
    const data = await listScans();
    setScans(data);
  }, []);

  useEffect(() => {
    refreshScans();
  }, [refreshScans]);

  useEffect(() => {
    if (!activeScanId) return;
    let cancelled = false;

    async function poll() {
      const scan = await getScan(activeScanId);
      if (cancelled) return;
      setActiveScan(scan);
      const findingRows = await getFindings(activeScanId);
      if (cancelled) return;
      setFindings(findingRows);
      refreshScans();
    }

    poll();
    const interval = setInterval(() => {
      if (activeScan && !ACTIVE_STATUSES.has(activeScan.status)) return;
      poll();
    }, 2000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeScanId]);

  return (
    <div className="app">
      <header>
        <h1>AI Kavach</h1>
        <p className="tagline">Autonomous Cyber Reasoning — MVP1</p>
      </header>
      <main>
        <aside>
          <UploadForm onScanCreated={(id) => { setActiveScanId(id); refreshScans(); }} />
          <ScanList scans={scans} activeScanId={activeScanId} onSelect={setActiveScanId} />
        </aside>
        <section>
          <FindingsView scan={activeScan} findings={findings} />
        </section>
      </main>
    </div>
  );
}
