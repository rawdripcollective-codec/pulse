import { Activity, Github } from "lucide-react";
import { Link } from "react-router-dom";

import { brand } from "../theme/brand";

export function Header() {
  return (
    <header className="border-b border-pulse-border bg-pulse-surface/50 backdrop-blur">
      <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-pulse-accent/10 border border-pulse-accent/30 flex items-center justify-center">
            <Activity className="w-5 h-5 text-pulse-accent" />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">{brand.name}</h1>
            <p className="text-xs text-pulse-fg-dim -mt-0.5">
              {brand.tagline}
            </p>
          </div>
        </Link>

        <div className="flex items-center gap-3">
          <a
            href="https://github.com/rawdripcollective-codec/pulse"
            target="_blank"
            rel="noreferrer"
            className="text-pulse-fg-muted hover:text-pulse-fg transition-colors"
            aria-label="GitHub repository"
          >
            <Github className="w-5 h-5" />
          </a>
        </div>
      </div>
    </header>
  );
}
