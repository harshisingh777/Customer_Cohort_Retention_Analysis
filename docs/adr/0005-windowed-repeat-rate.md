# 5. Repeat rate is windowed: "repeat within 90 days" among eligible customers

Status: accepted

## Context
An unwindowed repeat rate drops purely because recent customers are new.

## Decision
Repeat within 90 days = a second qualifying order on days 0-89 after the first, among customers
whose first order is at least 90 days before the cutoff. Historical LTV uses the same rule at
90/180/365 days. Vitals pick each metric's latest fully observed cohort.

## Consequences
Numbers are comparable across cohorts; recent cohorts appear once they are eligible.
