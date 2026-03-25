import { useRef, useEffect } from 'react';
import * as d3 from 'd3';
import type { GraphData, GraphNode } from '../lib/types';

const NODE_COLORS: Record<string, string> = {
  root: '#1E1E1E',
  citation: '#D9B756',
  author: '#7B8B9E',
  concept: '#8A9A86',
};

const TYPE_LABELS: Record<string, string> = {
  root: '目标论文',
  citation: '引用论文',
  author: '作者',
  concept: '来源',
};

export default function MiniStarGraph({ graphData }: { graphData: GraphData }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || !containerRef.current || !graphData?.nodes?.length) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const container = containerRef.current;
    let tooltipEl = document.getElementById('star-graph-tooltip') as HTMLDivElement;
    if (!tooltipEl) {
      tooltipEl = document.createElement('div');
      tooltipEl.id = 'star-graph-tooltip';
      Object.assign(tooltipEl.style, {
        position: 'fixed',
        pointerEvents: 'none',
        opacity: '0',
        background: '#F4F0EB',
        color: '#111111',
        border: '2px solid #111111',
        padding: '6px 10px',
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: '11px',
        fontWeight: '700',
        lineHeight: '1.3',
        maxWidth: '240px',
        zIndex: '9999',
        textTransform: 'uppercase',
        letterSpacing: '0.02em',
        transition: 'opacity 0.15s',
        whiteSpace: 'normal',
        wordBreak: 'break-word',
      });
      document.body.appendChild(tooltipEl);
    }

    const rect = svgRef.current.getBoundingClientRect();
    const width = rect.width || svgRef.current.clientWidth || 280;
    const height = rect.height || svgRef.current.clientHeight || 240;

    const nodes = graphData.nodes.map(n => ({ ...n }));
    const edges = graphData.edges.map(e => ({ ...e }));

    const simulation = d3.forceSimulation(nodes as d3.SimulationNodeDatum[])
      .force('link', d3.forceLink(edges).id((d: any) => d.id).distance(50))
      .force('charge', d3.forceManyBody().strength(-80))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius((d: any) => (d as GraphNode).size / 2 + 4));

    const link = svg.append('g')
      .selectAll('line')
      .data(edges)
      .join('line')
      .attr('stroke', '#F4F0EB')
      .attr('stroke-width', 1)
      .attr('opacity', 0.25);

    const node = svg.append('g')
      .selectAll('circle')
      .data(nodes)
      .join('circle')
      .attr('r', (d) => Math.max(d.size / 3, 4))
      .attr('fill', (d) => NODE_COLORS[d.type] || '#D9B756')
      .attr('stroke', '#F4F0EB')
      .attr('stroke-width', 1.5)
      .attr('cursor', 'pointer')
      .on('mouseenter', function (_e, d) {
        d3.select(this)
          .attr('fill', '#8A9A86')
          .attr('stroke-width', 3);
        const tag = TYPE_LABELS[d.type] || d.type;
        const scoreText = d.score != null ? ` · Score: ${d.score}` : '';
        const yearText = d.year ? ` · ${d.year}` : '';
        tooltipEl.innerHTML = `<span style="font-size:9px;opacity:0.6">${tag}${yearText}${scoreText}</span><br/>${d.label}`;
        tooltipEl.style.opacity = '1';
      })
      .on('mousemove', function (e) {
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const tw = tooltipEl.offsetWidth;
        const th = tooltipEl.offsetHeight;
        const left = e.clientX + tw + 16 > vw ? e.clientX - tw - 8 : e.clientX + 12;
        const top = Math.max(4, Math.min(e.clientY - 10, vh - th - 4));
        tooltipEl.style.left = `${left}px`;
        tooltipEl.style.top = `${top}px`;
      })
      .on('mouseleave', function (_e, d) {
        d3.select(this)
          .attr('fill', NODE_COLORS[d.type] || '#D9B756')
          .attr('stroke-width', 1.5);
        tooltipEl.style.opacity = '0';
      });

    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y);
      node
        .attr('cx', (d: any) => Math.max(10, Math.min(width - 10, d.x)))
        .attr('cy', (d: any) => Math.max(10, Math.min(height - 10, d.y)));
    });

    return () => {
      simulation.stop();
      tooltipEl.style.opacity = '0';
    };
  }, [graphData]);

  return (
    <div ref={containerRef} className="w-full h-full neo-border relative"
      style={{
        backgroundImage: 'radial-gradient(#F4F0EB 0.5px, transparent 0.5px)',
        backgroundSize: '20px 20px',
        backgroundPosition: '-10px -10px',
        minHeight: '200px',
        overflow: 'hidden',
      }}>
      <svg ref={svgRef} className="w-full h-full" style={{ minHeight: '200px' }} />
    </div>
  );
}
