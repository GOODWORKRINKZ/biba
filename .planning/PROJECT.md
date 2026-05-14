# BiBa

## What This Is

BiBa — колёсная двухколёсная робот-платформа с ручным радиоуправлением через ExpressLRS/CRSF.
Платформа модульная: поддерживает несколько аппаратных конфигураций (Pi Zero 2W, RP2040, STM32F103)
и разные типы приводов (коллекторные/бесколлекторные). Основной сценарий — надёжное выездное управление
оператором с пульта.

## Core Value

Робот должен ехать и слушаться пульта в любых условиях — всё остальное вторично.

## Requirements

### Validated

<!-- Возможности, уже реализованные и работающие в основной (Pi Zero 2W) версии. -->

- ✓ ELRS/CRSF приём и декодирование пакетов управления — existing
- ✓ Управление двумя каналами BTS7960 (левый/правый мотор) — existing
- ✓ IMU-стабилизированное вождение (heading hold по гироскопу) — existing
- ✓ PID-тюнинг с веб-UI — existing
- ✓ Замеры тока (ADS1115) — existing
- ✓ Управление BMS Daly 6S по BLE/USB-UART — existing
- ✓ Docker-стек на Pi Zero 2W — existing
- ✓ Русскоязычные голосовые ассеты и звуковая индикация — existing
- ✓ STM32 bridge (SPI/UART) для расширения I/O — existing
- ✓ Failsafe при потере связи CRSF — existing

### Active

<!-- Текущий скоуп — то, что строим. -->

- [ ] **RP2040-PORT-01**: ELRS/CRSF приём и декодирование работают на RP2040 (rp2040-port)
- [ ] **RP2040-PORT-02**: Управление BTS7960 (L/R каналы) с правильным PWM на RP2040
- [ ] **RP2040-PORT-03**: IMU (BMI160/LSM6DS3) стабилизация и heading-hold портированы на RP2040
- [ ] **RP2040-PORT-04**: Замеры тока (ADS1115 или внутренний АЦП) портированы и откалиброваны на RP2040
- [ ] **RP2040-PORT-05**: Триминг каналов (channel trim) портирован и проверен на RP2040
- [ ] **RP2040-PORT-06**: Failsafe при потере CRSF-связи работает на RP2040
- [ ] **THERMAL-01**: Аппаратная тепловая защита ESC/BTS7960 (крепёж на металл, гидроизоляция)
- [ ] **THERMAL-02**: Программная защита по температуре/перегрузке тока (throttle back при перегреве)
- [ ] **VARIANT-01**: Задокументирована матрица вариантов: платы × драйверы × опциональные модули
- [ ] **VARIANT-02**: Каждый вариант имеет описание подключения и статус реализации (ready / WIP / planned)

### Out of Scope

<!-- Явные границы. Не переносить сюда без обсуждения. -->

- Web UI, браузерная телеметрия — Phase 1 только ручное управление с пульта
- BMS интеграция на RP2040 — отложено, Pi Zero 2W остаётся референсом для BMS
- Голос/звук на RP2040 — нет достаточных ресурсов памяти на Pico, откладываем
- LED-матрицы (фары/индикаторы) — следующая аппаратная фаза
- Follow-me, автономная навигация, ROS2 integration — за пределами Phase 1
- ODrive/VESC интеграция в firmware — документируется в матрице вариантов, не реализуется в этой фазе

## Context

- Основная ветка: Pi Zero 2W + BTS7960 + Python-контроллер + Docker
- Активный порт: `rp2040-port` — RPICO_RP2040 как standalone embedded target (PlatformIO)
- Третья платформа: STM32F103C8T6 (Blue Pill) — задокументирована в отдельной ветке
- Физический статус (май 2026): платы BTS7960 перегревались при ~20-30 мин интенсивной езды,
  сейчас чинится (крепёж на металлическую пластину для теплоотвода)
- Аккумуляторная база: аккумуляторы от дрона не подходят — требуется отдельный подбор
- Выездные испытания проведены (09.05.2026, двор), основная проблема — тепловой режим ESC

## Constraints

- **Hardware**: Pi Zero 2W resource-constrained — Docker + Python только для Pi Zero 2W ветки; RP2040 — C/C++ embedded
- **Multi-target**: Три платы (Pi Zero 2W, RP2040, STM32) — любые изменения протокола затрагивают все
- **Field readiness**: Критерий готовности Phase 1 — практический выезд, не юнит-тесты
- **Thermal**: BTS7960 без теплоотвода — ограничение длительности полевых сессий

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| RP2040 как приоритет Phase 1 | Более компактная standalone embedded платформа без Linux overhead | — Pending |
| Pi Zero 2W как референс | Все advanced функции (BMS, голос, ROS2) остаются на Python-стеке | ✓ Good |
| PlatformIO для firmware | Мультитаргет (STM32, RP2040) из одной конфигурации | ✓ Good |
| BTS7960 как первичный драйвер | Дешёвый, доступный, достаточный для коллекторных моторов | ⚠️ Revisit — тепловой режим |
| Матрица вариантов как документация | Фиксирует все возможные конфигурации, не форсирует реализацию | — Pending |

---

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-14 after initialization*
