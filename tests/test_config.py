from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def config_module():
    module = importlib.import_module("config")
    return module


def test_config_uses_defaults_when_environment_is_missing(monkeypatch: pytest.MonkeyPatch, config_module) -> None:
    monkeypatch.delenv("MOTOR1_PWM", raising=False)
    monkeypatch.delenv("MOTOR1_INVERTED", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    module = importlib.reload(config_module)

    assert module.MOTOR1_PWM == 18
    assert module.MOTOR1_INVERTED == 0
    assert module.MOTOR2_INVERTED == 0
    assert module.LOG_LEVEL == "INFO"


def test_config_applies_environment_overrides(monkeypatch: pytest.MonkeyPatch, config_module) -> None:
    monkeypatch.setenv("MOTOR1_PWM", "19")
    monkeypatch.setenv("MOTOR1_INVERTED", "1")
    monkeypatch.setenv("MOTOR2_INVERTED", "1")
    monkeypatch.setenv("FAILSAFE_TIMEOUT_S", "0.75")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    module = importlib.reload(config_module)

    assert module.MOTOR1_PWM == 19
    assert module.MOTOR1_INVERTED == 1
    assert module.MOTOR2_INVERTED == 1
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