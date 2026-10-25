from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "src/quant_research_engine/gui/saas/templates/new.html").read_text()


def test_all_backtest_parameter_labels_have_actionable_tips():
    labels = [
        "回测区间", "标的范围", "板块/概念范围", "股票代码", "模式", "初始资金",
        "最大持仓股票数", "最大持仓天数", "入场价格", "出场价格", "止损 %", "止盈 %",
        "移动止损 %", "佣金率", "最低佣金", "印花税(卖出)", "买入滑点", "卖出滑点",
    ]
    for label in labels:
        pattern = (r'<label\b[^>]*data-tip="[^"]+"[^>]*>\s*' + re.escape(label)
                   + r'(?:\s*<span class="req">\*</span>)?\s*</label>')
        assert re.search(pattern, PAGE), f"缺少参数提示: {label}"


def test_parameter_tips_describe_units_defaults_and_execution_semantics():
    for text in [
        "每只股票独立使用初始资金", "多只股票共用同一份总资金", "单位：元",
        "0 = 不限", "0 或留空 = 不限", "下一交易日开盘价", "VWAP",
        "0.08 = 8%", "0.0003 = 0.03%", "相对持仓期间最高价的回撤比例",
        "无需输入 .SZ/.SH/.BJ 后缀",
    ]:
        assert text in PAGE, f"缺少口径: {text}"
