"""Runtime configuration for the BiBa controller."""

from __future__ import annotations

import os


def _get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


MOTOR1_PWM = _get_env_int("MOTOR1_PWM", 18)
MOTOR1_DIR = _get_env_int("MOTOR1_DIR", 23)
MOTOR2_PWM = _get_env_int("MOTOR2_PWM", 13)
MOTOR2_DIR = _get_env_int("MOTOR2_DIR", 24)
BUZZER_PIN = _get_env_int("BUZZER_PIN", 17)

CRSF_PORT = os.getenv("CRSF_PORT", "/dev/ttyAMA0")
CRSF_BAUD = _get_env_int("CRSF_BAUD", 420000)
BMS_PORT = os.getenv("BMS_PORT", "/dev/ttyUSB0")
BMS_BAUD = _get_env_int("BMS_BAUD", 9600)

FAILSAFE_TIMEOUT_S = _get_env_float("FAILSAFE_TIMEOUT_S", 0.5)
MAIN_LOOP_HZ = _get_env_int("MAIN_LOOP_HZ", 50)
BMS_POLL_INTERVAL_S = _get_env_float("BMS_POLL_INTERVAL_S", 1.0)

CH_STEERING = _get_env_int("CH_STEERING", 0)
CH_THROTTLE = _get_env_int("CH_THROTTLE", 1)
CH_ARM = _get_env_int("CH_ARM", 4)
ARM_THRESHOLD = _get_env_float("ARM_THRESHOLD", 0.3)

LOW_CELL_VOLTAGE = _get_env_float("LOW_CELL_VOLTAGE", 3.5)
LOW_PACK_VOLTAGE = _get_env_float("LOW_PACK_VOLTAGE", 21.0)
PWM_FREQUENCY_HZ = _get_env_int("PWM_FREQUENCY_HZ", 20000)
SERIAL_TIMEOUT_S = _get_env_float("SERIAL_TIMEOUT_S", 0.02)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
