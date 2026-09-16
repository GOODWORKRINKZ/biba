import usb.core

dev = usb.core.find(idVendor=0x1209, idProduct=0x0D32)
print("device:", dev)
if dev is None:
    raise SystemExit("not found")
print("bNumConfigurations:", dev.bNumConfigurations)
cfg = dev.get_active_configuration()
for intf in cfg:
    print("interface", intf.bInterfaceNumber,
          "class", intf.bInterfaceClass,
          "sub", intf.bInterfaceSubClass,
          "proto", intf.bInterfaceProtocol)
