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

SYSTEM = platform.system()

if SYSTEM == "Darwin":
    TAILSCALE = "/Applications/Tailscale.app/Contents/MacOS/tailscale"
elif SYSTEM == "Windows":
    TAILSCALE = r"C:\Program Files\Tailscale\tailscale.exe"
else:
    TAILSCALE = "tailscale"

latencies = deque(maxlen=10)

# ==============================
# NETWORK BYTES
# ==============================

def get_interface_bytes():
    try:
        if SYSTEM == "Windows":
            result = subprocess.run(["netstat", "-e"], capture_output=True, text=True)
            match = re.findall(r"\d+", result.stdout)
            if len(match) >= 2:
                return int(match[0]), int(match[1])
        else:
            result = subprocess.run(["netstat", "-ib"], capture_output=True, text=True)
            lines = result.stdout.splitlines()
            for line in lines:
                if "en0" in line or "en1" in line:
                    parts = line.split()
                    if len(parts) > 10:
                        return int(parts[6]), int(parts[9])
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
# LATENCY + PACKET LOSS
# ==============================

def get_ping_stats():
    try:
        if SYSTEM == "Windows":
            result = subprocess.run(
                ["ping", "-n", "5", OPS_HUB_IP],
                capture_output=True, text=True
            )
            loss_match = re.search(r"Lost = (\d+)", result.stdout)
            sent_match = re.search(r"Sent = (\d+)", result.stdout)
        else:
            result = subprocess.run(
                ["ping", "-c", "5", OPS_HUB_IP],
                capture_output=True, text=True
            )
            loss_match = re.search(r"(\d+)% packet loss", result.stdout)
            sent_match = None

        # Packet Loss
        if SYSTEM == "Windows" and loss_match and sent_match:
            lost = int(loss_match.group(1))
            sent = int(sent_match.group(1))
            packet_loss = round((lost / sent) * 100, 2)
        elif loss_match:
            packet_loss = float(loss_match.group(1))
        else:
            packet_loss = 0

        # Latency
        times = re.findall(r"time[=<]\s*(\d+\.?\d*)", result.stdout)
        latencies_local = [float(t) for t in times]

        if latencies_local:
            avg_latency = round(statistics.mean(latencies_local), 2)
            jitter = round(statistics.stdev(latencies_local), 2) if len(latencies_local) > 1 else 0
        else:
            avg_latency = 0
            jitter = 0

        return avg_latency, jitter, packet_loss

    except:
        return 0, 0, 0

# ==============================
# MAIN LOOP
# ==============================

old_in, old_out = get_interface_bytes()

while True:
    time.sleep(2)

    new_in, new_out = get_interface_bytes()

    download_mbps = ((new_in - old_in) * 8) / (2 * 1_000_000)
    upload_mbps = ((new_out - old_out) * 8) / (2 * 1_000_000)

    old_in, old_out = new_in, new_out

    status, relay = get_status()
    latency, jitter, packet_loss = get_ping_stats()

    payload = {
        "device": DEVICE_NAME,
        "status": status,
        "relay": relay,
        "latency": latency,
        "jitter": jitter,
        "packet_loss": f"{packet_loss}%",
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