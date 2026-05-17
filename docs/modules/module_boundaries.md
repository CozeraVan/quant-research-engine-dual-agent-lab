# Module Boundaries

## Core

Defines reusable abstractions:

- instrument
- clock
- event
- context
- engine lifecycle

The core must not know A-share-specific rules.

## Data

Reads and validates input data.

Initial implementation:

- `public.stock_daily`
- `factors.*`
- derived trading calendar if no calendar table exists
- inferred board information if no metadata table exists

Later implementations can add forex, crypto, futures, options, intraday bars, and tick data through adapters.

## Market Rules

Market rules are plugins or profiles.

They answer:

- Is the instrument tradable?
- Is the order allowed?
- What is the valid price range?
- What lot-size rule applies?
- What cost model applies?
- Does the position require settlement or margin treatment?

A-share rules must live here, not inside strategies.

## Signals

Signals decide what looks attractive.

Signal examples:

- boolean rule
- factor threshold
- factor rank
- quantile bucket
- cross-sectional score
- market-regime filter

Signals should not place orders directly.

## Strategies

Strategies convert signals into desired exposure or target positions.

The project should support two styles:

1. Expression strategies for fast batch testing.
2. Strategy classes for more complex Backtrader-like logic.

## Evaluation Engine

The evaluation engine is the large screening engine.

It should use fast vectorized or panel-based calculations where possible. It can include approximate friction but should not be responsible for detailed account accounting.

## Portfolio Engine

The portfolio engine is the realistic simulator.

It should handle:

- target positions
- orders
- fills
- transaction costs
- failed orders
- cash
- positions
- sellable inventory
- daily equity

## Analytics

Analytics compute metrics from evaluation or portfolio outputs.

The analytics module should not depend on one market. Market-specific grouping, such as A-share board or ST status, should be passed in as metadata.

## Reporting

Reporting should produce reusable artifacts:

- CSV tables
- Markdown summaries
- HTML reports
- charts
- experiment archives

Reports must include enough metadata to reproduce an experiment.
