import subprocess
import json
import requests
import time
import statistics
import re
import platform
import threading

CENTRAL_SERVER = "http://127.0.0.1:5000/api/update"
API_TOKEN = "rellatrix_noc_secure_2026"
DEVICE_NAME = platform.node()
OPS_HUB_IP = "100.76.204.94"

SYSTEM = platform.system()

if SYSTEM == "Darwin":
    TAILSCALE = "/Applications/Tailscale.app/Contents/MacOS/tailscale"
elif SYSTEM == "Windows":
    TAILSCALE = r"C:\Program Files\Tailscale\tailscale.exe"
else:
    TAILSCALE = "tailscale"

def get_bytes():
    try:
        if SYSTEM == "Windows":
            r = subprocess.run(["netstat","-e"],capture_output=True,text=True)
            nums = re.findall(r"\d+",r.stdout)
            return int(nums[0]), int(nums[1])
        else:
            r = subprocess.run(["netstat","-ib"],capture_output=True,text=True)
            for line in r.stdout.splitlines():
                if "en0" in line or "en1" in line:
                    p=line.split()
                    return int(p[6]), int(p[9])
    except:
        pass
    return 0,0

def get_status():
    try:
        r=subprocess.run([TAILSCALE,"status","--json"],capture_output=True,text=True)
        d=json.loads(r.stdout)
        self_data=d.get("Self",{})
        if self_data.get("InMagicSock") and not self_data.get("Relay"):
            return "DIRECT","-"
        return "DERP",self_data.get("Relay")
    except:
        return "UNKNOWN","-"

def ping_stats():
    try:
        r=subprocess.run(["ping","-c","5",OPS_HUB_IP],capture_output=True,text=True)
        loss=re.search(r"(\d+)% packet loss",r.stdout)
        times=re.findall(r"time[=<]\s*(\d+\.?\d*)",r.stdout)
        lat=[float(t) for t in times]
        return round(statistics.mean(lat),2) if lat else 0,\
               round(statistics.stdev(lat),2) if len(lat)>1 else 0,\
               loss.group(1)+"%" if loss else "0%"
    except:
        return 0,0,"0%"

def run_tailscale_ping():
    try:
        r=subprocess.run([TAILSCALE,"ping","-c","50",OPS_HUB_IP],
                         capture_output=True,text=True,timeout=60)
        return r.stdout
    except Exception as e:
        return str(e)

def listen_ping():
    while True:
        try:
            r=requests.get(CENTRAL_SERVER.replace("/update","/ping_request"),
                           headers={"Authorization":API_TOKEN})
            if r.json().get("ping")==DEVICE_NAME:
                out=run_tailscale_ping()
                requests.post(CENTRAL_SERVER.replace("/update","/ping_result"),
                              json={"device":DEVICE_NAME,"output":out},
                              headers={"Authorization":API_TOKEN})
        except:
            pass
        time.sleep(5)

threading.Thread(target=listen_ping,daemon=True).start()

old_in,old_out=get_bytes()

while True:
    time.sleep(2)
    new_in,new_out=get_bytes()

    download=((new_in-old_in)*8)/(2*1_000_000)
    upload=((new_out-old_out)*8)/(2*1_000_000)
    old_in,old_out=new_in,new_out

    status,relay=get_status()
    latency,jitter,packet_loss=ping_stats()

    payload={
        "device":DEVICE_NAME,
        "status":status,
        "relay":relay,
        "latency":latency,
        "jitter":jitter,
        "packet_loss":packet_loss,
        "download_mbps":round(download,2),
        "upload_mbps":round(upload,2)
    }

    try:
        requests.post(CENTRAL_SERVER,json=payload,
                      headers={"Authorization":API_TOKEN})
    except:
        pass