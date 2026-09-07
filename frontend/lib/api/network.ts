/**
 * DynamicGraph's network snapshot, read from the API instead of from a file.
 *
 * These three shapes used to be inferred with `typeof nodesSource[number]`
 * from the committed JSON. That inference was the reason the page could only
 * change on a deploy: the data was part of the bundle. Declaring the fields
 * here costs a few lines and lets the same components read a snapshot that
 * arrives over the wire and changes every session.
 */
import { useApi } from "@/lib/api/fetcher";

export interface NetworkNode {
  id: string;
  label: string;
  rank: number;
  sector: string;
  community: number;
  /** Sum of edge weights: how tied this stock is to the rest of the basket. */
  strength: number;
  degree: number;
  pagerank: number;
  clustering: number;
  betweenness_centrality: number;
  eigenvector_centrality: number;
  return_20d: number;
  volatility_20d: number;
  current_drawdown: number;
  risk_score: number;
  avg_neighbor_risk: number;
}

export interface NetworkEdge {
  rank: number;
  source: string;
  target: string;
  weight: number;
  window: number;
  edge_type: string;
  stability: number;
  /** Negative when the two move against each other. */
  signed_weight: number;
  absolute_weight: number;
  direction: string | null;
}

export interface NetworkCommunity {
  community_id: number;
  size: number;
  members: string[];
  cohesion: number;
  internal_weight: number;
  external_weight: number;
  dominant_sector: string;
  dominant_sector_share: number;
}

export interface NetworkSnapshot {
  index_name: string;
  as_of_date: string;
  generated_at: string;
  model_version: string;
  graph_layer: string;
  graph_window: number;
  node_count: number;
  /** Descriptive 0-100 state, not a probability of anything. */
  stress_score: number;
  stress_label: string;
  stress_percentile: number | null;
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  communities: NetworkCommunity[] | null;
}

/** One request shared by every panel on the page; SWR dedupes the rest. */
export function useNetworkSnapshot() {
  return useApi<NetworkSnapshot>("/api/v1/models/dynamic-graph/network");
}
