# System Deployment & Upstream Sync Manager

Modul ini adalah layanan mandiri (*decoupled service*) untuk melakukan otomatisasi sinkronisasi fork dari upstream dan re-deployment aplikasi secara aman tanpa interupsi proses UI.

---

## Fitur Utama

1. **One-Click Execution**: Satu tombol untuk menjalankan seluruh pipeline Git dan Docker.
2. **Decoupled Architecture**: Berjalan independen di luar stack `docker-compose.yml` utama sehingga tidak terputus saat aplikasi di-restart (`docker compose down`).
3. **Safe Pre-build Strategy**: Menjalankan `docker compose build` terlebih dahulu saat aplikasi lama masih aktif, mengurangi downtime layanan aplikasi dari beberapa menit menjadi hanya 3–10 detik.
4. **Real-time Live Streaming**: Log terminal dan progres tahapan ditampilkan secara real-time via Server-Sent Events (SSE).
5. **Git Conflict Protection**: Otomatis mendeteksi merge conflict, membatalkan secara aman (`git merge --abort`), dan mencegah kerusakan repository.
6. **Zero Upstream Interference**: Terisolasi di folder `services/deployer/` yang tidak dimiliki oleh repository upstream creator (`ferdeh/dispatcanalyzer`).

---

## Alur Pipeline (6 Tahap)

1. **Stage 1: Pre-flight Check**: Validasi git repo, cek ketersediaan remote `upstream` dan `origin`, stash perubahan lokal jika ada.
2. **Stage 2: Sync Upstream**: `git fetch upstream main --prune` untuk mengambil commit terbaru dari creator.
3. **Stage 3: Merge & Push Fork**: `git checkout main`, `git merge upstream/main --no-edit`, dan `git push origin main`.
4. **Stage 4: Pull Origin**: `git pull origin main` untuk memvalidasi branch lokal telah selaras dengan origin fork GitHub.
5. **Stage 5: Docker Safe Build & Recreate**: `docker compose build` (saat stack lama masih aktif) -> `docker compose down` -> `docker compose up -d`.
6. **Stage 6: Health Check Verification**: Polling endpoint kesehatan API (`/api/v1/health`) dan Web hingga status 200 OK.

---

## Cara Menjalankan

### Opsi A: Menjalankan Langsung di Host (Recommended untuk Server / VPS)

```bash
# Memberikan izin eksekusi
chmod +x services/deployer/run_deployer.sh

# Menjalankan deployer (default port 8080)
./services/deployer/run_deployer.sh host

# Atau dengan port kustom
DEPLOYER_PORT=8088 ./services/deployer/run_deployer.sh host
```

Dashboard dapat diakses di browser:
👉 **`http://<IP-SERVER>:8080`**

### Opsi B: Menjalankan via Docker Container Terisolasi

```bash
./services/deployer/run_deployer.sh docker
# Atau langsung menggunakan docker compose:
docker compose -f services/deployer/docker-compose.deployer.yml up -d --build
```

---

## Konfigurasi Lingkungan (Opsional)

Variabel lingkungan dapat didefinisikan sebelum menjalankan script atau di `.env`:

| Variabel | Default | Keterangan |
|---|---|---|
| `DEPLOYER_PORT` | `8080` | Port HTTP antarmuka deployer |
| `GIT_UPSTREAM_URL` | `https://github.com/ferdeh/dispatcanalyzer.git` | URL repository creator |
| `GIT_ORIGIN_URL` | `https://github.com/sandyrizqi19/dispatcanalyzer.git` | URL repository fork Anda |
| `GITHUB_TOKEN` | *(kosong)* | Personal Access Token jika push origin memerlukan auth token |
| `DEPLOYER_AUTH_TOKEN` | *(kosong)* | Kunci rahasia sederhana untuk membatasi akses tombol deploy |
| `API_HEALTH_URL` | `http://localhost:8000/api/v1/health` | URL healthcheck backend |
| `WEB_HEALTH_URL` | `http://localhost:3000` | URL healthcheck frontend |

---

## Menjalankan di Background (Systemd / Tmux / Screen)

Agar Deploy Manager tetap hidup di server saat sesi SSH ditutup:

**Menggunakan `nohup` / background:**
```bash
nohup ./services/deployer/run_deployer.sh host > deployer.log 2>&1 &
```

**Menggunakan `systemd` (opsional untuk production):**
Buat file `/etc/systemd/system/dispatc-deployer.service`:
```ini
[Unit]
Description=Dispatcanalyzer Deploy Manager
After=network.target docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/dispatcanalyzer
ExecStart=/path/to/dispatcanalyzer/services/deployer/run_deployer.sh host
Restart=always

[Install]
WantedBy=multi-user.target
```
Lalu aktifkan:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dispatc-deployer
```
