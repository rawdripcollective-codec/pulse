import { Activity, Github } from "lucide-react";
import { Link } from "react-router-dom";

export function Header() {
  return (
    <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur">
      <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center">
            <Activity className="w-5 h-5 text-cyan-400" />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Pulse</h1>
            <p className="text-xs text-slate-500 -mt-0.5">
              Agentic PR Triage
            </p>
          </div>
        </Link>

        <div className="flex items-center gap-3">
          <a
            href="https://github.com/rawdripcollective-codec/pulse"
            target="_blank"
            rel="noreferrer"
            className="text-slate-400 hover:text-slate-200 transition-colors"
            aria-label="GitHub repository"
          >
            <Github className="w-5 h-5" />
          </a>
        </div>
      </div>
    </header>
  );
}
