import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";
import type { GraphElements, GraphNodeData } from "../types";

const STYLE = [
  {
    selector: "node",
    style: {
      "background-color": "#9aa4b2",
      label: "data(label)",
      "font-size": 8,
      color: "#4b5563",
      width: 22,
      height: 22,
      "text-valign": "bottom",
      "text-margin-y": 4,
    },
  },
  { selector: 'node[dataset_label = "licit"]', style: { "background-color": "#4c9a6a" } },
  { selector: "node[?flagged]", style: { "background-color": "#d64545" } },
  {
    selector: 'node[dataset_label = "illicit"]',
    style: { "border-width": 3, "border-color": "#5a0000" },
  },
  {
    selector: "node[?is_case]",
    style: {
      width: 40,
      height: 40,
      "border-width": 4,
      "border-color": "#f2b705",
      "font-size": 10,
      "font-weight": "bold",
      color: "#111827",
    },
  },
  {
    selector: "edge",
    style: {
      width: 1.5,
      "line-color": "#c3c9d2",
      "target-arrow-color": "#c3c9d2",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      "arrow-scale": 0.8,
    },
  },
  { selector: "node:selected", style: { "overlay-color": "#2563eb", "overlay-opacity": 0.2 } },
];

interface Props {
  elements: GraphElements;
  onSelect: (node: GraphNodeData | null) => void;
}

export function GraphView({ elements, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!container.current) return;

    const cy = cytoscape({
      container: container.current,
      elements: [...elements.nodes, ...elements.edges] as unknown as cytoscape.ElementDefinition[],
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      style: STYLE as any,
      layout: { name: "cose", animate: false, padding: 30 },
      wheelSensitivity: 0.3,
    });

    cy.on("tap", "node", (event) => onSelect(event.target.data() as GraphNodeData));
    cy.on("tap", (event) => {
      if (event.target === cy) onSelect(null);
    });

    return () => cy.destroy();
  }, [elements, onSelect]);

  return (
    <div className="graph-wrap">
      <div ref={container} className="graph" />
      <div className="legend">
        <span><i className="dot case" /> This case</span>
        <span><i className="dot flagged" /> Flagged high risk</span>
        <span><i className="dot licit" /> Known licit</span>
        <span><i className="dot unknown" /> Unknown / not flagged</span>
        <span><i className="dot illicit" /> Known illicit (dark ring)</span>
      </div>
    </div>
  );
}
