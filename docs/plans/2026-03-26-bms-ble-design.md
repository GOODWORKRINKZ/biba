# Daly BMS over BLE — Design Document

## Summary

Add a Bluetooth Low Energy transport for Daly BMS telemetry and make BMS access transport-selectable at runtime. Keep the existing UART integration as a fallback so deployed robots can switch transports through environment variables instead of code changes.

## Problem

The current controller hardcodes Daly BMS access over `/dev/ttyUSB0`. On the robot, the BLE module is present, connectable, and exposes GATT services, but the controller cannot use it. That prevents a cable-free BMS integration and ties telemetry to a USB-UART adapter.

## Goals

1. Support Daly BMS over BLE without changing the rest of the control loop.
2. Preserve the UART path as a runtime-selectable fallback.
3. Keep failure behavior unchanged: if BMS is unavailable, controller still runs and emits fallback battery telemetry.
4. Keep the transport boundary small and unit-testable.

## Non-Goals

- Removing UART support.
- Auto-discovery of nearby BMS modules.
- Pairing workflows or persistent BLE trust management.
- Full integration testing against live BLE hardware inside CI.

## Design

### 1. Common BMS interface

Introduce a transport-agnostic BMS reader protocol with the existing surface area:

- `open()`
- `close()`
- `read_state()`

`BMSPoller` already depends only on `read_state()`, so the main change is replacing direct `DalyBMS(...)` construction with a factory function that chooses a transport from config.

### 2. UART implementation remains intact

Rename the current serial-only implementation conceptually to UART, but keep compatibility with the existing parsing logic and frame handling. Its request/response framing remains the reference implementation for Daly packet parsing.

### 3. BLE implementation

Add a new `DalyBMSBle` implementation that:

- connects to a configured MAC address
- subscribes to a notify characteristic
- writes Daly request frames to a configured write characteristic
- waits for a 13-byte reply frame matching the requested command
- reuses the same frame parsing logic as UART for SoC, cell voltages, and temperatures

The BLE transport will assume the common Daly BLE bridge layout with service `FFF0` and configurable request/response characteristics. Characteristic UUIDs stay configurable to avoid baking hardware-specific assumptions into code.

### 4. Configuration

Add the following env-driven settings:

- `BMS_TRANSPORT=UART|BLE`
- `BMS_PORT` and `BMS_BAUD` for UART
- `BMS_BLE_ADDRESS`
- `BMS_BLE_SERVICE_UUID`
- `BMS_BLE_WRITE_UUID`
- `BMS_BLE_NOTIFY_UUID`
- `BMS_BLE_TIMEOUT_S`

Default behavior stays `UART` to avoid unexpected deployment changes.

### 5. Dependency and runtime model

Use `bleak` for the BLE client implementation. The code will hide `bleak` behind a small adapter so tests can inject a fake client without requiring a Bluetooth stack.

Container runtime must expose the host BlueZ stack to the controller. The compose service will add the system D-Bus socket mount required by `bleak` on Linux.

### 6. Error handling

- `open()` failures in either transport are logged and leave the controller in the existing fallback telemetry mode.
- BLE command timeouts return `None`, matching UART behavior.
- Disconnects or malformed frames during polling are treated as read failures and logged by `BMSPoller`.

## Testing

1. Unit tests for config transport selection.
2. Unit tests for the BMS factory.
3. Unit tests for BLE frame exchange using a fake BLE client.
4. Regression tests proving `main()` still tolerates BMS startup failure in both UART and BLE modes.

## Deployment Notes

BLE should be enabled on the robot by setting `BMS_TRANSPORT=BLE` and the target BLE MAC address. UART fallback remains available by resetting `BMS_TRANSPORT=UART`.