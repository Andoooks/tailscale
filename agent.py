import subprocess
import json
import requests
import time
import statistics
import re
import platform
from collections import deque

# ==============================
# CONFIGURATION
# ==============================

CENTRAL_SERVER = "http://127.0.0.1:5000/api/update"  # <-- CHANGE to your central Tailscale IP
API_TOKEN = "rellatrix_monitoring_tailscale"
DEVICE_NAME = platform.node()
OPS_HUB_IP = "100.76.204.94"

# ==============================
# OS DETECTION
# ==============================

SYSTEM = platform.system()

if SYSTEM == "Darwin":
    TAILSCALE = "/Applications/Tailscale.app/Contents/MacOS/tailscale"
elif SYSTEM == "Windows":
    TAILSCALE = r"C:\Program Files\Tailscale\tailscale.exe"
else:
    TAILSCALE = "tailscale"

latencies = deque(maxlen=10)

# ==============================
# GET ACTIVE INTERFACE (Mac)
# ==============================

def get_active_interface():
    if SYSTEM == "Darwin":
        result = subprocess.run(["route", "get", "default"], capture_output=True, text=True)
        match = re.search(r"interface: (\w+)", result.stdout)
        if match:
            return match.group(1)
        return "en0"
    return None

# ==============================
# GET NETWORK BYTES
# ==============================

def get_interface_bytes(interface=None):
    try:
        if SYSTEM == "Darwin":
            result = subprocess.run(["netstat", "-ib"], capture_output=True, text=True)
            lines = result.stdout.splitlines()
            for line in lines:
                if interface in line:
                    parts = line.split()
                    if len(parts) > 10:
                        ibytes = int(parts[6])
                        obytes = int(parts[9])
                        return ibytes, obytes

        elif SYSTEM == "Windows":
            result = subprocess.run(["netstat", "-e"], capture_output=True, text=True)
            match = re.findall(r"\d+", result.stdout)
            if len(match) >= 2:
                return int(match[0]), int(match[1])

    except:
        pass

    return 0, 0

# ==============================
# TAILSCALE STATUS
# ==============================

def get_status():
    try:
        result = subprocess.run(
            [TAILSCALE, "status", "--json"],
            capture_output=True, text=True
        )
        data = json.loads(result.stdout)
        self_data = data.get("Self", {})

        relay = self_data.get("Relay")
        magic = self_data.get("InMagicSock")

        if magic and not relay:
            return "DIRECT", "-"
        return "DERP", relay
    except:
        return "UNKNOWN", "-"

# ==============================
# LATENCY
# ==============================

def get_latency():
    try:
        if SYSTEM == "Windows":
            result = subprocess.run(
                ["ping", "-n", "1", OPS_HUB_IP],
                capture_output=True, text=True
            )
        else:
            result = subprocess.run(
                ["ping", "-c", "1", OPS_HUB_IP],
                capture_output=True, text=True
            )

        match = re.search(r"time[=<]\s*(\d+\.?\d*)", result.stdout)
        if match:
            return float(match.group(1))
    except:
        pass
    return None

# ==============================
# MAIN LOOP
# ==============================

interface = get_active_interface()
old_in, old_out = get_interface_bytes(interface)

while True:
    time.sleep(2)

    if SYSTEM == "Darwin":
        interface = get_active_interface()

    new_in, new_out = get_interface_bytes(interface)

    download_mbps = ((new_in - old_in) * 8) / (2 * 1_000_000)
    upload_mbps = ((new_out - old_out) * 8) / (2 * 1_000_000)

    old_in, old_out = new_in, new_out

    status, relay = get_status()

    latency = get_latency()
    if latency:
        latencies.append(latency)

    avg = round(statistics.mean(latencies), 2) if latencies else 0
    jitter = round(statistics.stdev(latencies), 2) if len(latencies) > 1 else 0

    payload = {
        "device": DEVICE_NAME,
        "status": status,
        "relay": relay,
        "latency": avg,
        "jitter": jitter,
        "packet_loss": "0%",
        "download_mbps": round(download_mbps, 2),
        "upload_mbps": round(upload_mbps, 2)
    }

    try:
        requests.post(
            CENTRAL_SERVER,
            json=payload,
            headers={"Authorization": API_TOKEN},
            timeout=3
        )
    except:
        pass