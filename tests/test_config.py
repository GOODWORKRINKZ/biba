from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def config_module():
    module = importlib.import_module("config")
    return module


def test_config_uses_defaults_when_environment_is_missing(monkeypatch: pytest.MonkeyPatch, config_module) -> None:
    monkeypatch.delenv("MOTOR1_PWM", raising=False)
    monkeypatch.delenv("MOTOR_DRIVER_TYPE", raising=False)
    monkeypatch.delenv("MOTOR1_INVERTED", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    module = importlib.reload(config_module)

    assert module.MOTOR1_PWM == 18
    assert module.MOTOR_DRIVER_TYPE == "PWM_DIR"
    assert module.MOTOR1_INVERTED == 0
    assert module.MOTOR2_INVERTED == 0
    assert module.LEFT_MOTOR_RPWM == 18
    assert module.LEFT_MOTOR_LPWM == 13
    assert module.LEFT_MOTOR_REN == 23
    assert module.LEFT_MOTOR_LEN == 24
    assert module.RIGHT_MOTOR_RPWM == 12
    assert module.RIGHT_MOTOR_LPWM == 16
    assert module.RIGHT_MOTOR_REN == 20
    assert module.RIGHT_MOTOR_LEN == 21
    assert module.CRSF_PORT == "/dev/ttyS0"
    assert module.TEST_BATTERY_VOLTAGE == pytest.approx(25.0)
    assert module.TEST_BATTERY_CURRENT == pytest.approx(1.2)
    assert module.TEST_BATTERY_CAPACITY_MAH == 0
    assert module.TEST_BATTERY_REMAINING_PCT == 55
    assert module.LOG_LEVEL == "INFO"


def test_config_applies_environment_overrides(monkeypatch: pytest.MonkeyPatch, config_module) -> None:
    monkeypatch.setenv("MOTOR1_PWM", "19")
    monkeypatch.setenv("MOTOR_DRIVER_TYPE", "BTS7960")
    monkeypatch.setenv("MOTOR1_INVERTED", "1")
    monkeypatch.setenv("MOTOR2_INVERTED", "1")
    monkeypatch.setenv("LEFT_MOTOR_REN", "26")
    monkeypatch.setenv("RIGHT_MOTOR_LEN", "6")
    monkeypatch.setenv("FAILSAFE_TIMEOUT_S", "0.75")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    module = importlib.reload(config_module)

    assert module.MOTOR1_PWM == 19
    assert module.MOTOR_DRIVER_TYPE == "BTS7960"
    assert module.MOTOR1_INVERTED == 1
    assert module.MOTOR2_INVERTED == 1
    assert module.LEFT_MOTOR_REN == 26
    assert module.RIGHT_MOTOR_LEN == 6
    assert module.FAILSAFE_TIMEOUT_S == pytest.approx(0.75)
    assert module.LOG_LEVEL == "DEBUG"


def test_config_ignores_invalid_numeric_environment_values(monkeypatch: pytest.MonkeyPatch, config_module) -> None:
    monkeypatch.setenv("MOTOR1_PWM", "not-a-number")
    monkeypatch.setenv("MOTOR1_INVERTED", "broken")
    monkeypatch.setenv("FAILSAFE_TIMEOUT_S", "broken")

    module = importlib.reload(config_module)

    assert module.MOTOR1_PWM == 18
    assert module.MOTOR1_INVERTED == 0
    assert module.FAILSAFE_TIMEOUT_S == pytest.approx(0.5)


def test_docker_compose_exposes_beacon_environment_variables() -> None:
    with open("docker-compose.yml", encoding="utf-8") as compose_file:
        compose = compose_file.read()

    assert "BEACON_ENABLED:" in compose
    assert "BEACON_DELAY_S:" in compose
    assert "CH_BEACON:" in compose


def test_docker_compose_exposes_bts7960_environment_variables() -> None:
    with open("docker-compose.yml", encoding="utf-8") as compose_file:
        compose = compose_file.read()

    assert "MOTOR_DRIVER_TYPE:" in compose
    assert "LEFT_MOTOR_RPWM:" in compose
    assert "LEFT_MOTOR_LPWM:" in compose
    assert "LEFT_MOTOR_REN:" in compose
    assert "LEFT_MOTOR_LEN:" in compose
    assert "RIGHT_MOTOR_RPWM:" in compose
    assert "RIGHT_MOTOR_LPWM:" in compose
    assert "RIGHT_MOTOR_REN:" in compose
    assert "RIGHT_MOTOR_LEN:" in compose


def test_docker_compose_exposes_pigpio_device_mappings() -> None:
    with open("docker-compose.yml", encoding="utf-8") as compose_file:
        compose = compose_file.read()

    assert "/dev/gpiomem:/dev/gpiomem" in compose
    assert "/dev/vcio:/dev/vcio" in compose
    assert "/dev/mem:/dev/mem" in compose


def test_env_example_documents_beacon_environment_variables() -> None:
    with open(".env.example", encoding="utf-8") as env_file:
        env_example = env_file.read()

    assert "BEACON_ENABLED=" in env_example
    assert "BEACON_DELAY_S=" in env_example
    assert "CH_BEACON=" in env_example
    assert "MOTOR_DRIVER_TYPE=" in env_example
    assert "LEFT_MOTOR_RPWM=" in env_example
    assert "RIGHT_MOTOR_LEN=" in env_example