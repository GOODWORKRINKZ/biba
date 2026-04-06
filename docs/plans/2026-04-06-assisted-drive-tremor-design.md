# Assisted Drive Tremor Design

## Goal

Suppress neutral-stick twitching in IMU-assisted drive modes without making assisted turning feel sluggish again.

## Findings

- Recent armed logs show nonzero steering correction while throttle and operator steering remain at zero.
- The assist controller has stick deadband, but no deadband on measured yaw-rate noise and no output deadband on small corrective steering.
- Heading-hold state survives arm/disarm transitions, so stale heading reference can keep producing correction after the robot stops.

## Chosen Approach

Use a three-part fix in the assisted-drive controller:

1. Reset controller state on arm/disarm transitions so heading-hold does not carry stale state across runs.
2. Add a small measured-yaw-rate deadband near zero before yaw-rate control, so gyro noise and residual bias do not create visible steering output.
3. Add a lightweight first-order low-pass filter on measured yaw-rate to smooth short spikes while preserving operator-commanded turning response.

## Why This Approach

- Reset on arm/disarm addresses persistent correction and stale heading-reference drift at the source.
- Yaw-rate deadband handles the exact failure mode visible in logs: small nonzero measured yaw at neutral stick.
- A light filter reduces chatter without relying on heavy output smoothing, which would reintroduce slow turning.

## Non-Goals

- No stick-input filtering.
- No output-only masking in the motor driver.
- No retuning of operator speed modes in this change.

## Verification

- Add regression tests for arm/disarm reset behavior.
- Add regression tests ensuring small neutral yaw noise produces zero steering.
- Add regression tests showing brief spikes are attenuated while sustained yaw still generates correction.
- Run targeted assisted-drive tests, then the full pytest suite.