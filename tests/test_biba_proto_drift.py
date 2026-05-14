"""Guard: vendored biba_proto in biba_hardware_stm32 must match firmware.

If this test fails, someone edited one copy without re-vendoring the
other. Re-run::

    cp firmware/src/proto/biba_proto.h \\
       ros2_ws/src/biba_hardware_stm32/proto/biba_proto.h
    cp firmware/src/proto/biba_proto.c \\
       ros2_ws/src/biba_hardware_stm32/proto/biba_proto.c
    cp firmware/include/biba_version.h \\
       ros2_ws/src/biba_hardware_stm32/proto/biba_version.h

…then commit. Only edit the firmware copies; the SBC plugin always
follows.
"""

from __future__ import annotations

from pathlib import Path

import pytest


PAIRS = [
    (
        Path("firmware/src/proto/biba_proto.h"),
        Path("ros2_ws/src/biba_hardware_stm32/proto/biba_proto.h"),
    ),
    (
        Path("firmware/src/proto/biba_proto.c"),
        Path("ros2_ws/src/biba_hardware_stm32/proto/biba_proto.c"),
    ),
    (
        Path("firmware/include/biba_version.h"),
        Path("ros2_ws/src/biba_hardware_stm32/proto/biba_version.h"),
    ),
]


@pytest.mark.parametrize("source, vendored", PAIRS, ids=lambda p: p.name)
def test_vendored_copy_matches_firmware(source: Path, vendored: Path) -> None:
    assert source.is_file(), f"missing source {source}"
    assert vendored.is_file(), f"missing vendored {vendored}"

    src_bytes = source.read_bytes()
    vnd_bytes = vendored.read_bytes()

    assert src_bytes == vnd_bytes, (
        f"{vendored} drifted from {source}. "
        "Re-vendor by copying from the firmware tree."
    )


def test_python_protocol_version_matches_firmware() -> None:
    """PROTOCOL_VERSION on Python and BIBA_PROTO_VERSION on C must agree."""
    py = Path("biba-controller/stm32_link/protocol.py").read_text(encoding="utf-8")
    c = Path("firmware/include/biba_version.h").read_text(encoding="utf-8")

    # Find "PROTOCOL_VERSION = 0xNN" on the Python side.
    py_match = [
        line for line in py.splitlines() if line.startswith("PROTOCOL_VERSION")
    ]
    assert py_match, "PROTOCOL_VERSION not found in python protocol.py"

    # Find "#define BIBA_PROTO_VERSION 0xNN" on the C side.
    c_match = [
        line
        for line in c.splitlines()
        if line.lstrip().startswith("#define BIBA_PROTO_VERSION")
    ]
    assert c_match, "BIBA_PROTO_VERSION not found in biba_version.h"

    py_value = int(py_match[0].split("=", 1)[1].strip(), 0)
    c_value = int(c_match[0].split()[-1], 0)

    assert py_value == c_value, (
        f"PROTOCOL_VERSION mismatch: python={py_value:#04x} firmware={c_value:#04x}"
    )
