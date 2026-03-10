from flask import Flask, request, jsonify, render_template_string, redirect, session
import time
import sqlite3
import datetime
import subprocess  # Added for the ping command

app = Flask(__name__)
app.secret_key = "change_this_secret_key"

# ================= CONFIG =================
API_TOKEN = "rellatrix_noc_secure_2026"
DB = "monitoring.db"
OFFLINE_THRESHOLD = 15

users = {
    "jbabasa@rellatrix.com": "otm"
}

devices = {}

# ================= DATABASE =================
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device TEXT,
            timestamp DATETIME,
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

# ================= LOGIN =================
LOGIN_PAGE = """
<!DOCTYPE html>
<html>
<head>
<title>Login</title>
<style>
body { background:#0f172a; color:white; font-family:Arial; text-align:center; }
form { margin-top:120px; }
input { padding:10px; margin:10px; width:250px; border-radius:5px; border:none; }
button { padding:10px 20px; background:#2563eb; border:none; color:white; border-radius:5px; cursor:pointer; }
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

# ================= DASHBOARD =================
DASHBOARD_PAGE = """
<!DOCTYPE html>
<html>
<head>
<title>Rellatrix Tailscale Monitoring</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<script>
let charts = {};
let deviceCards = {};
let currentActiveDevice = ""; 

function todayDate() {
    const d = new Date();
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
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
            <button class="status-btn" onclick="statusNow('${name}')">Status Now</button>
            <button class="ping-btn" onclick="pingDevice('${name}')">Ping Device</button>
            <button class="summary-btn" onclick="showToday('${name}')">History</button>
        </div>

        <div class="range-section">
            <input type="date" id="start_${name}">
            <input type="date" id="end_${name}">
            <button class="range-btn" onclick="showRange('${name}')">View Range</button>
        </div>
        <canvas id="chart_${name}" height="120" style="margin-top:15px;"></canvas>
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

async function pingDevice(name) {
    const btn = event.target;
    const originalText = btn.innerText;
    btn.innerText = "Pinging...";
    btn.disabled = True;
    
    try {
        const res = await fetch('/api/ping/' + name, { method: 'POST' });
        const data = await res.json();
        alert(data.output);
    } catch (e) {
        alert("Ping failed to execute.");
    } finally {
        btn.innerText = originalText;
        btn.disabled = false;
    }
}

async function statusNow(name) {
    const res = await fetch('/api/status_now/' + name, { method: 'POST' });
    const data = await res.json();
    if(data.ok) {
        if (document.getElementById("modal").style.display === "flex" && currentActiveDevice === name) {
            refreshModal();
        } else {
            showToday(name);
        }
    }
}

async function showToday(device) {
    currentActiveDevice = device;
    const date = todayDate();
    const res = await fetch(`/api/daily_summary/${date}?device=${device}`);
    const data = await res.json();
    showModal(device, date, date, data);
}

async function refreshModal() {
    if (!currentActiveDevice) return;
    const date = todayDate();
    const res = await fetch(`/api/daily_summary/${date}?device=${currentActiveDevice}`);
    const data = await res.json();
    renderModalData(currentActiveDevice, date, date, data);
}

async function showRange(device) {
    currentActiveDevice = device;
    const start = document.getElementById("start_" + device).value;
    const end = document.getElementById("end_" + device).value;
    if (!start || !end) { alert("Select both dates."); return; }

    const res = await fetch(`/api/range_summary?device=${device}&start=${start}&end=${end}`);
    const data = await res.json();
    showModal(device, start, end, data);
}

function showModal(device, start, end, data) {
    renderModalData(device, start, end, data);
    document.getElementById("modal").style.display = "flex";
}

function renderModalData(device, start, end, data) {
    let output = `History for ${device}\\nFrom ${start} to ${end}\\n\\n`;
    if (data.length === 0) {
        output += "No status records found.";
    } else {
        data.forEach(e => {
            output += e.time + " → " + e.event + "\\n";
        });
    }
    const pre = document.getElementById("modalContent");
    pre.innerText = output;
    pre.scrollTop = pre.scrollHeight;
}

function closeModal() {
    document.getElementById("modal").style.display = "none";
    currentActiveDevice = "";
}

setInterval(fetchData, 2000);
window.onload = fetchData;
</script>

<style>
body { background:#0b1320; color:white; font-family:Arial; margin:0; }
.container { display:grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap:20px; padding:20px; }
.card { background:#1f2937; padding:20px; border-radius:10px; border: 1px solid #374151; }
.badge { padding:5px 10px; border-radius:20px; font-size:12px; font-weight: bold; }
.green { background:#16a34a; }
.red { background:#dc2626; }
.gray { background:#6b7280; }
.button-group { display:flex; flex-wrap: wrap; gap:10px; margin-top:10px; }
.range-section { margin-top:10px; display:flex; gap:6px; }
.range-section input { background:#0f172a; color:white; border:1px solid #374151; padding:5px; border-radius:5px; }

.status-btn { padding:6px 12px; background:#2563eb; border:none; color:white; border-radius:6px; cursor:pointer; font-weight:bold; }
.ping-btn { padding:6px 12px; background:#0d9488; border:none; color:white; border-radius:6px; cursor:pointer; font-weight:bold; }
.summary-btn { padding:6px 12px; background:#9333ea; border:none; color:white; border-radius:6px; cursor:pointer; font-weight:bold; }
.range-btn { padding:6px 12px; background:#f59e0b; border:none; color:white; border-radius:6px; cursor:pointer; font-weight:bold; }

.modal { display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.85); align-items:center; justify-content:center; z-index:100; }
.modal-content { background:#1f2937; padding:20px; width:700px; height:85vh; border-radius:10px; border: 1px solid #4b5563; display:flex; flex-direction: column; }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
.modal-title { font-size: 18px; font-weight: bold; }
.modal-actions { display: flex; gap: 15px; align-items: center; }
.refresh-link { color: #60a5fa; cursor: pointer; text-decoration: underline; font-size: 14px; }
.close-btn { cursor:pointer; color:#ef4444; font-size: 20px; font-weight:bold; }

pre { background:#0f172a; padding:15px; border-radius:5px; flex-grow: 1; overflow-y: auto; white-space: pre-wrap; font-family: 'Courier New', monospace; font-size: 14px; border: 1px solid #1e293b; }
</style>
</head>

<body>
<div class="container" id="deviceContainer"></div>
<div id="modal" class="modal">
    <div class="modal-content">
        <div class="modal-header">
            <span class="modal-title">Live History Log</span>
            <div class="modal-actions">
                <span class="refresh-link" onclick="refreshModal()">↻ Refresh Data</span>
                <span class="close-btn" onclick="closeModal()">Close ✖</span>
            </div>
        </div>
        <pre id="modalContent"></pre>
    </div>
</div>
</body>
</html>
"""

# ================= ROUTES =================

@app.route("/login", methods=["GET","POST"])
def login():
    error=""
    if request.method=="POST":
        if users.get(request.form["email"])==request.form["password"]:
            session["user"]=request.form["email"]
            return redirect("/")
        error="Invalid credentials"
    return render_template_string(LOGIN_PAGE,error=error)

@app.route("/api/update", methods=["POST"])
def update():
    if request.headers.get("Authorization")!=API_TOKEN:
        return jsonify({"error":"unauthorized"}),403
    data=request.json
    local_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    devices[data["device"]] = {**data, "last_seen": time.strftime("%H:%M:%S"), "timestamp": time.time()}
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("INSERT INTO logs (device,timestamp,status,latency,jitter,packet_loss,download,upload) VALUES (?,?,?,?,?,?,?,?)",
              (data["device"], local_ts, data["status"], data["latency"], data["jitter"], data["packet_loss"], data["download_mbps"], data["upload_mbps"]))
    conn.commit(); conn.close()
    return jsonify({"ok":True})

# --- NEW PING ROUTE ---
@app.route("/api/ping/<device_name>", methods=["POST"])
def ping_device(device_name):
    if "user" not in session: return jsonify({"error":"unauthorized"}),403
    # Note: Hardcoded IP as per your requirement
    cmd = ["/Applications/Tailscale.app/Contents/MacOS/tailscale", "ping", "-c", "10", "100.76.204.94"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return jsonify({"output": result.stdout if result.stdout else result.stderr})
    except Exception as e:
        return jsonify({"output": f"Error: {str(e)}"}), 500

@app.route("/api/status_now/<device_name>", methods=["POST"])
def status_now(device_name):
    if "user" not in session: return jsonify({"error":"unauthorized"}),403
    device = devices.get(device_name)
    if not device: return jsonify({"error": "Device not found"}), 404
    local_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB); c = conn.cursor()
    c.execute("INSERT INTO logs (device, timestamp, status, latency, jitter, packet_loss, download, upload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (device_name, local_ts, device["status"], device["latency"], device["jitter"], device["packet_loss"], device["download_mbps"], device["upload_mbps"]))
    conn.commit(); conn.close()
    return jsonify({"ok": True})

@app.route("/api/devices")
def get_devices():
    if "user" not in session: return jsonify({"error":"unauthorized"}),403
    now=time.time()
    return jsonify({name:{**data,"offline":(now-data["timestamp"])>OFFLINE_THRESHOLD} for name,data in devices.items()})

# --- UPDATED LOGIC FOR SPEEDS ---
@app.route("/api/daily_summary/<date>")
def daily_summary(date):
    if "user" not in session: return jsonify({"error":"unauthorized"}),403
    device_name = request.args.get("device")
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT timestamp, status, download, upload FROM logs WHERE DATE(timestamp) = ? AND device = ? ORDER BY timestamp ASC", (date, device_name))
    rows=c.fetchall(); conn.close()
    events=[]
    for ts, status, dl, ul in rows:
        events.append({"time": ts, "event": f"{status} routing"})
        events.append({"time": ts, "event": f"Speed: DL {dl} Mbps / UL {ul} Mbps"})
    return jsonify(events)

@app.route("/api/range_summary")
def range_summary():
    if "user" not in session: return jsonify({"error":"unauthorized"}),403
    device=request.args.get("device"); start=request.args.get("start"); end=request.args.get("end")
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT timestamp, status, download, upload FROM logs WHERE device=? AND DATE(timestamp) BETWEEN ? AND ? ORDER BY timestamp ASC",(device,start,end))
    rows=c.fetchall(); conn.close()
    events=[]
    for ts, status, dl, ul in rows:
        events.append({"time": ts, "event": f"{status} routing"})
        events.append({"time": ts, "event": f"Speed: DL {dl} Mbps / UL {ul} Mbps"})
    return jsonify(events)

@app.route("/")
def dashboard():
    if "user" not in session: return redirect("/login")
    return render_template_string(DASHBOARD_PAGE)

if __name__=="__main__":
    app.run(host="127.0.0.1", port=5000)