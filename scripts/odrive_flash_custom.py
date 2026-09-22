#!/usr/bin/env python
"""
Flash an ODrive v3.6-56V over USB DFU, bypassing the OTP hardware-version check.

The standard `odrivetool dfu` refuses to flash when the OTP memory is not
programmed (it cannot verify the board variant). On this board the OTP is empty,
but the running firmware falls back to the compiled-in default v3.6-56V, so we
know the board variant from the running firmware and can safely flash the
matching precompiled image.

Usage:
    .venv/bin/python scripts/odrive_flash_custom.py <path/to/firmware.hex> [expected-hw "3.6.56"]
"""
import sys
import time
import logging

import usb.core
import odrive
from odrive.utils import Event
from odrive.dfu import (
    DfuDevice,
    populate_sectors,
    get_first_mismatch_index,
    get_hw_version_string,
    get_fw_version_string,
    dump_otp,
)
from intelhex import IntelHex
from odrive import configuration

HEX_PATH = sys.argv[1] if len(sys.argv) > 1 else (
    "/home/ros2/Downloads/biba/artifacts/firmware/ODriveFirmware_v3.6-56V_0.5.6.hex")

# Expected hardware version (major, minor, variant). Variant 56 => 56V.
EXPECTED_HW = (3, 6, 56)

logger = logging.getLogger("odrive")
logging.basicConfig(level=logging.INFO)


def find_dfu_device(serial, deadline):
    """Poll libusb until an STM32 DFU bootloader with matching serial appears."""
    while time.time() < deadline:
        devs = usb.core.find(idVendor=0x0483, idProduct=0xDF11, find_all=True)
        for dev in devs:
            try:
                if dev.serial_number == serial:
                    return dev
            except ValueError:
                pass
        time.sleep(1)
    return None


def find_normal_device(deadline):
    """Poll until an ODrive reappears in normal (CDC) mode."""
    while time.time() < deadline:
        try:
            return odrive.find_any(timeout=3)
        except Exception:
            time.sleep(1)
    return None


def main():
    print("=== Finding ODrive (normal mode) ===")
    od = odrive.find_any(timeout=10)
    serial = "{:08X}".format(od.serial_number)
    hw = (od.hw_version_major, od.hw_version_minor, od.hw_version_variant)
    fw = (od.fw_version_major, od.fw_version_minor, od.fw_version_revision,
          od.fw_version_unreleased != 0 if hasattr(od, "fw_version_unreleased") else False)
    print("Found ODrive {} ({}) fw {}".format(
        serial, get_hw_version_string(hw), get_fw_version_string(fw)))

    if hw != EXPECTED_HW:
        print("ERROR: running firmware reports hw {} but we expect {}.".format(hw, EXPECTED_HW))
        print("Refusing to flash. Aborting.")
        return 1

    print("=== Loading firmware hex ===")
    hexfile = IntelHex(HEX_PATH)
    for s, e in hexfile.segments():
        print("  segment {:08X}-{:08X} ({} bytes)".format(s, e - 1, e - s))
    if hexfile.minaddr() < 0x08000000 or hexfile.maxaddr() > 0x080FFFFF:
        print("ERROR: hex file is not in the STM32F405 internal-flash range. Aborting.")
        return 1

    print("=== Backing up config ===")
    do_backup = od.user_config_loaded if hasattr(od, "user_config_loaded") else False
    if do_backup:
        configuration.backup_config(od, None, logger)

    print("=== Entering DFU mode ===")
    from odrive.dfu import put_into_dfu_mode
    put_into_dfu_mode(od, Event())

    print("=== Waiting for DFU bootloader ===")
    stm_dev = find_dfu_device(serial, time.time() + 60)
    if stm_dev is None:
        print("ERROR: DFU device did not appear within 60s. Aborting.")
        return 1
    dfudev = DfuDevice(stm_dev)
    print("DFU device found.")

    print("=== OTP dump (informational) ===")
    try:
        dump_otp(dfudev)
    except Exception as ex:
        print("  (could not dump OTP: {})".format(ex))

    print("=== Sectors ===")
    for sector in dfudev.sectors:
        print("  {:08X}-{:08X} ({})".format(
            sector["addr"], sector["addr"] + sector["len"] - 1, sector["name"]))

    touched_sectors = list(populate_sectors(dfudev.sectors, hexfile))
    print("Sectors to flash: {}".format(
        ["{:08X}".format(s["addr"]) for s, _ in touched_sectors]))

    # --- Erase all internal flash ---
    print("=== Erasing ===")
    internal = [s for s in dfudev.sectors if s["name"] == "Internal Flash"]
    for i, sector in enumerate(internal, 1):
        print("  erase {:08X} ({}/{})".format(sector["addr"], i, len(internal)), flush=True)
        dfudev.erase_sector(sector)
    print("  done")

    # --- Flash ---
    print("=== Flashing ===")
    for i, (sector, data) in enumerate(touched_sectors, 1):
        print("  flash {:08X} ({}/{})".format(sector["addr"], i, len(touched_sectors)), flush=True)
        dfudev.write_sector(sector, data)
    print("  done")

    # --- Verify ---
    print("=== Verifying ===")
    for i, (sector, expected) in enumerate(touched_sectors, 1):
        observed = dfudev.read_sector(sector)
        mismatch = get_first_mismatch_index(observed, expected)
        if mismatch is not None:
            mismatch -= mismatch % 16
            obs = " ".join("{:02X}".format(x) for x in observed[mismatch:mismatch + 16])
            exp = " ".join("{:02X}".format(x) for x in expected[mismatch:mismatch + 16])
            raise RuntimeError(
                "Verification failed at 0x{:08X}:\n  expected {}\n  observed {}".format(
                    sector["addr"] + mismatch, exp, obs))
        print("  verify {:08X} OK".format(sector["addr"]))
    print("  done")

    print("=== Jumping to application ===")
    dfudev.jump_to_application(0x08000000)

    print("=== Waiting for ODrive to reboot ===")
    new_od = find_normal_device(time.time() + 60)
    if new_od is None:
        print("WARNING: ODrive did not reappear within 60s. Check USB connection.")
        return 0
    new_fw = (new_od.fw_version_major, new_od.fw_version_minor, new_od.fw_version_revision, False)
    print("ODrive {} now reports fw {}".format(
        "{:08X}".format(new_od.serial_number), get_fw_version_string(new_fw)))
    print("=== SUCCESS ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
