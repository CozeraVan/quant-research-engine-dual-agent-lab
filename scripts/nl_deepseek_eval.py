"""QRE-SAAS-NL-A1：NL 输入校验离线评估（规则层全集 + DeepSeek 裁判分层小样本）。

数据：configs/nl_input_guard_samples.json（人工标注；label=strategy 期望 pass /
not_strategy 期望非 pass / boundary 期望 review）。

行为：
- 规则层：离线纯函数，总是运行（全集 54 条）；输出分类命中与误杀/漏放明细。
- DeepSeek 裁判：**仅跑分层小样本（默认 ≤12 条，strategy/not_strategy/boundary
  各类至少 3 条）**，走现有 QRE_NL_LLM_* 通道与 nl_compiler.call_llm（独立裁判
  prompt）；记录分类混淆、延迟与失败。无配置时明确写
  not_run_missing_credentials，不伪造任何结果。
- 不跑全量 54 条的真实裁判调用，不跑真实回测。

用法：
  python scripts/nl_deepseek_eval.py [--samples configs/nl_input_guard_samples.json]
                                     [--out .tmp/nl-input-guard/deepseek-eval.json]
                                     [--max-referee 12]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from quant_research_engine.gui import nl_compiler  # noqa: E402
from quant_research_engine.gui.saas import nl_input_guard as guard  # noqa: E402

LABELS = ("strategy", "not_strategy", "boundary")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", default="configs/nl_input_guard_samples.json")
    ap.add_argument("--out", default=".tmp/nl-input-guard/deepseek-eval.json")
    ap.add_argument("--max-referee", type=int, default=12)
    args = ap.parse_args()

    samples = json.loads((REPO / args.samples).read_text(encoding="utf-8"))["samples"]
    rule_rows = []
    for s in samples:
        r = guard.rule_check(s["text"])
        rule_rows.append({"text": s["text"], "label": s["label"],
                          "decision": r["decision"], "note": s.get("note", "")})

    def expect(label: str) -> str:
        return {"strategy": "pass", "not_strategy": "non-pass", "boundary": "review"}[label]

    rule_summary = {
        "total": len(rule_rows),
        "matches": sum(1 for r in rule_rows if (
            (expect(r["label"]) == "pass" and r["decision"] == "pass") or
            (expect(r["label"]) == "non-pass" and r["decision"] != "pass") or
            (expect(r["label"]) == "review" and r["decision"] == "review"))),
        "misjudged_strategy": [r for r in rule_rows
                               if r["label"] == "strategy" and r["decision"] != "pass"],
        "leaked_not_strategy": [r for r in rule_rows
                                if r["label"] == "not_strategy" and r["decision"] == "pass"],
        "boundary_not_review": [r for r in rule_rows
                                if r["label"] == "boundary" and r["decision"] != "review"],
    }

    # 分层抽样：每类至少 3 条，总数不超过 max_referee
    stratified: list[dict] = []
    per_label = max(3, args.max_referee // len(LABELS))
    for label in LABELS:
        pool = [s for s in samples if s["label"] == label]
        stratified.extend(pool[:per_label])
    stratified = stratified[: args.max_referee]

    config = nl_compiler.nl_config()
    referee_report: dict = {"status": "not_run_missing_credentials",
                            "sample_size": len(stratified)}
    if config is not None:
        calls = []
        for s in stratified:
            started = time.monotonic()
            out = guard.referee_classify(s["text"], config)
            calls.append({"text": s["text"], "label": s["label"],
                          "ok": out.get("ok"), "status": out.get("status"),
                          "referee_label": out.get("label"),
                          "latency_ms": round((time.monotonic() - started) * 1000, 1)})
        ok_calls = [c for c in calls if c["ok"]]
        confusion = Counter((c["label"], c["referee_label"]) for c in ok_calls)
        referee_report = {
            "status": "ran",
            "model": config["model"],
            "sample_size": len(stratified),
            "calls": calls,
            "failures": [c for c in calls if not c["ok"]],
            "confusion_matrix": {f"{k[0]}->{k[1]}": v for k, v in sorted(confusion.items())},
            "latency_ms": sorted(c["latency_ms"] for c in ok_calls),
            "note": "分层小样本（每类至少 3 条，总数 ≤ 配置上限）；"
                    "裁判无置信度输出，不做阈值校准结论",
        }

    report = {"guard_version": guard.GUARD_VERSION,
              "samples": len(samples), "rule_layer": rule_summary,
              "referee": referee_report}
    out_path = REPO / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"规则层：{rule_summary['matches']}/{rule_summary['total']} 与人工标注一致")
    if rule_summary["misjudged_strategy"]:
        print("  误杀(strategy→非pass)：",
              [(r["text"], r["decision"]) for r in rule_summary["misjudged_strategy"]])
    if rule_summary["leaked_not_strategy"]:
        print("  漏放(not_strategy→pass)：",
              [(r["text"], r["decision"]) for r in rule_summary["leaked_not_strategy"]])
    if rule_summary["boundary_not_review"]:
        print("  边界未review：",
              [(r["text"], r["decision"]) for r in rule_summary["boundary_not_review"]])
    if referee_report["status"] == "ran":
        print(f"DeepSeek 裁判真实小样本：模型 {referee_report['model']}，"
              f"{len(stratified)} 条，失败 {len(referee_report['failures'])}")
        print("  混淆矩阵：", referee_report["confusion_matrix"])
        print("  延迟 ms：", referee_report["latency_ms"])
    else:
        print("DeepSeek 裁判：未运行（缺少 QRE_NL_LLM_* 配置，未伪造评估结果）")
    print(f"报告：{out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
