import { useEffect, useRef } from "react";
import * as d3 from "d3";

interface Module {
  caller: string;
  caller_file: string;
  called: string;
  called_file: string;
}

interface Props {
  modules: Module[];
  changedFiles: string[];
}

export function BlastRadiusGraph({ modules, changedFiles }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || modules.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const width = svgRef.current.clientWidth || 600;
    const height = 400;

    // Build graph data
    const nodes = new Map<
      string,
      { id: string; isChanged: boolean; group: number }
    >();
    const links: { source: string; target: string }[] = [];

    changedFiles.forEach((f) => {
      nodes.set(f, { id: f, isChanged: true, group: 1 });
    });

    modules.forEach((m) => {
      if (!nodes.has(m.caller_file)) {
        nodes.set(m.caller_file, {
          id: m.caller_file,
          isChanged: false,
          group: 2,
        });
      }
      if (!nodes.has(m.called_file)) {
        nodes.set(m.called_file, {
          id: m.called_file,
          isChanged: false,
          group: 3,
        });
      }
      links.push({ source: m.caller_file, target: m.called_file });
    });

    const nodeArray = Array.from(nodes.values());

    // Force simulation
    const simulation = d3
      .forceSimulation(nodeArray as any)
      .force(
        "link",
        d3
          .forceLink(links)
          .id((d: any) => d.id)
          .distance(80)
      )
      .force("charge", d3.forceManyBody().strength(-300))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius(30));

    const g = svg.append("g");

    // Links
    const link = g
      .append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", "#475569")
      .attr("stroke-width", 1.5)
      .attr("stroke-opacity", 0.6);

    // Nodes
    const node = g
      .append("g")
      .selectAll("circle")
      .data(nodeArray)
      .join("circle")
      .attr("r", (d) => (d.isChanged ? 10 : 6))
      .attr("fill", (d) => (d.isChanged ? "#f59e0b" : "#3b82f6"))
      .attr("stroke", "#1e293b")
      .attr("stroke-width", 2)
      .call(
        d3
          .drag<any, any>()
          .on("start", (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      );

    // Labels
    const label = g
      .append("g")
      .selectAll("text")
      .data(nodeArray)
      .join("text")
      .text((d) => d.id.split("/").pop() || d.id)
      .attr("font-size", 10)
      .attr("fill", "#94a3b8")
      .attr("dx", 12)
      .attr("dy", 4);

    simulation.on("tick", () => {
      link
        .attr("x1", (d: any) => d.source.x)
        .attr("y1", (d: any) => d.source.y)
        .attr("x2", (d: any) => d.target.x)
        .attr("y2", (d: any) => d.target.y);

      node.attr("cx", (d: any) => d.x).attr("cy", (d: any) => d.y);

      label.attr("x", (d: any) => d.x).attr("y", (d: any) => d.y);
    });

    return () => {
      simulation.stop();
    };
  }, [modules, changedFiles]);

  if (modules.length === 0) {
    return (
      <div className="text-center py-8 text-slate-500">
        <p>No downstream impact detected</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
      <h3 className="font-medium mb-2">Blast Radius</h3>
      <p className="text-xs text-slate-500 mb-3">
        {modules.length} downstream callers affected across{" "}
        {new Set(modules.map((m) => m.caller_file)).size} files
      </p>
      <svg ref={svgRef} className="w-full" style={{ height: 400 }} />
      <div className="flex gap-4 mt-2 text-xs text-slate-500">
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-full bg-amber-500 inline-block" />
          Changed files
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 rounded-full bg-blue-500 inline-block" />
          Affected callers
        </span>
      </div>
    </div>
  );
}
