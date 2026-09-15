import { ExternalLink, RefreshCw, ShieldAlert, CheckCircle2, Terminal, Server } from "lucide-react";
import { useMemo } from "react";

export function SystemDeploymentPage() {
  const deployerUrl = useMemo(() => {
    const host = window.location.hostname || "localhost";
    const customPort = import.meta.env.VITE_DEPLOYER_PORT || "8083";
    return `http://${host}:${customPort}`;
  }, []);

  return (
    <div className="space-y-6" style={{ padding: "0.5rem 0" }}>
      {/* Header Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-[#0b73bf] to-[#034b82] flex items-center justify-center text-white shadow-md flex-shrink-0">
              <RefreshCw size={24} className="text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold text-slate-900">System Deployment & Upstream Sync</h2>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                  Decoupled Service
                </span>
              </div>
              <p className="text-sm text-slate-500 mt-1">
                Otomatisasi sinkronisasi fork dari upstream, pull origin, safe pre-build, dan restart stack Docker secara aman.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <a
              href={deployerUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[#0b73bf] text-white text-sm font-semibold shadow hover:bg-[#095c99] transition"
            >
              <span>Buka di Tab Terpisah</span>
              <ExternalLink size={16} />
            </a>
          </div>
        </div>

        {/* Notice banner */}
        <div className="mt-5 rounded-lg bg-blue-50 border border-blue-200 p-4 text-xs text-slate-700 flex items-start gap-3">
          <Server size={18} className="text-[#0b73bf] flex-shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold text-[#15385b]">Arsitektur Aman (Anti-Interupsi):</span> Layanan Deployment Manager berjalan pada port <code>8083</code> secara terpisah dari stack aplikasi utama. Ketika container aplikasi dimatikan dan dibangun ulang (<code>docker compose down &amp; build</code>), antarmuka pemantauan log di bawah ini <strong>tidak akan terputus</strong>.
          </div>
        </div>
      </div>

      {/* Embedded Deployer Iframe Container */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden" style={{ minHeight: "780px" }}>
        <iframe
          src={deployerUrl}
          title="System Deployment Manager"
          className="w-full border-0"
          style={{ width: "100%", height: "820px", display: "block" }}
        />
      </div>
    </div>
  );
}
