import { useState } from "react";
import { ChevronDown, FolderGit2 } from "lucide-react";

import type { RepoSummary } from "../types";

interface Props {
  repos: RepoSummary[];
  selected: string;
  onSelect: (fullName: string) => void;
}

export function RepoSelector({ repos, selected, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const current = repos.find((r) => r.full_name === selected);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm min-w-[200px] hover:border-slate-600 transition-colors"
      >
        <FolderGit2 className="w-4 h-4 text-slate-400" />
        <span className="flex-1 text-left">
          {current ? current.full_name : "All repositories"}
        </span>
        <ChevronDown className="w-4 h-4 text-slate-500" />
      </button>

      {open && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setOpen(false)}
          />
          <div className="absolute top-full left-0 mt-1 w-full bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-20 max-h-80 overflow-y-auto">
            <button
              onClick={() => {
                onSelect("");
                setOpen(false);
              }}
              className="w-full text-left px-3 py-2 text-sm hover:bg-slate-700 border-b border-slate-700"
            >
              All repositories
            </button>
            {repos.map((repo) => (
              <button
                key={repo.id}
                onClick={() => {
                  onSelect(repo.full_name);
                  setOpen(false);
                }}
                className="w-full text-left px-3 py-2 text-sm hover:bg-slate-700 flex items-center justify-between"
              >
                <span className="truncate">{repo.full_name}</span>
                <span className="text-xs text-slate-500">
                  {repo.open_prs} PR
                </span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
