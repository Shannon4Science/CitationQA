import { useState, useMemo } from 'react';
import type { Evaluation } from '../lib/types';

interface Props {
  evaluations: Evaluation[];
}

const TYPE_LABELS: Record<string, string> = {
  core_methodology: 'Methodology',
  literature_review: 'Literature Review',
  supporting_evidence: 'Supporting Evidence',
  contradictory: 'Contradictory',
  background_mention: 'Background',
  related_work_brief: 'Related Work',
  method_reference: 'Method Reference',
  experiment_comparison: 'Experiment Comparison',
  multiple_deep: 'Deep Multi-Citation',
  unknown: 'Unknown',
};

const SCORE_COLOR: Record<string, string> = {
  high: 'bg-neo-sage text-neo-black',
  medium: 'bg-neo-mustard text-neo-black',
  low: 'bg-neo-blue text-white',
};

function getScoreLevel(score: number) {
  if (score >= 4) return 'high';
  if (score >= 2.5) return 'medium';
  return 'low';
}

export default function CitationGallery({ evaluations }: Props) {
  const [typeFilters, setTypeFilters] = useState<Set<string>>(new Set(Object.keys(TYPE_LABELS)));
  const [sortBy, setSortBy] = useState<'relevance' | 'date' | 'impact'>('relevance');

  const allTypes = useMemo(() => {
    const types = new Set<string>();
    evaluations.forEach((e) => types.add(e.citation_type));
    return Array.from(types);
  }, [evaluations]);

  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    evaluations.forEach((e) => {
      counts[e.citation_type] = (counts[e.citation_type] || 0) + 1;
    });
    return counts;
  }, [evaluations]);

  const filtered = useMemo(() => {
    let result = evaluations.filter((e) => typeFilters.has(e.citation_type));
    if (sortBy === 'date') result = [...result].sort((a, b) => (b.citing_year || 0) - (a.citing_year || 0));
    else if (sortBy === 'impact') result = [...result].sort((a, b) => b.quality_score - a.quality_score);
    return result;
  }, [evaluations, typeFilters, sortBy]);

  const toggleFilter = (type: string) => {
    setTypeFilters((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  return (
    <section id="gallery" className="section-anchor max-w-[1600px] mx-auto neo-border-l neo-border-r">
      {/* Section Header */}
      <div className="p-6 bg-neo-dark text-neo-parchment neo-border-b flex justify-between items-center">
        <div>
          <h2 className="font-serif text-3xl md:text-4xl font-bold uppercase tracking-tight">Citation Gallery</h2>
          <p className="font-mono text-sm mt-1 text-neo-parchment/70 uppercase">
            INDEX: {evaluations.length} citations analyzed
          </p>
        </div>
      </div>

      <div className="flex flex-col md:flex-row min-h-[600px]">
        {/* Filter Sidebar */}
        <aside className="w-full md:w-64 neo-border-r flex-shrink-0 bg-neo-parchment">
          <div className="p-6">
            <h3 className="font-mono font-bold text-xs uppercase mb-4 tracking-wider neo-border-b pb-2 border-neo-black">
              Citation Type
            </h3>
            <ul className="space-y-3">
              {allTypes.map((type) => (
                <li key={type} className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    className="brutal-checkbox"
                    checked={typeFilters.has(type)}
                    onChange={() => toggleFilter(type)}
                  />
                  <label className="text-sm font-medium uppercase cursor-pointer select-none flex-1"
                    onClick={() => toggleFilter(type)}>
                    {TYPE_LABELS[type] || type}
                  </label>
                  <span className="font-mono text-xs opacity-60">{typeCounts[type] || 0}</span>
                </li>
              ))}
            </ul>

            <div className="mt-8">
              <h3 className="font-mono font-bold text-xs uppercase mb-4 tracking-wider neo-border-b pb-2 border-neo-black">
                Sort By
              </h3>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as any)}
                className="w-full neo-border bg-white font-mono text-xs uppercase py-2 px-3 focus:outline-none cursor-pointer"
              >
                <option value="relevance">Relevance</option>
                <option value="date">Date (Newest)</option>
                <option value="impact">Impact (Highest)</option>
              </select>
            </div>
          </div>
        </aside>

        {/* Cards Grid */}
        <div className="flex-1 p-6 bg-neo-parchment overflow-y-auto">
          <div className="flex justify-between items-center mb-6 neo-border-b pb-3 border-neo-black">
            <p className="font-mono text-sm font-bold uppercase">Showing: {filtered.length} Results</p>
          </div>

          {filtered.length === 0 ? (
            <div className="w-full h-64 crosshatch neo-border flex items-center justify-center">
              <div className="bg-white p-6 neo-border text-center">
                <h2 className="font-mono text-xl font-bold uppercase">No Citations Match Filter</h2>
                <p className="text-sm mt-2">ADJUST PARAMETERS IN LEFT PANEL</p>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {filtered.map((ev, i) => (
                <article key={i} className="neo-border bg-white flex flex-col">
                  <div className="p-5 flex-1">
                    {/* Badges */}
                    <div className="flex flex-wrap gap-2 mb-4">
                      <span className="bg-neo-black text-neo-parchment font-mono text-[11px] px-2 py-0.5 uppercase">
                        {TYPE_LABELS[ev.citation_type] || ev.citation_type}
                      </span>
                      <span className={`font-mono text-[11px] px-2 py-0.5 uppercase ${SCORE_COLOR[getScoreLevel(ev.quality_score)]}`}>
                        Score {ev.quality_score}/5
                      </span>
                      {ev.citation_depth && (
                        <span className="bg-neo-blue/20 text-neo-black font-mono text-[11px] px-2 py-0.5 uppercase">
                          {ev.citation_depth}
                        </span>
                      )}
                    </div>

                    <h2 className="text-lg font-bold leading-tight mb-2">{ev.citing_title}</h2>
                    <p className="font-mono text-xs text-neo-black/60 mb-4 uppercase">
                      {ev.citing_year} &middot; {ev.publication_source}
                    </p>

                    {/* Citation Context */}
                    {ev.citation_locations && ev.citation_locations.length > 0 && (
                      <div className="neo-border-t pt-3 mt-3">
                        <p className="font-mono text-xs font-bold uppercase mb-2">Cited in:</p>
                        <div className="space-y-2">
                          {ev.citation_locations.map((loc: any, j: number) => (
                            <div key={j} className="bg-neo-parchment p-2 neo-border">
                              <span className="font-mono text-[10px] font-bold uppercase block mb-1">
                                {typeof loc === 'string' ? loc : loc.section || 'Unknown Section'}
                              </span>
                              {typeof loc === 'object' && loc.context && (
                                <p className="font-mono text-[10px] leading-relaxed opacity-70 line-clamp-3">
                                  {loc.context.slice(0, 200)}{loc.context.length > 200 ? '…' : ''}
                                </p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* LLM Summary Block */}
                  <div className="bg-neo-sage neo-border-t p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="material-symbols-outlined text-[16px] text-neo-black">smart_toy</span>
                      <span className="font-mono text-[10px] font-bold uppercase tracking-widest text-neo-black">
                        LLM Analysis
                      </span>
                    </div>
                    <p className="font-mono text-xs text-neo-black leading-relaxed uppercase">
                      {ev.summary}
                    </p>
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
