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
from buzzer.buzzer import Buzzer
from crsf.receiver import CRSFReceiver
from crsf.telemetry import CRSFTelemetry
from motors.driver import DifferentialDrive, MotorDriver

LOGGER = logging.getLogger("biba-controller")
RUNNING = True


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


def main() -> int:
    """Run the BiBa control loop until a shutdown signal is received."""
    _setup_logging()

    pi = pigpio.pi()
    if not pi.connected:
        LOGGER.error("Could not connect to pigpio daemon")
        return 1

    receiver = CRSFReceiver(config.CRSF_PORT, config.CRSF_BAUD, config.SERIAL_TIMEOUT_S)
    telemetry = CRSFTelemetry(None)
    bms = DalyBMS(config.BMS_PORT, config.BMS_BAUD)
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

    try:
        receiver.open()
        telemetry.attach(receiver.serial_port)
        bms.open()
    except Exception as exc:
        LOGGER.exception("Hardware initialization failed: %s", exc)
        drive.stop()
        buzzer.off()
        pi.stop()
        return 1

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    armed = False
    low_voltage_alarm_at = 0.0
    last_frame_time = time.monotonic()
    last_bms_poll = 0.0
    battery_state: Optional[BatteryState] = None
    loop_period = 1.0 / max(config.MAIN_LOOP_HZ, 1)

    LOGGER.info("BiBa controller started")

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
                requested_armed = _is_armed(channels)
                if requested_armed != armed:
                    armed = requested_armed
                    if armed:
                        LOGGER.info("Platform armed")
                        buzzer.arm_tone()
                    else:
                        LOGGER.info("Platform disarmed")
                        drive.stop()
                        buzzer.disarm_tone()

                throttle = _get_channel(channels, config.CH_THROTTLE)
                steering = _get_channel(channels, config.CH_STEERING)
                if armed:
                    drive.drive(throttle, steering)
                else:
                    drive.stop()

            if drive.check_failsafe(last_frame_time):
                if armed:
                    LOGGER.warning("Failsafe triggered, disarming platform")
                armed = False

            if loop_started_at - last_bms_poll >= config.BMS_POLL_INTERVAL_S:
                last_bms_poll = loop_started_at
                try:
                    battery_state = bms.read_state()
                except Exception as exc:
                    LOGGER.warning("Failed to poll Daly BMS: %s", exc)
                    battery_state = None

                if battery_state is not None:
                    remaining_pct = int(round(battery_state.soc))
                    try:
                        telemetry.send_battery(
                            voltage_v=battery_state.voltage,
                            current_a=max(0.0, battery_state.current),
                            capacity_mah=0,
                            remaining_pct=remaining_pct,
                        )
                    except Exception as exc:
                        LOGGER.warning("Failed to send CRSF battery telemetry: %s", exc)

                    if _battery_is_low(battery_state) and loop_started_at - low_voltage_alarm_at > 3.0:
                        low_voltage_alarm_at = loop_started_at
                        LOGGER.warning("Low battery warning: %.2fV", battery_state.voltage)
                        buzzer.low_voltage_alarm()

            elapsed = time.monotonic() - loop_started_at
            if elapsed < loop_period:
                time.sleep(loop_period - elapsed)
    finally:
        LOGGER.info("Shutting down BiBa controller")
        drive.stop()
        buzzer.off()
        receiver.close()
        bms.close()
        pi.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())