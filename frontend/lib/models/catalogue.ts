import "server-only";

import {
  MODELS,
  getModel,
  publicModels,
  requiresAuth,
  type ModelCardData,
  type ModelConfig,
  type ModelStatus,
} from "@/config/models";
import {
  getModelResearch,
  type ModelResearchProfile,
} from "@/config/model-research";

interface ApiModelSummary {
  slug: string;
  name: string;
  code: string;
  markets: string[];
  category: ModelConfig["category"];
  status: ModelStatus;
  version: string;
  horizons: number[];
  access: ModelConfig["access"];
  locked: boolean;
  featured: boolean;
  tagline: ModelConfig["tagline"];
  key_output: ModelConfig["keyOutput"];
  sparkline: number[] | null;
  sparkline_label: ModelConfig["sparklineLabel"] | null;
  updated_at: string;
}

interface ApiModelDetail extends ApiModelSummary {
  show_forecast: boolean;
  show_performance: boolean;
  description: ModelConfig["description"];
  architecture: ModelConfig["architecture"] | null;
  research_profile: ModelResearchProfile | null;
}

interface ApiModelList {
  models: ApiModelSummary[];
}

export interface PublishedModel {
  model: ModelConfig;
  research: ModelResearchProfile | null;
  locked: boolean;
}

export function usesDatabaseApi() {
  return process.env.DATA_MODE === "api";
}

function apiBase() {
  const base = process.env.API_BASE_URL?.replace(/\/$/, "");
  if (!base) {
    throw new Error("API_BASE_URL is required when DATA_MODE=api");
  }
  return base;
}

async function serverApiFetch<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBase()}${path}`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Backend API ${response.status} for ${path}`);
  }
  return (await response.json()) as T;
}

function toCard(model: ApiModelSummary): ModelCardData {
  return {
    slug: model.slug,
    name: model.name,
    code: model.code,
    markets: model.markets,
    category: model.category,
    status: model.status,
    access: model.access,
    featured: model.featured,
    version: model.version,
    updatedAt: model.updated_at,
    sparkline: model.sparkline ?? undefined,
    sparklineLabel: model.sparkline_label ?? undefined,
    // How to scale the card figure and where its reference sits. This
    // describes how a number is drawn, not what the number is, so it
    // stays in the front-end config instead of making the round trip
    // through the database.
    sparklineScale: getModel(model.slug)?.sparklineScale,
    horizons: model.horizons,
    tagline: model.tagline,
    keyOutput: model.key_output,
  };
}

export async function getPublishedModels(): Promise<ModelCardData[]> {
  if (!usesDatabaseApi()) return publicModels();
  const payload = await serverApiFetch<ApiModelList>("/api/v1/models");
  return payload.models.map(toCard);
}

export async function getPublishedModel(
  slug: string
): Promise<PublishedModel | null> {
  if (!usesDatabaseApi()) {
    const model = getModel(slug);
    if (!model || model.visibility !== "public") return null;
    return {
      model,
      research: getModelResearch(slug) ?? null,
      locked: requiresAuth(model),
    };
  }

  const response = await fetch(`${apiBase()}/api/v1/models/${slug}`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`Backend API ${response.status} for model ${slug}`);
  }
  const item = (await response.json()) as ApiModelDetail;
  const model: ModelConfig = {
    ...toCard(item),
    visibility: "public",
    show_forecast: item.show_forecast,
    show_performance: item.show_performance,
    show_internal_signal: false,
    description: item.description,
    architecture: item.architecture ?? undefined,
  };
  return {
    model,
    research: item.research_profile,
    locked: item.locked,
  };
}

// Kept as a compile-time assertion that the fixture and API mapping stay
// compatible when ModelConfig evolves.
void (MODELS satisfies ModelConfig[]);
