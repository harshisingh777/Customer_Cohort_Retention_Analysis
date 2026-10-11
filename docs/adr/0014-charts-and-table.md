# 14. visx for charts; the heatmap is an HTML table

Status: accepted

## Decision
Curves and the histogram use visx (`@visx/shape`, `@visx/group`) with d3-scale. The cohort
heatmap and the RFM grid are semantic `<table>`s: keyboard-navigable (roving tabindex, arrow keys,
Enter selects), screen-reader friendly (each cell's label is the full sentence) and copyable.
Recharts is not used.

## Consequences
One rendering model, one visual language. The table keeps native table semantics plus roving
focus rather than `role="grid"`.
