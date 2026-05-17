# Product Vision

Project name: quant-research-engine-dual-agent-lab

## Long-Term Vision

TODO: Describe the long-term goal of this project.

## What This Project Is

TODO: Describe the system/product/research project.

## What This Project Is Not

TODO: Describe boundaries and non-goals.

## Target Users / Operators

TODO: Describe who will use or maintain this project.

## Core Principles

- Preserve working behavior.
- Prefer incremental changes.
- Keep architecture understandable.
- Make important decisions explicit.
- Keep implementation and review separated when using dual agents.
- Do not rely on chat history as the only source of truth.

## Dual-Agent Development Philosophy

This project uses Codex and Claude Code together:

- Codex converts ideas into structured implementation briefs.
- Claude Code implements the brief.
- Codex reviews the implementation and performs final git operations after approval.
- User remains the final product owner and acceptance authority.
