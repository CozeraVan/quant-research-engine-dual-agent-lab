# Project Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first runnable skeleton for `quant-research-engine` without implementing full backtest logic.

**Architecture:** Create a small Python package with stable boundaries for core models, market profiles, configuration loading, and a CLI smoke command. Keep A-share as the first concrete market profile while keeping core models market-agnostic.

**Tech Stack:** Python 3.10+, dataclasses, PyYAML, pytest, src-layout package.

---

## File Structure

- `pyproject.toml`: package metadata, dependencies, pytest config, CLI entry point.
- `src/quant_research_engine/__init__.py`: package exports and version.
- `src/quant_research_engine/core/models.py`: reusable instrument, bar, order, fill, position, and account models.
- `src/quant_research_engine/markets/base.py`: abstract market profile interface and order validation result.
- `src/quant_research_engine/markets/ashare.py`: first A-share daily market profile implementation.
- `src/quant_research_engine/config/loader.py`: YAML market profile loader.
- `src/quant_research_engine/apps/cli.py`: minimal CLI for skeleton smoke checks.
- `tests/test_core_models.py`: core model behavior tests.
- `tests/test_ashare_market_profile.py`: A-share rule behavior tests.
- `tests/test_config_loader.py`: YAML loading tests.
- `tests/test_cli.py`: CLI smoke test.

## Tasks

- [x] Create failing tests for core models, A-share profile, config loader, and CLI.
- [x] Verify tests fail because implementation is missing.
- [x] Implement minimal package skeleton and behavior.
- [x] Run focused tests until green.
- [x] Update `进度.md` with implementation status.

## Scope Boundaries

This plan does not implement:

- PostgreSQL adapters.
- Factor evaluation engine.
- Portfolio backtest loop.
- Report generation.
- Strategy library migration from `research-notes` or `strategy-research`.

Those are follow-up milestones after the project skeleton runs cleanly.
