import usb.core
import usb.util

dev = usb.core.find(idVendor=0x1209, idProduct=0x0D32)
print("bNumConfigurations:", dev.bNumConfigurations)
for cfg in dev:
    print("=== CONFIG", cfg.bConfigurationValue, "bNumInterfaces:", cfg.bNumInterfaces)
    for intf in cfg:
        print("   intf", intf.bInterfaceNumber,
              "alt", intf.bAlternateSetting,
              "class", intf.bInterfaceClass,
              "sub", intf.bInterfaceSubClass,
              "proto", intf.bInterfaceProtocol)
