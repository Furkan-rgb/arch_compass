/** The row that decides which graph is on screen: search, lens, filters, and the highlight. */

import { Search } from "lucide-react";
import { type FormEvent } from "react";

import { humanizeLabel } from "../components";
import type { AtlasLens, RepositoryAtlasProps } from "./graph-model";
import { PULSES, type AtlasPulse } from "./pulse";

export function LensControls({
  lens,
  onLens,
  searchValue,
  onSearchValue,
  onSubmitSearch,
  hideTests,
  onHideTests,
  publicOnly,
  onPublicOnly,
  pulse,
  onPulse,
  onExploreAtlas,
  loading,
}: {
  lens: AtlasLens;
  onLens: (lens: AtlasLens) => void;
  searchValue: string;
  onSearchValue: (value: string) => void;
  onSubmitSearch: (event: FormEvent) => void;
  hideTests: boolean;
  onHideTests: () => void;
  publicOnly: boolean;
  onPublicOnly: () => void;
  pulse: AtlasPulse;
  onPulse: (pulse: AtlasPulse) => void;
  onExploreAtlas?: RepositoryAtlasProps["onExploreAtlas"];
  loading: boolean;
}) {
  return (
    <div className="atlas-explorer" aria-label="Atlas exploration controls">
      <form className="atlas-search" role="search" onSubmit={onSubmitSearch}>
        <Search size={14} />
        <input
          value={searchValue}
          onChange={(event) => onSearchValue(event.target.value)}
          placeholder="Find a module, class, or path"
          aria-label="Search repository atlas"
        />
        <button type="submit">Find</button>
      </form>
      <div className="atlas-lenses" role="group" aria-label="Graph lens">
        {(["structure", "dependencies", "risk"] as const).map((value) => (
          <button
            key={value}
            type="button"
            className={lens === value ? "active" : ""}
            aria-pressed={lens === value}
            onClick={() => onLens(value)}
          >
            {humanizeLabel(value)}
          </button>
        ))}
      </div>
      <button
        type="button"
        className={`atlas-filter-toggle ${hideTests ? "active" : ""}`}
        aria-pressed={hideTests}
        onClick={onHideTests}
      >
        Hide tests
      </button>
      <button
        type="button"
        className={`atlas-filter-toggle ${publicOnly ? "active" : ""}`}
        aria-pressed={publicOnly}
        onClick={onPublicOnly}
      >
        Public only
      </button>
      {/* A select rather than a fifth row of pill buttons. The lens changes which graph is
          on screen and earns its width; this only changes how the selected node's
          neighbourhood moves, and a control that is set once should not out-shout one that
          is pressed constantly. */}
      <label className="atlas-pulse-select">
        <span>Highlight</span>
        <select
          value={pulse}
          aria-label="Highlight motion for the selected node"
          onChange={(event) => onPulse(event.target.value as AtlasPulse)}
        >
          {PULSES.map(({ value, label }) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {lens === "risk" && onExploreAtlas && (
        <>
          <button
            type="button"
            className="atlas-filter-toggle"
            disabled={loading}
            onClick={() => onExploreAtlas("signals")}
          >
            Surface signals
          </button>
          <button
            type="button"
            className="atlas-filter-toggle"
            disabled={loading}
            onClick={() => onExploreAtlas("cycles")}
          >
            Surface cycles
          </button>
        </>
      )}
    </div>
  );
}
