"""共享 store 来源加载（W5，46 号 §12 / §11.2）。

供五年驱动（game_five_year_drive.py）与预览服务（start-game-preview.py）共用，
使两者都能在不改代码的前提下切换到外部 store（WSL 交付的脱敏快照同构类）。
零数据库连接；不向 qre_ui_dev 导数据。

来源形式：module:Class（可导入）或 path/file.py:Class（按文件路径加载）。
优先级：CLI 参数 > 环境变量 QRE_GAME_STORE_SOURCE > 默认合成样本。
"""
from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path

DEFAULT_STORE_SOURCE = "game_preview_sample:SampleGameStore"


def resolve_source(cli_value: str | None = None) -> str:
    return cli_value or os.environ.get("QRE_GAME_STORE_SOURCE") or DEFAULT_STORE_SOURCE


def load_store(source: str, seed: int | None = None):
    """按 module:Class 或 path/file.py:Class 加载 store 实例。

    seed=None 时用 store 自身默认 seed（保持预览服务既有行为）；
    传入 seed 时优先 cls(seed=seed)，无 seed 参数的 store 回退 cls()。
    """
    if ":" not in source:
        raise SystemExit("--store-source 须为 module:Class 或 path/file.py:Class")
    mod_part, cls_name = source.rsplit(":", 1)
    if mod_part.endswith(".py") or "/" in mod_part or os.path.sep in mod_part:
        path = Path(mod_part).resolve()
        spec = importlib.util.spec_from_file_location("_qre_game_ext_store", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        module = importlib.import_module(mod_part)
    cls = getattr(module, cls_name)
    if seed is None:
        return cls()
    try:
        return cls(seed=seed)
    except TypeError:
        return cls()