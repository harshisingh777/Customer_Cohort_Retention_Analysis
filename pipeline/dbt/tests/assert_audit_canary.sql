-- A deliberately failing test, switched on only by the var `audit_canary` (test suite and
-- drills). Proves a failing test blocks the publish and leaves yesterday's data in place.
select 1 as canary
where {{ 'true' if var('audit_canary', false) else 'false' }}
