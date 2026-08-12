"""GUI 新因子创建闭环（P2）：查重 → 沙箱冒烟 → 用户确认晋升 → indicators 入库。

与 ``factor_admin.py``（既有因子补周期/补列）区分：本模块管**全新因子**。
- 沙箱在 indicators 项目内 ``sandbox/factors/``（独立目录，不在 factors 包内，
  不会被 core/factor_registry.py 自动发现）。
- 冒烟 = 子进程跑 indicators 官方 ``sandbox/smoke_factor.py``（单股、只读 DB）。
- 晋升 = pgrep 安全检查 → 复制为 ``factors/<name>_factor.py`` → 追加
  ``config/factors.yaml`` → 后台 job（validate → backfill --execute，复用
  daily_jobs.start_script_job，lock_key="indicators" 与日更/补全共用锁）。

QRE 对业务 DB 只读；所有写库动作全部走 indicators 官方脚本。
repo / runner / job_starter 均可注入，便于测试。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from quant_research_engine.gui.daily_jobs import UV_BIN, start_script_job
from quant_research_engine.gui.factor_admin import config_path_for, indicators_repo
from quant_research_engine.gui.factor_nl_compiler import check_code_safety

# 合法类别（决定目标表 stock_daily_<category>_<price_col>）
FACTOR_CATEGORIES = (
    "candle",
    "momentum",
    "overlap",
    "performance",
    "statistics",
    "trend",
    "volatility",
    "volume",
)

PRICE_COLUMNS = ("close", "typical_price", "average_price", "median_price")

SMOKE_DEFAULT_CODE = "600519.SH"
SMOKE_DEFAULT_DAYS = 400
SMOKE_TIMEOUT_SECONDS = 120

_NAME_RE = re.compile(r"[a-z][a-z0-9_]*")


def _safe_name(name: str) -> str:
    return name.replace("/", "_").replace("\\", "_").strip()


def _param_to_suffix(param: Any) -> str:
    """与 indicators core.factor_base.param_to_suffix 等价的本地实现（跨项目不共享代码）。"""
    if param is None:
        return ""
    if isinstance(param, (list, tuple)):
        return "_".join(str(v).replace(".", "_") for v in param)
    return str(param).replace(".", "_")


def normalize_params(periods: Any = None, params: Any = None) -> list[Any]:
    """把用户输入规范化为 param 列表：periods=[5,20] → [5,20]；params=[[10,2]] → [[10,2]]；
    [None] 表无参（pandas_ta 默认参数）。"""
    if params is not None:
        items = params if isinstance(params, list) else [params]
        return [list(p) if isinstance(p, (list, tuple)) else p for p in items]
    if periods is None:
        return [None]
    items = periods if isinstance(periods, list) else [periods]
    result: list[Any] = []
    for p in items:
        if p is None or (isinstance(p, str) and not p.strip()):
            result.append(None)
        else:
            result.append(int(p) if not isinstance(p, bool) else p)
    return result or [None]


# ---------------------------------------------------------------------------
# 查重
# ---------------------------------------------------------------------------


def check_factor_duplicate(
    indicator_name: str,
    category: str,
    price_col: str,
    periods_or_params: list[Any],
    tables_columns: dict[str, list[str]] | None = None,
    config_path: Path | None = None,
) -> str | None:
    """判断目标输出列是否已存在。命中返回中文冲突详情，否则 None。

    两个来源：
    - factors schema 现列（``load_factor_tables_columns()`` 的结果，可注入）；
      对单输出指标直接比对 ``<name>_<suffix>``；多输出指标比对同 (name, category,
      column) 已配置参数占用的前缀列。
    - indicators ``config/factors.yaml`` 已配置条目：name+category+column 相同
      且参数有交集即冲突；同名指标（任意类别/价格列）视为已注册，提示改走
      factor-admin 补周期/补列通道（registry 按 indicator_name 去重，不允许重复类）。
    """
    name = (indicator_name or "").strip().lower()
    category = (category or "").strip().lower()
    price_col = (price_col or "").strip().lower()
    if not name or not category:
        return None
    table = f"stock_daily_{category}_{price_col}"

    # ① 库中现列
    if tables_columns and table in tables_columns:
        existing = [c for c in tables_columns[table] if c not in ("ts_code", "trade_date")]
        hits: list[str] = []
        for param in periods_or_params or [None]:
            suffix = _param_to_suffix(param)
            expected = f"{name}_{suffix}" if suffix else name
            for column in existing:
                if column == expected or column.startswith(f"{expected}_"):
                    hits.append(column)
        if hits:
            return f"目标表 factors.{table} 已存在列: {', '.join(sorted(set(hits)))}"

    # ② 已配置条目（默认读真实 repo 的 config，可注入路径）
    if config_path is None:
        config_path = config_path_for(indicators_repo())
    if config_path.exists():
        try:
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            data = {}
        new_keys = {json.dumps(p, sort_keys=True) for p in (periods_or_params or [None])}
        for entry in data.get("factors") or []:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("name", "")).strip().lower() != name:
                continue
            same_target = (
                str(entry.get("category", "")).strip().lower() == category
                and str(entry.get("column", "close")).strip().lower() == price_col
            )
            if same_target:
                raw = entry.get("params") or entry.get("periods") or [None]
                old_params = raw if isinstance(raw, list) else [raw]
                old_keys = {json.dumps(p, sort_keys=True) for p in old_params}
                overlap = new_keys & old_keys
                if overlap:
                    return (
                        f"config/factors.yaml 已配置同名条目（name={name}, category={category}, "
                        f"column={price_col}），参数 {sorted(overlap)} 重复"
                    )
            # 同名指标已存在（任意类别/价格列）：新周期/新价格列走既有因子补全通道，
            # 不允许新建重复因子类（registry 按 indicator_name 去重，重复类会互相覆盖）。
            return (
                f"指标 {name} 已在 indicators_tushare 注册/配置（如 "
                f"{entry.get('category')}/{entry.get('column', 'close')}）。"
                "补周期或新价格列请走「新因子申请」（factor-admin）通道，无需新建因子类"
            )
    return None


# ---------------------------------------------------------------------------
# 沙箱（indicators 项目内 sandbox/factors/）
# ---------------------------------------------------------------------------


def sandbox_factors_dir(repo: Path | None = None) -> Path:
    repo = repo or indicators_repo()
    return repo / "sandbox" / "factors"


def save_factor_to_sandbox(
    code: str,
    name: str,
    *,
    repo: Path | None = None,
) -> dict[str, Any]:
    """静态安全检查 → 落盘 ``sandbox/factors/<name>_factor.py``。"""
    name = _safe_name(name).lower()
    if not _NAME_RE.fullmatch(name):
        return {"ok": False, "code": "invalid_name", "error": f"指标名非法: {name!r}（应为小写 snake_case）"}
    violations = check_code_safety(code)
    if violations:
        return {"ok": False, "code": "unsafe", "error": "安全检查未通过：" + "；".join(violations)}
    sandbox_dir = sandbox_factors_dir(repo)
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    path = sandbox_dir / f"{name}_factor.py"
    path.write_text(code, encoding="utf-8")
    return {"ok": True, "name": name, "path": str(path)}


def list_sandbox(repo: Path | None = None) -> list[dict[str, Any]]:
    sandbox_dir = sandbox_factors_dir(repo)
    entries: list[dict[str, Any]] = []
    if not sandbox_dir.exists():
        return entries
    for path in sorted(sandbox_dir.glob("*_factor.py")):
        entries.append(
            {
                "name": path.name[: -len("_factor.py")],
                "file": str(path),
                "mtime": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return entries


def discard_factor(name: str, *, repo: Path | None = None) -> dict[str, Any]:
    sandbox_dir = sandbox_factors_dir(repo)
    path = sandbox_dir / f"{_safe_name(name).lower()}_factor.py"
    if not path.exists():
        return {"ok": False, "code": "not_found", "error": f"沙箱中不存在因子: {name}"}
    path.unlink()
    return {"ok": True, "deleted": [str(path)]}


# ---------------------------------------------------------------------------
# 冒烟（子进程跑 indicators sandbox/smoke_factor.py）
# ---------------------------------------------------------------------------


def _default_smoke_runner(cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)


def run_smoke(
    name: str,
    *,
    code: str = SMOKE_DEFAULT_CODE,
    days: int = SMOKE_DEFAULT_DAYS,
    params: list[Any] | None = None,
    repo: Path | None = None,
    timeout: int = SMOKE_TIMEOUT_SECONDS,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> dict[str, Any]:
    """跑沙箱因子的单股冒烟；解析子进程 stdout 最后一行 JSON。"""
    repo = repo or indicators_repo()
    sandbox_file = sandbox_factors_dir(repo) / f"{_safe_name(name).lower()}_factor.py"
    if not sandbox_file.exists():
        return {"ok": False, "error": f"沙箱中不存在因子: {name}（请先保存代码到沙箱）"}
    cmd = [
        UV_BIN,
        "run",
        "python",
        "sandbox/smoke_factor.py",
        str(sandbox_file),
        "--code",
        code,
        "--days",
        str(days),
        "--params",
        json.dumps(params if params is not None else [None]),
    ]
    run = runner or _default_smoke_runner
    try:
        proc = run(cmd, repo, timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"冒烟超时（>{timeout}s），已中止"}
    except Exception as exc:
        return {"ok": False, "error": f"冒烟子进程异常：{exc}"}

    stdout = (proc.stdout or "").strip()
    payload: dict[str, Any] | None = None
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if payload is None:
        tail = (proc.stderr or stdout)[-500:]
        return {"ok": False, "error": f"冒烟输出无法解析（exit={proc.returncode}）：{tail}"}
    payload["exit_code"] = proc.returncode
    return payload


# ---------------------------------------------------------------------------
# 晋升
# ---------------------------------------------------------------------------


def _default_pgrep_runner() -> subprocess.CompletedProcess:
    return subprocess.run(
        ["pgrep", "-af", "run_factor_admin|run_factor_repair"],
        capture_output=True,
        text=True,
        timeout=15,
    )


def check_no_admin_running(
    runner: Callable[[], subprocess.CompletedProcess] | None = None,
) -> str | None:
    """有 run_factor_admin/run_factor_repair 在跑时返回中文提示，否则 None。"""
    run = runner or _default_pgrep_runner
    try:
        proc = run()
    except Exception as exc:
        return f"无法确认后台任务状态（pgrep 失败：{exc}），为安全起见拒绝晋升"
    # pgrep -f 会匹配到命令行里含模式串的调用方 shell（如 bash -c "... pgrep -af run_factor_admin ..."），
    # 过滤含 "pgrep" 的行消除这类自匹配误报。
    lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip() and "pgrep" not in ln]
    if lines:
        return "检测到正在运行的 backfill/repair 任务，拒绝修改因子配置：\n" + "\n".join(lines)
    return None


def append_config_entry(
    config_path: Path,
    *,
    name: str,
    category: str,
    column: str,
    params: list[Any],
    now: datetime | None = None,
) -> Path:
    """备份并追加 config 条目（跟随文件现有 YAML 风格）。返回备份路径。"""
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    stamp = (now or datetime.now(tz=timezone.utc)).strftime("%Y%m%dT%H%M%S")
    backup_path = config_path.with_suffix(config_path.suffix + f".bak-{stamp}")
    shutil.copy2(config_path, backup_path)

    if params == [None]:
        param_block = "    params: [null]\n"
    elif all(not isinstance(p, list) for p in params):
        param_block = f"    periods: [{', '.join(str(p) for p in params)}]\n"
    else:
        lines = "\n".join(f"      - [{', '.join(str(v) for v in p)}]" if isinstance(p, list) else f"      - {p}" for p in params)
        param_block = f"    params:\n{lines}\n"
    block = (
        f"\n  - name: {name}  # GUI 新建因子（factor-create 通道）\n"
        f"    category: {category}\n"
        f"    column: {column}\n"
        f"{param_block}"
    )
    with config_path.open("a", encoding="utf-8") as fh:
        fh.write(block)
    return backup_path


def promote_factor(
    name: str,
    category: str,
    column: str,
    periods_or_params: list[Any],
    *,
    validate_code: str = "600519.SH",
    repo: Path | None = None,
    pgrep_runner: Callable[[], subprocess.CompletedProcess] | None = None,
    job_starter: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """晋升：pgrep 检查 → 复制进 factors/ → 追加 config → 后台 validate+backfill job。

    任一步失败自动回滚（删新文件、恢复 config 备份）。
    """
    name = _safe_name(name).lower()
    category = (category or "").strip().lower()
    column = (column or "").strip().lower()
    if not _NAME_RE.fullmatch(name):
        return {"ok": False, "code": "invalid_name", "error": f"指标名非法: {name!r}"}
    if category not in FACTOR_CATEGORIES:
        return {"ok": False, "code": "invalid_category", "error": f"非法类别: {category or '(空)'}（可选: {', '.join(FACTOR_CATEGORIES)}）"}
    if column not in PRICE_COLUMNS:
        return {"ok": False, "code": "invalid_column", "error": f"非法价格列: {column or '(空)'}（可选: {', '.join(PRICE_COLUMNS)}）"}

    repo = repo or indicators_repo()
    src = sandbox_factors_dir(repo) / f"{name}_factor.py"
    if not src.exists():
        return {"ok": False, "code": "not_found", "error": f"沙箱中不存在因子: {name}（请先冒烟通过）"}

    busy = check_no_admin_running(pgrep_runner)
    if busy:
        return {"ok": False, "code": "admin_busy", "error": busy}

    dest = repo / "factors" / f"{name}_factor.py"
    if dest.exists():
        return {"ok": False, "code": "duplicate_name", "error": f"factors/ 已存在同名模块: {dest}"}

    # 安全检查兜底（沙箱代码可被手改）
    code_text = src.read_text(encoding="utf-8")
    violations = check_code_safety(code_text)
    if violations:
        return {"ok": False, "code": "unsafe", "error": "安全检查未通过：" + "；".join(violations)}

    config_path = config_path_for(repo)
    backup_path: Path | None = None
    try:
        shutil.copy2(src, dest)
        backup_path = append_config_entry(
            config_path, name=name, category=category, column=column, params=periods_or_params
        )
    except Exception as exc:
        if dest.exists():
            dest.unlink()
        if backup_path is not None and backup_path.exists():
            shutil.copy2(backup_path, config_path)
        return {"ok": False, "code": "write_failed", "error": f"写入 indicators 项目失败（已回滚）：{exc}"}

    starter = job_starter or start_script_job
    cmd = [
        "/bin/bash",
        "-c",
        " ".join(
            [
                UV_BIN,
                "run",
                "python",
                "run_factor_admin.py",
                "validate",
                "--codes",
                validate_code,
                "--sample-rows",
                "800",
                "&&",
                UV_BIN,
                "run",
                "python",
                "run_factor_admin.py",
                "backfill",
                "--baseline-ref",
                "HEAD",
                "--categories",
                category,
                "--max-workers",
                "4",
                "--execute",
            ]
        ),
    ]
    try:
        record = starter(
            lock_key="indicators",  # 与日更/补全共用锁
            label=f"新因子入库 {name}（{category}/{column}）",
            cmd=cmd,
            cwd=repo,
        )
    except RuntimeError as exc:
        return {
            "ok": False,
            "code": "job_conflict",
            "error": f"文件与配置已写入，但后台任务启动失败：{exc}。请稍后手动执行 validate + backfill。",
            "path": str(dest),
        }
    except Exception as exc:
        return {
            "ok": False,
            "code": "job_failed",
            "error": f"文件与配置已写入，但后台任务异常：{exc}。请手动执行 validate + backfill。",
            "path": str(dest),
        }

    return {
        "ok": True,
        "name": name,
        "path": str(dest),
        "config_backup": str(backup_path),
        "job_id": record.get("job_id"),
    }
