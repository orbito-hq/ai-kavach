{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  name = "ai-kavach-dev";

  buildInputs = [
    pkgs.python311
    pkgs.nodejs_20
    pkgs.git
  ];
  # semgrep is installed via pip (backend/requirements.txt) instead of
  # nixpkgs, since the nixpkgs semgrep derivation fails to build here
  # (sphinx/python3.11 incompatibility in this channel snapshot).
  # pip/virtualenv come from python3's stdlib venv module instead of
  # python311Packages.pip, which pulls in the same broken sphinx build.

  shellHook = ''
    echo "ai-kavach dev shell: python=$(python3 --version), node=$(node --version)"
    echo "semgrep is installed via backend/.venv (pip) — activate it and run 'semgrep --version' to check"
  '';
}
