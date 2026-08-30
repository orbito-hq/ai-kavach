const BASE = "/api";

async function request(path, options) {
  const res = await fetch(`${BASE}${path}`, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export function createScanFromRepo(repoUrl) {
  const form = new FormData();
  form.append("repo_url", repoUrl);
  return request("/scans", { method: "POST", body: form });
}

export function createScanFromZip(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/scans", { method: "POST", body: form });
}

export function listScans() {
  return request("/scans");
}

export function getScan(scanId) {
  return request(`/scans/${scanId}`);
}

export function getFindings(scanId) {
  return request(`/scans/${scanId}/findings`);
}

export function getScanLogs(scanId) {
  return request(`/scans/${scanId}/logs`);
}
