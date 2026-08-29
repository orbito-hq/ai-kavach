import io
import zipfile

import pytest

from app import intake


def make_zip_bytes(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_prepare_from_zip_extracts_files(tmp_path, monkeypatch):
    monkeypatch.setattr(intake, "WORKSPACE_ROOT", tmp_path)
    zip_bytes = make_zip_bytes({"app.py": "print('hi')\n", "sub/mod.py": "x = 1\n"})

    target = intake.prepare_from_zip("scan-a", zip_bytes)

    assert (target / "app.py").read_text() == "print('hi')\n"
    assert (target / "sub" / "mod.py").read_text() == "x = 1\n"


def test_prepare_from_zip_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(intake, "WORKSPACE_ROOT", tmp_path)
    zip_bytes = make_zip_bytes({"../evil.py": "pwn()\n"})

    with pytest.raises(intake.IntakeError):
        intake.prepare_from_zip("scan-b", zip_bytes)


def test_prepare_from_zip_rejects_bad_zip(tmp_path, monkeypatch):
    monkeypatch.setattr(intake, "WORKSPACE_ROOT", tmp_path)

    with pytest.raises(intake.IntakeError):
        intake.prepare_from_zip("scan-c", b"not a zip file")


def test_prepare_from_git_rejects_non_https(tmp_path, monkeypatch):
    monkeypatch.setattr(intake, "WORKSPACE_ROOT", tmp_path)

    with pytest.raises(intake.IntakeError):
        intake.prepare_from_git("scan-d", "file:///etc/passwd")


def test_detect_languages_counts_by_extension(tmp_path):
    (tmp_path / "a.py").write_text("x = 1")
    (tmp_path / "b.py").write_text("y = 2")
    (tmp_path / "c.js").write_text("var z = 3;")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignored.js").write_text("ignored")

    langs = intake.detect_languages(tmp_path)

    assert langs["Python"] == 2
    assert langs["JavaScript"] == 1
