import psutil


def get_system_stats():

    return {
        "cpu": psutil.cpu_percent(),
        "ram": psutil.virtual_memory().percent,
        "battery": get_battery()
    }


def get_battery():

    battery = psutil.sensors_battery()

    if battery:
        return battery.percent

    return None
