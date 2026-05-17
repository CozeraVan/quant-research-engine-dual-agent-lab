# Architecture Mindmap

```text
quant-research-engine
├── 1. Universal Core
│   ├── Instrument abstraction
│   │   ├── stock
│   │   ├── fund
│   │   ├── forex pair
│   │   ├── crypto asset
│   │   ├── futures contract
│   │   └── option contract
│   ├── Time abstraction
│   │   ├── daily
│   │   ├── intraday bar
│   │   ├── tick
│   │   ├── millisecond event
│   │   └── event-driven clock
│   ├── Event abstraction
│   │   ├── market event
│   │   ├── signal event
│   │   ├── order event
│   │   ├── fill event
│   │   └── accounting event
│   └── Engine orchestration
│       ├── evaluation engine
│       ├── portfolio engine
│       ├── batch runner
│       └── report runner
│
├── 2. Data Layer
│   ├── market bars
│   ├── tick data
│   ├── factor data
│   ├── benchmark data
│   ├── security metadata
│   ├── calendar data
│   └── adapters
│       ├── PostgreSQL A-share adapter
│       ├── future crypto adapter
│       ├── future forex adapter
│       └── future futures/options adapter
│
├── 3. Market Profiles
│   ├── base market profile
│   ├── A-share profile
│   │   ├── T+1
│   │   ├── price limits
│   │   ├── suspensions
│   │   ├── ST rules
│   │   ├── board-specific limits
│   │   ├── lot size
│   │   ├── commission
│   │   ├── stamp tax
│   │   └── transfer fee
│   ├── future fund profile
│   ├── future forex profile
│   ├── future crypto profile
│   ├── future futures profile
│   └── future options profile
│
├── 4. Signal and Strategy Layer
│   ├── expression strategy
│   │   ├── close > sma_20
│   │   ├── rsi_2 < 10
│   │   └── macd_diff > macd_dea
│   ├── strategy class API
│   │   ├── prepare
│   │   ├── generate_signals
│   │   ├── generate_targets
│   │   └── on_rebalance
│   ├── factor strategy
│   ├── technical strategy templates
│   ├── stop loss / take profit modules
│   └── parameter grid
│
├── 5. Large Evaluation Engine
│   ├── event study
│   ├── IC / Rank IC
│   ├── quantile return
│   ├── factor decay
│   ├── regime split
│   ├── industry / board / bucket comparison
│   ├── benchmark comparison
│   ├── random baseline
│   └── clustering-ready outputs
│
├── 6. Detailed Portfolio Engine
│   ├── order generation
│   ├── execution simulation
│   ├── fill model
│   ├── failed order reasons
│   ├── cash accounting
│   ├── position accounting
│   ├── sellable inventory
│   ├── daily mark-to-market
│   └── equity curve
│
├── 7. Analytics
│   ├── return metrics
│   ├── risk metrics
│   ├── drawdown metrics
│   ├── trade statistics
│   ├── turnover and friction analysis
│   ├── cross-sectional comparison
│   ├── regime analysis
│   └── attribution
│
└── 8. Reporting and Interfaces
    ├── CLI
    ├── YAML config
    ├── Python API
    ├── CSV outputs
    ├── Markdown reports
    ├── HTML reports
    └── experiment archive
```
