import React, { useEffect, useState } from 'react';
import { ShieldAlert, Activity, CheckCircle2, AlertTriangle, ExternalLink } from 'lucide-react';

interface HealthStatus {
  status: string;
  version: string;
  environment: string;
}

export const App: React.FC = () => {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/v1/health')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setHealth(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return (
    <div className="min-h-screen flex flex-col justify-between p-6 max-w-5xl mx-auto">
      <header className="border-b border-slate-800 pb-4 mb-8 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-blue-600/20 text-blue-400 rounded-lg border border-blue-500/30">
            <ShieldAlert className="w-7 h-7" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white">IDRA</h1>
            <p className="text-xs text-slate-400">Intelligent Disaster Response Agents</p>
          </div>
        </div>
        <div className="flex items-center space-x-2">
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-900/40 text-emerald-300 border border-emerald-500/30">
            Milestone M2: API Core & Events
          </span>
        </div>
      </header>

      <main className="space-y-6 flex-1">
        <div className="bg-slate-800/60 border border-slate-700/60 rounded-xl p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-white mb-2 flex items-center gap-2">
            <Activity className="w-5 h-5 text-blue-400" /> System Status
          </h2>
          <p className="text-sm text-slate-300 mb-6">
            Foundation infrastructure, database schema, and event domain API status.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 bg-slate-900/80 rounded-lg border border-slate-700/40">
              <div className="text-xs font-medium text-slate-400">API Health</div>
              <div className="mt-2 flex items-center space-x-2">
                {loading ? (
                  <span className="text-xs text-slate-500">Checking...</span>
                ) : error ? (
                  <>
                    <AlertTriangle className="w-4 h-4 text-rose-400" />
                    <span className="text-sm font-semibold text-rose-300">Disconnected</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span className="text-sm font-semibold text-emerald-300">
                      {health?.status.toUpperCase()}
                    </span>
                  </>
                )}
              </div>
            </div>

            <div className="p-4 bg-slate-900/80 rounded-lg border border-slate-700/40">
              <div className="text-xs font-medium text-slate-400">Environment</div>
              <div className="mt-2 text-sm font-semibold text-slate-200">
                {health?.environment || 'development'}
              </div>
            </div>

            <div className="p-4 bg-slate-900/80 rounded-lg border border-slate-700/40">
              <div className="text-xs font-medium text-slate-400">Study Area</div>
              <div className="mt-2 text-sm font-semibold text-slate-200">
                Chennai Core (BBox)
              </div>
            </div>
          </div>
        </div>

        <div className="bg-slate-800/40 border border-slate-700/40 rounded-xl p-6">
          <h3 className="text-sm font-medium text-slate-200 mb-3">Quick Navigation</h3>
          <div className="flex flex-wrap gap-3 text-sm">
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-700/60 hover:bg-slate-700 text-slate-200 rounded-md border border-slate-600/50 transition-colors"
            >
              API Swagger Docs <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
            </a>
            <a
              href="/api/v1/health/deep"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-700/60 hover:bg-slate-700 text-slate-200 rounded-md border border-slate-600/50 transition-colors"
            >
              Deep Health Diagnostic <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
            </a>
          </div>
        </div>
      </main>

      <footer className="mt-12 pt-4 border-t border-slate-800 text-xs text-slate-500 text-center">
        IDRA Decision Support Platform &bull; B.Tech Project-I BITE497J
      </footer>
    </div>
  );
};

export default App;
