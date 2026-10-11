# 12. Ramp step 5 is #4A79A8, not #5584B3

Status: accepted

## Context
Spec section 8.2 flips cell text from ink to white at step 5 and requires a contrast check on
every step. At the specified `#5584B3` neither works: ink is 4.09:1 and white 3.93:1, both below
WCAG AA (4.5:1).

## Decision
Step 5 is `#4A79A8` (white text 4.57:1), the smallest darkening of the same hue that passes.
Rates from fewer than 30 customers drop the fill and use graphite text on white (5.87:1) rather
than reduced-opacity graphite on a coloured cell, which would fail contrast on dark steps.

## Consequences
`apps/web/tests/unit/ramp.test.ts` checks every step; axe passes on every page.
