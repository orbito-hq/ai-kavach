import { useState } from "react";
import { createScanFromRepo, createScanFromZip } from "../api.js";

export default function UploadForm({ onScanCreated }) {
  const [repoUrl, setRepoUrl] = useState("");
  const [file, setFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    if (!repoUrl && !file) {
      setError("Provide a Git repo URL or select a ZIP file.");
      return;
    }
    setSubmitting(true);
    try {
      const result = file
        ? await createScanFromZip(file)
        : await createScanFromRepo(repoUrl);
      setRepoUrl("");
      setFile(null);
      onScanCreated(result.scan_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="upload-form" onSubmit={handleSubmit}>
      <h2>Secure a Target</h2>
      <label>
        Git repository URL
        <input
          type="text"
          placeholder="https://github.com/org/repo.git"
          value={repoUrl}
          disabled={!!file}
          onChange={(e) => setRepoUrl(e.target.value)}
        />
      </label>
      <div className="divider">or</div>
      <label>
        Upload ZIP
        <input
          type="file"
          accept=".zip"
          disabled={!!repoUrl}
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </label>
      {error && <p className="error">{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? "Starting scan…" : "Run Scan"}
      </button>
    </form>
  );
}
