# 16. A calm, statistical-report visual language

Status: accepted

## Decision
Spec section 8 tokens (ink, graphite, rule, ground, sheet, highlighter, signal); Public Sans for
the interface and numbers (tabular figures); Source Serif 4 for findings, titles and the filter
sentence. Filters read as a sentence of underlined clauses. Selection is always the yellow
highlighter. Data is encoded with one sequential hue. No KPI card row, no gradients, no entrance
animation; motion only answers an action (120 ms) and is removed under `prefers-reduced-motion`.

## Consequences
Every data component has loading, empty, error and ready states; previous numbers stay visible
at reduced opacity while new ones load, with a 2 px progress line only after 300 ms.
