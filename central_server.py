from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session
import time

app = Flask(__name__)
app.secret_key = "change_this_to_random_secret_key"

# ==================================================
# 🔐 USER ACCOUNTS
# ==================================================

users = {
    "jbabasa@rellatrix.com": "otm"
}

# Do you want to add more account?
# Example:
# users["newemail@example.com"] = "newpassword"

# ==================================================
# 🔐 AGENT API TOKEN
# ==================================================

API_TOKEN = "rellatrix_monitoring_tailscale"

# ==================================================
# DEVICE STORAGE
# ==================================================

devices = {}
OFFLINE_THRESHOLD = 15  # seconds before marking device offline

# ==================================================
# LOGIN PAGE
# ==================================================

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

# ==================================================
# DASHBOARD PAGE (Cisco-style + Live Graphs)
# ==================================================

DASHBOARD_PAGE = """
<!DOCTYPE html>
<html>
<head>
<title>Tailscale NOC Dashboard</title>
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
    card.id = "card_" + name;

    card.innerHTML = `
        <div class="card-header">
            <span>${name}</span>
            <span id="badge_${name}" class="badge gray">UNKNOWN</span>
        </div>

        <p><b>Relay:</b> <span id="relay_${name}">-</span></p>
        <p><b>Latency:</b> <span id="latency_${name}">0</span> ms</p>
        <p><b>Jitter:</b> <span id="jitter_${name}">0</span></p>
        <p><b>Download:</b> <span id="download_${name}">0</span> Mbps</p>
        <p><b>Upload:</b> <span id="upload_${name}">0</span> Mbps</p>
        <p><b>Last Seen:</b> <span id="last_${name}">-</span></p>

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
            scales: {
                y: { beginAtZero: true }
            }
        }
    });

    deviceCards[name] = true;
}

function updateDeviceCard(name, device) {

    document.getElementById("relay_" + name).innerText = device.relay;
    document.getElementById("latency_" + name).innerText = device.latency;
    document.getElementById("jitter_" + name).innerText = device.jitter;
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

setInterval(fetchData, 2000);
window.onload = fetchData;
</script>

<style>
body { background:#0f172a; color:white; font-family:Arial; margin:0; }

.header {
    padding:20px;
    background:#111827;
    font-size:20px;
}

.container {
    display:grid;
    grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
    gap:20px;
    padding:20px;
}

.card {
    background:#1f2937;
    border-radius:10px;
    padding:15px;
    box-shadow:0 0 15px rgba(0,0,0,0.4);
}

.card-header {
    display:flex;
    justify-content:space-between;
    font-size:18px;
    margin-bottom:10px;
}

.badge {
    padding:5px 12px;
    border-radius:20px;
    font-size:12px;
}

.green { background:#16a34a; }
.red { background:#dc2626; }
.gray { background:#6b7280; }
</style>
</head>

<body>
<div class="header">
Tailscale Network Operations Center
</div>

<div class="container" id="deviceContainer"></div>

</body>
</html>
"""

# ==================================================
# AUTH ROUTES
# ==================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        if email in users and users[email] == password:
            session["user"] = email
            return redirect(url_for("dashboard"))
        else:
            error = "Invalid credentials"

    return render_template_string(LOGIN_PAGE, error=error)


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

# ==================================================
# AGENT UPDATE API
# ==================================================

@app.route("/api/update", methods=["POST"])
def update():
    token = request.headers.get("Authorization")
    if token != API_TOKEN:
        return jsonify({"error": "unauthorized"}), 403

    data = request.json
    name = data.get("device")

    devices[name] = {
        "status": data.get("status"),
        "relay": data.get("relay"),
        "latency": data.get("latency"),
        "jitter": data.get("jitter"),
        "packet_loss": data.get("packet_loss"),
        "download_mbps": data.get("download_mbps", 0),
        "upload_mbps": data.get("upload_mbps", 0),
        "last_seen": time.strftime("%H:%M:%S"),
        "timestamp": time.time()
    }

    return jsonify({"ok": True})

# ==================================================
# DEVICE DATA API
# ==================================================

@app.route("/api/devices")
def get_devices():
    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 403

    current_time = time.time()
    output = {}

    for name, data in devices.items():
        offline = (current_time - data["timestamp"]) > OFFLINE_THRESHOLD
        output[name] = {
            **data,
            "offline": offline
        }

    return jsonify(output)

# ==================================================
# DASHBOARD
# ==================================================

@app.route("/")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template_string(DASHBOARD_PAGE)

# ==================================================
# RUN SERVER
# ==================================================

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)