export type SourceCard = {
  title: string;
  subtitle?: string;
  description?: string;
  kind?: string;
  metric?: string;
  confidence?: number;
  quote?: string;
  url?: string;
};

export type Kpi = { label: string; value: string };

export type Opportunity = {
  zone: string;
  category: string;
  score: number;
  risk: number;
  supply_gap: number;
  competition_level: string;
  providers: number;
  providers_per_100k: number;
  population: number;
  density: number;
};

export type RetrievedContext = {
  title: string;
  source_path: string;
  source?: string;
  kind: string;
  score: number;
  text: string;
  content?: string;
};

export type ChatAnswer = {
  query: string;
  question?: string;
  answer_markdown: string;
  top_zone: string;
  score: number;
  risk: number;
  category: string;
  sector?: string | null;
  subcategory?: string | null;
  subcategory_label?: string | null;
  sources: SourceCard[];
  kpis: Kpi[];
  map_focus: { label: string; lat: number; lon: number; zoom: number };
  related_opportunities: Opportunity[];
  retrieved_contexts: RetrievedContext[];
  rag_status: string;
  model?: string;
  suggested_view?: "intelligence" | "map" | "reports" | "sources";
  suggested_questions?: string[];
  // Conversational memory (echoed back by the client on the next turn):
  investor_profile?: Record<string, any> | null;
  standalone_query?: string | null;
  debug?: Record<string, any> | null;
  web_results?: Array<{ title: string; url: string; snippet?: string }>;
};

export type DataFileStatus = {
  exists: boolean;
  path: string;
  updated_at: number | null;
  size_bytes: number;
};

export type AdminDataStatus = {
  admin_mode: boolean;
  token_configured: boolean;
  files: Record<string, DataFileStatus>;
};

export type AdminRefreshResult = {
  ok: boolean;
  elapsed_seconds: number;
  failed_step?: string;
  steps?: Array<{
    name: string;
    returncode: number;
    elapsed_seconds: number;
    stdout_tail: string;
    stderr_tail: string;
  }>;
  rag?: {
    ok: boolean;
    chunk_count?: number;
    embedding_model?: string;
    chat_model?: string;
    error?: string;
  };
  status?: AdminDataStatus;
};

const CHAT_REQUEST_TIMEOUT_MS = 180_000;

// Backend base URL. Defaults to same-origin "/api" (works when the API is on the
// same Vercel deployment). Set VITE_API_BASE_URL to point at an external backend
// (e.g. a host running Ollama + qwen2.5, or a serverless API on another domain).
const API_BASE = (import.meta as any).env?.VITE_API_BASE_URL?.replace(/\/$/, "") || "/api";
const apiUrl = (path: string) => `${API_BASE}${path}`;

export const fallbackAnswer: ChatAnswer = {
  query: "Nouvelle discussion",
  answer_markdown:
    "Bonjour. Posez une question sur l'implantation à Casablanca pour lancer une analyse Invest Search.\n\n" +
    "Vous pouvez demander une recommandation pour une pharmacie, une clinique, un laboratoire, " +
    "mais aussi un restaurant, un commerce, une école ou une salle de sport — ou indiquer votre budget.\n\n" +
    "Exemples utiles :\n\n" +
    "- Où ouvrir une pharmacie à faible concurrence ?\n" +
    "- Comparer Anfa et Maarif pour une clinique de jour.\n" +
    "- Génère un rapport investisseur pour une clinique vétérinaire.\n" +
    "- Quels quartiers ont une faible couverture médicale ?",
  top_zone: "Casablanca",
  score: 0,
  risk: 0,
  category: "General",
  sources: [
    { title: "HCP Recensement", subtitle: "Population, densité et structure territoriale" },
    { title: "OpenStreetMap", subtitle: "Points santé et multi-secteurs géocodés" },
    { title: "Min. Santé", subtitle: "Réglementations sanitaires" },
  ],
  kpis: [
    { label: "Périmètre", value: "Casablanca" },
    { label: "Domaines", value: "Santé, food, retail, éducation, wellness" },
    { label: "Sources", value: "HCP + OSM + Santé" },
    { label: "État", value: "Prêt" },
  ],
  map_focus: { label: "Casablanca", lat: 33.57, lon: -7.59, zoom: 12 },
  related_opportunities: [],
  retrieved_contexts: [],
  rag_status: "ready",
  suggested_view: "intelligence",
};

function normalize(raw: any): ChatAnswer {
  return {
    query: raw.question || raw.query || "",
    question: raw.question,
    answer_markdown: raw.answer_markdown || "",
    top_zone: raw.top_zone || "Casablanca",
    score: raw.score ?? 0,
    risk: raw.risk ?? 0,
    category: raw.category || "",
    sector: raw.sector ?? null,
    subcategory: raw.subcategory ?? null,
    subcategory_label: raw.subcategory_label ?? null,
    sources: (raw.sources || []).map((s: any) => ({
      ...s,
      description: s.subtitle || s.description || s.kind || "",
    })),
    kpis: raw.kpis || [],
    map_focus: raw.map_focus || { label: "Casablanca", lat: 33.57, lon: -7.59, zoom: 12 },
    related_opportunities: raw.related_opportunities || [],
    retrieved_contexts: (raw.retrieved_contexts || []).map((c: any) => ({
      ...c,
      source: c.source_path || "",
      content: c.text || "",
    })),
    rag_status: raw.rag_status || "unknown",
    model: raw.model,
    suggested_view: raw.suggested_view,
    suggested_questions: raw.suggested_questions,
    investor_profile: raw.investor_profile ?? null,
    standalone_query: raw.standalone_query ?? null,
    debug: raw.debug ?? null,
    web_results: raw.web_results ?? undefined,
  };
}

const DEBUG = typeof window !== "undefined" && window.localStorage?.getItem("invest-debug") === "1";

export type AskOptions = {
  investorProfile?: Record<string, any> | null;
  history?: Array<{ role: string; content: string }>;
  webSearch?: boolean;
};

export async function askInvestSearch(message: string, opts?: AskOptions): Promise<ChatAnswer> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), CHAT_REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(apiUrl("/chat"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        message,
        category: "Small Private Clinic",
        locale: "fr",
        // Conversational memory: the server is stateless, so the client carries it.
        investor_profile: opts?.investorProfile ?? null,
        history: opts?.history ?? [],
        web_search: opts?.webSearch ?? false,
        debug: DEBUG,
      }),
    });
    if (!response.ok) throw new Error(`API ${response.status}`);
    return normalize(await response.json());
  } catch {
    return { ...fallbackAnswer, query: message };
  } finally {
    window.clearTimeout(timeout);
  }
}

export type RagHealth = {
  ollama_available?: boolean;
  llm_available?: boolean;
  llm_provider?: string;
  chat_model?: string;
  embedding_model?: string;
  chunk_count?: number;
};

export async function getRagStatus(): Promise<RagHealth | null> {
  try {
    const r = await fetch(apiUrl("/rag/status"));
    return r.ok ? ((await r.json()) as RagHealth) : null;
  } catch {
    return null;
  }
}

export async function getAdminDataStatus(): Promise<AdminDataStatus> {
  const response = await fetch(apiUrl("/admin/data-status"));
  if (!response.ok) throw new Error(`Admin status ${response.status}`);
  return response.json();
}

export async function refreshAdminData(
  token: string,
  options: { use_cache: boolean; rebuild_rag: boolean },
): Promise<AdminRefreshResult> {
  const response = await fetch(apiUrl("/admin/refresh-data"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-admin-token": token,
    },
    body: JSON.stringify(options),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Admin refresh ${response.status}`);
  }
  return response.json();
}
