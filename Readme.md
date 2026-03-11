Need to install
pip3 install --user requests
pip3 install --user flask requests


git clone <your_repo>
cd <file>
pip3 install --user -r requirements.txt
python3 central_server.py
or
python central_server.py



The script is currently monitoring the Tailscale Tunnel performance, specifically the path between your laptop and the Tailscale entry point.


What the Monitoring System is Doing:

- Real-Time Monitoring: Every 2 seconds, the dashboard polls the backend to see if the device has checked in. If a device hasn't sent data within 15 seconds, it is flagged as OFFLINE.

- Path Diagnostics (Direct vs. DERP): It identifies how your data is traveling.

      1. Direct: A peer-to-peer connection (High speed, low latency).

      2. DERP: A relayed connection via Tailscale servers (Low speed, higher latency).

- Tunnel Throughput Tracking: It measures the current capacity of the Tailscale interface.

- Latency & Jitter Analysis: * Latency: The "lag" or time it takes for a packet to travel.


- Automated Remote Ping: When you click the "Ping Device" button, the server triggers a system-level command to test the path specifically to that internal Tailscale IP.
