import { useRef, useEffect, useState, useCallback } from 'react';
import * as d3 from 'd3';
import type { GraphData, GraphNode } from '../lib/types';

const NODE_COLORS: Record<string, string> = {
  root: '#1E1E1E',
  citation: '#D9B756',
  author: '#7B8B9E',
  concept: '#8A9A86',
};
const TYPE_LABELS: Record<string, string> = {
  root: 'Root Paper',
  citation: 'Citing Paper',
  author: 'Author',
  concept: 'Concept',
};

interface SimNode extends GraphNode, d3.SimulationNodeDatum {}

export default function KnowledgeGraph({ graphData }: { graphData: GraphData }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const simulationRef = useRef<d3.Simulation<SimNode, any> | null>(null);

  const renderGraph = useCallback(() => {
    if (!svgRef.current || !graphData.nodes.length) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const container = svgRef.current.parentElement!;
    const width = container.clientWidth;
    const height = container.clientHeight;
    svg.attr('width', width).attr('height', height);

    const g = svg.append('g');

    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 3])
      .on('zoom', (e) => g.attr('transform', e.transform));
    svg.call(zoom);

    const nodes: SimNode[] = graphData.nodes.map(d => ({ ...d }));
    const edges = graphData.edges.map(d => ({ ...d }));

    const sim = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(edges).id((d: any) => d.id).distance(100))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius((d: any) => d.size + 5));
    simulationRef.current = sim;

    const link = g.append('g')
      .selectAll('line')
      .data(edges)
      .join('line')
      .attr('stroke', '#111111')
      .attr('stroke-width', 1)
      .attr('opacity', 0.4);

    const nodeGroup = g.append('g')
      .selectAll<SVGGElement, SimNode>('g')
      .data(nodes)
      .join('g')
      .attr('cursor', 'pointer')
      .call(d3.drag<SVGGElement, SimNode>()
        .on('start', (e, d) => {
          if (!e.active) sim.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
        .on('end', (e, d) => {
          if (!e.active) sim.alphaTarget(0);
          d.fx = null; d.fy = null;
        })
      );

    nodeGroup.append('circle')
      .attr('r', d => Math.max(d.size * 0.8, 8))
      .attr('fill', d => NODE_COLORS[d.type] || '#D9B756')
      .attr('stroke', '#111111')
      .attr('stroke-width', 2);

    nodeGroup.append('text')
      .text(d => d.label.length > 12 ? d.label.slice(0, 12) + '…' : d.label)
      .attr('font-family', "'IBM Plex Mono', monospace")
      .attr('font-size', d => d.type === 'root' ? 11 : 9)
      .attr('font-weight', d => d.type === 'root' ? 700 : 600)
      .attr('fill', d => d.type === 'root' || d.type === 'citation' ? '#F4F0EB' : '#111111')
      .attr('text-anchor', 'middle')
      .attr('dy', d => d.size * 0.8 + 14)
      .attr('opacity', 0.8);

    nodeGroup.on('click', (_e, d) => setSelected(d));
    nodeGroup.on('mouseenter', function () {
      d3.select(this).select('circle').attr('stroke-width', 3);
    });
    nodeGroup.on('mouseleave', function () {
      d3.select(this).select('circle').attr('stroke-width', 2);
    });

    sim.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y);
      nodeGroup.attr('transform', (d: any) => `translate(${d.x},${d.y})`);
    });
  }, [graphData]);

  useEffect(() => {
    renderGraph();
    return () => { simulationRef.current?.stop(); };
  }, [renderGraph, isExpanded]);

  if (!isExpanded) {
    return (
      <section id="graph" className="section-anchor max-w-[1600px] mx-auto neo-border-l neo-border-r">
        <div className="p-6 neo-border-b bg-neo-dark text-neo-parchment flex justify-between items-center">
          <div>
            <h2 className="font-serif text-3xl md:text-4xl font-bold uppercase tracking-tight">Knowledge Graph</h2>
            <p className="font-mono text-sm mt-1 text-neo-parchment/70 uppercase">Paper citation network topology</p>
          </div>
        </div>
        <div className="relative bg-neo-parchment" style={{ height: '500px' }}>
          <div className="absolute inset-0 blueprint-grid z-0" />
          <div className="relative z-10 w-full h-full">
            <svg ref={svgRef} className="w-full h-full" />
          </div>

          {/* Legend */}
          <div className="absolute bottom-4 right-4 z-30 bg-neo-parchment neo-border p-3 brutal-shadow">
            <h3 className="font-mono text-xs font-bold uppercase mb-2 neo-border-b pb-1" style={{ borderColor: '#111111' }}>Legend</h3>
            <ul className="space-y-1.5">
              {Object.entries(NODE_COLORS).map(([type, color]) => (
                <li key={type} className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full neo-border" style={{ backgroundColor: color, borderRadius: '50%' }} />
                  <span className="font-mono text-[10px] uppercase">{TYPE_LABELS[type] || type}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Expand Button */}
          <button
            onClick={() => setIsExpanded(true)}
            className="absolute bottom-4 left-4 z-30 bg-neo-parchment neo-border px-4 py-2 font-mono text-sm font-bold uppercase brutal-shadow flex items-center gap-2"
            style={{ transition: 'all 0s' }}
            onMouseEnter={e => { e.currentTarget.style.backgroundColor = '#111111'; e.currentTarget.style.color = '#F4F0EB'; }}
            onMouseLeave={e => { e.currentTarget.style.backgroundColor = '#F4F0EB'; e.currentTarget.style.color = '#111111'; }}
          >
            <span className="material-symbols-outlined text-[18px]">fullscreen</span>
            [EXPAND GRAPH]
          </button>

          {/* Selected node panel (inline) */}
          {selected && (
            <div className="absolute top-0 left-0 h-full w-[320px] bg-neo-dark neo-border-r z-40 flex flex-col overflow-y-auto"
              style={{ borderColor: '#111111' }}>
              <div className="p-3 bg-neo-black">
                <span className="font-mono text-neo-parchment text-xs uppercase tracking-widest">
                  Selected: {selected.type.toUpperCase()}
                </span>
              </div>
              <div className="p-5 flex-1">
                <h3 className="font-serif text-neo-parchment text-2xl leading-tight mb-3">{selected.label}</h3>
                {selected.year && <div className="font-mono text-neo-sage text-sm mb-1">Year: {selected.year}</div>}
                {selected.score && <div className="font-mono text-neo-mustard text-sm">Score: {selected.score}/5</div>}
                <div className="mt-4 bg-neo-sage neo-border p-3">
                  <span className="font-mono text-[10px] font-bold uppercase text-neo-black">Node Type</span>
                  <p className="font-mono text-xs text-neo-black mt-1">{TYPE_LABELS[selected.type] || selected.type}</p>
                </div>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="m-4 bg-neo-parchment neo-border text-neo-black font-mono font-bold py-2 uppercase text-sm"
                style={{ transition: 'all 0s' }}
              >
                Close Panel
              </button>
            </div>
          )}
        </div>
      </section>
    );
  }

  // Fullscreen mode
  return (
    <div className="fixed inset-0 z-[9999] bg-neo-parchment" style={{ overflow: 'hidden' }}>
      <div className="absolute inset-0 blueprint-grid z-0" />
      <div className="relative z-10 w-full h-full">
        <svg ref={svgRef} className="w-full h-full" />
      </div>

      {/* Close button */}
      <button
        onClick={() => setIsExpanded(false)}
        className="absolute top-6 right-6 z-50 w-16 h-16 bg-neo-mustard neo-border flex items-center justify-center font-mono font-bold text-neo-black text-2xl brutal-shadow"
        style={{ transition: 'all 0s' }}
        onMouseEnter={e => { e.currentTarget.style.backgroundColor = '#111111'; e.currentTarget.style.color = '#D9B756'; }}
        onMouseLeave={e => { e.currentTarget.style.backgroundColor = '#D9B756'; e.currentTarget.style.color = '#111111'; }}
      >
        [X]
      </button>

      {/* Zoom controls */}
      <div className="absolute top-6 right-28 z-50 flex flex-col neo-border bg-neo-parchment brutal-shadow">
        <button className="p-2 neo-border-b w-12 h-12 flex items-center justify-center"
          style={{ transition: 'all 0s' }}
          onMouseEnter={e => { e.currentTarget.style.backgroundColor = '#1E1E1E'; e.currentTarget.style.color = '#F4F0EB'; }}
          onMouseLeave={e => { e.currentTarget.style.backgroundColor = '#F4F0EB'; e.currentTarget.style.color = '#111111'; }}
          onClick={() => {
            if (!svgRef.current) return;
            const svg = d3.select(svgRef.current);
            svg.transition().duration(300).call(
              d3.zoom<SVGSVGElement, unknown>().scaleExtent([0.3, 3]).on('zoom', () => {}).scaleBy as any, 1.3
            );
          }}>
          <span className="material-symbols-outlined">add</span>
        </button>
        <button className="p-2 w-12 h-12 flex items-center justify-center"
          style={{ transition: 'all 0s' }}
          onMouseEnter={e => { e.currentTarget.style.backgroundColor = '#1E1E1E'; e.currentTarget.style.color = '#F4F0EB'; }}
          onMouseLeave={e => { e.currentTarget.style.backgroundColor = '#F4F0EB'; e.currentTarget.style.color = '#111111'; }}
          onClick={() => {
            if (!svgRef.current) return;
            const svg = d3.select(svgRef.current);
            svg.transition().duration(300).call(
              d3.zoom<SVGSVGElement, unknown>().scaleExtent([0.3, 3]).on('zoom', () => {}).scaleBy as any, 0.7
            );
          }}>
          <span className="material-symbols-outlined">remove</span>
        </button>
      </div>

      {/* Legend */}
      <div className="absolute bottom-6 right-6 z-40 bg-neo-parchment neo-border p-4 brutal-shadow">
        <h3 className="font-mono text-xs font-bold uppercase mb-3 neo-border-b pb-1" style={{ borderColor: '#111111' }}>Topology Legend</h3>
        <ul className="space-y-2">
          {Object.entries(NODE_COLORS).map(([type, color]) => (
            <li key={type} className="flex items-center gap-3">
              <div className="w-4 h-4 neo-border" style={{ backgroundColor: color, borderRadius: '50%' }} />
              <span className="font-mono text-xs uppercase">{TYPE_LABELS[type] || type}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Coordinates (decorative) */}
      <div className="absolute bottom-6 left-6 z-40">
        <div className="font-mono text-xs text-neo-black/50 bg-neo-parchment neo-border px-2 py-1">
          NODES: {graphData.nodes.length} / EDGES: {graphData.edges.length} / ZOOM: 1.0
        </div>
      </div>

      {/* Selected node overlay */}
      {selected && (
        <aside className="absolute top-0 left-0 h-full w-[360px] bg-neo-dark neo-border-r z-40 flex flex-col overflow-y-auto"
          style={{ borderColor: '#111111' }}>
          <div className="p-4 bg-neo-black">
            <span className="font-mono text-neo-parchment text-xs uppercase tracking-widest">
              Selected Node: {selected.label}
            </span>
          </div>
          <div className="p-6 neo-border-b" style={{ borderColor: '#111111' }}>
            <h1 className="font-serif text-neo-parchment text-3xl leading-tight mb-4">{selected.label}</h1>
            <div className="font-mono text-neo-sage text-sm uppercase">{TYPE_LABELS[selected.type]}</div>
            {selected.year && <div className="font-mono text-neo-parchment/70 text-xs mt-1">Year: {selected.year}</div>}
          </div>
          {selected.score != null && (
            <div className="grid grid-cols-2 neo-border-b" style={{ borderColor: '#111111' }}>
              <div className="p-4 neo-border-r" style={{ borderColor: '#111111' }}>
                <div className="font-mono text-neo-parchment/50 text-xs mb-1 uppercase">Score</div>
                <div className="font-mono text-neo-parchment text-2xl font-semibold">{selected.score}/5</div>
              </div>
              <div className="p-4">
                <div className="font-mono text-neo-parchment/50 text-xs mb-1 uppercase">Type</div>
                <div className="font-mono text-neo-mustard text-lg font-semibold uppercase">{selected.type}</div>
              </div>
            </div>
          )}
          <div className="p-6 flex-grow">
            <div className="bg-neo-sage neo-border p-4 brutal-shadow">
              <div className="flex items-center gap-2 mb-3 neo-border-b pb-2" style={{ borderColor: '#111111' }}>
                <span className="material-symbols-outlined text-neo-black">analytics</span>
                <span className="font-mono text-neo-black text-xs font-bold uppercase">Node Analysis</span>
              </div>
              <p className="font-mono text-neo-black text-sm leading-relaxed">
                {selected.type === 'root'
                  ? 'Central hub node. All citation edges converge to this paper.'
                  : selected.type === 'citation'
                  ? 'Citing paper node. Connected to the root paper through a direct citation relationship.'
                  : selected.type === 'author'
                  ? 'Scholar node. Connected through authorship relationship.'
                  : 'Conceptual topic node linking related papers in this domain.'}
              </p>
            </div>
          </div>
          <div className="p-6 mt-auto">
            <button
              onClick={() => setSelected(null)}
              className="w-full bg-neo-parchment neo-border text-neo-black font-mono font-bold py-3 uppercase brutal-shadow"
              style={{ transition: 'all 0s' }}
              onMouseEnter={e => { e.currentTarget.style.backgroundColor = '#D9B756'; }}
              onMouseLeave={e => { e.currentTarget.style.backgroundColor = '#F4F0EB'; }}
            >
              Close Panel →
            </button>
          </div>
        </aside>
      )}
    </div>
  );
}
