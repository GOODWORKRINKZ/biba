import usb.core
import usb.util

dev = usb.core.find(idVendor=0x1209, idProduct=0x0D32)
print("device:", dev)
if dev is None:
    raise SystemExit("not found")

# try to claim the native interface (2) and do bulk endpoint test
try:
    dev.set_configuration()
    print("set_configuration OK")
except Exception as e:
    print("set_configuration error:", repr(e))

try:
    if dev.is_kernel_driver_active(2):
        print("kernel driver active on intf 2, detaching")
        dev.detach_kernel_driver(2)
except Exception as e:
    print("kernel driver check error:", repr(e))

try:
    usb.util.claim_interface(dev, 2)
    print("claim_interface(2) OK")
    # find endpoints
    cfg = dev.get_active_configuration()
    intf = usb.util.find_descriptor(cfg, bInterfaceNumber=2)
    ep_out = usb.util.find_descriptor(intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
    ep_in = usb.util.find_descriptor(intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
    print("ep_out:", hex(ep_out.bEndpointAddress), "ep_in:", hex(ep_in.bEndpointAddress))
except Exception as e:
    print("claim error:", repr(e))
