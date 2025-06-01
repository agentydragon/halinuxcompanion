#!/usr/bin/env python3
# bluetooth_dashboard.py
# deps:  pydbus  PyGObject   (apt install python3-pydbus python3-gi)
#        rich (optional, prettier table)  pip install rich


from typing import Any

from gi.repository import GLib
from pydbus import SystemBus

# ───── optional pretty output via Rich ───────────
from rich.console import Console
from rich.table import Table

console = Console()

bus = SystemBus()
om = bus.get("org.bluez", "/")
objs = om.GetManagedObjects()  # global cache we keep in sync

# pick first adapter
adapter_path = next(p for p, i in objs.items() if "org.bluez.Adapter1" in i)
adapter = bus.get("org.bluez", adapter_path)

devices: dict[str, dict[str, Any]] = {}  # addr  -> info-dict


# ───────────────── helper funcs ──────────────────
def ensure_dev_props(path):
    """Return up-to-date org.bluez.Device1 dict or None."""
    if path in objs and "org.bluez.Device1" in objs[path]:
        return objs[path]["org.bluez.Device1"]

    props = bus.get("org.bluez", path).GetAll("org.bluez.Device1")
    if not props:
        return None
    objs.setdefault(path, {})["org.bluez.Device1"] = props
    return props


def iface_list(path):
    if path in objs:
        return tuple(sorted(objs[path].keys()))
    # lazy introspection for brand-new object
    try:
        xml = bus.get("org.bluez", path).Introspect()
        names = [ln.split('"')[1] for ln in xml.splitlines() if "interface name=" in ln]
        objs[path] = {n: {} for n in names}
        return tuple(sorted(names))
    except Exception as e:
        print(e)
        return ()


def transport_props(dev_path):
    """Find first MediaTransport1 child under dev_path."""
    for p, ifs in objs.items():
        if p.startswith(dev_path) and "org.bluez.MediaTransport1" in ifs:
            return ifs["org.bluez.MediaTransport1"]
    # lazy fetch if not in cache yet
    for p in bus.get("org.bluez", dev_path).Introspect().split():
        pass
    return None


def codec_name(code):
    return {0x00: "SBC", 0x01: "SBC", 0x02: "AAC", 0x03: "aptX", 0xFF: "Vendor"}.get(code, "")


def update_entry(path, changed=None):
    dev = ensure_dev_props(path)
    if not dev:  # not a Device1 object
        return
    info = devices.setdefault(dev["Address"], {})
    info.update(
        {
            "alias": dev.get("Alias") or "?",
            "addr": dev["Address"],
            "rssi": dev.get("RSSI"),
            "bat": dev.get("BatteryPercentage"),
            "connected": dev.get("Connected"),
            "ifaces": iface_list(path),
        }
    )

    if tx := transport_props(path):
        info.update(
            {
                "state": tx.get("State"),
                "codec": codec_name(tx.get("Codec")),
                "delay": tx.get("Delay"),
                "vol": tx.get("Volume"),
            }
        )
    if changed:
        info.update(changed)


# seed with currently known Device1 objects
for p, ifs in objs.items():
    if "org.bluez.Device1" in ifs:
        update_entry(p)


# ───── subscribe to live changes ─────────────
def on_props(sender, path, iface, signal, params):
    if signal != "PropertiesChanged":
        return
    intf, changed, _ = params
    if intf != "org.bluez.Device1":
        return
    ensure_dev_props(path)  # refresh cache
    update_entry(path, changed)


bus.subscribe(
    iface="org.freedesktop.DBus.Properties",
    signal="PropertiesChanged",
    arg0="org.bluez.Device1",
    signal_fired=on_props,
)

# continuous discovery for RSSI
adapter.SetDiscoveryFilter(
    {
        "Transport": GLib.Variant("s", "auto"),
        "RSSI": GLib.Variant("n", -127),
    }
)
adapter.StartDiscovery()


# ───── display loop ───────────────────────────
def render():
    tbl = Table(header_style="bold cyan")
    for h in (
        "Alias",
        "MAC",
        "RSSI",
        "Bat%",
        "State",
        "Codec",
        "Delay",
        "Vol",
        "Interfaces",
    ):
        tbl.add_column(h, overflow="fold")
    for d in sorted(devices.values(), key=lambda x: (not x["connected"], x["alias"])):
        tbl.add_row(
            d["alias"],
            d["addr"],
            f"{d['rssi']} dBm" if d.get("rssi") is not None else "-",
            f"{d['bat']:.0f}%" if d.get("bat") is not None else "-",
            d.get("state") or ("on" if d["connected"] else "-"),
            d.get("codec", ""),
            str(d.get("delay", "")),
            str(d.get("vol", "")),
            ",".join(i.split(".")[-1] for i in d["ifaces"]),
        )
    console.clear()
    console.print(tbl)


def tick():
    render()
    return True


GLib.timeout_add_seconds(1, tick)

try:
    GLib.MainLoop().run()
except KeyboardInterrupt:
    adapter.StopDiscovery()
    print("\nStopped.")
