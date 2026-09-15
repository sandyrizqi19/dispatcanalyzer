# System Deployment Manager

Sistem Deployment Manager independen adalah sebuah layanan terpisah yang berjalan pada port `8083`. Tujuannya adalah untuk memungkinkan eksekusi proses sinkronisasi Git (fetch, merge, push) dan pembaruan Docker container (docker compose down & up) dari antarmuka web, tanpa takut proses tersebut terputus saat aplikasi web utama dimatikan.

## Arsitektur

1. **Standalone Go Backend** (`tools/deployer/main.go`)
   *   Menggunakan Golang, kita membuat web server kecil yang mengekspos endpoint API di port **8083**.
   *   Layanan ini menangani *Basic Authentication* menggunakan kredensial `deployer` / `Cilandak26#`.
   *   Menggunakan teknologi **SSE (Server-Sent Events)** untuk mengalirkan (*stream*) teks output langsung dari terminal (*stdout/stderr*) ke antarmuka web, sehingga proses *git* dan *docker* terlihat *real-time*.

2. **Web Interface** (`tools/deployer/index.html`)
   *   Dilengkapi dengan **Live Console (Terminal)** berwarna hitam yang secara visual menyerupai terminal asli.
   *   Terdapat panel **Settings/Configuration** yang tersembunyi (bisa di-*toggle*). Panel ini menyimpan data ke `.deployer_config.json` di *backend*.
   *   Target direktori secara *default* sudah diatur dinamis untuk mendeteksi *parent folder* dari direktori `deployer`.

## Cara Menjalankannya di Server

1. **Clone repositori** / masuk ke dalam folder repositori Anda di server:
   ```bash
   cd /var/dispatchanalyzer/tools/deployer
   ```
2. **Build binary Go** (cukup dilakukan sekali atau jika ada pembaruan kode):
   ```bash
   go build -o deployer_bin main.go
   ```
3. **Jalankan layanan** menggunakan `nohup` atau buat `systemd` service agar tetap hidup di background:
   ```bash
   nohup ./deployer_bin &
   ```

## Integrasi Frontend
Menu **System Deployment** di aplikasi Dispatch Analyzer (*frontend*) secara *default* akan memuat URL ini melalui iframe port 8083. Saat pertama kali diakses, sistem akan meminta otentikasi:
- **Username**: `deployer`
- **Password**: `Cilandak26#`

## Langkah Deployment Tester (Server Setup)
Jika Anda ingin mengetes branch ini (`deploy_test`) di folder baru pada server tanpa mengganggu versi *production*:

1. **Clone repositori** ke folder tester (misal `dispatchanalyzer-tester`):
   ```bash
   gh repo clone sandyrizqi19/dispatcanalyzer dispatchanalyzer-tester -- -b deploy_test
   # atau menggunakan git:
   # git clone -b deploy_test https://github.com/sandyrizqi19/dispatcanalyzer.git dispatchanalyzer-tester
   ```

2. **Sesuaikan port di `.env`**:
   Masuk ke folder tersebut dan pastikan Anda membuat file `.env`. Ubah port agar tidak bentrok dengan production:
   ```env
   VITE_API_BASE_URL=http://localhost:8001
   CORS_ORIGINS=http://localhost:3000,http://localhost:3001,http://localhost:5173
   
   API_PORT=8001
   WEB_PORT=3001
   ```

3. **Jalankan aplikasi utama (Docker)**:
   ```bash
   cd dispatchanalyzer-tester
   docker compose up --build -d
   ```

4. **Jalankan Deployment Manager (Go)**:
   ```bash
   cd tools/deployer
   go build -o deployer_bin main.go
   nohup ./deployer_bin &
   ```

Setelah itu, Anda bisa membuka aplikasi tester Anda di port **3001**, masuk ke halaman System Deployment, dan mengakses *Deployer* independen ini (di port 8083).
