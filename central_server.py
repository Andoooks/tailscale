from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session, send_file
import time
import sqlite3
import os
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

app = Flask(__name__)
app.secret_key = "change_this_to_random_secret_key"

# =============================
# CONFIGURATION
# =============================

API_TOKEN = "rellatrix_noc_secure_2026"
DB = "monitoring.db"
OFFLINE_THRESHOLD = 15

users = {
    "jbabasa@rellatrix.com": "otm"
}
# Do you want to add more account?
# users["new@email.com"] = "password"

devices = {}
ping_requests = {}
ping_results = {}

# =============================
# DATABASE INIT
# =============================

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT,
            latency REAL,
            jitter REAL,
            packet_loss TEXT,
            download REAL,
            upload REAL
        )
    """)
    conn.commit()
    conn.close()

init_db()

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
<h2>Rellatrix Tailscale Monitoring</h2>
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
# DASHBOARD UI
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

function todayDate() {
    const d = new Date();
    return d.toISOString().split('T')[0];
}

async function fetchData() {
    const response = await fetch('/api/devices');
    const data = await response.json();

    for (const [name, device] of Object.entries(data)) {
        if (!deviceCards[name]) createDeviceCard(name);
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

        <p><b>Relay:</b> <span id="relay_${name}">-</span></p>
        <p><b>Latency:</b> <span id="latency_${name}">0</span> ms</p>
        <p><b>Jitter:</b> <span id="jitter_${name}">0</span></p>
        <p><b>Packet Loss:</b> <span id="packet_${name}">0%</span></p>
        <p><b>Download:</b> <span id="download_${name}">0</span> Mbps</p>
        <p><b>Upload:</b> <span id="upload_${name}">0</span> Mbps</p>
        <p><b>Last Seen:</b> <span id="last_${name}">-</span></p>

        <div class="button-group">
            <button class="ping-btn" onclick="runPing('${name}')">Run Ping</button>
            <button class="summary-btn" onclick="showDailyStatus('${name}')">Daily Status</button>
        </div>

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
                { label: 'Download Mbps', borderColor: '#22c55e', data: [] },
                { label: 'Upload Mbps', borderColor: '#3b82f6', data: [] }
            ]
        },
        options: { responsive: true, animation: false }
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
    document.getElementById("ping_" + name).innerText = "Running ping...";
    setTimeout(async () => {
        const res = await fetch('/api/get_ping/' + name);
        const data = await res.json();
        document.getElementById("ping_" + name).innerText = data.output;
    }, 8000);
}

async function showDailyStatus(device) {
    const date = todayDate();
    const res = await fetch('/api/daily_summary/' + date);
    const data = await res.json();

    let output = "Daily Status for " + device + " (" + date + ")\\n\\n";

    const filtered = data.filter(e => e.device === device);

    if (filtered.length === 0) {
        output += "No incidents recorded today.";
    } else {
        filtered.forEach(e => {
            output += e.time + " → " + e.event + "\\n";
        });
    }

    document.getElementById("modalContent").innerText = output;
    document.getElementById("modal").style.display = "flex";
}

function closeModal() {
    document.getElementById("modal").style.display = "none";
}

setInterval(fetchData, 2000);
window.onload = fetchData;

</script>

<style>
body { background:#0b1320; color:white; font-family:Arial; margin:0; }

.container {
    display:grid;
    grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
    gap:20px;
    padding:20px;
}

.card {
    background:#1f2937;
    padding:20px;
    border-radius:10px;
}

.badge {
    padding:5px 10px;
    border-radius:20px;
}

.green { background:#16a34a; }
.red { background:#dc2626; }
.gray { background:#6b7280; }

.button-group {
    margin-top:10px;
    display:flex;
    gap:10px;
}

.ping-btn {
    padding:8px 14px;
    background:#2563eb;
    border:none;
    color:white;
    border-radius:6px;
    cursor:pointer;
}

.summary-btn {
    padding:8px 14px;
    background:#9333ea;
    border:none;
    color:white;
    border-radius:6px;
    cursor:pointer;
}

.ping-output {
    background:#0f172a;
    padding:10px;
    margin-top:10px;
    height:120px;
    overflow:auto;
}

.modal {
    display:none;
    position:fixed;
    top:0;
    left:0;
    width:100%;
    height:100%;
    background:rgba(0,0,0,0.6);
    align-items:center;
    justify-content:center;
}

.modal-content {
    background:#1f2937;
    padding:20px;
    width:600px;
    max-height:80%;
    overflow:auto;
    border-radius:8px;
}

.close-btn {
    float:right;
    cursor:pointer;
    color:#ef4444;
}
</style>
</head>

<body>

<div class="container" id="deviceContainer"></div>

<div id="modal" class="modal">
    <div class="modal-content">
        <span class="close-btn" onclick="closeModal()">Close ✖</span>
        <pre id="modalContent"></pre>
    </div>
</div>

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

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        INSERT INTO logs (device, status, latency, jitter, packet_loss, download, upload)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        data["device"],
        data["status"],
        data["latency"],
        data["jitter"],
        data["packet_loss"],
        data["download_mbps"],
        data["upload_mbps"]
    ))
    conn.commit()
    conn.close()

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

@app.route("/api/daily_summary/<date>")
def daily_summary(date):
    if "user" not in session:
        return jsonify({"error":"unauthorized"}),403

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT device, timestamp, status, packet_loss, download FROM logs WHERE DATE(timestamp)=?", (date,))
    rows = c.fetchall()
    conn.close()

    events = []
    for device, ts, status, loss, download in rows:
        if status == "DERP":
            events.append({"time": ts, "device": device, "event": "DERP routing"})
        try:
            if float(loss.replace("%","")) > 5:
                events.append({"time": ts, "device": device, "event": "High packet loss"})
        except:
            pass
        if download is not None and download < 1:
            events.append({"time": ts, "device": device, "event": "Slow internet"})
    return jsonify(events)

@app.route("/report/<date>")
def generate_report(date):
    if "user" not in session:
        return jsonify({"error":"unauthorized"}),403

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT device, timestamp, status, packet_loss, download FROM logs WHERE DATE(timestamp)=?", (date,))
    rows = c.fetchall()
    conn.close()

    filename = f"report_{date}.pdf"
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph("Rellatrix Tailscale Monitoring Report", styles['Title']))
    story.append(Paragraph(f"Date: {date}", styles['Normal']))
    story.append(Spacer(1,20))

    for row in rows:
        story.append(Paragraph(str(row), styles['Normal']))

    doc = SimpleDocTemplate(filename)
    doc.build(story)

    return send_file(filename, as_attachment=True)

@app.route("/")
def dashboard():
    if "user" not in session:
        return redirect("/login")
    return render_template_string(DASHBOARD_PAGE)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)