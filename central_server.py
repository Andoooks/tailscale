from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session
import time

app = Flask(__name__)
app.secret_key = "change_this_to_random_secret_key"

# =============================
# USERS
# =============================

users = {
    "jbabasa@rellatrix.com": "otm"
}
# Do you want to add more account?
# users["new@email.com"] = "password"

# =============================
# SECURITY
# =============================

API_TOKEN = "rellatrix_noc_secure_2026"

# =============================
# STORAGE
# =============================

devices = {}
ping_requests = {}
ping_results = {}
OFFLINE_THRESHOLD = 15


# =============================
# LOGIN PAGE
# =============================

LOGIN_PAGE = """
<!DOCTYPE html>
<html>
<head>
<title>Login</title>
<style>
body { background:#0f172a; color:white; font-family:Arial; text-align:center; }
form { margin-top:120px; }
input { padding:10px; margin:10px; width:250px; border-radius:5px; border:none; }
button { padding:10px 20px; background:#2563eb; border:none; color:white; border-radius:5px; }
</style>
</head>
<body>
<h2>Tailscale NOC Login</h2>
<form method="POST">
<input type="email" name="email" placeholder="Email" required><br>
<input type="password" name="password" placeholder="Password" required><br>
<button type="submit">Login</button>
</form>
<p style="color:red;">{{error}}</p>
</body>
</html>
"""


# =============================
# DASHBOARD
# =============================

DASHBOARD_PAGE = """
<!DOCTYPE html>
<html>
<head>
<title>Rellatrix Tailscale Monitoring</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<script>
let charts = {};
let deviceCards = {};

async function fetchData() {
    const response = await fetch('/api/devices');
    const data = await response.json();

    for (const [name, device] of Object.entries(data)) {
        if (!deviceCards[name]) {
            createDeviceCard(name);
        }
        updateDeviceCard(name, device);
    }
}

function createDeviceCard(name) {
    const container = document.getElementById("deviceContainer");

    const card = document.createElement("div");
    card.className = "card";

    card.innerHTML = `
        <div class="card-header">
            <span class="device-name">${name}</span>
            <span id="badge_${name}" class="badge gray">UNKNOWN</span>
        </div>

        <div class="metrics">
            <p><b>Relay:</b> <span id="relay_${name}">-</span></p>
            <p><b>Latency:</b> <span id="latency_${name}">0</span> ms</p>
            <p><b>Jitter:</b> <span id="jitter_${name}">0</span></p>
            <p><b>Packet Loss:</b> <span id="packet_${name}">0%</span></p>
            <p><b>Download:</b> <span id="download_${name}">0</span> Mbps</p>
            <p><b>Upload:</b> <span id="upload_${name}">0</span> Mbps</p>
            <p><b>Last Seen:</b> <span id="last_${name}">-</span></p>
        </div>

        <button class="ping-btn" onclick="runPing('${name}')">
         Run Tailscale Ping
        </button>

        <pre id="ping_${name}" class="ping-output"></pre>

        <canvas id="chart_${name}" height="120"></canvas>
    `;

    container.appendChild(card);

    const ctx = document.getElementById("chart_" + name).getContext('2d');

    charts[name] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Download Mbps',
                    borderColor: '#22c55e',
                    data: [],
                    tension: 0.3
                },
                {
                    label: 'Upload Mbps',
                    borderColor: '#3b82f6',
                    data: [],
                    tension: 0.3
                }
            ]
        },
        options: {
            responsive: true,
            animation: false,
            scales: { y: { beginAtZero: true } }
        }
    });

    deviceCards[name] = true;
}

function updateDeviceCard(name, device) {
    document.getElementById("relay_" + name).innerText = device.relay;
    document.getElementById("latency_" + name).innerText = device.latency;
    document.getElementById("jitter_" + name).innerText = device.jitter;
    document.getElementById("packet_" + name).innerText = device.packet_loss;
    document.getElementById("download_" + name).innerText = device.download_mbps;
    document.getElementById("upload_" + name).innerText = device.upload_mbps;
    document.getElementById("last_" + name).innerText = device.last_seen;

    const badge = document.getElementById("badge_" + name);

    if (device.offline) {
        badge.className = "badge gray";
        badge.innerText = "OFFLINE";
    } else if (device.status === "DIRECT") {
        badge.className = "badge green";
        badge.innerText = "DIRECT";
    } else {
        badge.className = "badge red";
        badge.innerText = "DERP";
    }

    const chart = charts[name];

    if (chart.data.labels.length > 30) {
        chart.data.labels.shift();
        chart.data.datasets[0].data.shift();
        chart.data.datasets[1].data.shift();
    }

    chart.data.labels.push("");
    chart.data.datasets[0].data.push(device.download_mbps);
    chart.data.datasets[1].data.push(device.upload_mbps);

    chart.update();
}

async function runPing(name) {
    await fetch('/api/request_ping/' + name);
    document.getElementById("ping_" + name).innerText = "Running tailscale ping...";

    setTimeout(async () => {
        const res = await fetch('/api/get_ping/' + name);
        const data = await res.json();
        document.getElementById("ping_" + name).innerText = data.output;
    }, 8000);
}

setInterval(fetchData, 2000);
window.onload = fetchData;
</script>

<style>
body {
    background:#0b1320;
    color:white;
    font-family:Arial;
    margin:0;
}

.banner {
    background:linear-gradient(90deg,#111827,#1e293b);
    padding:20px;
    font-size:22px;
    font-weight:bold;
    text-align:center;
    border-bottom:1px solid #1f2937;
}

.container {
    display:grid;
    grid-template-columns: repeat(auto-fill, minmax(450px, 1fr));
    gap:25px;
    padding:25px;
}

.card {
    background:#1f2937;
    border-radius:12px;
    padding:20px;
    box-shadow:0 0 25px rgba(0,0,0,0.4);
}

.card-header {
    display:flex;
    justify-content:space-between;
    margin-bottom:15px;
}

.device-name {
    font-size:18px;
    font-weight:bold;
}

.badge {
    padding:6px 14px;
    border-radius:20px;
    font-size:12px;
    font-weight:bold;
}

.green { background:#16a34a; }
.red { background:#dc2626; }
.gray { background:#6b7280; }

.metrics p {
    margin:4px 0;
}

.ping-btn {
    margin-top:10px;
    padding:10px 18px;
    background:linear-gradient(90deg,#2563eb,#1d4ed8);
    border:none;
    color:white;
    font-weight:bold;
    border-radius:8px;
    cursor:pointer;
    transition:0.2s;
}

.ping-btn:hover {
    transform:translateY(-2px);
    box-shadow:0 4px 12px rgba(37,99,235,0.6);
}

.ping-output {
    background:#0f172a;
    padding:10px;
    margin-top:10px;
    height:130px;
    overflow:auto;
    border-radius:6px;
}
</style>
</head>

<body>
<div class="banner">
    Rellatrix Tailscale Monitoring
</div>

<div class="container" id="deviceContainer"></div>
</body>
</html>
"""

# =============================
# ROUTES
# =============================

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        if users.get(request.form["email"]) == request.form["password"]:
            session["user"] = request.form["email"]
            return redirect("/")
        error = "Invalid credentials"
    return render_template_string(LOGIN_PAGE, error=error)

@app.route("/api/update", methods=["POST"])
def update():
    if request.headers.get("Authorization") != API_TOKEN:
        return jsonify({"error": "unauthorized"}), 403

    data = request.json
    devices[data["device"]] = {
        **data,
        "last_seen": time.strftime("%H:%M:%S"),
        "timestamp": time.time()
    }
    return jsonify({"ok": True})

@app.route("/api/devices")
def get_devices():
    if "user" not in session:
        return jsonify({"error":"unauthorized"}),403
    now = time.time()
    return jsonify({
        name: {**data, "offline": (now - data["timestamp"]) > OFFLINE_THRESHOLD}
        for name, data in devices.items()
    })

@app.route("/api/request_ping/<device>")
def request_ping(device):
    if "user" not in session:
        return jsonify({"error":"unauthorized"}),403
    ping_requests["target"] = device
    return jsonify({"ok":True})

@app.route("/api/ping_request")
def ping_request():
    if request.headers.get("Authorization") != API_TOKEN:
        return jsonify({"error":"unauthorized"}),403
    target = ping_requests.get("target")
    ping_requests["target"] = None
    return jsonify({"ping": target})

@app.route("/api/ping_result", methods=["POST"])
def ping_result():
    if request.headers.get("Authorization") != API_TOKEN:
        return jsonify({"error":"unauthorized"}),403
    ping_results[request.json["device"]] = request.json["output"]
    return jsonify({"ok":True})

@app.route("/api/get_ping/<device>")
def get_ping(device):
    if "user" not in session:
        return jsonify({"error":"unauthorized"}),403
    return jsonify({"output": ping_results.get(device, "Waiting...")})

@app.route("/")
def dashboard():
    if "user" not in session:
        return redirect("/login")
    return render_template_string(DASHBOARD_PAGE)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)