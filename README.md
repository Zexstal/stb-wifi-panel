# STB WiFi Panel — HG680P (Amlogic S905X)

Web panel ringan untuk kelola Wi-Fi di STB HG680P / Amlogic S905X yang jalan Armbian/Debian. Satu file Python (Flask + `nmcli`) — scan, connect, disconnect, Wi-Fi ON/OFF, dan **Hotspot 2.4 GHz** (share internet dari `eth0` → `wlan0`). Cocok untuk STB yang dipakai sebagai mini-router.

> Asal: panel yang sebelumnya jalan di `/opt/ap-panel/app.py` pada STB, dipoles jadi repo yang layak publish.

## Fitur

- **Status** — `wlan0` (disconnected / connected / hotspot), `eth0`, IP, dot warna (merah / hijau / oranye).
- **Wi-Fi ON/OFF** — toggle `nmcli radio wifi` (buat hemat daya / reset driver yang ngadat).
- **Scan & Connect** — list jaringan sort by sinyal, signal bar, security badge, input password + eye-toggle, tombol Connect.
- **Hotspot** — bikin AP 2.4 GHz via `nmcli device wifi hotspot` (`SSID` + password custom, default `STB-Hotspot`). Otomatis jadi NAT dari `eth0`.
- **Rescan / Disconnect** — disable otomatis saat hotspot aktif / Wi-Fi OFF biar tidak bentrok.
- Satu file, tanpa DB, tanpa Docker, tanpa `hostapd`/`dnsmasq` manual (NetworkManager yang urus).

## Kebutuhan

- **Hardware**: HG680P / STB Amlogic S905X lain dengan `wlan0` yang support mode AP (`iw list | grep -A5 "Supported interface modes"` harus ada `* AP`). Chipset ini **single-band 2.4 GHz** — HP 5 GHz-only tidak akan lihat SSID.
- **OS**: Armbian / Debian (dites di Armbian 26.8.3, kernel 6.6.x).
- **Software**: `NetworkManager` (`nmcli`), `python3`, `python3-flask`. `hostapd`/`dnsmasq` **tidak** dibutuhkan — malah harus `masked`/`disabled` biar tidak rebutan `wlan0`.
- Port `8080` bebas.

## Install cepat

Jalankan di STB sebagai `root`:

```bash
curl -fsSL https://raw.githubusercontent.com/USER/stb-wifi-panel/main/install.sh | bash
# ganti USER dengan username GitHub kamu
```

Atau manual:

```bash
git clone https://github.com/USER/stb-wifi-panel.git
cd stb-wifi-panel
chmod +x install.sh
sudo ./install.sh
```

`install.sh` akan:
1. Cek `nmcli` + `python3` + `flask` (auto `apt install python3-flask` kalau belum ada).
2. Copy `app.py` ke `/opt/stb-wifi-panel/app.py`.
3. Bikin & enable systemd service `stb-wifi-panel.service` → jalan di `0.0.0.0:8080`.

## Pakai

- Buka `http://<IP-STB>:8080` (mis. `http://192.168.0.100:8080` atau `192.168.2.7:8080`).
- **Connect Wi-Fi**: isi password di baris SSID → **Connect**. Yang sudah connected jadi label hijau `✓ Connected`.
- **Hotspot**: isi SSID + password (min 8 char, kosong = open) → **Nyalakan Hotspot**. HP/laptop connect ke SSID itu; internet ngalir dari `eth0`. Matikan via **Matikan Hotspot**.
- **Wi-Fi OFF**: switch di card `Wi-Fi`. Berguna kalau driver `wlan0` ngadat (hilang dari `nmcli device`).

## Troubleshooting

| Gejala | Cek |
|---|---|
| Panel tidak kebuka | `systemctl status stb-wifi-panel`, `journalctl -u stb-wifi-panel -f`, cek `ss -tlnp \| grep 8080` |
| `wlan0` hilang / `disconnected` terus | `nmcli radio wifi` harus `enabled`; `nmcli device status`; `dmesg \| grep -i wlan\|brcm\|rtl`; coba Wi-Fi OFF → ON di panel |
| Hotspot tidak muncul di HP | `iw list` harus ada `* AP`; pastikan HP support 2.4 GHz; `nmcli con show --active` harus ada `Hotspot` di `wlan0` |
| Hotspot tidak ada internet | `ip route \| grep default` harus via `eth0`; `cat /proc/sys/net/ipv4/ip_forward` harus `1`; `eth0` harus konek internet |
| `hostapd` rebutan | `systemctl is-enabled hostapd` harus `masked`/`disabled`; jangan install `hostapd`/`dnsmasq` kalau pakai `nmcli hotspot` |

## Struktur repo

```
.
├── app.py        # aplikasi Flask + template HTML/CSS/JS inline
├── install.sh    # installer systemd
├── README.md
└── .gitignore
```

## Pengembangan

```bash
python3 app.py              # dev, http://127.0.0.1:8080
# atau
systemctl restart stb-wifi-panel && journalctl -u stb-wifi-panel -f
```

PR welcome — jaga tetap satu file & minim dependensi.

## Lisensi

MIT — bebas pakai di STB kamu. Lihat `LICENSE` (tambahkan file-nya kalau mau publish beneran).
