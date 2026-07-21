import { useEffect, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { searchAssets } from "../api/client";
import type { AssetOption } from "../types";

interface Props {
  selected: AssetOption[];
  onChange: (assets: AssetOption[]) => void;
}

export function AssetPicker({ selected, onChange }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<AssetOption[]>([]);
  const [open, setOpen] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      searchAssets(query, 15)
        .then(setResults)
        .catch(() => setResults([]));
    }, 250);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  const add = (asset: AssetOption) => {
    if (!selected.some((a) => a.asset_id === asset.asset_id)) {
      onChange([...selected, asset]);
    }
    setQuery("");
    setOpen(false);
  };

  const remove = (assetId: string) => {
    onChange(selected.filter((a) => a.asset_id !== assetId));
  };

  return (
    <div className="relative">
      <div className="flex flex-wrap gap-1.5 mb-1.5">
        {selected.map((asset) => (
          <span
            key={asset.asset_id}
            className="inline-flex items-center gap-1 bg-purple-500/15 border border-purple-400/30 text-purple-200 text-[11px] rounded-full px-2 py-0.5"
          >
            {asset.asset_name}
            <button onClick={() => remove(asset.asset_id)} className="hover:text-white">
              <X size={11} />
            </button>
          </span>
        ))}
      </div>
      <div className="relative">
        <Search size={13} className="absolute left-2.5 top-2.5 text-gray-500" />
        <input
          className="w-full bg-white/5 border border-white/10 rounded-lg pl-8 pr-3 py-2 text-xs"
          placeholder="Search affected assets by name…"
          value={query}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
        />
      </div>
      {open && results.length > 0 && (
        <div className="absolute z-10 mt-1 w-full max-h-56 overflow-y-auto bg-[#121826] border border-white/10 rounded-lg shadow-xl">
          {results.map((asset) => (
            <button
              key={asset.asset_id}
              onClick={() => add(asset)}
              className="w-full text-left px-3 py-2 text-xs hover:bg-white/5 flex justify-between gap-2"
            >
              <span className="truncate">{asset.asset_name}</span>
              <span className="text-gray-500 shrink-0">{asset.asset_label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
