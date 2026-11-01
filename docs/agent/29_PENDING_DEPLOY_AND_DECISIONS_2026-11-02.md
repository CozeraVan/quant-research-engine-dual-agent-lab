# 29_PENDING_DEPLOY_AND_DECISIONS_2026-11-02.md — ECS 部署清单、seed.json 处置、P2-14/P2-15 决策单

> 本文是 2026-11-02 的轻量待办清单：不跑重活、不干扰 03:00 全期全量压力测试。
> 真部署/重启/默认开启前，需用户按本文件逐项批准。

---

## 1. ECS 待部署清单（已提交但未部署）

### 1.1 待部署文件
| 文件 | 原因 |
|---|---|
| `src/quant_research_engine/gui/saas/templates/job.html` | P2-15 波动率时序曲线 + 前期 P1-9/P1-10 改动 |
| `src/quant_research_engine/gui/templates/lab_result.html` | P2-15 波动率时序曲线 |
| `src/quant_research_engine/gui/static/vol-regime.js` | P2-15 seriesModel/seriesChartOption |
| `src/quant_research_engine/gui/lab_result.py` | P2-15 透出 `volatility.series` + P2-14 参数变体 |
| `src/quant_research_engine/risk/report.py` | P1-10 regime 修复 + P2-15 可选序列 |
| `src/quant_research_engine/risk/volatility.py` | P1-10 全零波动率修复 + P2-15 GARCH 序列 |
| `src/quant_research_engine/gui/risk_report.py` | P2-15 默认开启波动率时序序列 |

### 1.2 部署命令（用户批准后执行）
```bash
cd /home/van/quant-workspace/quant-research-engine-dual-agent-lab
./deploy/saas/deploy-ecs.sh \
  src/quant_research_engine/gui/saas/templates/job.html \
  src/quant_research_engine/gui/templates/lab_result.html \
  src/quant_research_engine/gui/static/vol-regime.js \
  src/quant_research_engine/gui/lab_result.py \
  src/quant_research_engine/risk/report.py \
  src/quant_research_engine/risk/volatility.py \
  src/quant_research_engine/gui/risk_report.py
```

### 1.3 回滚
- `deploy-ecs.sh` 会自动在 ECS `/tmp/qre-deploy-<STAMP>.bak/` 留副本。
- 回滚：把备份文件 `sudo -n install` 回原路径并 `sudo -n systemctl restart qre-saas`。
- 只重启 `qre-saas`，不重启 worker。

### 1.4 部署后验证
```bash
ssh -i ~/.ssh/aguhuice_ed25519 deploy@47.119.127.40 \
  'sudo -n systemctl is-active qre-saas; curl -s -o /dev/null -w "%{http_code}\n" -H "Host: www.aguhuice.com" http://127.0.0.1:8090/saas/new; curl -s -o /dev/null -w "%{http_code}\n" -H "Host: www.aguhuice.com" http://127.0.0.1:8090/static/vol-regime.js'
```
- 预期：`active` + 两个 `200`。
- 若失败，立即按 §1.3 回滚。

---

## 2. `deploy/saas/public-beta-audit/seed.json` 处置

- 现状：未跟踪；内容是公测审计本地种子数据，含测试手机号和测试 token，不应进仓库。
- 处置：**已加入 `.gitignore`**，保留本地文件，不提交、不删除。
- 重新生成：按 `deploy/saas/public-beta-audit/seed.py` 的用法生成。

---

## 3. P2-14 worker 重启与小样本验证计划（3 点压测后再做）

### 3.1 重启命令
```bash
sudo -n systemctl restart qre-saas-worker.service
systemctl status qre-saas-worker.service --no-pager | head -12
```

### 3.2 重启后小样本验证
- 用一个小样本批量任务验证参数变体已注入：
  - 策略：`strategies/classic/classic_macd_12_26_9_golden_cross.yaml`
  - 标的：5 只样本股
  - 区间：近两年
- 检查点：
  - `symbol_details` manifest 中 `param_variants_included > 0`
  - 单股产物 `factors` 含多组 MACD 参数
  - 前端参数切换正常
  - 物体积增量符合实测 ratio 1.73 量级

### 3.3 全量预算报告（批准全量前必须给用户）
- 小样本实测：约 **+71.7KB/股**。
- TOP-N=20 理论增量：约 **1.4MB/任务**。
- 因 `SYMBOL_DETAILS_MAX_BYTES=15MiB` 已紧，超额会先砍变体，再砍个股。
- 需明确：是否接受“个股覆盖数可能下降”换取“TOP-N 股票可切参数”。

---

## 4. P2-15 生产默认开启决策单

### 4.1 当前状态
- **2026-11-02 用户已批准默认开启。**
- `gui/risk_report.py::generate_risk_report` 已默认传入：
  `include_volatility_series=True`、`volatility_series_max_points=500`。
- 前端已就绪：有 `volatility.series` 自动画曲线，无序列降级为阈值标尺。
- 实测增量：`risk_report.json` 9,244 → 19,405 bytes，ratio 2.10。

### 4.2 回滚
- 删除 `gui/risk_report.py` 中这两行 config 即可恢复默认关。
- 历史产物不受影响；新产物在回滚后不再带序列。

---

## 5. 当前结论

- 可立即提交：`.gitignore` 的 `seed.json` 规则 + 本文档。
- P2-15 已批准默认开启，代码已改，待全量测试通过后提交并部署 ECS。
- 需用户批准：ECS 部署、worker 重启、P2-14 全量。
- 03:00 前不跑重活，避免影响压力测试。
