# Standalone CMakeLists.txt for the RPICO_RP2040_BLDC firmware target.
#
# This file is **optional** — the project is driven by PlatformIO via
# `platformio.ini` (`pio run -e rpico_rp2040_bldc_standalone`).
# It exists because:
#   1. Some IDEs (CLion, VS Code with CMake Tools) want a `CMakeLists.txt`
#      near every target for code-intel / static analysis to resolve.
#   2. Power users who want to bypass PlatformIO and build with
#      `cmake -G Ninja + ninja + picotool` directly can do so.
#
# Prereqs (host-side): Pico SDK 1.5+, GCC arm-none-eabi, picotool,
# `pico_enable_stdio_usb()`-friendly CMake config.
#
# Usage:
#   mkdir build && cd build
#   cmake -G Ninja -DPICO_SDK_PATH=/path/to/pico-sdk ..
#   ninja          # produces firmware.elf, firmware.uf2
#   picotool load -p /dev/ttyACM0 firmware.uf2
#
# This file does NOT run as part of CI; CI uses `.github/workflows/`
# which builds via `pio run` exclusively.
#
# References:
#   - platformio.ini `[env:rpico_rp2040_bldc_*]` — primary build path
#   - docs/adr/0001-pico-bldc-target.md — architecture (ADR-0001)
#   - docs/mcp2515_bldc_research.md — hardware reference

cmake_minimum_required(VERSION 3.16)
project(biba_rpico_rp2040_bldc C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED PICO_SDK_PATH)
    message(FATAL_ERROR
        "PICO_SDK_PATH is required.  e.g. cmake -DPICO_SDK_PATH=$HOME/pico-sdk ..")
endif()
get_filename_component(PICO_SDK_PATH "${PICO_SDK_PATH}" ABSOLUTE)

include(${PICO_SDK_PATH}/pico_sdk_init.cmake)
pico_sdk_init()

add_executable(biba_rpico_rp2040_bldc
    ${CMAKE_CURRENT_LIST_DIR}/../../src/drivers/mcp2515.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/drivers/can_queue.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/drivers/odrive_can.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/drivers/crsf.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/drivers/imu.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/hal/biba_hal_rp2040.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/hal/biba_hal_motor_bldc.c
    ${CMAKE_CURRENT_LIST_DIR}/../../src/hal/biba_hal_serial.cpp
    ${CMAKE_CURRENT_LIST_DIR}/../../src/main_rp2040.cpp
    # Add the rest of the bare minimum build here.  Adjust as the
    # firmware picks up new modules.  The full list is encoded in
    # platformio.ini's `[rp2040_bldc_src_filter]`.
)

target_compile_definitions(biba_rpico_rp2040_bldc PRIVATE
    -DBIBA_TARGET_HAS_BTS7960_2CH=0
    -DBIBA_TARGET_HAS_BLDC_2CH=1
    -DBIBA_TARGET_HAS_MCP2515=1
    -DBIBA_TARGET_HAS_SPI_SLAVE=0
    -DBIBA_MODE_STANDALONE=1
)

target_include_directories(biba_rpico_rp2040_bldc PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}/../../include
    ${CMAKE_CURRENT_LIST_DIR}/../../src
    ${CMAKE_CURRENT_LIST_DIR}/../../src/proto
    ${CMAKE_CURRENT_LIST_DIR}            # for target.h
)

target_compile_options(biba_rpico_rp2040_bldc PRIVATE
    -Wall -Wextra -Wpedantic -O2 -g
)

pico_enable_stdio_usb(biba_rpico_rp2040_bldc 1)
pico_enable_stdio_uart(biba_rpico_rp2040_bldc 0)

pico_add_extra_outputs(biba_rpico_rp2040_bldc)
