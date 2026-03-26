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


def _get_env_choice(name: str, default: str, choices: set[str]) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().upper()
    if normalized in choices:
        return normalized
    return default


MOTOR_DRIVER_TYPE = _get_env_choice("MOTOR_DRIVER_TYPE", "BTS7960", {"PWM_DIR", "BTS7960"})
MOTOR1_PWM = _get_env_int("MOTOR1_PWM", 18)
MOTOR1_DIR = _get_env_int("MOTOR1_DIR", 23)
MOTOR2_PWM = _get_env_int("MOTOR2_PWM", 13)
MOTOR2_DIR = _get_env_int("MOTOR2_DIR", 24)
LEFT_MOTOR_RPWM = _get_env_int("LEFT_MOTOR_RPWM", 18)
LEFT_MOTOR_LPWM = _get_env_int("LEFT_MOTOR_LPWM", 13)
LEFT_MOTOR_REN = _get_env_int("LEFT_MOTOR_REN", 23)
LEFT_MOTOR_LEN = _get_env_int("LEFT_MOTOR_LEN", 24)
LEFT_MOTOR_ENABLED = bool(_get_env_int("LEFT_MOTOR_ENABLED", 1))
RIGHT_MOTOR_RPWM = _get_env_int("RIGHT_MOTOR_RPWM", 12)
RIGHT_MOTOR_LPWM = _get_env_int("RIGHT_MOTOR_LPWM", 19)
RIGHT_MOTOR_REN = _get_env_int("RIGHT_MOTOR_REN", 20)
RIGHT_MOTOR_LEN = _get_env_int("RIGHT_MOTOR_LEN", 21)
RIGHT_MOTOR_ENABLED = bool(_get_env_int("RIGHT_MOTOR_ENABLED", 1))
MOTOR1_INVERTED = _get_env_int("MOTOR1_INVERTED", 0)
MOTOR2_INVERTED = _get_env_int("MOTOR2_INVERTED", 0)
BUZZER_PIN = _get_env_int("BUZZER_PIN", 17)

CRSF_PORT = os.getenv("CRSF_PORT", "/dev/ttyS0")
CRSF_BAUD = _get_env_int("CRSF_BAUD", 420000)
BMS_TRANSPORT = _get_env_choice("BMS_TRANSPORT", "UART", {"UART", "BLE"})
BMS_PORT = os.getenv("BMS_PORT", "/dev/ttyUSB0")
BMS_BAUD = _get_env_int("BMS_BAUD", 9600)
BMS_BLE_ADDRESS = os.getenv("BMS_BLE_ADDRESS", "")
BMS_BLE_SERVICE_UUID = os.getenv("BMS_BLE_SERVICE_UUID", "0000fff0-0000-1000-8000-00805f9b34fb")
BMS_BLE_WRITE_UUID = os.getenv("BMS_BLE_WRITE_UUID", "0000fff2-0000-1000-8000-00805f9b34fb")
BMS_BLE_NOTIFY_UUID = os.getenv("BMS_BLE_NOTIFY_UUID", "0000fff1-0000-1000-8000-00805f9b34fb")
BMS_BLE_TIMEOUT_S = _get_env_float("BMS_BLE_TIMEOUT_S", 1.5)

FAILSAFE_TIMEOUT_S = _get_env_float("FAILSAFE_TIMEOUT_S", 0.5)
MAIN_LOOP_HZ = _get_env_int("MAIN_LOOP_HZ", 50)
BMS_POLL_INTERVAL_S = _get_env_float("BMS_POLL_INTERVAL_S", 1.0)
TEST_BATTERY_VOLTAGE = _get_env_float("TEST_BATTERY_VOLTAGE", 25.0)
TEST_BATTERY_CURRENT = _get_env_float("TEST_BATTERY_CURRENT", 1.2)
TEST_BATTERY_CAPACITY_MAH = _get_env_int("TEST_BATTERY_CAPACITY_MAH", 0)
TEST_BATTERY_REMAINING_PCT = _get_env_int("TEST_BATTERY_REMAINING_PCT", 55)

CH_STEERING = _get_env_int("CH_STEERING", 3)
CH_THROTTLE = _get_env_int("CH_THROTTLE", 1)
CH_ARM = _get_env_int("CH_ARM", 4)
ARM_THRESHOLD = _get_env_float("ARM_THRESHOLD", 0.3)
THROTTLE_FILTER_MODE = _get_env_choice("THROTTLE_FILTER_MODE", "NONE", {"NONE", "KALMAN"})
THROTTLE_KALMAN_PROCESS_NOISE = _get_env_float("THROTTLE_KALMAN_PROCESS_NOISE", 0.02)
THROTTLE_KALMAN_MEASUREMENT_NOISE = _get_env_float("THROTTLE_KALMAN_MEASUREMENT_NOISE", 0.5)

LOW_CELL_VOLTAGE = _get_env_float("LOW_CELL_VOLTAGE", 3.5)
LOW_PACK_VOLTAGE = _get_env_float("LOW_PACK_VOLTAGE", 21.0)
PWM_FREQUENCY_HZ = _get_env_int("PWM_FREQUENCY_HZ", 20000)
SERIAL_TIMEOUT_S = _get_env_float("SERIAL_TIMEOUT_S", 0.02)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Motor ramping / slew rate
RAMP_ACCEL_RATE = _get_env_float("RAMP_ACCEL_RATE", 2.0)
RAMP_DECEL_RATE = _get_env_float("RAMP_DECEL_RATE", 0.5)
RAMP_REVERSE_DECEL_RATE = _get_env_float("RAMP_REVERSE_DECEL_RATE", 0.5)
RAMP_ZERO_HOLD_S = _get_env_float("RAMP_ZERO_HOLD_S", 0.15)
MOTOR_DEADBAND = _get_env_float("MOTOR_DEADBAND", 0.05)

# Beacon / SOS
BEACON_ENABLED = bool(_get_env_int("BEACON_ENABLED", 1))
BEACON_DELAY_S = _get_env_float("BEACON_DELAY_S", 300.0)
CH_BEACON = _get_env_int("CH_BEACON", 7)

# Melody selection
ENABLE_RC_MELODIES = bool(_get_env_int("ENABLE_RC_MELODIES", 0))
CH_MELODY = _get_env_int("CH_MELODY", 8)
STARTUP_MELODY = os.getenv("STARTUP_MELODY", "biba_signature")
