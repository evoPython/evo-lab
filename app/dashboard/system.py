import glob
import os
import socket
import time

import psutil


# Captured once at import time so uptime is measured against actual
# system boot, not process start.
BOOT_TIME = psutil.boot_time()

# Baseline sample for network throughput. Rates are derived from the
# delta between calls, so we need a starting point captured at import
# time rather than assuming the first call's counters are a rate.
_last_net_io = psutil.net_io_counters()
_last_net_time = time.time()


def get_system_stats():

    return {
        "cpu": get_cpu(),
        "ram": get_ram(),
        "swap": get_swap(),
        "battery": get_battery(),
        "disk": get_disk(),
        "network": get_network(),
        "load": get_load_avg(),
        "processes": get_process_count(),
        "uptime": get_uptime(),
    }


def get_cpu():

    return {
        "percent": psutil.cpu_percent(interval=0.2),
        "cores": psutil.cpu_count(logical=True),
        "temperature": get_cpu_temperature(),
    }


def get_cpu_temperature():
    """
    Not all hardware/drivers expose sensors_temperatures() (and it
    doesn't exist at all on macOS/Windows), so this fails soft and
    returns None instead of raising.
    """

    try:
        temps = psutil.sensors_temperatures()
    except (AttributeError, OSError):
        return None

    if not temps:
        return None

    # Common labels on Arch/Linux laptops, checked in priority order.
    for label in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
        entries = temps.get(label)
        if entries:
            return entries[0].current

    # Fall back to whatever sensor is available.
    for entries in temps.values():
        if entries:
            return entries[0].current

    return None


def get_ram():

    mem = psutil.virtual_memory()

    return {
        "percent": mem.percent,
        "used_gb": round(mem.used / (1024 ** 3), 2),
        "total_gb": round(mem.total / (1024 ** 3), 2),
    }


def get_swap():

    swap = psutil.swap_memory()

    return {
        "percent": swap.percent,
        "used_gb": round(swap.used / (1024 ** 3), 2),
        "total_gb": round(swap.total / (1024 ** 3), 2),
    }


def _find_battery_sysfs_path():
    matches = glob.glob("/sys/class/power_supply/BAT*")
    return matches[0] if matches else None


def _read_sysfs_int(path):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _read_sysfs_str(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _read_battery_sysfs():
    """
    Arch/Linux batteries expose kernel power_supply attributes under
    /sys/class/power_supply/BAT*. psutil's sensors_battery() reads
    the same files but only surfaces a whole-percent capacity and a
    coarse secsleft, so for anything more precise (watts, 2-decimal
    percent, an accurate ETA) it's simplest to read the raw files
    directly. Some laptops expose energy_* (µWh, power-based), others
    charge_* + current_now (µAh, current-based) — handle both, and
    fail soft (return None) if neither is present, e.g. desktops/VMs.
    """

    base = _find_battery_sysfs_path()
    if not base:
        return None

    status = _read_sysfs_str(os.path.join(base, "status"))
    charging = status.lower() == "charging" if status else None

    watts = None
    power_now = _read_sysfs_int(os.path.join(base, "power_now"))
    current_now = _read_sysfs_int(os.path.join(base, "current_now"))
    voltage_now = _read_sysfs_int(os.path.join(base, "voltage_now"))
    if power_now is not None:
        watts = power_now / 1_000_000
    elif current_now is not None and voltage_now is not None:
        watts = (current_now / 1_000_000) * (voltage_now / 1_000_000)

    percent = None
    hours_to_full = None
    hours_to_empty = None

    energy_now = _read_sysfs_int(os.path.join(base, "energy_now"))
    energy_full = _read_sysfs_int(os.path.join(base, "energy_full"))
    if energy_now is not None and energy_full:
        percent = (energy_now / energy_full) * 100
        if watts and watts > 0.05:
            hours_to_full = max(energy_full - energy_now, 0) / 1_000_000 / watts
            hours_to_empty = energy_now / 1_000_000 / watts
    else:
        charge_now = _read_sysfs_int(os.path.join(base, "charge_now"))
        charge_full = _read_sysfs_int(os.path.join(base, "charge_full"))
        if charge_now is not None and charge_full:
            percent = (charge_now / charge_full) * 100
            current_a = (current_now / 1_000_000) if current_now else None
            if current_a and current_a > 0.01:
                hours_to_full = max(charge_full - charge_now, 0) / 1_000_000 / current_a
                hours_to_empty = charge_now / 1_000_000 / current_a

    return {
        "percent": percent,
        "charging": charging,
        "watts": round(watts, 2) if watts is not None else None,
        "hours_to_full": hours_to_full,
        "hours_to_empty": hours_to_empty,
    }


def get_battery():

    battery = psutil.sensors_battery()

    if not battery:
        return None

    sysfs = _read_battery_sysfs()

    percent = battery.percent
    charging = battery.power_plugged
    watts = None
    secsleft = None

    if sysfs:
        if sysfs["percent"] is not None:
            percent = sysfs["percent"]
        if sysfs["charging"] is not None:
            charging = sysfs["charging"]
        watts = sysfs["watts"]

        if charging and sysfs["hours_to_full"] is not None:
            secsleft = round(sysfs["hours_to_full"] * 3600)
        elif not charging and sysfs["hours_to_empty"] is not None:
            secsleft = round(sysfs["hours_to_empty"] * 3600)

    if secsleft is None:
        raw = battery.secsleft
        if raw not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN, None):
            secsleft = raw

    return {
        "percent": round(percent, 2),
        "charging": charging,
        "secsleft": secsleft,
        "watts": watts,
    }


def get_disk():

    usage = psutil.disk_usage("/")

    return {
        "percent": usage.percent,
        "used_gb": round(usage.used / (1024 ** 3), 2),
        "total_gb": round(usage.total / (1024 ** 3), 2),
    }


def _friendly_iface_name(name):
    """
    Maps raw kernel interface names (wlp1s0, enp2s0, tailscale0, ...)
    to short human labels. Prefix-based since exact names vary by
    hardware/driver — this covers the common Arch/systemd-networkd
    and NetworkManager naming schemes without needing to shell out
    to nmcli/iw for the actual SSID.
    """

    n = name.lower()
    if n.startswith(("wl", "wifi")):
        return "Wi-Fi"
    if n.startswith(("en", "eth")):
        return "Ethernet"
    if n.startswith("tailscale"):
        return "Tailscale"
    if n.startswith("wg"):
        return "WireGuard"
    if n.startswith(("docker", "veth", "br-", "virbr")):
        return "Virtual"
    return name


def get_network():

    global _last_net_io, _last_net_time

    io_counters = psutil.net_io_counters()
    addrs = psutil.net_if_addrs()

    interfaces = {}
    for name, addr_list in addrs.items():
        if name == "lo":
            continue
        for addr in addr_list:
            if addr.family == socket.AF_INET:
                interfaces[_friendly_iface_name(name)] = addr.address

    now = time.time()
    elapsed = max(now - _last_net_time, 0.001)
    sent_rate_bps = max(io_counters.bytes_sent - _last_net_io.bytes_sent, 0) / elapsed
    recv_rate_bps = max(io_counters.bytes_recv - _last_net_io.bytes_recv, 0) / elapsed

    _last_net_io = io_counters
    _last_net_time = now

    return {
        "interfaces": interfaces,
        "sent_mb": round(io_counters.bytes_sent / (1024 ** 2), 2),
        "recv_mb": round(io_counters.bytes_recv / (1024 ** 2), 2),
        "sent_rate_bps": round(sent_rate_bps, 1),
        "recv_rate_bps": round(recv_rate_bps, 1),
    }


def get_load_avg():
    """
    1/5/15-minute load averages. Not available on Windows, so this
    fails soft and returns None there.
    """

    try:
        one, five, fifteen = os.getloadavg()
    except (OSError, AttributeError):
        return None

    return {"1m": round(one, 2), "5m": round(five, 2), "15m": round(fifteen, 2)}


def get_process_count():

    return len(psutil.pids())


def get_uptime():

    seconds = int(time.time() - BOOT_TIME)

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    return {
        "seconds": seconds,
        "text": f"{days}d {hours}h {minutes}m {secs}s",
    }
