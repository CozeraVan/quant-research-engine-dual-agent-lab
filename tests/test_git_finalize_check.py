import shutil
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "git-finalize-check.sh"


def run_finalize_check(tmp_path: Path, initial: str, changed: str) -> subprocess.CompletedProcess:
    script_path = tmp_path / "scripts" / SCRIPT.name
    script_path.parent.mkdir()
    shutil.copy(SCRIPT, script_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    source = tmp_path / "example.js"
    source.write_text(initial)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=tmp_path, check=True)
    source.write_text(changed)
    return subprocess.run(
        ["bash", str(script_path)], cwd=tmp_path, text=True, capture_output=True
    )


def test_credential_scan_ignores_unchanged_diff_context(tmp_path):
    credential_fixture = "function saas" + "To" + "ken() { return 'example'; }\n"
    result = run_finalize_check(
        tmp_path,
        credential_fixture + "const oldValue = 1;\n",
        credential_fixture + "const oldValue = 2;\n",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_credential_scan_rejects_new_sensitive_text(tmp_path):
    result = run_finalize_check(
        tmp_path,
        "const oldValue = 1;\n",
        "const oldValue = 1;\nconst api" + "Key = 'example-sensitive-value';\n",
    )
    assert result.returncode == 1
    assert "Potential " + "secret-like text" in result.stdout
