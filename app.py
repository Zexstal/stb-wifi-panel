from flask import Flask, request, redirect, render_template_string
import subprocess

app = Flask(__name__)

def run_cmd(*a):
    try:
        r = subprocess.run(a, capture_output=True, text=True, timeout=15)
        return r.stdout.strip() + r.stderr.strip()
    except Exception as e:
        return str(e)

def get_status():
    dev = run_cmd("nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status")
    act = run_cmd("nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active")
    state, ssid = "disconnected", None
    for l in dev.splitlines():
        if l.startswith("wlan0:wifi:"):
            state = l.split(":")[2]
    for l in act.splitlines():
        if l.endswith(":wlan0"):
            ssid = l.split(":")[0]
            break
    radio = run_cmd("nmcli", "radio", "wifi").strip() == "enabled"
    hs_active, hs_ssid = False, None
    for l in act.splitlines():
        parts = l.split(":")
        if len(parts) >= 3 and parts[2] == "wlan0" and "hotspot" in parts[0].lower():
            hs_active, hs_ssid, state = True, (run_cmd("nmcli", "-t", "-f", "802-11-wireless.ssid", "connection", "show", parts[0]) or parts[0]), "hotspot"
            break
    return state, ssid, radio, hs_active, hs_ssid

def get_networks(wifi_on, hs_active):
    if not wifi_on or hs_active:
        return []
    run_cmd("nmcli", "device", "wifi", "rescan", "ifname", "wlan0")
    out = run_cmd("nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list", "ifname", "wlan0")
    nets = []
    for l in out.splitlines():
        p = l.split(":")
        if len(p) >= 3 and p[0]:
            nets.append({"ssid": p[0], "sig": int(p[1]) if p[1].isdigit() else 0, "sec": p[2]})
    nets.sort(key=lambda x: x["sig"], reverse=True)
    return nets

def get_known():
    out = run_cmd("nmcli", "-t", "-f", "NAME,TYPE,UUID", "connection", "show")
    known = []
    for line in out.splitlines():
        # NAME may contain ':', so split from right: TYPE and UUID have no ':'
        # format is NAME:TYPE:UUID — rsplit max 2
        if line.count(":") < 2:
            continue
        name, conn_type, uuid = line.rsplit(":", 2)
        name, conn_type, uuid = name.strip(), conn_type.strip(), uuid.strip()
        if conn_type != "802-11-wireless":
            continue
        if name == "Hotspot" or name.startswith("STB-Hotspot"):
            continue
        if not name:
            continue
        autoconnect = run_cmd("nmcli", "-g", "connection.autoconnect", "connection", "show", uuid).strip()
        ts = run_cmd("nmcli", "-g", "connection.timestamp", "connection", "show", uuid).strip()
        try:
            ts_int = int(ts) if ts else 0
        except ValueError:
            ts_int = 0
        known.append({"ssid": name, "uuid": uuid, "autoconnect": autoconnect == "yes", "last_used": ts, "last_used_int": ts_int})
    known.sort(key=lambda x: x["last_used_int"], reverse=True)
    return known

def format_ts(ts_str):
    try:
        ts = int(ts_str)
        if ts == 0:
            return "never"
    except (ValueError, TypeError):
        return "-"
    from datetime import datetime
    delta = datetime.now() - datetime.fromtimestamp(ts)
    if delta.days > 30:
        return f"{delta.days // 30}bln lalu"
    if delta.days > 0:
        return f"{delta.days}hr lalu"
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours}jam lalu"
    mins = (delta.seconds // 60) % 60
    return f"{mins}mnt lalu" if mins > 0 else "baru saja"

HTML = r"""
<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>STB WiFi Panel</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background: #f0f2f5; min-height: 100vh; }
.header { background: linear-gradient(135deg, #1976d2, #1565c0); color: white; padding: 24px 20px; text-align: center; }
.header h1 { font-size: 1.4em; font-weight: 700; }
.container { max-width: 900px; margin: -12px auto 0; padding: 0 12px 30px; }
.status-card { background: white; border-radius: 12px; padding: 16px 20px; margin-bottom: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.status-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
.status-dot.on { background: #4caf50; box-shadow: 0 0 6px #4caf50; }
.status-dot.off { background: #f44336; box-shadow: 0 0 6px #f44336; }
.status-dot.ap { background: #ff9800; box-shadow: 0 0 6px #ff9800; }
.status-text { flex: 1; min-width: 90px; }
.status-label { font-size: 0.8em; color: #888; }
.status-value { font-weight: 600; font-size: 0.95em; }
.status-value.ok { color: #4caf50; }
.status-value.err { color: #f44336; }
.status-value.ap { color: #ff9800; }
.ip-text { font-size: 0.85em; color: #666; }
.ctrl-card { background: white; border-radius: 12px; padding: 14px 16px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
.ctrl-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; justify-content: space-between; }
.ctrl-group { display: flex; align-items: center; gap: 10px; }
.ctrl-label { font-size: 0.88em; font-weight: 600; color: #333; }
.switch { position: relative; display: inline-block; width: 44px; height: 24px; flex-shrink: 0; }
.switch input { opacity: 0; width: 0; height: 0; }
.slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background: #ccc; border-radius: 12px; transition: .2s; }
.slider:before { content: ""; position: absolute; height: 18px; width: 18px; left: 3px; bottom: 3px; background: white; border-radius: 50%; transition: .2s; box-shadow: 0 1px 3px rgba(0,0,0,0.3); }
input:checked + .slider { background: #4caf50; }
input:checked + .slider:before { transform: translateX(20px); }
.hs-panel { margin-top: 12px; padding-top: 12px; border-top: 1px solid #f0f0f0; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.hs-badge { background: #fff3e0; color: #ef6c00; padding: 4px 10px; border-radius: 20px; font-size: 0.82em; font-weight: 700; }
.hs-form { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; flex: 1; }
.hs-form input { padding: 8px 10px; border: 1.5px solid #e0e0e0; border-radius: 8px; font-size: 0.82em; outline: none; }
.hs-form input:focus { border-color: #1976d2; box-shadow: 0 0 0 3px rgba(25,118,210,0.12); }
.btn-hs { background: linear-gradient(135deg, #ff9800, #ef6c00); color: white; border: none; padding: 8px 14px; border-radius: 8px; cursor: pointer; font-size: 0.82em; font-weight: 700; white-space: nowrap; }
.btn-hs:hover { transform: translateY(-1px); }
.btn-hs-stop { background: #ef5350; }
.btn-hs:disabled { opacity: 0.5; cursor: not-allowed; }
.hint { font-size: 0.75em; color: #999; }
.net-card { background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); overflow-x: auto; }
.net-card-inner { min-width: 640px; }
.net-head { display: grid; grid-template-columns: 1fr 80px 90px 300px; align-items: center; padding: 10px 16px; background: #e3f2fd; border-bottom: 2px solid #bbdefb; font-size: 0.75em; font-weight: 700; color: #1565c0; text-transform: uppercase; letter-spacing: 0.5px; }
.net-head .c-name { min-width: 120px; }
.net-head .c-sig { text-align: center; }
.net-head .c-sec { text-align: center; }
.net-head .c-act { text-align: center; }
.net-row { display: grid; grid-template-columns: 1fr 80px 90px 300px; align-items: center; padding: 10px 16px; border-bottom: 1px solid #f0f0f0; gap: 8px; }
.net-row:last-child { border-bottom: none; }
.net-row:hover { background: #fafafa; }
.net-name { font-weight: 500; font-size: 0.88em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.net-sig { display: flex; align-items: center; justify-content: center; gap: 3px; }
.sig-bar { display: inline-block; width: 5px; border-radius: 2px; background: #e0e0e0; }
.sig-pct { font-size: 0.75em; color: #666; margin-left: 4px; font-weight: 500; }
.net-sec { text-align: center; font-size: 0.68em; color: #fff; }
.net-sec span { background: #78909c; padding: 2px 6px; border-radius: 4px; white-space: nowrap; }
.net-sec span.open { background: #4caf50; }
.net-act { display: flex; gap: 6px; align-items: center; }
.pw-wrap { flex: 1; min-width: 0; display: flex; align-items: center; background: #f8f9fa; border: 1.5px solid #e0e0e0; border-radius: 8px; padding: 0 8px; gap: 6px; transition: all 0.2s; }
.pw-wrap:focus-within { background: #fff; border-color: #1976d2; box-shadow: 0 0 0 3px rgba(25,118,210,0.12); }
.pw-wrap input { flex: 1; min-width: 0; border: none; outline: none; padding: 9px 2px; font-size: 0.82em; background: transparent; }
.pw-wrap input::placeholder { color: #aaa; }
.pw-icon { font-size: 0.9em; opacity: 0.4; flex-shrink: 0; }
.pw-toggle { background: none; border: none; cursor: pointer; font-size: 0.9em; padding: 4px; opacity: 0.4; flex-shrink: 0; border-radius: 4px; }
.pw-toggle:hover { opacity: 0.8; background: #eee; }
.net-act .btn-connect { flex-shrink: 0; background: linear-gradient(135deg, #1976d2, #1565c0); color: white; border: none; padding: 9px 14px; border-radius: 8px; cursor: pointer; font-size: 0.82em; font-weight: 700; white-space: nowrap; box-shadow: 0 2px 6px rgba(25,118,210,0.3); transition: all 0.15s; }
.net-act .btn-connect:hover { background: linear-gradient(135deg, #1565c0, #0d47a1); transform: translateY(-1px); box-shadow: 0 4px 10px rgba(25,118,210,0.4); }
.net-act .btn-connect:active { transform: translateY(0); }
.net-act .btn-connect:disabled { opacity: 0.6; cursor: wait; }
.net-act .connected-label { color: #4caf50; font-weight: 700; font-size: 0.85em; display: flex; align-items: center; gap: 4px; }
.empty-msg { text-align: center; padding: 30px; color: #999; }
.btn-bar { display: flex; justify-content: center; gap: 12px; margin-top: 16px; flex-wrap: wrap; }
.btn-bar button { padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 0.9em; font-weight: 600; transition: all 0.15s; }
.btn-bar button:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
.btn-scan { background: #607d8b; color: white; box-shadow: 0 2px 6px rgba(96,125,139,0.3); }
.btn-scan:hover:not(:disabled) { background: #546e7a; transform: translateY(-1px); }
.btn-disc { background: #ef5350; color: white; box-shadow: 0 2px 6px rgba(239,83,80,0.3); }
.btn-disc:hover:not(:disabled) { background: #e53935; transform: translateY(-1px); }
.footer { text-align: center; color: #aaa; font-size: 0.8em; margin-top: 24px; }
/* Known networks card */
.known-card { background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); overflow-x: auto; margin-top: 16px; }
.known-card .net-head { background: #fff3e0; border-bottom-color: #ffe0b2; color: #ef6c00; }
.known-card .net-row { grid-template-columns: 1fr 90px 100px 220px; }
.known-card .net-head { grid-template-columns: 1fr 90px 100px 220px; }
.btn-known { background: #1976d2; color: white; border: none; padding: 6px 10px; border-radius: 6px; cursor: pointer; font-size: 0.75em; font-weight: 700; }
.btn-known:hover { background: #1565c0; }
.btn-forget { background: #ef5350; color: white; border: none; padding: 6px 10px; border-radius: 6px; cursor: pointer; font-size: 0.75em; font-weight: 700; }
.btn-forget:hover { background: #e53935; }
.btn-auto { background: #78909c; color: white; border: none; padding: 6px 8px; border-radius: 6px; cursor: pointer; font-size: 0.7em; font-weight: 700; }
.btn-auto.on { background: #4caf50; }
@media (max-width: 700px) { .net-card-inner { min-width: 600px; } }
</style>
</head>
<body>
<div class="header"><h1>&#x1f4f6; STB WiFi Panel</h1></div>
<div class="container">
  <div class="status-card">
    <div class="status-dot {{ 'on' if connected else 'ap' if hs_active else 'off' }}"></div>
    <div class="status-text">
      <div class="status-label">Status</div>
      <div class="status-value {{ 'ok' if connected else 'ap' if hs_active else 'err' }}">{{ state }}</div>
      {% if hs_ssid %}<div style="font-size:0.78em;color:#ef6c00;">{{ hs_ssid }}</div>{% elif active %}<div style="font-size:0.78em;color:#4caf50;">{{ active }}</div>{% endif %}
    </div>
    <div class="status-text" style="text-align:right">
      <div class="status-label">IP Address</div>
      <div class="ip-text">{{ ip }}</div>
    </div>
  </div>

  <div class="ctrl-card">
    <div class="ctrl-row">
      <div class="ctrl-group">
        <span class="ctrl-label">Wi-Fi</span>
        <label class="switch"><input type="checkbox" {{ 'checked' if wifi_on else '' }} onchange="fetch('/wifi/toggle',{method:'POST'}).then(()=>location.reload())"><span class="slider"></span></label>
        <span style="font-size:0.82em;color:{{ '#4caf50' if wifi_on else '#f44336' }};font-weight:600;">{{ 'ON' if wifi_on else 'OFF' }}</span>
      </div>
      <div class="hint">Matikan untuk hemat daya / reset driver</div>
    </div>
    <div class="hs-panel">
      {% if hs_active %}
        <span class="hs-badge">&#x1f525; Hotspot aktif — {{ hs_ssid }}</span>
        <span class="hint">HP/laptop bisa connect ke hotspot ini (internet dari eth0)</span>
        <form method="post" action="/hotspot/stop" style="margin-left:auto"><button class="btn-hs btn-hs-stop" type="submit">Matikan Hotspot</button></form>
      {% else %}
        <span class="ctrl-label" style="white-space:nowrap;">Hotspot</span>
        <form method="post" action="/hotspot/start" class="hs-form">
          <input name="hs_ssid" placeholder="SSID hotspot" value="STB-Hotspot" required style="width:140px">
          <input name="hs_pass" type="password" placeholder="Password (min 8)" minlength="8" style="width:140px">
          <button class="btn-hs" type="submit" {{ 'disabled' if not wifi_on else '' }}>&#x1f4f6; Nyalakan Hotspot</button>
        </form>
        <span class="hint">Bagi internet eth0 → Wi-Fi</span>
      {% endif %}
    </div>
  </div>

  <div class="net-card">
  <div class="net-card-inner">
    <div class="net-head">
      <div class="c-name">Network Name</div>
      <div class="c-sig">Signal</div>
      <div class="c-sec">Security</div>
      <div class="c-act">Action</div>
    </div>
    {% for n in nets %}
    <div class="net-row">
      <div class="net-name" title="{{ n.ssid }}">{{ n.ssid }}</div>
      <div class="net-sig">
        <div class="sig-bar" style="height:6px; background:{% if n.sig >= 20 %}#4caf50{% else %}#e0e0e0{% endif %}"></div>
        <div class="sig-bar" style="height:10px; background:{% if n.sig >= 40 %}#4caf50{% else %}#e0e0e0{% endif %}"></div>
        <div class="sig-bar" style="height:14px; background:{% if n.sig >= 70 %}#4caf50{% elif n.sig >= 40 %}#ff9800{% else %}#e0e0e0{% endif %}\"></div>
        <div class="sig-bar" style="height:18px; background:{% if n.sig >= 85 %}#4caf50{% elif n.sig >= 55 %}#ff9800{% elif n.sig >= 25 %}#f44336{% else %}#e0e0e0{% endif %}\"></div>
        <span class="sig-pct">{{ n.sig }}%</span>
      </div>
      <div class="net-sec"><span class="{% if n.sec in ['', '--', ''] %}open{% endif %}">{{ n.sec if n.sec else 'Open' }}</span></div>
      <div class="net-act">
        {% if n.ssid == active %}
          <span class="connected-label">&#10003; Connected</span>
        {% else %}
          <div class="pw-wrap"><span class="pw-icon">&#128274;</span><input type="password" placeholder="Enter password" id="pw-{{ loop.index }}" autocomplete="off"><button type="button" class="pw-toggle" onclick="var i=document.getElementById('pw-{{ loop.index }}'); i.type=i.type=='password'?'text':'password'; this.textContent=i.type=='password'?'&#128065;':'&#128064;'" title="Show/Hide">&#128065;</button></div>
          <button type="button" class="btn-connect" onclick="doConnect({{ loop.index }},'{{ n.ssid }}',this)">Connect</button>
        {% endif %}
      </div>
    </div>
    {% endfor %}
    {% if hs_active %}
    <div class="empty-msg">Hotspot aktif — scan Wi-Fi dijeda. Matikan hotspot untuk scan lagi.</div>
    {% elif not wifi_on %}
    <div class="empty-msg">Wi-Fi OFF — nyalakan switch di atas</div>
    {% elif not nets %}
    <div class="empty-msg">No networks found &mdash; tap Rescan</div>
    {% endif %}
  </div>
  </div>
  <div class="btn-bar">
    <form method="post" action="/rescan" style="display:inline"><button class="btn-scan" type="submit" {{ 'disabled' if not wifi_on or hs_active else '' }}>&#21bb; Rescan Networks</button></form>
    <form method="post" action="/disconnect" style="display:inline"><button class="btn-disc" type="submit" {{ 'disabled' if hs_active else '' }}>&#2716; Disconnect</button></form>
  </div>

  <div class="known-card">
    <div class="net-head">
      <div>Saved Networks</div>
      <div style="text-align:center">Auto</div>
      <div style="text-align:center">Last Used</div>
      <div style="text-align:center">Action</div>
    </div>
    {% for k in known %}
    <div class="net-row">
      <div class="net-name" title="{{ k.ssid }}">{{ k.ssid }} {% if k.ssid == active %}<span style="color:#4caf50;font-weight:700;font-size:0.85em">(connected)</span>{% endif %}</div>
      <div class="net-sec"><span class="{% if k.autoconnect %}open{% endif %}">{{ "ON" if k.autoconnect else "OFF" }}</span></div>
      <div class="net-sig"><span class="sig-pct">{{ format_ts(k.last_used) }}</span></div>
      <div class="net-act" style="justify-content:center">
        <form method="post" action="/known/reconnect" style="display:inline">
          <input type="hidden" name="uuid" value="{{ k.uuid }}">
          <button type="submit" class="btn-known">Connect</button>
        </form>
        <form method="post" action="/known/autoconnect" style="display:inline">
          <input type="hidden" name="uuid" value="{{ k.uuid }}">
          <input type="hidden" name="state" value="{{ 'no' if k.autoconnect else 'yes' }}">
          <button type="submit" class="btn-auto {{ 'on' if k.autoconnect else '' }}">{{ "ON" if k.autoconnect else "OFF" }}</button>
        </form>
        <form method="post" action="/forget" style="display:inline" onsubmit="return confirm('Forget {{ k.ssid }}? Hapus password tersimpan.')">
          <input type="hidden" name="uuid" value="{{ k.uuid }}">
          <button type="submit" class="btn-forget">Forget</button>
        </form>
      </div>
    </div>
    {% endfor %}
    {% if not known %}
    <div class="empty-msg">Belum ada jaringan tersimpan. Connect di atas untuk menyimpan.</div>
    {% endif %}
  </div>

  <div class="footer">STB WiFi Panel &copy; {{ year }}</div>
</div>
<script>
function doConnect(idx, ssid, btn) {
  var el = document.getElementById('pw-' + idx);
  if(!el) return;
  var pw = el.value;
  if(!pw){ el.focus(); el.parentElement.style.borderColor='#f44336'; setTimeout(function(){el.parentElement.style.borderColor='';},1200); return; }
  var f = document.createElement('form');
  f.method = 'POST'; f.action = '/connect';
  var s1 = document.createElement('input'); s1.type='hidden'; s1.name='ssid'; s1.value=ssid; f.appendChild(s1);
  var s2 = document.createElement('input'); s2.type='hidden'; s2.name='password'; s2.value=pw; f.appendChild(s2);
  btn.disabled=true; btn.textContent='Connecting...';
  document.body.appendChild(f); f.submit();
}
</script>
</body>
</html>
"""

@app.route("/")
def index():
    state, ssid, wifi_on, hs_active, hs_ssid = get_status()
    connected = (state == "connected")
    ip = run_cmd("hostname", "-I").split()[0] if run_cmd("hostname", "-I") else "?"
    nets = get_networks(wifi_on, hs_active)
    known = get_known()
    from datetime import datetime
    return render_template_string(HTML, state=state.capitalize(), connected=connected, active=ssid, ip=ip, nets=nets, year=datetime.now().year, wifi_on=wifi_on, hs_active=hs_active, hs_ssid=hs_ssid, known=known, format_ts=format_ts)

@app.route("/connect", methods=["POST"])
def connect():
    ssid = request.form.get("ssid", "").strip()
    pw = request.form.get("password", "")
    if ssid:
        cmd = ["nmcli", "device", "wifi", "connect", ssid, "ifname", "wlan0"]
        if pw: cmd += ["password", pw]
        run_cmd(*cmd)
    return redirect("/")

@app.route("/disconnect", methods=["GET", "POST"])
def disconnect():
    run_cmd("nmcli", "device", "disconnect", "wlan0")
    return redirect("/")

@app.route("/rescan", methods=["GET", "POST"])
def rescan():
    run_cmd("nmcli", "device", "wifi", "rescan", "ifname", "wlan0")
    return redirect("/")

@app.route("/wifi/toggle", methods=["POST"])
def wifi_toggle():
    cur = run_cmd("nmcli", "radio", "wifi").strip()
    if cur == "enabled":
        run_cmd("nmcli", "radio", "wifi", "off")
    else:
        run_cmd("nmcli", "radio", "wifi", "on")
    return redirect("/")

@app.route("/hotspot/start", methods=["POST"])
def hotspot_start():
    ssid = request.form.get("hs_ssid", "").strip() or "STB-Hotspot"
    pw = request.form.get("hs_pass", "").strip()
    if pw and len(pw) < 8:
        return redirect("/")
    run_cmd("nmcli", "connection", "delete", "Hotspot")
    run_cmd("nmcli", "radio", "wifi", "on")
    if pw:
        run_cmd("nmcli", "device", "wifi", "hotspot", "ifname", "wlan0", "ssid", ssid, "password", pw, "con-name", "Hotspot")
    else:
        run_cmd("nmcli", "device", "wifi", "hotspot", "ifname", "wlan0", "ssid", ssid, "con-name", "Hotspot")
    return redirect("/")

@app.route("/hotspot/stop", methods=["POST"])
def hotspot_stop():
    run_cmd("nmcli", "connection", "down", "Hotspot")
    run_cmd("nmcli", "connection", "delete", "Hotspot")
    run_cmd("nmcli", "radio", "wifi", "on")
    return redirect("/")

@app.route("/forget", methods=["POST"])
def forget():
    uuid = request.form.get("uuid", "").strip()
    if uuid:
        run_cmd("nmcli", "connection", "delete", uuid)
    return redirect("/")

@app.route("/known/autoconnect", methods=["POST"])
def known_autoconnect():
    uuid = request.form.get("uuid", "").strip()
    state = request.form.get("state", "").strip()
    if uuid and state in ("yes", "no"):
        run_cmd("nmcli", "connection", "modify", uuid, "connection.autoconnect", state)
    return redirect("/")

@app.route("/known/reconnect", methods=["POST"])
def known_reconnect():
    uuid = request.form.get("uuid", "").strip()
    if uuid:
        run_cmd("nmcli", "connection", "up", uuid, "ifname", "wlan0")
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
