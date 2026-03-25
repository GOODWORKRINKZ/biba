"""Main runtime loop for the BiBa wheeled platform controller."""

from __future__ import annotations

import logging
import signal
import time
from types import FrameType
from typing import Optional

import pigpio

import config
from bms.daly import BatteryState, DalyBMS
from buzzer.beacon import BeaconManager
from buzzer.buzzer import Buzzer
from crsf.receiver import CRSFReceiver
from crsf.telemetry import CRSFTelemetry
from motors.driver import DifferentialDrive, MotorDriver

LOGGER = logging.getLogger("biba-controller")
RUNNING = True


class _NullDrive:
    def drive(self, throttle: float, steering: float, dt: float = 0.02) -> None:
        del throttle, steering, dt

    def stop(self) -> None:
        pass

    def check_failsafe(self, last_frame_time: float) -> bool:
        del last_frame_time
        return False

    def emergency_stop(self) -> None:
        pass


class _NullBuzzer:
    def off(self) -> None:
        pass

    def startup_tone(self) -> None:
        pass

    def shutdown_tone(self) -> None:
        pass

    def connected_tone(self) -> None:
        pass

    def disconnected_tone(self) -> None:
        pass

    def arm_tone(self) -> None:
        pass

    def disarm_tone(self) -> None:
        pass

    def failsafe_tone(self) -> None:
        pass

    def sos_beacon(self) -> None:
        pass

    def low_voltage_alarm(self) -> None:
        pass


def _setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _signal_handler(signum: int, frame: Optional[FrameType]) -> None:
    del signum, frame
    global RUNNING
    RUNNING = False


def _is_armed(channels: list[float]) -> bool:
    if len(channels) <= config.CH_ARM:
        return False
    return channels[config.CH_ARM] > config.ARM_THRESHOLD


def _get_channel(channels: list[float], index: int) -> float:
    if index >= len(channels):
        return 0.0
    return channels[index]


def _battery_is_low(state: BatteryState) -> bool:
    if state.cells and state.min_cell > 0:
        return state.min_cell <= config.LOW_CELL_VOLTAGE
    return state.voltage <= config.LOW_PACK_VOLTAGE


def _send_battery_telemetry(telemetry: CRSFTelemetry, state: Optional[BatteryState]) -> None:
    if state is None:
        telemetry.send_battery(
            voltage_v=config.TEST_BATTERY_VOLTAGE,
            current_a=config.TEST_BATTERY_CURRENT,
            capacity_mah=config.TEST_BATTERY_CAPACITY_MAH,
            remaining_pct=config.TEST_BATTERY_REMAINING_PCT,
        )
        return

    telemetry.send_battery(
        voltage_v=state.voltage,
        current_a=max(0.0, state.current),
        capacity_mah=0,
        remaining_pct=int(round(state.soc)),
    )


def main() -> int:
    """Run the BiBa control loop until a shutdown signal is received."""
    _setup_logging()

    receiver = CRSFReceiver(config.CRSF_PORT, config.CRSF_BAUD, config.SERIAL_TIMEOUT_S)
    telemetry = CRSFTelemetry(None)
    bms = DalyBMS(config.BMS_PORT, config.BMS_BAUD)
    pi = pigpio.pi()
    if pi.connected:
        left_motor = MotorDriver(
            pi,
            config.MOTOR1_PWM,
            config.MOTOR1_DIR,
            inverted=bool(config.MOTOR1_INVERTED),
        )
        right_motor = MotorDriver(
            pi,
            config.MOTOR2_PWM,
            config.MOTOR2_DIR,
            inverted=bool(config.MOTOR2_INVERTED),
        )
        drive = DifferentialDrive(left_motor, right_motor)
        buzzer = Buzzer(pi, config.BUZZER_PIN)
    else:
        LOGGER.warning("Could not connect to pigpio daemon, starting in telemetry-only mode")
        drive = _NullDrive()
        buzzer = _NullBuzzer()
    beacon = BeaconManager(
        delay_s=config.BEACON_DELAY_S,
        enabled=config.BEACON_ENABLED,
    )

    bms_available = False

    try:
        receiver.open()
        telemetry.attach(receiver.serial_port)
    except Exception as exc:
        LOGGER.exception("Hardware initialization failed: %s", exc)
        drive.stop()
        buzzer.off()
        if pi.connected:
            pi.stop()
        return 1

    try:
        bms.open()
        bms_available = True
    except Exception as exc:
        LOGGER.warning("Daly BMS unavailable on %s: %s", config.BMS_PORT, exc)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    armed = False
    had_connection = False
    low_voltage_alarm_at = 0.0
    last_frame_time = time.monotonic()
    last_bms_poll = 0.0
    battery_state: Optional[BatteryState] = None
    loop_period = 1.0 / max(config.MAIN_LOOP_HZ, 1)

    LOGGER.info("BiBa controller started")
    buzzer.startup_tone()

    try:
        while RUNNING:
            loop_started_at = time.monotonic()

            try:
                channels = receiver.get_channels()
            except Exception as exc:
                LOGGER.warning("Failed to read CRSF channels: %s", exc)
                channels = None

            if channels is not None:
                last_frame_time = loop_started_at

                if not had_connection:
                    had_connection = True
                    buzzer.connected_tone()
                beacon.on_connected()

                requested_armed = _is_armed(channels)
                if requested_armed != armed:
                    armed = requested_armed
                    if armed:
                        LOGGER.info("Platform armed")
                        buzzer.arm_tone()
                    else:
                        LOGGER.info("Platform disarmed")
                        buzzer.disarm_tone()

                throttle = _get_channel(channels, config.CH_THROTTLE)
                steering = _get_channel(channels, config.CH_STEERING)
                if armed:
                    drive.drive(throttle, steering, loop_period)
                else:
                    drive.drive(0.0, 0.0, loop_period)

                # Manual beacon toggle via RC channel
                beacon_ch = _get_channel(channels, config.CH_BEACON)
                beacon.set_manual(beacon_ch > config.ARM_THRESHOLD)

            if drive.check_failsafe(last_frame_time):
                if armed:
                    LOGGER.warning("Failsafe triggered, disarming platform")
                    buzzer.failsafe_tone()
                drive.drive(0.0, 0.0, loop_period)
                if had_connection:
                    had_connection = False
                    buzzer.disconnected_tone()
                armed = False
                beacon.on_failsafe(loop_started_at)

            if beacon.should_sos(loop_started_at):
                buzzer.sos_beacon()

            if loop_started_at - last_bms_poll >= config.BMS_POLL_INTERVAL_S:
                last_bms_poll = loop_started_at
                if bms_available:
                    try:
                        battery_state = bms.read_state()
                    except Exception as exc:
                        LOGGER.warning("Failed to poll Daly BMS: %s", exc)
                        battery_state = None
                else:
                    battery_state = None

                try:
                    _send_battery_telemetry(telemetry, battery_state)
                except Exception as exc:
                    LOGGER.warning("Failed to send CRSF battery telemetry: %s", exc)

                if battery_state is not None:
                    if _battery_is_low(battery_state) and loop_started_at - low_voltage_alarm_at > 3.0:
                        low_voltage_alarm_at = loop_started_at
                        LOGGER.warning("Low battery warning: %.2fV", battery_state.voltage)
                        buzzer.low_voltage_alarm()

            elapsed = time.monotonic() - loop_started_at
            if elapsed < loop_period:
                time.sleep(loop_period - elapsed)
    finally:
        LOGGER.info("Shutting down BiBa controller")
        drive.emergency_stop()
        buzzer.shutdown_tone()
        buzzer.off()
        receiver.close()
        bms.close()
        if pi.connected:
            pi.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())