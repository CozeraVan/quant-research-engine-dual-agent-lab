# CR-2026-10-27 M10.4 ML 聚类首个分析切片

## 目标

在 M10.1 的显著赢家、90%/99%/99.9% 置信层级、超额收益门控和类别富集之上，增加 scikit-learn 聚类与噪声识别，回答“同一策略的有效股票是否具有可解释的共同特征”。先交付可复现的分析模块、CLI 和测试，不在本切片新增公网 UI。

## 权威输入与复用

- 复用 `analysis/strategy_fit.py`、`scripts/strategy_fit_report.py` 的输入/输出合同，不重写统计检验，不降低 tier 标准。
- 只读已有回测/fit 产物与股票元数据；禁止为了本任务运行全量、全期或新回测。真实数据不可用或字段不足时用合成夹具验证并明确缺口。
- 使用既有 `.venv-ml`（scikit-learn 1.9.0 / pandas 3.0.5 / numpy 2.5.1），不加入主环境重依赖，不改主 `pyproject.toml`。

## 首个垂直切片

1. 新增独立 ML 分析模块：数值/类别预处理、缺失值处理、特征标准化、聚类与 noise 标签；scikit-learn 惰性导入，主环境无 sklearn 时不影响既有功能。
2. 小样本与单簇边界必须有确定行为；参数、随机种子、输入字段、模型版本写入 manifest。不得默认对每个小样本硬套固定簇数。
3. 输出每股票 cluster/noise 与策略、tier 的对应关系，以及每簇规模、收益/超额收益、主要类别特征和可解释摘要；没有足够样本时返回明确 insufficient，不伪造聚类结论。
4. 增加 CLI，输入已有 fit/batch 目录和元数据，输出独立 ML 子目录，不覆盖 M10.1 产物。
5. 测试覆盖：合成已知分组与离群点、90/99/99.9 tier 保留、缺失/常数特征、样本不足、可复现性、主环境可选依赖降级、原 M10.1 回归。

## 边界与验收

- 不做全市场回测、不做压力测试、不安装新依赖、不改游戏、不部署 ECS、不 commit/push。
- 只修改 M10.4 新模块/脚本/测试及本 CR；不要并行修改 04/05/08/09/10/11/14 等共享文档，由主 Agent 统一回写。
- 运行 `.venv-ml` 新测试和主环境相关回归；提供命令、结果、真实数据可用性和下一阶段 UI 接入点。

## 实现记录（2026-10-27，首个垂直切片完成）

### 新增文件

- `src/quant_research_engine/analysis/ml_cluster.py` — 独立 ML 分析模块：
  数值/类别预处理（中位数填补、缺失→unknown、one-hot、StandardScaler）、
  DBSCAN 聚类 + noise 标签（label -1）；scikit-learn 惰性导入，主环境无
  sklearn 时 `ml_cluster_available()=False`、入口抛 `MlUnavailableError`，
  既有功能零影响；不预设簇数，小样本（n < min_samples）返回 `insufficient`，
  另有 `single_cluster` / `all_noise` / `small_clusters_only` 确定状态；
  90%/99%/99.9% tier 与超额收益门控语义原样继承自 M10.1（仅读取
  `strategy_fit_stocks.csv`，不重算统计、不降低标准）；tier 经 CSV 往返后
  归一化回 `'90'/'99'/'99.9'` 标签。
- `scripts/strategy_fit_ml_report.py` — 独立 CLI：`--fit-dir`（M10.1 fit 产物）
  + 可选 `--metadata-csv`（只读元数据，扩展特征），输出独立 ML 子目录
  （默认 `outputs/strategy_fit_ml/<fit_dir_name>`），不覆盖 M10.1 产物；
  主环境无 sklearn 时明确报错并 exit 2（优雅降级）。
- `tests/test_strategy_fit_ml.py` — 17 个测试：合成双组+离群点、tier 保留
  （含 CSV 往返）、缺失/常数特征、样本不足、单簇/全噪声边界、可复现性、
  pool-only、manifest 合同、CLI 降级与 happy path、M10.1 输入契约校验。

### 输出物（每个 ML 子目录）

`ml_cluster_stocks.csv`（每股票 cluster/noise × 策略 × tier）、
`ml_cluster_clusters.csv`（每簇规模/收益/超额/tier 构成/主要类别特征/摘要，
noise 行 cluster=-1，insufficient 行 cluster 为空）、`ml_cluster_report.md`、
`ml_cluster_manifest.json`（kind=`strategy_fit_ml_cluster_manifest`，
含 eps/min_samples/min_cluster_size/random_state、scikit-learn 版本、
输入字段、每策略状态与预处理报告、确定性说明）。

### 验证命令与结果

- `.venv-ml` 新测试（sklearn 经 PYTHONPATH 影子加载，未改 .venv-ml）：
  `PYTHONPATH=.venv-ml/lib/python3.13/site-packages uv run pytest tests/test_strategy_fit_ml.py -q`
  → 17 passed。
- 主环境（无 sklearn）：同命令去掉 PYTHONPATH → 5 passed, 11 skipped
  （聚类类测试按设计跳过，降级测试实跑通过）。
- 主环境回归：`uv run pytest tests/test_strategy_fit.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q`
  → 462 passed（M10.1 口径未动）。
- 真实数据只读验证（无任何回测）：
  `.venv-ml/bin/python scripts/strategy_fit_ml_report.py --fit-dir outputs/strategy_fit/f365c8a07b33`
  → 81 策略：41 insufficient（显著股票 < 5）、40 all_noise、0 成簇；
  585 显著股票 tier 90/99/99.9 = 560/24/1 原样保留；产物写入
  `outputs/strategy_fit_ml/f365c8a07b33/`。eps=2.0 敏感性：5 策略成簇
  （参数敏感，默认保持保守）。

### 遗留 / 交接

- ~~`ml_cluster_manifest.json` 的 kind 尚未登记进 `portfolio/report_manifest.py`~~ **已完成（收尾）**：
  kind `strategy_fit_ml_cluster_manifest` 已登记进
  `portfolio/report_manifest.py` 的 `_SUPPORTED_MANIFEST_KINDS`，并为
  `ml_cluster_stocks` / `ml_cluster_clusters` / `ml_cluster_report` /
  `ml_cluster_manifest` 四个 role 添加必需列校验；
  `ReportManifest.from_path(...).validate_contents()` 对真实产物
  `outputs/strategy_fit_ml/f365c8a07b33/ml_cluster_manifest.json` 实跑
  issues == []（另有用例覆盖缺列/缺文件负路径）。
- 真实 fit 产物中多数策略显著股票过少，ML 结论以 insufficient/all_noise 为主，
  属预期（不伪造聚类）；UI 接入点见交付说明。

## 实现记录（2026-10-27，参数敏感性工具化切片）

### 变更

- `src/quant_research_engine/analysis/ml_cluster.py`：新增纯函数
  `parse_eps_grid()`（逗号分隔浮点解析，空值报错）、`analyze_eps_grid()`
  （对同一批 M10.1 显著股票逐 eps 复跑 `analyze_fit_stocks`，不重算统计、
  不跑回测；每个 eps 输出策略数、成簇策略数、ok 簇数、显著股票数、
  noise 股票数及各状态计数）、`write_eps_sensitivity()`（写
  `ml_cluster_sensitivity.csv` / `ml_cluster_sensitivity_strategies.csv` /
  `ml_cluster_sensitivity.json`，kind=`strategy_fit_ml_cluster_sensitivity`，
  记录 fit_dir、eps_grid、基础 config、scikit-learn 版本、确定性说明；
  文件不含时间戳，重复运行字节级一致）。
- `scripts/strategy_fit_ml_report.py`：新增可选 `--eps-grid`（默认 `None`＝关闭）。
  不传时主产物（4 个 `ml_cluster_*` 文件）与 manifest 合同完全不变；
  传入时在主产物之外另写 `ml_cluster_sensitivity_*`，不覆盖、不登记进主 manifest。
- `tests/test_strategy_fit_ml.py`：新增 7 个用例——`parse_eps_grid` 解析与
  非法输入、默认关闭时 4 产物/角色/无 sensitivity 文件、网格两次运行三份
  文件字节相等且主 manifest 仍只声明 4 个 role、单 eps 结论与默认 eps=1.0
  一致、空输入与全部 insufficient 输入的安全计数、空网格 CLI exit 2 且不写目录、
  无 sklearn 时带 `--eps-grid` 仍 exit 2 且不写 sensitivity。

### 验证（真实输出摘要）

- `uv run pytest tests/test_showcase_roller.py -q` → 14 passed, 1 skipped。
- `uv run pytest tests/ -q` → 见本轮主 Agent 汇总（本切片新增/修改用例全绿）。
- `PYTHONPATH=.venv-ml/lib/python3.13/site-packages uv run pytest
  tests/test_strategy_fit_ml.py tests/test_strategy_fit.py tests/test_portfolio_report_manifest.py -q`
  → 165 passed。
- `.venv-ml/bin/python scripts/strategy_fit_ml_report.py --fit-dir outputs/strategy_fit/f365c8a07b33 --eps-grid 1.0,1.5,2.0`
  → eps=1.0: 0 成簇 / 490 noise / 41 insufficient；eps=1.5: 2 成簇、5 簇 /
  451 noise；eps=2.0: 5 成簇、12 簇 / 396 noise（与本文档早期记录一致）。
  主产物 `ml_cluster_stocks.csv`、`ml_cluster_clusters.csv` 运行前后 md5 不变。

### 遗留

- 真实 fit 产物 41/81 策略显著股票 < 5，任何 eps 都只能是 insufficient；
  网格只对样本充足的 40 个策略给出结论，不改变该事实。
