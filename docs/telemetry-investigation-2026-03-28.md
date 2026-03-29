# Telemetry Investigation Report - 2026-03-28

## Scope

This report closes the current investigation into BiBa transmitter-side Lua telemetry logging over USB VCP and its correlation with robot-side battery telemetry logs.

## Changes Implemented

1. Added VCP telemetry logging to the EdgeTX Lua screen in `lua/SCRIPTS/TELEMETRY/biba.lua`.
2. Added host-side capture tooling in `scripts/vcp_capture.py` to prepend local wall-clock time and epoch seconds to each VCP line.
3. Added focused regression tests for the Lua telemetry screen and the VCP capture script.
4. Added the narrow debugging skill `.agents/skills/telemetry-correlation-debugging/SKILL.md` for repeating this workflow.

## Lua No-Telemetry Safety Check

Current conclusion: the Lua telemetry screen should not crash merely because telemetry is absent.

Evidence:

1. Connection gating happens before battery sensor reads.
2. The disconnected branch logs only explicit zero or empty values and returns immediately.
3. The telemetry log formatter uses defensive fallbacks such as `or 0`, `text_or_dash(...)`, and empty-table handling in `format_cells_for_log(...)`.
4. `sensor(...)` returns the provided fallback when telemetry sensors are missing or zero.

Important limitation:

1. This verification covers the script logic and the current regression tests.
2. It does not prove behavior if the radio firmware lacks `serialWrite` or `setSerialBaudrate` support while VCP logging remains enabled.
3. For the target setup used in this investigation, VCP was enabled in `LUA` mode and produced valid output, so that interface is considered operational for this report.

## Verification

Executed:

```bash
/home/builder/biba/.venv/bin/python -m pytest tests/test_lua_telemetry_screen.py tests/test_vcp_capture.py
```

Result:

- 54 tests passed

## Correlation Findings

Sources compared:

1. App-side VCP capture with local timestamps: `artifacts/telemetry-captures/vcp-20260328-215311.log`
2. Robot-side battery telemetry from controller container logs

Observed event sequence in the VCP capture:

1. `DIS 3.00 A`
2. `DIS 4.90 A`
3. `DIS 3.20 A`

Observed event sequence in robot logs:

1. `DIS 3.00 A`
2. `IDLE 0.00 A`
3. `DIS 3.20 A`
4. `IDLE 0.00 A`

Interpretation:

1. The robot and transmitter agree on the sustained `3.00 A` and `3.20 A` discharge plateaus.
2. The short `4.90 A` plateau appears only in the VCP log.
3. The most likely reason is coarse robot-side battery telemetry logging at about 5-second cadence, which can miss short intermediate plateaus.
4. The matched app-side delay from the compared points is approximate, not exact, because the robot log is too sparse for point-level latency claims.

## Practical Outcome

The new VCP path is useful for debugging because it captures transmitter-visible telemetry at much finer granularity than the robot battery log stream. For this class of issue, the correct workflow is to normalize timestamps first, match plateau shapes rather than individual samples, and avoid over-claiming exact latency from sparse robot logs.