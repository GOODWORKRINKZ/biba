# Wheel Current Telemetry Cleanup Design

## Goal

Replace the current ad hoc left and right wheel-current telemetry flow with a clean BIBA-specific contract so the rest of the codebase works with semantic wheel-current values instead of transport-specific CRSF carrier fields.

## Problem

The current telemetry path works, but it leaks transport details through every layer:

- Python telemetry code packs left wheel current into GPS heading.
- Python telemetry code packs right wheel current into GPS altitude, including the CRSF altitude offset.
- Lua screen logic reads `Hdg` and `Alt` directly.
- UI formatting therefore depends on unrelated transport semantics.

This creates three concrete problems:

1. left and right wheel current do not share one honest semantic contract
2. transport-specific offsets can leak into display behavior
3. changing the transport mapping later would require touching both producer and UI code

## Goals

1. Define canonical BIBA wheel-current signals for left and right sides.
2. Keep transport-specific CRSF carrier mapping isolated to a narrow adapter layer.
3. Make Lua UI and telemetry logging consume BIBA semantics rather than raw carrier fields.
4. Ensure left and right wheel current use the same units, scale, rounding, and fallback behavior.
5. Preserve runtime compatibility with the existing CRSF transport in the first iteration.

## Non-Goals

- Replacing CRSF itself.
- Adding a new custom CRSF protocol extension in this iteration.
- Changing the physical ADS1115 current-sense path.
- Reworking the battery telemetry contract.
- Rewriting the visual layout of the Lua telemetry screen.

## Approaches Considered

### Option 1: Normalize only in Lua

Move all cleanup into the Lua script and keep Python telemetry mapping as-is.

Pros:
- smallest code change
- lowest short-term risk

Cons:
- Python still publishes semantically misleading telemetry
- UI remains coupled to transport quirks
- no clean domain contract exists on the controller side

### Option 2: Introduce a BIBA domain contract plus transport adapters

Define canonical wheel-current values in Python, keep a dedicated CRSF carrier encoder on the controller side, and add a dedicated BIBA sensor adapter layer in Lua before values reach UI code.

Pros:
- clean semantic boundary
- transport quirks isolated to one place per side of the interface
- future transport changes do not force UI rewrites
- testable contract across Python and Lua

Cons:
- requires coordinated updates in controller, Lua, and tests
- existing direct sensor reads in Lua must be refactored

### Option 3: Build a new custom telemetry transport end-to-end

Replace the carrier approach with a custom protocol surface for wheel-current data.

Pros:
- highest semantic purity on the wire

Cons:
- highest implementation and compatibility risk
- likely disproportionate to the current need
- not necessary to eliminate the current architectural leak

## Recommendation

Use Option 2.

This gives the codebase a clean BIBA-facing contract immediately, while keeping the first migration compatible with the existing CRSF transport. The transport may still temporarily reuse standard carrier fields, but that detail becomes private to the adapter layer instead of contaminating business logic and UI code.

## Design

### 1. Canonical BIBA data contract

Inside BIBA, wheel current becomes a semantic value, not a transport trick.

The canonical fields are:

- `left_wheel_current_ma`
- `right_wheel_current_ma`

Contract rules:

- both use `mA`
- both use the same rounding rules
- both use the same saturation rules
- neither contains hidden transport offsets
- absence or invalidity degrades to a predictable safe value

These fields become the only wheel-current values that higher-level code should reason about.

### 2. Python domain layer

Add a narrow domain representation for system telemetry values that belong to BIBA semantics rather than CRSF semantics.

This layer should:

- accept measured current in amps from the controller loop
- convert wheel-current values to canonical `mA`
- clamp or round once, consistently, in one place
- expose semantic fields for downstream encoding

This layer must not know about `Hdg`, `Alt`, `GSpd`, or `Sats`.

### 3. Python transport adapter

Add a dedicated encoder that maps the canonical BIBA telemetry values onto the currently available CRSF carrier fields.

In the first iteration, this adapter can continue using the existing GPS-based transport path. The difference is architectural: only this adapter knows that the left wheel current currently rides in one carrier field and the right wheel current in another.

Responsibilities of this layer:

- encode canonical BIBA values into CRSF payload fields
- apply any required CRSF-specific offset or scale locally
- keep compatibility with current transmitter behavior
- avoid leaking carrier details upward into the rest of the controller

### 4. Lua BIBA sensor adapter

Refactor the Lua script so raw carrier reads happen only in a small adapter section.

This adapter should provide functions such as:

- `read_left_wheel_current_ma()`
- `read_right_wheel_current_ma()`
- `read_biba_system_stats()`

Those functions may temporarily read `Hdg`, `Alt`, `GSpd`, and `Sats`, but they must normalize them back into the canonical BIBA meaning before returning values to the rest of the script.

### 5. Lua UI layer

The UI layer should consume only canonical BIBA values.

That means:

- screen rendering does not call `sensor("Hdg", 0)` or `sensor("Alt", 0)` directly
- current formatting treats left and right identically
- telemetry logging prints BIBA wheel-current values, not raw carrier values

After this change, the UI will not need to know where the transport hid the data.

### 6. Failure handling

Failure behavior must be symmetric and predictable.

Rules:

- if wheel-current data is unavailable in Python, the canonical domain values fall back safely
- if carrier decoding fails in Lua, the adapter returns `0 mA`
- the UI never attempts heuristic reconstruction from broken carrier values
- missing data should degrade to stable zeros rather than misleading spikes or mixed units

This keeps the display safe and makes transport or discovery errors obvious without corrupting layout behavior.

### 7. Migration strategy

Use a compatibility-preserving migration:

1. introduce canonical BIBA telemetry helpers in Python
2. route the current CRSF GPS-based carrier encoding through a dedicated adapter
3. add Lua BIBA sensor adapter functions
4. update screen rendering and Lua telemetry logging to use only adapter-returned values
5. remove direct UI dependency on raw carrier fields for wheel current

This allows the transport implementation to remain compatible during the cleanup while the architectural boundaries are repaired.

## Testing Strategy

### Python domain tests

Verify that:

- left and right current are converted from amps to `mA` identically
- rounding and saturation rules are symmetric
- canonical values do not depend on CRSF-specific offsets

### Python transport tests

Verify that:

- canonical left wheel current encodes into the chosen carrier field correctly
- canonical right wheel current encodes into the chosen carrier field correctly
- all CRSF-specific offset handling is confined to the transport adapter

### Lua adapter tests

Verify that:

- adapter functions read the raw carrier sensors and return canonical wheel-current values
- the right-side carrier offset is normalized before values reach UI logic
- unavailable carrier values return safe defaults

### Lua screen tests

Verify that:

- UI code uses BIBA adapter functions rather than direct raw carrier reads for wheel current
- left and right current formatting is identical
- logging paths also use canonical values

## Success Criteria

The cleanup is complete only when all of the following are true:

1. controller-side wheel-current semantics are expressed in canonical BIBA fields
2. controller domain code does not mention transport carrier names
3. Lua UI code does not directly read raw carrier fields for wheel current
4. left and right wheel current share the same units, scale, rounding, and fallback behavior
5. transport-specific quirks are isolated to adapter code on each side of the interface
6. changing the carrier mapping later would not require rewriting screen rendering logic

## Open Constraint

The first iteration still depends on the existing CRSF carrier path for compatibility. That is acceptable as long as the carrier detail remains isolated in adapter code and no longer leaks into domain or UI logic.