import asyncio
import sys

sys.path.insert(0, r"C:\ProgramData\Anaconda3\envs\odrive\lib\site-packages\odrive\pyfibre")
import fibre

async def main():
    print("libfibre version:", fibre.libfibre.version)
    path = "usb:idVendor=0x1209,idProduct=0x0D32,bInterfaceClass=0,bInterfaceSubClass=1,bInterfaceProtocol=0"
    print("opening domain:", path)
    with fibre.Domain(path) as domain:
        found = []
        async def on_found(obj):
            found.append(obj)
            print("FOUND object:", type(obj).__name__)
        discovery = domain.run_discovery(on_found)
        await asyncio.sleep(5)
        discovery.stop()
        print("total found:", len(found))

asyncio.run(main())
print("done")
