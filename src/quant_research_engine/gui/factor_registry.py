"""因子语义注册表只读加载层（QRE-GUI-FACTOR-REGISTRY-001）。

权威设计：``docs/superpowers/specs/2026-10-25-factor-registry-design.md``。

定位：**单一因子语义来源**。canonical ``schema.table.column`` 仍是数据库、YAML、
回测和因子申请的唯一字段标识；本模块只负责：

- 展示：中文名、价格口径、别名（供自选因子弹窗与 SaaS metadata 增量字段）；
- 解析：把自然语言里的中英文指标名/别名/参数确定性地映射到 canonical，
  不依赖 LLM 猜测，也不把全量别名注入 Prompt；
- 防漂移：``validate_registry`` 校验注册表与因子库快照一致，漏注册要告警。

纯只读、零 DB 访问（只读 ``configs/factor_registry.json``）。
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "factor_registry.json"
)

# 与 factor_wizard.PRICE_BASIS_PREFERENCE / gen_factor_registry 保持一致
PRICE_BASIS_PREFERENCE = ("close", "typical_price", "average_price")

PRICE_BASIS_ZH = {
    "close": "收盘价",
    "typical_price": "典型价",
    "average_price": "均价",
}

_CANONICAL_PREFIX = "factors."
_MARKET_TABLE = "public.stock_daily"

# QRE-FACTOR-DISPLAY-CONTRACT：呈现合同合法值与行情字段默认合同
DISPLAY_CHART_TYPES = ("overlay", "pane")
DISPLAY_SERIES_TYPES = ("line", "bar")
DISPLAY_AXES = ("price", "value")
DISPLAY_ROLES = ("main", "signal", "hist", "k", "d", "j", "up", "down", "line", "band")
_MARKET_FIELD_DISPLAY = {
    "chart_type": "overlay", "panel_id": None, "role": "line",
    "series_type": "line", "axis": "price", "precision": 2,
    "color": "#6750A4", "price_basis": None, "render_order": 0,
}

# 归一化要剔除的字符：空白、下划线、连字符、间隔号与中文特有标点。
# 逗号/括号/小数点保留——参数写法（MACD(12,26,9)）依赖它们唯一命中；
# 句读只从首尾剥离，避免 "…均线。" 这类尾缀挡住命中。
_STRIP_CHARS = re.compile(
    "[" + re.escape(
        " \t\r\n_-"
        "\u00b7\u30fb"                     # 间隔号
        "\u2010\u2011\u2012\u2013\u2014\u2015"  # 各类横线
        "\u3001\u3002\uff0c\uff1b\uff1a\uff01\uff1f"  # 中文标点（NFKC 后残留项）
        "\u3008\u3009\u300a\u300b\u300c\u300d\u300e\u300f"
        "\u3010\u3011\u2018\u2019\u201c\u201d"
        "\u2026\uff0e"
    ) + "]"
)
_EDGE_PUNCT = ".,;:!?\"'`\u2026"

_CJK = re.compile(r"[\u4e00-\u9fff]")
_LETTER = re.compile(r"[a-z]")


def normalize_alias(text: str) -> str:
    """别名归一化：全角转半角、英文小写、去空白/下划线/连字符/中文标点。

    ``ＥＭＡ＿５`` / ``ema-5`` / ``Ema 5`` → ``ema5``；
    ``MACD(12,26,9)`` 保留括号与逗号（参数写法仍可唯一命中）。
    """
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", str(text)).lower()
    normalized = _STRIP_CHARS.sub("", normalized)
    return normalized.strip(_EDGE_PUNCT)


def _extract_numbers(text: str) -> list[int]:
    return [int(m) for m in re.findall(r"\d+", str(text))]


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _params_text(params: dict[str, Any], order: Iterable[str]) -> str:
    return ",".join(str(params[k]) for k in order if k in params)


@dataclass(frozen=True)
class Resolution:
    """一次别名解析结果。

    ``status``: ``unique`` / ``ambiguous`` / ``missing``；
    ``kind``: ``factor`` / ``market``；
    ``candidates``: 歧义时的 canonical 候选（不自动错配）；
    ``notice``: 需要提示用户的口径/参数默认说明。
    """

    status: str
    kind: str = "factor"
    canonical: str | None = None
    candidates: tuple[str, ...] = ()
    price_basis: str | None = None
    notice: str | None = None
    family: str | None = None
    output: str | None = None
    zh: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "unique" and bool(self.canonical)


@dataclass(frozen=True)
class FactorEntry:
    table: str
    column: str
    canonical: str
    zh: str | None
    price_basis: str | None
    category: str | None
    family: str | None
    output: str | None
    params: dict[str, Any]
    aliases: tuple[str, ...]
    common: bool
    core: bool = False
    # QRE-FACTOR-DISPLAY-CONTRACT：呈现合同（chart_type/panel_id/role/
    # series_type/axis/precision/color/price_basis/render_order）。旧注册表
    # （无 display 键）为 None，页面走启发式回退。
    display: dict[str, Any] | None = None


@dataclass
class _FamilyInfo:
    abbr: str | None
    zh_base: str | None
    default_output: str | None
    default_params: dict[str, Any]
    param_order: list[str]
    aliases: list[str] = field(default_factory=list)
    family_tokens: list[str] = field(default_factory=list)


class FactorRegistry:
    """版本化注册表的只读视图（归一化索引 + 校验 + 消歧）。"""

    def __init__(self, data: dict[str, Any]) -> None:
        self.version = str(data.get("version") or "")
        self.generated_at = data.get("generated_at")
        self.price_basis_preference = tuple(
            data.get("price_basis_preference") or PRICE_BASIS_PREFERENCE
        )
        self._market_fields: dict[str, FactorEntry] = {}
        for name, info in (data.get("market_fields") or {}).items():
            canonical = f"{_MARKET_TABLE}.{name}"
            self._market_fields[canonical] = FactorEntry(
                table=_MARKET_TABLE,
                column=name,
                canonical=canonical,
                zh=info.get("zh") or name,
                price_basis=None,
                category=None,
                family=None,
                output=None,
                params={},
                aliases=tuple(info.get("aliases") or ()),
                common=True,
                display=dict(_MARKET_FIELD_DISPLAY),
            )
        self._entries: dict[str, FactorEntry] = {}
        for raw in data.get("factors") or []:
            entry = FactorEntry(
                table=str(raw["table"]),
                column=str(raw["column"]),
                canonical=str(raw.get("canonical") or f"{_CANONICAL_PREFIX}{raw['table']}.{raw['column']}"),
                zh=raw.get("zh"),
                price_basis=raw.get("price_basis"),
                category=raw.get("category"),
                family=raw.get("family"),
                output=raw.get("output"),
                params=dict(raw.get("params") or {}),
                aliases=tuple(raw.get("aliases") or ()),
                common=bool(raw.get("common")),
                core=bool(raw.get("core")),
                display=dict(raw["display"]) if isinstance(raw.get("display"), dict) else None,
            )
            self._entries[entry.canonical] = entry
        self.tables: dict[str, dict[str, Any]] = dict(data.get("tables") or {})
        self._families: dict[str, _FamilyInfo] = {}
        for name, raw in (data.get("families") or {}).items():
            self._families[name] = _FamilyInfo(
                abbr=raw.get("abbr"),
                zh_base=raw.get("zh_base"),
                default_output=raw.get("default_output"),
                default_params=dict(raw.get("default_params") or {}),
                param_order=list(raw.get("param_order") or []),
                aliases=list(raw.get("aliases") or []),
                family_tokens=list(raw.get("family_tokens") or []),
            )
        self._extra_aliases: dict[str, list[str]] = {
            k: list(v) for k, v in (data.get("extra_aliases") or {}).items()
        }
        self._build_indexes()

    # --- 索引 ---

    def _build_indexes(self) -> None:
        canonical_keys: dict[str, str] = {}
        alias_index: dict[str, list[str]] = {}
        market_keys: dict[str, str] = {}
        family_index: dict[str, list[str]] = {}

        for canonical, entry in self._market_fields.items():
            market_keys[normalize_alias(entry.column)] = canonical
            market_keys[normalize_alias(entry.zh or "")] = canonical
            for alias in entry.aliases:
                market_keys.setdefault(normalize_alias(alias), canonical)

        for canonical, entry in self._entries.items():
            for key in (
                normalize_alias(canonical),
                normalize_alias(f"{entry.table}.{entry.column}"),
            ):
                canonical_keys.setdefault(key, canonical)
            if entry.family:
                family_index.setdefault(entry.family, []).append(canonical)
            for alias in entry.aliases:
                key = normalize_alias(alias)
                if not key:
                    continue
                bucket = alias_index.setdefault(key, [])
                if canonical not in bucket:
                    bucket.append(canonical)

        for alias, canonicals in self._extra_aliases.items():
            key = normalize_alias(alias)
            if not key:
                continue
            bucket = alias_index.setdefault(key, [])
            for canonical in canonicals:
                if canonical not in bucket:
                    bucket.append(canonical)

        # 族识别 token：英文 ≥3 字符或含中文，避免 "ad"/"sr" 之类误匹配。
        # 只取 abbr / zh_base / 规则显式声明的 family_tokens——不把全部别名当
        # token，否则 "macd signal" 这类别名会让 macd_signal_12_26_9 被误判成
        # MACD 快线（应交回旧别名字典子串兜底）。
        family_tokens: dict[str, str] = {}
        for name, info in self._families.items():
            tokens = set(info.family_tokens)
            if info.abbr:
                tokens.add(info.abbr)
            if info.zh_base:
                tokens.add(info.zh_base)
            for token in tokens:
                key = normalize_alias(token)
                if not key:
                    continue
                if len(key) >= 3 or _CJK.search(key):
                    family_tokens.setdefault(key, name)
        self._ordered_family_tokens = sorted(family_tokens, key=len, reverse=True)
        self._family_tokens = family_tokens

        self._canonical_keys = canonical_keys
        self._alias_index = alias_index
        self._market_keys = market_keys
        self._family_index = family_index

    # --- 加载 ---

    @classmethod
    def load(cls, path: str | Path | None = None) -> "FactorRegistry":
        target = Path(path) if path else DEFAULT_REGISTRY_PATH
        data = json.loads(target.read_text(encoding="utf-8"))
        return cls(data)

    # --- 查询 ---

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> dict[str, FactorEntry]:
        return self._entries

    def entry(self, canonical: str) -> FactorEntry | None:
        return self._entries.get(canonical)

    def display(self, table: str, column: str) -> dict[str, Any] | None:
        """表名/列名 → 展示信息（zh / canonical / price_basis / aliases）。未注册返回 None。"""
        short = str(table).removeprefix(_CANONICAL_PREFIX)
        if short == _MARKET_TABLE:
            entry = self._market_fields.get(f"{_MARKET_TABLE}.{column}")
            if entry is not None:
                return {
                    "zh": entry.zh,
                    "canonical": entry.canonical,
                    "price_basis": None,
                    "price_basis_zh": None,
                    "family": None,
                    "output": None,
                    "aliases": list(entry.aliases),
                    "common": True,
                    "core": True,
                    "display": dict(entry.display) if entry.display else None,
                }
            return None
        entry = self._entries.get(f"{_CANONICAL_PREFIX}{short}.{column}")
        if entry is None:
            return None
        return {
            "zh": entry.zh,
            "canonical": entry.canonical,
            "price_basis": entry.price_basis,
            "price_basis_zh": PRICE_BASIS_ZH.get(entry.price_basis or ""),
            "family": entry.family,
            "output": entry.output,
            "aliases": list(entry.aliases),
            "common": entry.common,
            "display": dict(entry.display) if entry.display else None,
        }

    def common_factor_targets(self) -> tuple[str, ...]:
        """常用已落库因子清单（替代手写 COMMON_FACTOR_TARGETS）。

        取注册表 ``core`` 条目：LLM prompt 只放少量常用示例，**不注入全量别名**。
        """
        return tuple(
            self._entries[c].canonical
            for c in sorted(self._entries)
            if self._entries[c].core and self._entries[c].price_basis == "close"
        )

    def curated_targets(self) -> tuple[str, ...]:
        """全部标记为常用（``common``）的已落库因子（界面/提示用，非 prompt）。"""
        return tuple(
            self._entries[c].canonical
            for c in sorted(self._entries)
            if self._entries[c].common and self._entries[c].price_basis == "close"
        )

    def search(self, text: str, *, limit: int = 50) -> list[str]:
        """展示用搜索：中文名 / canonical / 列名 / 别名 / 族名 包含即命中。"""
        key = normalize_alias(text)
        if not key:
            return []
        hits: list[str] = []
        for canonical, entry in self._entries.items():
            haystack = [
                normalize_alias(entry.zh or ""),
                normalize_alias(canonical),
                normalize_alias(entry.column),
                normalize_alias(entry.family or ""),
            ]
            haystack.extend(normalize_alias(a) for a in entry.aliases)
            if any(key in h for h in haystack if h):
                hits.append(canonical)
        hits.sort()
        return hits[:limit]

    # --- 解析 ---

    def resolve(self, text: str, price_basis: str | None = None) -> Resolution:
        """确定性解析：canonical 精确 → 归一化别名 → family+params 结构化 → 消歧。"""
        raw = (text or "").strip()
        if not raw:
            return Resolution(status="missing")
        key = normalize_alias(raw)
        if not key:
            return Resolution(status="missing")

        # 1) 完整 canonical 精确命中
        canonical = self._canonical_keys.get(key)
        if canonical is not None:
            return self._finish(raw, [canonical], price_basis)

        # 行情字段单独识别（不混入 factor_fields）
        market = self._market_keys.get(key)
        if market is not None:
            entry = self._market_fields[market]
            return Resolution(
                status="unique", kind="market", canonical=market,
                price_basis=None, zh=entry.zh,
            )

        numbers = _extract_numbers(raw)

        # 2) 归一化别名唯一命中（带参数时再用数字收窄）
        hits = list(self._alias_index.get(key, []))
        if hits:
            narrowed = self._filter_by_params(hits, numbers)
            if narrowed:
                hits = narrowed
            return self._finish(raw, hits, price_basis)

        # 3) family + params 结构化匹配（MACD(12,26,9)、20 日指数均线…）
        family = self._family_from_text(key)
        if family is None:
            return Resolution(status="missing")
        info = self._families[family]
        output = info.default_output
        candidates = [
            c for c in self._family_index.get(family, [])
            if output is None or self._entries[c].output == output
        ]
        if not candidates:
            return Resolution(status="missing", family=family)
        defaulted = False
        if numbers:
            narrowed = self._filter_by_params(candidates, numbers)
            candidates = narrowed or candidates
        elif info.default_params:
            order = info.param_order or list(info.default_params)
            values = [info.default_params[k] for k in order if k in info.default_params]
            narrowed = self._filter_by_params(candidates, [int(v) for v in values])
            if narrowed:
                candidates = narrowed
                defaulted = True
        return self._finish(raw, candidates, price_basis, family=family,
                            defaulted_params=defaulted)

    def _family_from_text(self, key: str) -> str | None:
        """从归一化文本识别族 token（最长优先，先前缀后包含）。

        token 之外的剩余部分不得含英文字母——否则说明这是带后缀的列名写法
        （如 ``macd_signal_12_26_9`` → ``macdsignal12269``），应交回旧别名字典
        子串兜底，而不是按族默认参数猜成 MACD 快线。
        """
        for token in self._ordered_family_tokens:
            if key.startswith(token) and not _LETTER.search(key[len(token):]):
                return self._family_tokens[token]
        for token in self._ordered_family_tokens:
            if token in key and not _LETTER.search(key.replace(token, "", 1)):
                return self._family_tokens[token]
        return None

    def _filter_by_params(self, canonicals: list[str], numbers: list[int]) -> list[str]:
        if not numbers:
            return []
        out: list[str] = []
        for canonical in canonicals:
            entry = self._entries[canonical]
            info = self._families.get(entry.family or "")
            if info is None or not info.param_order:
                continue
            values = [_as_float(entry.params.get(k)) for k in info.param_order]
            if any(v is None for v in values):
                continue
            if [int(v) for v in values[: len(numbers)]] == list(numbers):
                out.append(canonical)
        return out

    def _unique_result(self, raw: str, canonical: str, notices: list[str]) -> Resolution:
        """唯一命中的收口：补「未指定参数 → 族默认值」提示。"""
        entry = self._entries[canonical]
        info = self._families.get(entry.family or "")
        if not _extract_numbers(raw) and info is not None and info.default_params:
            if all(
                _as_float(entry.params.get(k)) == float(v)
                for k, v in info.default_params.items()
            ):
                text = _params_text(
                    info.default_params, info.param_order or list(info.default_params)
                )
                notices.insert(0, f"未指定 {info.abbr or entry.family} 参数，已按默认 ({text}) 处理。")
        return Resolution(
            status="unique", canonical=entry.canonical, price_basis=entry.price_basis,
            notice="；".join(notices) or None, family=entry.family,
            output=entry.output, zh=entry.zh,
        )

    def _finish(
        self,
        raw: str,
        canonicals: list[str],
        price_basis: str | None,
        *,
        family: str | None = None,
        defaulted_params: bool = False,
    ) -> Resolution:
        unique_hits: list[str] = []
        for canonical in canonicals:
            if canonical in self._entries and canonical not in unique_hits:
                unique_hits.append(canonical)
        notices: list[str] = []
        if defaulted_params:
            info = self._families.get(family or "")
            if info is not None and info.default_params:
                text = _params_text(info.default_params, info.param_order or list(info.default_params))
                notices.append(f"未指定 {info.abbr or family} 参数，已按默认 ({text}) 处理。")
        if len(unique_hits) == 1:
            return self._unique_result(raw, unique_hits[0], notices)
        if not unique_hits:
            return Resolution(status="missing", family=family)

        # 显式价格口径
        if price_basis:
            filtered = [
                c for c in unique_hits
                if self._entries[c].price_basis == price_basis
            ]
            if len(filtered) == 1:
                return self._unique_result(raw, filtered[0], notices)
            if filtered:
                unique_hits = filtered

        # 仅价格口径不同（同类同列）→ 默认 close 并提示
        groups: dict[tuple[Any, str], list[str]] = {}
        for canonical in unique_hits:
            entry = self._entries[canonical]
            groups.setdefault((entry.category, entry.column), []).append(canonical)
        if len(groups) == 1:
            for basis in self.price_basis_preference:
                same_basis = [
                    c for c in unique_hits if self._entries[c].price_basis == basis
                ]
                if same_basis:
                    entry = self._entries[same_basis[0]]
                    others = sorted({
                        PRICE_BASIS_ZH[self._entries[c].price_basis]
                        for c in unique_hits
                        if c != entry.canonical and self._entries[c].price_basis in PRICE_BASIS_ZH
                    })
                    if others:
                        chosen = PRICE_BASIS_ZH.get(entry.price_basis or "", entry.price_basis)
                        notices.append(
                            f"「{raw}」在因子库中同时存在{'、'.join(others)}等口径，"
                            f"已默认取{chosen}（{entry.canonical}）；如需其他口径请明确说明。"
                        )
                    return self._unique_result(raw, entry.canonical, notices)
                    return self._unique_result(raw, entry.canonical, notices)

        return Resolution(
            status="ambiguous",
            candidates=tuple(unique_hits),
            notice="；".join(notices) or None,
            family=family,
        )

    # --- 覆盖与校验 ---

    def coverage_report(self, snapshot: dict[str, list[str]]) -> dict[str, Any]:
        """注册表相对因子库快照的覆盖情况（未维护条目如实列出，不伪造中文名）。"""
        registered: list[str] = []
        unregistered: list[str] = []
        by_table: dict[str, dict[str, int]] = {}
        for table, columns in sorted(snapshot.items()):
            counts = {"total": 0, "registered": 0}
            for column in columns:
                if column in ("ts_code", "trade_date"):
                    continue
                counts["total"] += 1
                entry = self._entries.get(f"{_CANONICAL_PREFIX}{table}.{column}")
                if entry is None:
                    unregistered.append(f"{table}.{column}")
                elif not entry.zh:
                    unregistered.append(f"{table}.{column}")
                    counts["registered"] += 0
                else:
                    registered.append(f"{table}.{column}")
                    counts["registered"] += 1
            by_table[table] = counts
        total = sum(c["total"] for c in by_table.values())
        return {
            "registry_version": self.version,
            "generated_at": self.generated_at,
            "total_columns": total,
            "registered_columns": len(registered),
            "unregistered_columns": len(unregistered),
            "coverage_pct": round(100.0 * len(registered) / total, 1) if total else 0.0,
            "by_table": by_table,
            "unregistered": unregistered,
        }

    def validate(self, snapshot: dict[str, list[str]]) -> list[str]:
        """注册表 ↔ 因子库快照一致性校验；返回人类可读问题列表（空 = 通过）。"""
        return validate_registry(snapshot, registry=self)


_REGISTRY_CACHE: dict[str, FactorRegistry] = {}


def load_registry(path: str | Path | None = None) -> FactorRegistry:
    """进程内缓存的注册表加载（文件 mtime 变化时重读）。"""
    target = Path(path) if path else DEFAULT_REGISTRY_PATH
    key = str(target)
    try:
        mtime = target.stat().st_mtime
    except OSError:
        return FactorRegistry.load(target)
    cached = _REGISTRY_CACHE.get(key)
    if cached is not None and getattr(cached, "_mtime", None) == mtime:
        return cached
    registry = FactorRegistry.load(target)
    registry._mtime = mtime  # type: ignore[attr-defined]
    _REGISTRY_CACHE[key] = registry
    return registry


def validate_display(registry: FactorRegistry) -> list[str]:
    """QRE-FACTOR-DISPLAY-CONTRACT：display 合同校验（合法/无冲突/无失效引用）。

    - 每个条目都有 display，枚举值合法（chart_type/series_type/axis/role）；
    - overlay ⇔ panel_id 为 None 且价格轴；pane ⇔ panel_id 非空且数值轴；
    - panel_id 形如 ``group:table:params:basis`` / ``pane:table:column:basis``，
      且 basis 与条目 price_basis 一致（同列不同口径不串键）；
    - 同一 panel_id 下的条目必须同表同口径同 chart_type（无冲突）；
    - 旧注册表（无 display）整体报一条，提示重新生成——不静默放行。
    """
    issues: list[str] = []
    by_panel: dict[str, set[tuple[str, str | None, str]]] = {}
    missing = 0
    for canonical, entry in registry.entries.items():
        disp = entry.display
        if not disp:
            missing += 1
            continue
        chart_type = disp.get("chart_type")
        panel_id = disp.get("panel_id")
        if chart_type not in DISPLAY_CHART_TYPES:
            issues.append(f"display.chart_type 非法: {canonical} -> {chart_type!r}")
            continue
        if disp.get("series_type") not in DISPLAY_SERIES_TYPES:
            issues.append(f"display.series_type 非法: {canonical} -> {disp.get('series_type')!r}")
        if disp.get("axis") not in DISPLAY_AXES:
            issues.append(f"display.axis 非法: {canonical} -> {disp.get('axis')!r}")
        if disp.get("role") not in DISPLAY_ROLES:
            issues.append(f"display.role 非法: {canonical} -> {disp.get('role')!r}")
        precision = disp.get("precision")
        if not isinstance(precision, int) or isinstance(precision, bool) or precision < 0:
            issues.append(f"display.precision 非法: {canonical} -> {precision!r}")
        render_order = disp.get("render_order")
        if not isinstance(render_order, int) or isinstance(render_order, bool) or render_order < 0:
            issues.append(f"display.render_order 非法: {canonical} -> {render_order!r}")
        color = disp.get("color")
        if not (isinstance(color, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", color)):
            issues.append(f"display.color 非法: {canonical} -> {color!r}")
        if chart_type == "overlay":
            if panel_id is not None:
                issues.append(f"overlay 不得有 panel_id: {canonical}")
            if disp.get("axis") != "price":
                issues.append(f"overlay 必须价格轴: {canonical}")
            continue
        if not panel_id or not isinstance(panel_id, str):
            issues.append(f"pane 必须有 panel_id: {canonical}")
            continue
        parts = panel_id.split(":")
        if len(parts) != 4:
            issues.append(f"panel_id 形如 group:table:params:basis: {canonical} -> {panel_id}")
            continue
        group, _table, _params, basis = parts
        if not group or not _table:
            issues.append(f"panel_id 组/表为空: {canonical} -> {panel_id}")
        expected_basis = entry.price_basis or "na"
        if basis != expected_basis:
            issues.append(
                f"panel_id 口径与条目不一致: {canonical} -> {panel_id}（期望 …:{expected_basis}）")
        if disp.get("axis") != "value":
            issues.append(f"pane 必须数值轴: {canonical}")
        by_panel.setdefault(panel_id, set()).add(
            (entry.table, entry.price_basis, chart_type))
    for panel_id, members in by_panel.items():
        if len(members) > 1:
            issues.append(f"panel_id 跨表/跨口径/跨类型冲突: {panel_id} -> {sorted(members)}")
    if missing:
        issues.append(
            f"{missing} 个条目缺 display 合同（请用 scripts/gen_factor_registry.py 重新生成）")
    return issues


def validate_registry(
    snapshot: dict[str, list[str]],
    registry: FactorRegistry | None = None,
) -> list[str]:
    """校验注册表与因子库快照一致（坏 canonical / 悬空别名 / 漏注册新列）。

    ``snapshot``: ``{table: [columns]}``（不含 schema 前缀，与
    ``configs/factor_catalog_llm.json`` 同构）。返回问题列表，空列表 = 通过。
    QRE-FACTOR-DISPLAY-CONTRACT：display 合同校验并入本门禁。
    """
    reg = registry if registry is not None else load_registry()
    issues: list[str] = []
    known: set[str] = set()
    for table, cols in snapshot.items():
        for column in cols:
            if column in ("ts_code", "trade_date"):
                continue
            known.add(f"{_CANONICAL_PREFIX}{table}.{column}")

    for canonical in sorted(reg._entries):
        if canonical not in known:
            issues.append(f"注册条目指向因子库不存在的字段：{canonical}")

    for alias, canonicals in sorted(reg._extra_aliases.items()):
        key = normalize_alias(alias)
        if not key:
            issues.append("extra_aliases 存在空别名")
            continue
        for canonical in canonicals:
            if canonical not in reg._entries:
                issues.append(f"别名「{alias}」指向注册表不存在的字段：{canonical}")
            elif canonical not in known:
                issues.append(f"别名「{alias}」指向因子库不存在的字段：{canonical}")
    issues.extend(validate_display(registry))
    return issues


def duplicate_aliases(registry: FactorRegistry | None = None) -> dict[str, list[str]]:
    """同一归一化别名指向多个字段的映射（必须形成候选，不得静默覆盖）。"""
    reg = registry if registry is not None else load_registry()
    index: dict[str, list[str]] = {}
    for canonical in sorted(reg._entries):
        for alias in reg._entries[canonical].aliases:
            key = normalize_alias(alias)
            if not key:
                continue
            bucket = index.setdefault(key, [])
            if canonical not in bucket:
                bucket.append(canonical)
    for alias, canonicals in reg._extra_aliases.items():
        key = normalize_alias(alias)
        if not key:
            continue
        bucket = index.setdefault(key, [])
        for canonical in canonicals:
            if canonical not in bucket:
                bucket.append(canonical)
    return {k: sorted(v) for k, v in index.items() if len(v) > 1}


def unregistered_columns(
    snapshot: dict[str, list[str]],
    registry: FactorRegistry | None = None,
) -> list[str]:
    """因子库快照中存在但注册表未维护中文名的列（漏注册告警）。"""
    reg = registry if registry is not None else load_registry()
    return reg.coverage_report(snapshot)["unregistered"]
