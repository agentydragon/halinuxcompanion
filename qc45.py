#!/usr/bin/env python3
"""
Read Battery % from a Bose QC45 (or any device that implements
the standard BLE Battery Service 0x180F / characteristic 0x2A19).

▪ pip install bleak
▪ If you run as a normal user: give python CAP_NET_RAW + CAP_NET_ADMIN
  sudo setcap cap_net_raw,cap_net_admin+eip $(readlink -f $(which python3))
"""
import argparse
import asyncio
import sys

from bleak import BleakClient, BleakScanner

BAT_SVC = "0000180f-0000-1000-8000-00805f9b34fb"
BAT_CHAR = "00002a19-0000-1000-8000-00805f9b34fb"


async def get_batt(address: str | None = None, name_hint: str = "Rai's QC45"):
    if address is None:  # quick 5-s scan
        print("Scanning for headset…")
        for dev in await BleakScanner.discover(timeout=5.0):
            if dev.name and name_hint.lower() in dev.name.lower():
                address = dev.address
                print(f"  ↳ found {dev.name}  ➜  {address}")
                break
        else:
            sys.exit("No matching device found — try passing MAC explicitly.")

    async with BleakClient(address) as cli:
        if not cli.is_connected:
            sys.exit("Couldn’t connect.")
        # make sure Battery Service is there
        if BAT_SVC not in {s.uuid for s in await cli.get_services()}:
            sys.exit("Device doesn’t expose the standard Battery Service.")
        val = await cli.read_gatt_char(BAT_CHAR)
        return int(val[0])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mac", nargs="?", help="Bluetooth MAC (leave blank to scan)")
    args = p.parse_args()
    pct = asyncio.run(get_batt(args.mac))
    print(f"Battery level: {pct}%")


if __name__ == "__main__":
    main()
