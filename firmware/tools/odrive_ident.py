"""Print identity of the currently connected ODrive (USB or serial)."""
import sys

import odrive


def connect():
    try:
        return odrive.find_any(timeout=5), "USB"
    except Exception:
        pass
    try:
        import serial.tools.list_ports
        for p in serial.tools.list_ports.comports():
            try:
                return odrive.find_any("serial:" + p.device, timeout=5), "serial:" + p.device
            except Exception:
                continue
    except ImportError:
        pass
    sys.exit("No ODrive found (USB or serial)")


def main():
    odrv, transport = connect()
    print("transport:", transport)
    print("serial:", odrv.serial_number)
    print("hw:", odrv.hw_version_major, odrv.hw_version_minor, odrv.hw_version_variant)
    print("fw:", odrv.fw_version_major, odrv.fw_version_minor,
          odrv.fw_version_revision, "unreleased:", odrv.fw_version_unreleased)


if __name__ == "__main__":
    main()
