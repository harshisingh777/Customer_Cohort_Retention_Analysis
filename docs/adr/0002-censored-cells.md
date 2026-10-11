# 2. Censored cells are absent, not zero

Status: accepted

## Context
Without explicit handling, every recent cohort shows 0% in months that haven't happened yet,
the most common lie in cohort charts.

## Decision
`macros/cohort_cells.sql` generates a grid only up to the last complete period before the
cutoff. A missing row means "not observable yet"; a row with 0 means "observed, nobody bought".
The current, incomplete month is excluded both as a cohort and as an activity period. The API's
arrays end where observability ends and the client never invents zeros; the table renders the
missing cells as empty `ground` (a staircase) and observed zeros as "0%" on the lightest step.

## Consequences
Tests assert the newest cohort has exactly one row and that observed zeros exist.
