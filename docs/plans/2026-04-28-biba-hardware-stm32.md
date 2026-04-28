# biba_hardware_stm32 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Promote `biba_hardware_stm32` from a skeleton to a working `ros2_control` `SystemInterface` so `diff_drive_controller` can drive the robot directly through SPI without a Python hop.

**Architecture:**
- The hardware plugin becomes the **sole owner** of `/dev/spidev0.0`. Python `biba_stm32_bridge` is reduced to a non-IO node: it keeps `/biba/crsf/status` publication, `/biba/arm` service, and `/biba/stm32/telemetry` republish — all of which it now reads from a **shared in-process queue** populated by the C++ plugin... NO, that crosses a process boundary. Reframed below.
- Final design: Python bridge **stops touching SPI entirely**. Hardware plugin handles all SPI traffic (set_setpoint, get_telemetry). Python bridge subscribes to telemetry-mirror topics that the plugin (or a thin companion node) publishes, and serves `/biba/arm` by writing to a small `/biba/arm_request` topic that the plugin consumes during its `write()` cycle. This keeps a single SPI owner and avoids RPC across containers.
- The C++ plugin reuses `firmware/src/proto/biba_proto.{h,c}` (vendored into the package via CMake `add_subdirectory` or symlink) — protocol logic is not re-implemented.

**Tech Stack:** C++17, ros2_control humble, hardware_interface, pluginlib, Linux spidev ioctl.

---

## Tasks

### Task 1: Vendor the C protocol library into the package

**Files:**
- Create: `ros2_ws/src/biba_hardware_stm32/proto/biba_proto.h` (symlink or copy from `firmware/src/proto/biba_proto.h`)
- Create: `ros2_ws/src/biba_hardware_stm32/proto/biba_proto.c`
- Create: `ros2_ws/src/biba_hardware_stm32/proto/biba_version.h` (minimal stub — the firmware version constants are not needed on SBC)
- Modify: `ros2_ws/src/biba_hardware_stm32/CMakeLists.txt` — add `add_library(biba_proto STATIC proto/biba_proto.c)`, `target_include_directories(biba_proto PUBLIC proto)`.

**Decision:** copy, not symlink. Symlinks across the firmware/SBC boundary cause portability problems in Docker COPY contexts and on Windows clones. Add a CI check that diffs the two copies (Task 9).

**Test:** none yet — vendored files compile-tested via Task 2.

**Commit:** `chore(biba_hardware_stm32): vendor biba_proto from firmware`

### Task 2: SpiTransport thin wrapper around spidev ioctl

**Files:**
- Create: `ros2_ws/src/biba_hardware_stm32/include/biba_hardware_stm32/spi_transport.hpp`
- Create: `ros2_ws/src/biba_hardware_stm32/src/spi_transport.cpp`
- Test: `ros2_ws/src/biba_hardware_stm32/test/test_spi_transport.cpp` (gtest, `BUILD_TESTING` only)

**Step 1: Write the failing test**

Test that `SpiTransport::open("/dev/null")` returns false (or throws) — sanity check that the wrapper attempts `ioctl(SPI_IOC_*)` and reports failure rather than crashing. Use `ament_add_gtest`.

**Step 2: Implement minimal API**

```cpp
class SpiTransport {
 public:
  bool open(const std::string& device, uint32_t hz, uint8_t mode);
  bool transfer(const uint8_t* tx, uint8_t* rx, size_t len);
  void close();
};
```

Use `linux/spi/spidev.h`, `ioctl(SPI_IOC_WR_MODE)`, `ioctl(SPI_IOC_WR_MAX_SPEED_HZ)`, `ioctl(SPI_IOC_MESSAGE(1))`. Mode default `SPI_MODE_0`.

**Test:** colcon build + `colcon test` passes the gtest.

**Commit:** `feat(biba_hardware_stm32): add SpiTransport wrapper`

### Task 3: Stm32Link C++ — frame send/recv

**Files:**
- Create: `ros2_ws/src/biba_hardware_stm32/include/biba_hardware_stm32/stm32_link.hpp`
- Create: `ros2_ws/src/biba_hardware_stm32/src/stm32_link.cpp`
- Test: `ros2_ws/src/biba_hardware_stm32/test/test_stm32_link.cpp`

**API:**

```cpp
struct Setpoint { double left; double right; };
struct Telemetry {
  double left_velocity;
  double right_velocity;
  double battery_voltage;
  uint8_t flags;
  // ... mirror biba_proto_telemetry_t
};

class Stm32Link {
 public:
  bool open(const SpiConfig& cfg);
  bool exchange_setpoint(const Setpoint& sp, Telemetry& out_tlm);
  bool exchange_arm(bool armed, Telemetry& out_tlm);
  bool exchange_ping(Telemetry& out_tlm);
};
```

Internally calls `biba_proto_build_request_*` (from C lib) → `SpiTransport::transfer` → `biba_proto_parse_telemetry`. Increments `seq` monotonically. Returns false on CRC mismatch.

**Test:** mock `SpiTransport` (inject via constructor) and verify CRC vectors match the Python-side `tests/test_stm32_link_protocol.py` fixed vectors. Copy the byte-level fixtures verbatim from there.

**Commit:** `feat(biba_hardware_stm32): add Stm32Link C++ port`

### Task 4: BibaStm32SystemHardware skeleton

**Files:**
- Create: `ros2_ws/src/biba_hardware_stm32/include/biba_hardware_stm32/biba_stm32_system.hpp`
- Create: `ros2_ws/src/biba_hardware_stm32/src/biba_stm32_system.cpp`

**Inherits:** `hardware_interface::SystemInterface`.

**Joints:** two — `wheel_left_joint`, `wheel_right_joint`.

**State interfaces:** `position`, `velocity` per joint (4 total).
**Command interfaces:** `velocity` per joint (2 total).

**Lifecycle:**
- `on_init`: parse `info_.hardware_parameters` (`spi_device`, `spi_speed_hz`, `wheel_radius`, `max_wheel_speed`); validate joint names match; call `link_.open()`.
- `read(time, period)`: `link_.exchange_ping(tlm)`; integrate `tlm.left_velocity * period` into `pos_l_`, ditto right; store velocities.
- `write(time, period)`: convert `cmd_l_`, `cmd_r_` (rad/s) to normalised setpoints (`cmd / max_wheel_speed_rad_s`); `link_.exchange_setpoint(...)`. CRC failures trigger return ERROR but watchdog on STM32 will still cut motors.
- `on_shutdown`: send zero setpoint, call `link_.exchange_arm(false, ...)`.

**Commit:** `feat(biba_hardware_stm32): add BibaStm32SystemHardware skeleton`

### Task 5: Plugin XML + CMake export

**Files:**
- Create: `ros2_ws/src/biba_hardware_stm32/biba_hardware_stm32_plugin.xml`
- Modify: `ros2_ws/src/biba_hardware_stm32/CMakeLists.txt` — `pluginlib_export_plugin_description_file(hardware_interface biba_hardware_stm32_plugin.xml)`.
- Modify: `ros2_ws/src/biba_hardware_stm32/package.xml` — uncomment the `<hardware_interface plugin=".../>` line.

**plugin XML body:**
```xml
<library path="biba_hardware_stm32">
  <class name="biba_hardware_stm32/BibaStm32SystemHardware"
         type="biba_hardware_stm32::BibaStm32SystemHardware"
         base_class_type="hardware_interface::SystemInterface">
    <description>SPI-backed diff-drive system for BiBa composition C.</description>
  </class>
</library>
```

**Test:** colcon build, `ros2 pkg prefix biba_hardware_stm32` lists the lib, `ros2 control list_hardware_interfaces` after launch shows the joints (manual integration test).

**Commit:** `feat(biba_hardware_stm32): export pluginlib hardware_interface plugin`

### Task 6: Wire ros2_control into URDF

**Files:**
- Modify: `ros2_ws/src/biba_description/urdf/biba.urdf.xacro` — add `<ros2_control name="BibaSystem" type="system">` block referencing `biba_hardware_stm32/BibaStm32SystemHardware`, with two joints and `<param>` entries for `spi_device`, `spi_speed_hz`, `wheel_radius`, `max_wheel_speed`.
- Test: `tests/test_biba_description_ros2_control.py` — parse URDF, assert `<ros2_control>` block exists with the two joints and the plugin name.

**Commit:** `feat(biba_description): add ros2_control block for BibaStm32SystemHardware`

### Task 7: diff_drive_controller config + launch

**Files:**
- Create: `ros2_ws/src/biba_bringup/config/diff_drive_controller.yaml` — left/right wheel names, `wheel_separation`, `wheel_radius`, `cmd_vel_timeout`, `publish_odom`, `odom_frame_id=odom`, `base_frame_id=base_link`. Subscribe to `/cmd_vel` (output of twist_mux).
- Create: `ros2_ws/src/biba_bringup/launch/control.launch.py` — start `controller_manager` (`ros2_control_node`) with the URDF + a controllers YAML that includes both `joint_state_broadcaster` and `diff_drive_controller`. Spawn both via `Node(spawner)`.
- Test: `tests/test_biba_bringup_control.py` — yaml structure, joint names, controller types.

**Commit:** `feat(biba_bringup): add diff_drive controller config + launch`

### Task 8: Trim Python bridge — stop touching SPI

**Decision:** This is breaking. Approach in two phases to keep the system bootable.

Phase 8a — flag-gated. Add parameter `spi_owner` (`"bridge" | "external"`) to `bridge_node.py`. When `external`, the node:
- does NOT instantiate `STM32Link` (or instantiates it but never calls it)
- still serves `/biba/arm` but routes through publishing on `/biba/arm_request` (`std_msgs/Bool`)
- still publishes `/biba/stm32/telemetry` and `/biba/crsf/status`, but sources data from a new `/biba/raw_telemetry` topic (which the C++ plugin or controller_manager-side companion publishes) — TBD which side publishes.

Files:
- Modify: `ros2_ws/src/biba_stm32_bridge/biba_stm32_bridge/bridge_node.py`
- Modify: `tests/test_stm32_bridge_translator.py` (no change needed; translator stays pure)
- Add: `tests/test_stm32_bridge_node_owner.py` covering the new parameter branches with mocks.

**Open question (decide before starting):** does the C++ plugin publish `/biba/raw_telemetry`, or do we kill the Python bridge entirely in composition C and let the plugin handle telemetry directly? The cleaner answer is **kill the bridge** and have the plugin (or a small ros2_control-side companion node) publish CRSF/telemetry. But that turns Task 8 into "delete biba_stm32_bridge from the compose stack". Defer the decision to a follow-up plan.

**Commit:** `refactor(biba_stm32_bridge): allow external SPI ownership via spi_owner=external`

### Task 9: CI guard against protocol drift

**Files:**
- Create: `tests/test_biba_proto_drift.py` — assert `firmware/src/proto/biba_proto.h` and `ros2_ws/src/biba_hardware_stm32/proto/biba_proto.h` are byte-identical (same for `.c`).

**Commit:** `test(ci): guard against biba_proto drift between firmware and SBC plugin`

### Task 10: Update compose stack and docs

**Files:**
- Modify: `docker/ros2/docker-compose.yml` — replace the `biba-stm32-bridge` service's `command` with the `biba_bringup/control.launch.py` invocation; keep the bridge container only for arm-service / telemetry republish (or remove entirely depending on Task 8 outcome).
- Modify: `docker/ros2/README.md` — document the new ros2_control flow.
- Modify: `docs/deployment.md` composition C — note that `/cmd_vel` now feeds `diff_drive_controller`, not the bridge.

**Commit:** `feat(docker/ros2): switch to ros2_control-driven composition C`

---

## Risk callouts

1. **SPI clock speed**: Pi Zero 2W spidev jitter at >2 MHz is real. Pick a conservative default (`spi_speed_hz: 1000000`) and expose as a parameter.
2. **Velocity units mismatch**: `diff_drive_controller` writes `velocity` interface in **rad/s**. The STM32 protocol speaks normalised setpoints (`-1.0..1.0`). The conversion is `rad/s → normalised = ω / max_wheel_speed_rad_s`. Calibration of `max_wheel_speed_rad_s` is a field-test value; keep it as a hardware parameter.
3. **Telemetry ownership during transition**: while Task 8 is half-done, both sides will try to read SPI. Force `spi_owner=external` from day one in the composition C compose file once Task 5 lands, so the Python bridge never opens spidev under composition C.
4. **The plan has not been validated with `ros2 control` on hardware** — the first real-hardware run is the integration test for Tasks 4–7.

## Verification milestone (after all tasks)

```bash
ros2 launch biba_bringup control.launch.py
ros2 control list_hardware_interfaces
# Expected: command (velocity) and state (position, velocity) interfaces
# for wheel_left_joint and wheel_right_joint, all CLAIMED.

ros2 topic pub --once /cmd_vel_teleop geometry_msgs/Twist '{linear: {x: 0.2}}'
# Expected: STM32 LEDs / motors react; /odom advances; twist_mux logs the
# winner as "teleop"; /biba/stm32/telemetry shows non-zero left/right velocity.
```

## Execution Handoff

This plan has 10 tasks. Recommended cadence: tasks 1–3 in one session (compile-only, deterministic), 4–5 next session (plugin shape), 6–7 next (URDF + launch), 8–10 last (trimming Python and docs). Each task is independently committable.

Run via the `executing-plans` skill, one task at a time, with a build+test gate before each commit.
