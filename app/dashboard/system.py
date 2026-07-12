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


def get_battery():

    battery = psutil.sensors_battery()

    if not battery:
        return None

    secsleft = battery.secsleft
    if secsleft in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN, None):
        secsleft = None

    return {
        "percent": battery.percent,
        "charging": battery.power_plugged,
        "secsleft": secsleft,
    }


def get_disk():

    usage = psutil.disk_usage("/")

    return {
        "percent": usage.percent,
        "used_gb": round(usage.used / (1024 ** 3), 2),
        "total_gb": round(usage.total / (1024 ** 3), 2),
    }


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
                interfaces[name] = addr.address

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
    minutes, _ = divmod(remainder, 60)

    return f"{days}d {hours}h {minutes}m"
