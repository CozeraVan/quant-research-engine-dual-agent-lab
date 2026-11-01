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
    # 合成「像真泄漏」的值：长随机串，不含 test/example 等占位符词
    # （2026-11-03 起占位符词被硬失败链过滤，避免测试夹具误报；
    #  本用例因此改用随机形态的值来守住「真泄漏仍要硬失败」这条线。）
    result = run_finalize_check(
        tmp_path,
        "const oldValue = 1;\n",
        "const oldValue = 1;\nconst api" + "Key = 'Xk29fJQ8LmNoPzR7vTy3Wq';\n",
    )
    assert result.returncode == 1
    assert "Potential " + "secret-like text" in result.stdout


def test_credential_scan_allows_known_placeholders(tmp_path):
    """占位符不算泄漏：tests 里的 X-Worker-Token: "test-worker-token" 曾误报，
    导致提交门禁 exit 1。真实长随机串仍由上一用例守住。"""
    result = run_finalize_check(
        tmp_path,
        "const oldValue = 1;\n",
        'const oldValue = 1;\nheaders={"X-Worker-' + 'Token": "test-worker-token"}\n',
    )
    assert result.returncode == 0, result.stdout + result.stderr
