#!/usr/bin/env python3
"""
Dump *everything* a BLE peripheral exposes (services, characteristics, descriptors),
auto-retrying on disconnects.  Tested with Bose QC45 + Bleak ≥0.22.

Usage:
    python dump_ble.py 4B:A8:33:4C:9B:E5        # by MAC
    python dump_ble.py "LE-Rai's QC45"           # by (partial) name
"""

import asyncio
import binascii
import itertools
import sys

from bleak import BleakClient, BleakScanner

MAX_RETRIES = 5  # connection attempts before giving up
RETRY_DELAY_S = 3  # seconds between retries


def format_value(data: bytes, limit: int = 32) -> str:
    """Pretty-print a bytearray, trimming long values."""
    if data is None:
        return "<None>"
    if len(data) == 0:
        return "<empty>"
    hexstr = binascii.hexlify(data).decode()
    if len(hexstr) > limit * 2:
        return hexstr[: limit * 2] + "…"
    return hexstr


async def find_device(identifier: str):
    """Return BleakScanner BLEDevice by MAC or (partial) name."""
    print(f"Scanning for '{identifier}' …")
    for _ in range(3):
        devices = await BleakScanner.discover(timeout=5.0)
        for d in devices:
            if identifier.lower() in d.name.lower():
                print(f"↳ found {d.name} @ {d.address}")
                return d
        print("  not found, retrying …")
    raise RuntimeError(f"Device '{identifier}' not found")


async def dump(client: BleakClient):
    """Iterate through the whole GATT DB and print everything reachable."""
    print("\n=== GATT DATABASE ===")
    for svc in client.services:
        print(f"[Service] {svc.uuid} (Handle {svc.handle})  {svc.description}")
        for char in svc.characteristics:
            props = ",".join(char.properties)
            print(f"  [Char] {char.uuid} (Handle {char.handle})  [{props}]")
            # attempt read if allowed
            if "read" in char.properties:
                try:
                    data = await client.read_gatt_char(char)
                    print(f"         Value: {format_value(data)}")
                except Exception as e:
                    print(f"         !read failed: {e}")
            for desc in char.descriptors:
                try:
                    data = await client.read_gatt_descriptor(desc.handle)
                    print(f"      [Desc] {desc.uuid} (Handle {desc.handle}) Value: {format_value(data)}")
                except Exception as e:
                    print(f"      [Desc] {desc.uuid} (Handle {desc.handle}) !read failed: {e}")
    print("=== END ===\n")


async def main():
    # if len(sys.argv) != 2:
    #     sys.exit(f"Usage: {sys.argv[0]} <MAC-addr | name-substring>")

    # identifier = sys.argv[1] or "4B:A8:33:4C:9B:E5"
    dev = await find_device("Rai's QC45")

    # BLE:
    ## identifier = "4B:A8:33:4C:9B:E5"

    # Big boy device:
    ## identifier = "78:2B:64:A1:0E:1E"

    for attempt in itertools.count(1):
        if attempt > MAX_RETRIES:
            sys.exit("Too many failures, giving up.")

        print(f"\nAttempt {attempt}/{MAX_RETRIES} – connecting …")
        try:
            # dev<-identifier
            async with BleakClient(dev, disconnected_callback=lambda _: None) as cl:
                await dump(cl)
                return  # success → done
        # except BleakError as e:
        except Exception as e:
            print(f"⚠️  {e}")

        print(f"… reconnecting in {RETRY_DELAY_S}s")
        await asyncio.sleep(RETRY_DELAY_S)


if __name__ == "__main__":
    asyncio.run(main())

"""
=== GATT DATABASE ===
[Service] 0000180a-0000-1000-8000-00805f9b34fb (Handle 32)  Device Information
  [Char] 00002a29-0000-1000-8000-00805f9b34fb (Handle 33)  [read]
         Value: 426f736520436f72706f726174696f6e
  [Char] 00002a50-0000-1000-8000-00805f9b34fb (Handle 47)  [read]
         Value: 019e0039
  [Char] 00002a24-0000-1000-8000-00805f9b34fb (Handle 35)  [read]
         Value: 3836363732342d30313030
  [Char] 00002a28-0000-1000-8000-00805f9b34fb (Handle 41)  [read]
         Value: 342e302e34
  [Char] 00002a26-0000-1000-8000-00805f9b34fb (Handle 39)  [read]
         Value: 342e302e34
  [Char] 00002a23-0000-1000-8000-00805f9b34fb (Handle 43)  [read]
         Value: 00000000001fdf08
  [Char] 00002a2a-0000-1000-8000-00805f9b34fb (Handle 45)  [read]
         Value: <empty>
  [Char] 00002a27-0000-1000-8000-00805f9b34fb (Handle 37)  [read]
         Value: 312e302e30
[Service] 00001801-0000-1000-8000-00805f9b34fb (Handle 1)  Generic Attribute Profile
  [Char] 00002a05-0000-1000-8000-00805f9b34fb (Handle 2)  [indicate]
      [Desc] 00002902-0000-1000-8000-00805f9b34fb (Handle 4) Value: 0200
[Service] 0000fe03-0000-1000-8000-00805f9b34fb (Handle 21)  Vendor specific
  [Char] f04eb177-3005-43a7-ac61-a390ddf83076 (Handle 22)  [write]
  [Char] 2beea05b-1879-4bb4-8a2f-72641f82420b (Handle 24)  [read,notify]
         !read failed:
      [Desc] 00002902-0000-1000-8000-00805f9b34fb (Handle 26) !read failed: Not connected
[Service] 0000febe-0000-1000-8000-00805f9b34fb (Handle 5)  Bose Corporation
  [Char] c1c449f8-34d7-4c61-ad8a-4fb364f10b27 (Handle 19)  [write]
  [Char] b8ec1fa5-f56b-4aad-8961-856b84fed4f8 (Handle 17)  [write]
  [Char] d417c028-9818-4354-99d1-2ac09d074591 (Handle 9)  [read,write-without-response,write,notify]
         !read failed: Not connected
      [Desc] 00002902-0000-1000-8000-00805f9b34fb (Handle 11) !read failed: Not connected
  [Char] c65b8f2f-aee2-4c89-b758-bc4892d6f2d8 (Handle 12)  [read,write-without-response,write,notify]
         !read failed: Not connected
      [Desc] 00002902-0000-1000-8000-00805f9b34fb (Handle 14) !read failed: Not connected
  [Char] 9ec813b4-256b-4090-93a8-a4f0e9107733 (Handle 6)  [read,notify]
         !read failed: Not connected
      [Desc] 00002902-0000-1000-8000-00805f9b34fb (Handle 8) !read failed: Not connected
  [Char] 234bfbd5-e3b3-4536-a3fe-723620d4b78d (Handle 15)  [write]
=== END ===


bluetoothctl reports:

 ~/code/halinuxcompanion  agentydragon-wip wip ⇡3 +27 !20 ?5  bluetoothctl                                                                              system   12:49:44
Agent registered
AdvertisementMonitor path registered
[Rai's QC45]# info
Device 78:2B:64:A1:0E:1E (public)
	Name: Rai's QC45
	Alias: Rai's QC45
	Class: 0x00240418
	Icon: audio-headphones
	Paired: yes
	Trusted: yes
	Blocked: no
	Connected: yes
	LegacyPairing: no
	UUID: Vendor specific           (00000000-deca-fade-deca-deafdecacaff)
	UUID: Serial Port               (00001101-0000-1000-8000-00805f9b34fb)
	UUID: Headset                   (00001108-0000-1000-8000-00805f9b34fb)
	UUID: Audio Sink                (0000110b-0000-1000-8000-00805f9b34fb)
	UUID: A/V Remote Control Target (0000110c-0000-1000-8000-00805f9b34fb)
	UUID: Advanced Audio Distribu.. (0000110d-0000-1000-8000-00805f9b34fb)
	UUID: A/V Remote Control        (0000110e-0000-1000-8000-00805f9b34fb)
	UUID: Handsfree                 (0000111e-0000-1000-8000-00805f9b34fb)
	UUID: Phonebook Access Server   (0000112f-0000-1000-8000-00805f9b34fb)
	UUID: PnP Information           (00001200-0000-1000-8000-00805f9b34fb)
	UUID: Vendor specific           (9b26d8c0-a8ed-440b-95b0-c4714a518bcc)
	Modalias: bluetooth:v009Ep4039d0404
	Battery Percentage: 0x50 (80)

"""
