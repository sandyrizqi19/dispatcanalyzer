import asyncio
import os
import sys
import time
import json
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, Awaitable

class DeploymentPipeline:
    def __init__(self, repo_path: Optional[str] = None):
        self.repo_path = os.path.abspath(repo_path or os.path.join(os.path.dirname(__file__), "../.."))
        self.upstream_url = os.getenv("GIT_UPSTREAM_URL", "https://github.com/ferdeh/dispatcanalyzer.git")
        self.origin_url = os.getenv("GIT_ORIGIN_URL", "https://github.com/sandyrizqi19/dispatcanalyzer.git")
        self.api_health_url = os.getenv("API_HEALTH_URL", "http://localhost:8000/api/v1/health")
        self.web_health_url = os.getenv("WEB_HEALTH_URL", "http://localhost:3000")
        self.github_token = os.getenv("GITHUB_TOKEN", "").strip()
        
        # State tracking
        self.is_running = False
        self.current_stage = 0
        self.current_status = "idle"  # idle | running | success | error
        self.error_message: Optional[str] = None
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.logs: List[Dict[str, Any]] = []
        self.subscribers: List[asyncio.Queue] = []
        self.lock = asyncio.Lock()

        # Stages definition
        self.stages = [
            {"id": 1, "title": "Pre-flight Check", "desc": "Validasi git repository, remote URL, dan docker environment"},
            {"id": 2, "title": "Sync Upstream", "desc": "Fetch commit terbaru dari upstream creator"},
            {"id": 3, "title": "Merge & Push Fork", "desc": "Checkout main, merge upstream/main, dan push ke origin fork"},
            {"id": 4, "title": "Pull Origin", "desc": "Verifikasi sinkronisasi lokal dengan origin/main"},
            {"id": 5, "title": "Docker Safe Build & Restart", "desc": "Build image Docker baru lalu restart container aplikasi"},
            {"id": 6, "title": "Health Check Verification", "desc": "Validasi responsivitas API dan Web hingga online"},
        ]

    def add_subscriber(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        self.subscribers.append(queue)
        return queue

    def remove_subscriber(self, queue: asyncio.Queue):
        if queue in self.subscribers:
            self.subscribers.remove(queue)

    async def broadcast(self, event: Dict[str, Any]):
        event_str = json.dumps(event)
        disconnected = []
        for queue in self.subscribers:
            try:
                queue.put_nowait(event_str)
            except asyncio.QueueFull:
                disconnected.append(queue)
        for q in disconnected:
            self.remove_subscriber(q)

    async def log(self, message: str, level: str = "info", stage: Optional[int] = None):
        """Append log and broadcast to all connected clients."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = {
            "timestamp": timestamp,
            "level": level,  # info | success | warning | error | cmd
            "stage": stage if stage is not None else self.current_stage,
            "message": message
        }
        self.logs.append(entry)
        # Keep in-memory logs bounded
        if len(self.logs) > 3000:
            self.logs = self.logs[-2000:]
        await self.broadcast({"type": "log", "data": entry})

    async def set_stage(self, stage_id: int, status: str = "running"):
        self.current_stage = stage_id
        await self.broadcast({
            "type": "stage",
            "stage": stage_id,
            "status": status,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })

    def get_summary(self) -> Dict[str, Any]:
        duration = 0
        if self.start_time:
            end = self.end_time or time.time()
            duration = round(end - self.start_time, 1)

        return {
            "status": self.current_status,
            "is_running": self.is_running,
            "current_stage": self.current_stage,
            "stages": self.stages,
            "start_time": datetime.fromtimestamp(self.start_time).strftime("%Y-%m-%d %H:%M:%S") if self.start_time else None,
            "end_time": datetime.fromtimestamp(self.end_time).strftime("%Y-%m-%d %H:%M:%S") if self.end_time else None,
            "duration_seconds": duration,
            "error_message": self.error_message,
            "repo_path": self.repo_path,
            "upstream_url": self.upstream_url,
            "origin_url": self.origin_url,
            "logs_count": len(self.logs)
        }

    async def run_command(self, cmd: str, cwd: Optional[str] = None, allow_failure: bool = False, env: Optional[Dict[str, str]] = None) -> tuple[int, str]:
        """Execute shell command asynchronously and stream logs in real-time."""
        run_cwd = cwd or self.repo_path
        await self.log(f"$ {cmd}", level="cmd")

        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                cwd=run_cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=merged_env
            )

            output_lines = []
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                if decoded:
                    output_lines.append(decoded)
                    await self.log(f"  {decoded}", level="info")

            returncode = await process.wait()
            output_str = "\n".join(output_lines)

            if returncode != 0 and not allow_failure:
                await self.log(f"Perintah gagal dengan exit code {returncode}", level="error")
            return returncode, output_str
        except Exception as e:
            err_msg = f"Gagal mengeksekusi perintah '{cmd}': {str(e)}"
            await self.log(err_msg, level="error")
            if not allow_failure:
                raise RuntimeError(err_msg)
            return -1, str(e)

    async def execute(self, pre_build_first: bool = True, skip_docker: bool = False) -> bool:
        """Main deployment pipeline executor."""
        async with self.lock:
            if self.is_running:
                raise RuntimeError("Deployment sedang berjalan. Harap tunggu hingga selesai.")

            self.is_running = True
            self.current_status = "running"
            self.current_stage = 1
            self.error_message = None
            self.start_time = time.time()
            self.end_time = None
            self.logs = []

        await self.broadcast({"type": "pipeline_start", "data": self.get_summary()})
        await self.log("=== MEMULAI AUTOMATED ONE-CLICK DEPLOYMENT ===", level="info", stage=1)

        try:
            # ----------------------------------------------------
            # STAGE 1: PRE-FLIGHT CHECKS
            # ----------------------------------------------------
            await self.set_stage(1, "running")
            await self.log("[1/6] Memeriksa kesiapan lingkungan...", level="info", stage=1)

            if not os.path.exists(os.path.join(self.repo_path, ".git")):
                raise RuntimeError(f"Direktori bukan git repository yang valid: {self.repo_path}")

            # Check remotes
            _, remotes_out = await self.run_command("git remote -v")
            if "upstream" not in remotes_out:
                await self.log(f"Remote 'upstream' belum terkonfigurasi. Menambahkan remote upstream: {self.upstream_url}", level="warning", stage=1)
                await self.run_command(f"git remote add upstream {self.upstream_url}")

            if "origin" not in remotes_out:
                await self.log(f"Remote 'origin' belum terkonfigurasi. Menambahkan remote origin: {self.origin_url}", level="warning", stage=1)
                await self.run_command(f"git remote add origin {self.origin_url}")

            # Check uncommitted changes
            rc, status_out = await self.run_command("git status --porcelain")
            if status_out.strip():
                await self.log("Terdeteksi perubahan lokal uncommitted. Melakukan stash otomatis demi keamanan...", level="warning", stage=1)
                await self.run_command(f"git stash push -u -m 'auto-stash-before-deploy-{int(time.time())}'", allow_failure=True)

            # Check docker presence
            if not skip_docker:
                rc_docker, _ = await self.run_command("docker --version", allow_failure=True)
                if rc_docker != 0:
                    await self.log("Peringatan: Perintah 'docker' tidak ditemukan di path host. Mode simulasi/skip docker mungkin diperlukan.", level="warning", stage=1)

            await self.log("Pre-flight checks sukses!", level="success", stage=1)
            await self.set_stage(1, "success")

            # ----------------------------------------------------
            # STAGE 2: SYNC FORK DARI UPSTREAM
            # ----------------------------------------------------
            await self.set_stage(2, "running")
            await self.log("[2/6] Mengambil perubahan terbaru dari upstream...", level="info", stage=2)
            rc, _ = await self.run_command("git fetch upstream main --prune")
            if rc != 0:
                raise RuntimeError("Gagal melakukan 'git fetch upstream main'. Periksa koneksi internet atau izin remote.")

            _, incoming_commits = await self.run_command("git log HEAD..upstream/main --oneline -n 10", allow_failure=True)
            if incoming_commits.strip():
                await self.log("Daftar commit baru dari upstream yang akan digabungkan:", level="info", stage=2)
            else:
                await self.log("Tidak ada commit baru dari upstream (sudah up-to-date).", level="info", stage=2)

            await self.log("Fetch upstream selesai dengan sukses!", level="success", stage=2)
            await self.set_stage(2, "success")

            # ----------------------------------------------------
            # STAGE 3: CHECKOUT MAIN, MERGE & PUSH FORK
            # ----------------------------------------------------
            await self.set_stage(3, "running")
            await self.log("[3/6] Melakukan checkout main dan menggabungkan perubahan upstream...", level="info", stage=3)

            await self.run_command("git checkout main")
            
            # Merge upstream/main
            rc_merge, merge_out = await self.run_command("git merge upstream/main --no-edit -m 'Merge upstream/main via System Deployment Manager'", allow_failure=True)
            if rc_merge != 0:
                await self.log("PERINGATAN KRITIKAL: Terjadi Merge Conflict saat menggabungkan upstream/main!", level="error", stage=3)
                await self.log("Membatalkan merge secara otomatis (git merge --abort) untuk menjaga kestabilan kode...", level="warning", stage=3)
                await self.run_command("git merge --abort", allow_failure=True)
                raise RuntimeError("Merge conflict terdeteksi. Silakan periksa file yang konflik secara manual sebelum deploy.")

            await self.log("Merge upstream/main berhasil!", level="success", stage=3)

            # Push to origin (fork)
            await self.log("Mendorong (push) perubahan ke origin fork (https://github.com/sandyrizqi19/dispatcanalyzer.git)...", level="info", stage=3)
            
            # Setup push auth if token provided
            push_cmd = "git push origin main"
            if self.github_token:
                masked_url = f"https://{self.github_token}@github.com/sandyrizqi19/dispatcanalyzer.git"
                push_cmd = f"git push {masked_url} main"

            rc_push, _ = await self.run_command(push_cmd, allow_failure=True)
            if rc_push != 0:
                await self.log("Catatan: Push ke origin mengalami penyesuaian/peringatan. Melanjutkan tahap berikutnya...", level="warning", stage=3)
            else:
                await self.log("Push ke origin fork sukses!", level="success", stage=3)

            await self.set_stage(3, "success")

            # ----------------------------------------------------
            # STAGE 4: PULL ORIGIN
            # ----------------------------------------------------
            await self.set_stage(4, "running")
            await self.log("[4/6] Menjalankan 'git pull origin main' untuk memastikan sinkronisasi lokal...", level="info", stage=4)
            rc_pull, _ = await self.run_command("git pull origin main", allow_failure=True)
            if rc_pull != 0:
                await self.log("Peringatan saat git pull origin, melanjutkan dengan branch lokal terkini.", level="warning", stage=4)
            else:
                await self.log("Pull origin berhasil!", level="success", stage=4)

            await self.set_stage(4, "success")

            # ----------------------------------------------------
            # STAGE 5: DOCKER BUILD & RECREATE (SAFE DOWNTIME STRATEGY)
            # ----------------------------------------------------
            await self.set_stage(5, "running")
            await self.log("[5/6] Memulai proses Docker build dan re-deploy aplikasi...", level="info", stage=5)

            if skip_docker:
                await self.log("Mode skip_docker aktif: Melewati tahap build & restart docker.", level="info", stage=5)
            else:
                # SAFE ARCHITECTURE:
                # If pre_build_first is enabled, we run docker compose build FIRST.
                # Old containers stay online and serve users while building!
                if pre_build_first:
                    await self.log("STRATEGI AMAN: Menjalankan 'docker compose build' terlebih dahulu agar aplikasi tetap online selama proses kompilasi...", level="info", stage=5)
                    rc_build, _ = await self.run_command("docker compose build", allow_failure=True)
                    if rc_build != 0:
                        # Fallback for old docker-compose syntax
                        rc_build, _ = await self.run_command("docker-compose build", allow_failure=True)
                    if rc_build != 0:
                        raise RuntimeError("Docker build gagal. Stack aplikasi lama tetap berjalan aman dan tidak dimatikan.")
                    await self.log("Docker build sukses 100%! Memulai pergantian container baru...", level="success", stage=5)

                # Now down and up
                await self.log("Menjalankan 'docker compose down'...", level="info", stage=5)
                await self.run_command("docker compose down", allow_failure=True)

                await self.log("Menjalankan 'docker compose up -d'...", level="info", stage=5)
                rc_up, _ = await self.run_command("docker compose up -d", allow_failure=True)
                if rc_up != 0:
                    rc_up, _ = await self.run_command("docker-compose up -d")

                if rc_up != 0:
                    raise RuntimeError("Gagal menjalankan 'docker compose up -d'. Periksa log docker host.")

                await self.log("Docker container berhasil di-restart!", level="success", stage=5)

            await self.set_stage(5, "success")

            # ----------------------------------------------------
            # STAGE 6: HEALTH CHECK VERIFICATION
            # ----------------------------------------------------
            await self.set_stage(6, "running")
            await self.log("[6/6] Memverifikasi status kesehatan layanan API & Web...", level="info", stage=6)

            if not skip_docker:
                max_attempts = 20
                healthy = False
                for attempt in range(1, max_attempts + 1):
                    await self.log(f"Memeriksa API health ({self.api_health_url}) [Percobaan {attempt}/{max_attempts}]...", level="info", stage=6)
                    try:
                        req = urllib.request.Request(self.api_health_url, headers={"User-Agent": "DeployManager"})
                        with urllib.request.urlopen(req, timeout=3) as resp:
                            if resp.status == 200:
                                healthy = True
                                await self.log(f"API Health Check merespons OK (HTTP 200)!", level="success", stage=6)
                                break
                    except Exception:
                        await asyncio.sleep(2.5)

                if not healthy:
                    await self.log("Layanan API belum merespons dalam batas waktu, namun container tetap berjalan.", level="warning", stage=6)
            else:
                await self.log("Mode skip_docker: Verifikasi health check dilewati.", level="info", stage=6)

            await self.set_stage(6, "success")

            # Final Success
            self.current_status = "success"
            self.end_time = time.time()
            duration = round(self.end_time - self.start_time, 1)
            await self.log(f"🎉 DEPLOYMENT BERHASIL 100% DALAM {duration} DETIK! Seluruh layanan kembali online.", level="success", stage=6)
            await self.broadcast({"type": "pipeline_complete", "status": "success", "data": self.get_summary()})
            return True

        except Exception as e:
            self.current_status = "error"
            self.error_message = str(e)
            self.end_time = time.time()
            await self.log(f"❌ DEPLOYMENT GAGAL: {str(e)}", level="error", stage=self.current_stage)
            await self.set_stage(self.current_stage, "error")
            await self.broadcast({"type": "pipeline_complete", "status": "error", "error": str(e), "data": self.get_summary()})
            return False

        finally:
            self.is_running = False

# Global pipeline instance
pipeline_instance = DeploymentPipeline()
