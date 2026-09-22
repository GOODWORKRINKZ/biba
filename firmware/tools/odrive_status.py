"""Print identity + calibration state of the connected ODrive.

Usage:
    python tools\\odrive_status.py [serial:COM27 | usb]
"""
import sys

import odrive


def connect(arg):
    if not arg:
        # auto: try native USB then serial
        try:
            return odrive.find_any(timeout=8), "USB"
        except Exception:
            pass
        import serial.tools.list_ports
        for p in serial.tools.list_ports.comports():
            try:
                return odrive.find_any("serial:" + p.device, timeout=8), "serial:" + p.device
            except Exception:
                continue
        sys.exit("No ODrive found")
    return odrive.find_any(arg, timeout=8), arg


def hexv(v):
    return "0x%X" % v


def main():
    od, transport = connect(sys.argv[1] if len(sys.argv) > 1 else "")
    print("transport:", transport)
    print("serial:", od.serial_number)
    print("hw:", od.hw_version_major, od.hw_version_minor, od.hw_version_variant)
    print("fw:", od.fw_version_major, od.fw_version_minor, od.fw_version_revision)
    for name in ("axis0", "axis1"):
        ax = getattr(od, name)
        print("--", name)
        print("  axis_error:    ", hexv(ax.error))
        print("  motor_error:   ", hexv(ax.motor.error))
        print("  encoder_error: ", hexv(ax.encoder.error))
        print("  motor.is_calibrated:", ax.motor.is_calibrated,
              " pre_calibrated:", ax.motor.pre_calibrated)
        print("  enc.is_ready:       ", ax.encoder.is_ready,
              " pre_calibrated:", ax.encoder.pre_calibrated)
        print("  enc.offset:         ", ax.encoder.offset,
              " offset_float:", ax.encoder.offset_float)
        print("  motor.R/L/poles:    ", ax.motor.phase_resistance,
              ax.motor.phase_inductance, ax.motor.pole_pairs)


if __name__ == "__main__":
    main()
