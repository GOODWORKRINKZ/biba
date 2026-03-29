---
name: telemetry-correlation-debugging
description: Use when correlating BiBa transmitter-side VCP telemetry logs with robot battery telemetry logs, especially when timestamps come from different time domains, one side samples much more slowly than the other, or short current plateaus may be missed between robot log entries.
---

# Telemetry Correlation Debugging

## Overview

Use this skill to compare EdgeTX Lua VCP captures against robot-side battery telemetry logs without drawing false conclusions from timezone mismatches or unequal sampling rates.

Core principle: normalize time first, then match event shapes, then state what the coarse side cannot prove.

## Workflow

### 1. Identify the two log domains

Collect and label each source before comparing anything:

- VCP capture from `artifacts/telemetry-captures/*.log`
- Robot battery telemetry from `docker logs --timestamps ...`

For VCP logs, confirm whether lines contain:

- local wall time, such as `2026-03-28T21:53:21.752444+01:00`
- epoch seconds, such as `epoch=1774731201.752499`
- app-side values, such as `RAWI=3.00`, `RAWDIR=DIS`

For robot logs, confirm whether lines contain:

- container UTC timestamps ending in `Z`
- battery telemetry values, such as `telemetry_current_a=3.00`
- direction values, such as `telemetry_direction=DIS`

### 2. Normalize timestamps before matching

Do not compare local wall time to robot logs directly.

Use one shared time domain:

- Prefer UTC if both sources expose wall-clock timestamps.
- Prefer epoch seconds if the VCP capture includes them.

For BiBa telemetry sessions, the common pattern has been:

- local workstation log: `+01:00`
- robot shell clock: `+03:00`
- container logs: `UTC Z`

If these domains are not stated explicitly in the result, the comparison is incomplete.

### 3. Match event plateaus, not individual samples

The robot battery log is typically much coarser than the VCP stream. Treat the robot log as sparse checkpoints.

Match using event shape:

- current magnitude plateau, such as `3.00 A`
- battery direction transition, such as `IDLE -> DIS -> IDLE`
- voltage step accompanying the current event
- ordering of plateaus, such as `3.0 -> 4.9 -> 3.2 A`

Do not claim exact point-by-point equality when one side only logs every few seconds.

### 4. Separate valid conclusions from invalid ones

Valid conclusions:

- both sides saw the same sustained `DIS` event
- app-side event appears about `N` seconds after the robot-side log point
- robot-side logging frequency is too coarse to capture short peaks

Invalid conclusions:

- the robot never produced a short current plateau just because it is absent from a coarse log
- app-side latency is exactly `N` seconds from one sparse match
- the transmitter display is wrong merely because it shows more detail than the robot log

### 5. Report both the match and the gap

Every comparison should include:

- matched plateaus
- unmatched short events
- observed lag range
- confidence level based on sampling density

If the robot logs once every about 5 seconds, explicitly say that short events between samples can be missed.

## Quick Commands

Typical local VCP inspection:

```bash
grep -n 'RAWI=\|RAWDIR=' artifacts/telemetry-captures/vcp-YYYYMMDD-HHMMSS.log
```

Typical robot log extraction:

```bash
sshpass -p 'open' ssh -o StrictHostKeyChecking=no biba@192.168.2.185 \
	"docker logs --timestamps biba-biba-controller-1 2>&1 | grep 'Battery telemetry' | tail -n 120"
```

Typical narrow robot time window:

```bash
sshpass -p 'open' ssh -o StrictHostKeyChecking=no biba@192.168.2.185 \
	"docker logs --timestamps biba-biba-controller-1 2>&1 | grep '2026-03-28T20:53' | grep 'Battery telemetry'"
```

## Output Pattern

Use a compact table when presenting results:

| Event | App-side evidence | Robot-side evidence | Observed lag | Confidence |
| --- | --- | --- | --- | --- |
| `DIS 3.00 A` | VCP line and timestamp | Robot line and timestamp | Approximate | High |
| `DIS 4.90 A` | Present in VCP | Missing in robot log | Not measurable | Low because coarse robot sampling |

Then summarize:

1. what clearly matches
2. what the coarse robot log missed
3. what latency range is supportable
4. what additional logging frequency would be needed for tighter proof

## Common Mistakes

| Mistake | Why it is wrong |
| --- | --- |
| Comparing `+01:00` timestamps directly to `Z` timestamps | Time domains are different |
| Declaring a short event absent because robot logs do not show it | Coarse sampling can skip it |
| Using one matched point as an exact latency measurement | Sparse robot logs only bound the delay roughly |
| Ignoring direction fields like `DIS` and `IDLE` | Plateau ordering becomes ambiguous |

## BiBa-Specific Notes

- The active controller container may be `biba-biba-controller-1`, not `biba-controller`.
- VCP capture files can begin with one truncated line if capture starts mid-stream.
- App-side logs can show finer detail than robot logs; that is expected when the transmitter logs more frequently.
