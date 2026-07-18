# Product Vision

Project name: quant-research-engine

## Long-Term Vision

`quant-research-engine` is a small, independent experimental research and backtesting engine. It screens factor and strategy ideas on top of existing local data producers, then validates promising candidates with realistic portfolio simulation.

The long-term direction is a reusable engine with market profiles. A-share daily technical-factor research is the first concrete target, but the core should not hardcode A-share-only or daily-only assumptions.

## What This Project Is

- A Python research and backtesting framework.
- A full-market evaluation engine for fast factor and strategy screening.
- A detailed portfolio engine for account-level validation.
- A read-only consumer of upstream market and factor databases.
- A single-agent development lab where Kimi Code plans, implements, self-reviews, and finalizes approved work, with `docs/agent/` markdown files as the project's long-term memory.

## What This Project Is Not

- It is not the whole `quant-workspace` program.
- It is not responsible for downloading market data.
- It is not responsible for computing or repairing technical indicators.
- It is not a production trading system.
- It is not allowed to treat smoke-test strategy outputs as research conclusions.

## Target Users / Operators

- The project owner, acting as research lead and final approver.
- Kimi Code, acting as the single development agent: planner, implementer, self-reviewer, and git executor.
- Future research scripts that need stable CLI, report, and manifest outputs.

## Core Principles

- Preserve working behavior.
- Prefer incremental changes.
- Keep architecture understandable.
- Make important decisions explicit.
- The `docs/agent/` markdown files are the only authoritative project memory; do not rely on chat history as a source of truth.
- Prevent future-function leakage and lookahead bias.
- Keep market-specific rules in market profiles, not strategy logic.
- Keep technical indicators as upstream inputs, not engine-computed internals.

## Engine Model

- Evaluation engine: fast full-market screening for factors, expressions, IC/Rank IC, quantile returns, and rough friction-adjusted summaries.
- Portfolio engine: realistic validation with orders, fills, failed orders, costs, slippage, cash, positions, sellable inventory, equity curve, risk metrics, and reports.

## First Market Profile

The first market profile is A-share daily: signal on `t`, earliest execution on `t+1`, T+1 sellability, price limits, suspensions when data is available, ST/risk-warning handling when data is available, board-specific limits, lot-size rules, commission, stamp tax, transfer fee, and percent slippage.
