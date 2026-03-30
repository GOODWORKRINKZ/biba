# BLHeli Melody Anti-Roll Design

## Summary

Restore anti-roll behavior for shared-channel BLHeli motor melodies without returning to the previous failure mode where only the wheel with a broken complementary PWM path remained audible. The solution is to give BLHeli tone playback its own slower bipolar switching cadence, separate from the faster zero-mean cadence used by WAV and spectral playback.

## Problem

The current motor-audio stack has two bad extremes for shared-channel BLHeli melody playback:

1. Driving tones only on the primary PWM pins keeps melodies audible on both motors, but introduces a net drive bias and can rotate a wheel during alarms such as `sos`.
2. Reusing the existing fast bipolar zero-mean alternation removes average bias, but on real hardware it makes the healthy wheel nearly silent while the wheel with a faulty complementary PWM path remains audible.

WAV and spectral playback are not the problem. They already have a working fast bipolar path and sound acceptable on both sides.

## Requirements

1. Apply the fix to all shared-channel BLHeli melodies, not just `sos`.
2. Reduce wheel rotation during melody playback, but do not require mathematically perfect zero drift.
3. Keep melody playback audible on both motors.
4. Leave WAV and spectral playback behavior unchanged.
5. Keep non-shared-channel melody playback unchanged.

## Approaches Considered

### 1. Keep melody playback one-directional

Pros:

- loudest melody playback
- simplest code path

Cons:

- produces obvious wheel rotation
- unacceptable for alarms and beacons

### 2. Reuse the current fast zero-mean cadence

Pros:

- minimal average torque
- code already exists

Cons:

- regressed real-world audibility on the healthy wheel
- too aggressive for pure tone playback on this BTS7960 wiring

### 3. Add a dedicated slower BLHeli bipolar cadence

Pros:

- reduces average torque without fully cancelling audibility
- isolates melody behavior from WAV/spectral behavior
- can be tuned independently if hardware response changes

Cons:

- adds a second bipolar strategy to maintain
- still allows some residual wheel motion by design

## Recommendation

Use approach 3.

Shared-channel BLHeli melody playback should alternate direction in coarse slices that are longer than the current fast audio cadence. This preserves enough sustained excitation for the motor to stay audible while reducing the long-term drive bias that causes wheel roll.

## Design

### 1. Separate BLHeli melody anti-roll path

Keep the existing WAV/spectral bipolar helpers unchanged.

Add a distinct helper in `MotorSynth` for BLHeli tone playback on shared-channel motor groups:

- input: left frequency, right frequency, duration
- behavior: play one direction for a melody slice, then switch direction for the next slice
- cadence: use a dedicated melody slice interval rather than the fast 8 ms cadence used previously

This helper becomes the shared-channel path for:

- `_tone()`
- `_split_tone()`

### 2. Dedicated melody slice interval

Introduce a constant for BLHeli shared-channel anti-roll slices, for example `24 ms` or `32 ms`.

The exact value should be chosen empirically from these constraints:

1. long enough to keep tones audible on a healthy wheel
2. short enough to reduce obvious rolling during `sos`, `failsafe`, and other sustained melodies
3. consistent across mono and split BLHeli playback

The initial implementation should use one fixed value rather than per-melody tuning.

### 3. Scope of behavior change

Apply the slower slice-switching path to all shared-channel BLHeli melodies:

- mono BLHeli melodies via `_tone()`
- split BLHeli melodies via `_split_tone()`

Do not change:

- non-shared-channel melody playback
- WAV playback
- spectral playback

### 4. Test strategy

Add regression coverage showing that shared-channel BLHeli melody playback:

1. no longer stays pinned to only the primary PWM direction for the full note duration
2. still energizes both left and right motor groups with non-zero frequencies
3. continues to avoid using the old too-fast behavior assumption from the WAV/spectral tests

Because hardware audibility cannot be directly asserted in unit tests, tests should verify the intended switching structure rather than psychoacoustic outcome.

## Out of Scope

1. Per-melody slice tuning.
2. User-configurable anti-roll slice intervals.
3. Changes to WAV/spectral playback.
4. Hardware rewiring or motor driver redesign.