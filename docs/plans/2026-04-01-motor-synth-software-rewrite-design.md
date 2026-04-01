# Motor Synth Software Rewrite Design

**Date:** 2026-04-01

## Goal

Переписать `MotorSynth` заново вокруг простой и проверенной модели software PWM synth:
два мотора, у каждого по два PWM канала (`LPWM`, `RPWM`), с базовым примитивом прямой отправки двух частот и двух duty на мотор и независимым воспроизведением левой и правой мелодий для полифонии.

## Scope

Первая версия поддерживает только software PWM и обычный synth playback:

- `play`
- `play_blheli`
- `play_split_blheli`
- `play_manual_split_pwm`
- `play_named`
- `off`
- `set_control_active`

Из первой версии временно исключаются:

- `HARDWARE` mode
- `play_wav`
- `play_spectral`

## Mental Model

Главная модель синта больше не строится вокруг абстрактных `pwm_pins` и `comp_pins`.
Главная модель:

- левый мотор: `left_lpwm_pin`, `left_rpwm_pin`
- правый мотор: `right_lpwm_pin`, `right_rpwm_pin`

Термины:

- `left/right` всегда означают мотор
- `lpwm/rpwm` всегда означают конкретный вход внутри мотора

Это убирает путаницу между "левый мотор" и "LPWM".

## Core Principle

Базовый рабочий примитив должен уметь на один мотор подать:

- частоту на `LPWM`
- duty на `LPWM`
- частоту на `RPWM`
- duty на `RPWM`

То есть synth строится снизу вверх от прямого управления каналами, а не от старой логики detune/shared groups.

## Base API

Внутри `MotorSynth` вводятся такие примитивы:

- `_apply_motor_pwm(lpwm_pin, rpwm_pin, lpwm_frequency_hz, lpwm_duty, rpwm_frequency_hz, rpwm_duty)`
- `_apply_dual_motor_pwm(left_lpwm_frequency_hz, left_lpwm_duty, left_rpwm_frequency_hz, left_rpwm_duty, right_lpwm_frequency_hz, right_lpwm_duty, right_rpwm_frequency_hz, right_rpwm_duty)`
- `_stop_motor_pwm(lpwm_pin, rpwm_pin)`

`play_manual_split_pwm` в первой версии остается прямым тестовым путем и должен опираться на тот рабочий паттерн, который уже подтвердился на железе.

## Synth Mapping

Для музыкального режима на один мотор используется helper, который из:

- `base_frequency_hz`
- `delta_percent`
- `duty`

считает две частоты для одного мотора.

Согласованное правило первой версии:

- `delta_percent` по умолчанию `20`
- duty на `LPWM` и `RPWM` одинаковый
- колесо должно оставаться без тягового дисбаланса

Helper возвращает пару частот для одного мотора, а затем они раскладываются на `LPWM/RPWM` этого мотора.

## Polyphony

Полифония реализуется не через смешивание пинов, а через независимые потоки нот:

- левый мотор может играть свою последовательность
- правый мотор может играть свою последовательность

Для `play_split_blheli` это означает отдельные левые и правые ноты без склейки старых combined pin groups.

Для обычного `play` и `play_blheli` одна и та же synth-note mapping может подаваться на оба мотора одновременно.

## Compatibility Constraints

Несмотря на переписывание, внешний контракт должен остаться совместимым с `main.py` и motor test API:

- сохранить класс `MotorSynth`
- сохранить конструктор с текущими аргументами
- сохранить поля pin groups, которые читает `main.py`
- сохранить `_pwm_mode`
- сохранить метод `play_manual_split_pwm`

Даже если часть старых аргументов внутри новой реализации больше не играет главную роль, они должны продолжать приниматься для совместимости wiring.

## Testing Strategy

Переписывание идет TDD-циклом.

Сначала новые/обновленные тесты должны зафиксировать:

- правильное отображение pins в модель двух моторов
- прямой software PWM manual path
- synth mapping на одном моторе при `delta_percent = 20`
- одинаковый duty на `LPWM` и `RPWM`
- одновременное воспроизведение на двух моторах
- независимое split playback для левого и правого мотора
- `play_named` через новый synth path

Старые тесты на `HARDWARE`, `wav`, `spectral`, shared channel dropping и старую detune/group semantics должны быть либо удалены из первой версии, либо временно переведены в ожидание новой фазы.

## Deferred Work

После стабилизации обычного software synth отдельно проектируются:

- `HARDWARE` mode
- `play_wav`
- `play_spectral`
- возможная более сложная мультитональная схема поверх базового software synth