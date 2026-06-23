import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import {
  ArrowRight,
  Bell,
  Bot,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  Database,
  FileSearch,
  Globe2,
  HelpCircle,
  Info,
  LayoutDashboard,
  Loader2,
  Menu,
  Map,
  MapPinned,
  MessageSquarePlus,
  Moon,
  MoreVertical,
  Paperclip,
  Settings,
  Share2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  TrendingUp,
  UploadCloud,
  X,
  Copy,
  Download,
  AlertTriangle,
  Wifi,
  WifiOff,
  LogOut,
  RefreshCw,
} from "lucide-react";
import "./styles.css";
import {
  AdminDataStatus,
  ChatAnswer,
  askInvestSearch,
  fallbackAnswer,
  getAdminDataStatus,
  getRagStatus,
  refreshAdminData,
} from "./api";
import InvestMap from "./components/InvestMap";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import LandingPage from "./pages/LandingPage";
import AuthPage from "./pages/AuthPage";
import AboutPage from "./pages/AboutPage";
import InvestorReport from "./components/InvestorReport";

const HISTORY_KEY = "invest-search-history";
const CONVERSATIONS_KEY = "invest-search-conversations-v1";
const MAX_CONVERSATIONS = 7;
const MAX_TURNS_PER_CONVERSATION = 30;
const REPORT_INTENT_RE = /\b(rapport|rapports|memo|note|investisseur|pdf|report)\b/i;

type WorkspaceView = "intelligence" | "map" | "reports" | "sources";
type OverlayKind = "settings" | "help" | null;

type ConversationTurn = {
  id: string;
  question: string;
  answer: ChatAnswer;
  createdAt: number;
};

type Conversation = {
  id: string;
  title: string;
  turns: ConversationTurn[];
  updatedAt: number;
  legacyQuestion?: string;
};

function createId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function loadConversations(): Conversation[] {
  try {
    const stored = localStorage.getItem(CONVERSATIONS_KEY);
    const parsed = stored ? JSON.parse(stored) : [];
    if (stored !== null && Array.isArray(parsed)) {
      return parsed
        .filter((item) => item && typeof item.id === "string" && typeof item.title === "string")
        .map((item) => ({ ...item, turns: Array.isArray(item.turns) ? item.turns : [] }))
        .slice(0, MAX_CONVERSATIONS);
    }

    // The old format only stored question strings. Keep them visible and
    // hydrate each one with a real answer the first time it is opened.
    const legacyStored = localStorage.getItem(HISTORY_KEY);
    const legacy = legacyStored ? JSON.parse(legacyStored) : [];
    return Array.isArray(legacy)
      ? legacy.filter(Boolean).slice(0, MAX_CONVERSATIONS).map((question, index) => ({
          id: `legacy-${index}-${String(question).slice(0, 24)}`,
          title: String(question),
          turns: [],
          updatedAt: Date.now() - index,
          legacyQuestion: String(question),
        }))
      : [];
  } catch {
    return [];
  }
}

function saveConversations(items: Conversation[]) {
  try {
    localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(items.slice(0, MAX_CONVERSATIONS)));
    localStorage.removeItem(HISTORY_KEY);
  } catch {
    // Keep the in-memory conversation usable if browser storage is unavailable.
  }
}

const quickPrompts = [
  "Comparer Anfa, Maarif et Sidi Maarouf pour une école privée",
  "Où ouvrir un restaurant avec faible concurrence ?",
  "J'ai 800 000 DH pour un commerce à Casablanca",
  "Où ouvrir une salle de sport à Casablanca ?",
];

const sourceInventory = [
  {
    title: "HCP RGPH 2024",
    description: "Population officielle et ménages des 16 arrondissements.",
    icon: Database,
    status: "Structuré",
  },
  {
    title: "OpenStreetMap",
    description: "Points santé et multi-secteurs géolocalisés.",
    icon: Globe2,
    status: "Géocodé",
  },
  {
    title: "Ministère de la Santé",
    description: "117 centres de soins et 13 hôpitaux publics MSPS 2024.",
    icon: ShieldCheck,
    status: "Référence",
  },
  {
    title: "Scores Invest Search",
    description: "Opportunités, saturation, accessibilité et concurrence.",
    icon: TrendingUp,
    status: "Calculé",
  },
];

function SourceCardView({ source }: { source: ChatAnswer["sources"][number] }) {
  return (
    <article className="source-card">
      <div className={`source-icon ${source.kind}`}>
        <Database size={15} />
      </div>
      <div>
        {source.url ? (
          <a href={source.url} target="_blank" rel="noreferrer"><strong>{source.title}</strong></a>
        ) : <strong>{source.title}</strong>}
        <p>{source.subtitle || source.description || source.kind || "Source de données"}</p>
        {source.metric ? <span className="source-metric">{source.metric}</span> : null}
      </div>
    </article>
  );
}

function RagBadge({ answer }: { answer: ChatAnswer }) {
  const contextCount = answer.retrieved_contexts?.length || 0;
  const label =
    isRagAnswer(answer)
      ? `RAG · ${contextCount || answer.sources.length} source${(contextCount || answer.sources.length) > 1 ? "s" : ""}`
      : answer.rag_status?.startsWith("easy_")
      ? "Réponse rapide"
      : answer.rag_status?.includes("ollama") || answer.rag_status === "llm_rag"
      ? `RAG local · ${answer.model || "Ollama"}`
      : answer.rag_status?.includes("api_openai")
        ? `RAG API · ${answer.model || "OpenAI"}`
      : answer.rag_status?.includes("api_anthropic")
        ? `RAG API · ${answer.model || "Anthropic"}`
      : answer.rag_status === "semantic_scoring"
        ? "Recherche sémantique locale"
        : "Analyse Invest Search";

  return (
    <div className="rag-badge">
      <Bot size={16} />
      <span>{label}</span>
    </div>
  );
}

function isRagAnswer(answer: ChatAnswer): boolean {
  const status = answer.rag_status || "";
  return (
    answer.retrieved_contexts?.length > 0 ||
    status.startsWith("hybrid") ||
    status.startsWith("lexical") ||
    status.startsWith("semantic") ||
    status.includes("_ollama") ||
    status.includes("api_openai") ||
    status.includes("api_anthropic")
  );
}

const markdownComponents = {
  table({ node: _node, ...props }: any) {
    return (
      <div className="markdown-table-wrap">
        <table {...props} />
      </div>
    );
  },
};

function Sidebar({
  conversations,
  activeConversationId,
  view,
  open = false,
  onSelectConversation,
  onDeleteConversation,
  onClearConversations,
  onNewChat,
  onNavigate,
  onOpenOverlay,
  onLogout,
  onRequestClose,
}: {
  conversations: Conversation[];
  activeConversationId: string | null;
  view: WorkspaceView;
  open?: boolean;
  onSelectConversation: (conversation: Conversation) => void;
  onDeleteConversation: (id: string) => void;
  onClearConversations: () => void;
  onNewChat: () => void;
  onNavigate: (view: WorkspaceView) => void;
  onOpenOverlay: (kind: OverlayKind) => void;
  onLogout: () => void;
  onRequestClose?: () => void;
}) {
  const navItems = [
    { id: "intelligence" as const, label: "Intelligence", icon: LayoutDashboard },
    { id: "map" as const, label: "Invest Map", icon: Map },
    { id: "reports" as const, label: "Rapports", icon: ClipboardList },
    { id: "sources" as const, label: "Sources", icon: Database },
  ];

  return (
    <aside
      className="sidebar"
      style={{
        "--sidebar-left": open ? "0" : "calc(-1 * min(88vw, 320px) - 8px)",
      } as CSSProperties}
    >
      <button className="sidebar-close" type="button" aria-label="Fermer le menu" onClick={onRequestClose}>
        <X size={18} />
      </button>
      <div className="brand">
        <div className="brand-mark">
          <TrendingUp size={22} />
        </div>
        <div>
          <h1>Invest Search</h1>
          <span>Market & Location Intelligence</span>
        </div>
      </div>

      <button className="new-chat" onClick={() => { onNewChat(); onRequestClose?.(); }}>
        <MessageSquarePlus size={19} />
        Nouvelle discussion
      </button>

      <nav className="nav-main" aria-label="Navigation principale">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              className={view === item.id ? "active" : ""}
              onClick={() => { onNavigate(item.id); onRequestClose?.(); }}
            >
              <Icon size={18} />
              <span>{item.label}</span>
              {view === item.id ? <ChevronRight size={15} /> : null}
            </button>
          );
        })}
      </nav>

      <section className="history-panel" aria-label="Conversations récentes">
        <div className="history-header">
          <span>Conversations</span>
          {conversations.length ? (
            <button className="history-clear" onClick={onClearConversations}>
              Effacer
            </button>
          ) : null}
        </div>

        <div className="history-list">
          {conversations.length ? (
            conversations.map((conversation) => (
              <div
                className={`history-row ${activeConversationId === conversation.id ? "active" : ""}`}
                key={conversation.id}
              >
                <button className="history-query" onClick={() => { onSelectConversation(conversation); onRequestClose?.(); }}>
                  <span>{conversation.title}</span>
                  <small>
                    {conversation.turns.length
                      ? `${conversation.turns.length} message${conversation.turns.length > 1 ? "s" : ""}`
                      : "Ancienne requête"}
                  </small>
                </button>
                <button
                  className="history-delete"
                  aria-label={`Supprimer ${conversation.title}`}
                  title="Supprimer"
                  onClick={() => onDeleteConversation(conversation.id)}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))
          ) : (
            <p className="empty-history">Aucune requête récente.</p>
          )}
        </div>
      </section>

      <div className="sidebar-footer">
        <button onClick={() => { onOpenOverlay("settings"); onRequestClose?.(); }}>
          <Settings size={18} />
          Paramètres
        </button>
        <button onClick={() => { onOpenOverlay("help"); onRequestClose?.(); }}>
          <HelpCircle size={18} />
          Aide
        </button>
        <button className="logout-btn" onClick={onLogout}>
          <LogOut size={18} />
          Déconnexion
        </button>
        <div className="profile-mini">
          <div className="avatar">NB</div>
          <div>
            <strong>Dr. A. Benali</strong>
            <span>Casablanca · Mode démo</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

type HeaderMenu = "none" | "notif" | "more" | "profile";

const HEADER_NOTIFICATIONS = [
  "Données multi-secteurs mises à jour (food, retail, éducation, bien-être).",
  "Nouveau : analyse selon votre budget (faisabilité + scénarios).",
];

function Header({
  view,
  setView,
  onMenuClick,
}: {
  view: WorkspaceView;
  setView: (view: WorkspaceView) => void;
  onMenuClick: () => void;
}) {
  const [menu, setMenu] = useState<HeaderMenu>("none");
  const [toast, setToast] = useState<string | null>(null);
  const actionsRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (menu === "none") return;
    function onDocClick(e: MouseEvent) {
      if (actionsRef.current && !actionsRef.current.contains(e.target as Node)) setMenu("none");
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [menu]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 2600);
    return () => window.clearTimeout(t);
  }, [toast]);

  async function handleShare() {
    setMenu("none");
    const shareData = {
      title: "Invest Search",
      text: "Intelligence de marché et d'implantation à Casablanca (santé + multi-secteurs).",
      url: window.location.href,
    };
    try {
      if (navigator.share) {
        await navigator.share(shareData);
        return;
      }
      await navigator.clipboard.writeText(shareData.url);
      setToast("Lien copié dans le presse-papiers");
    } catch {
      setToast("Partage indisponible sur ce navigateur");
    }
  }

  const dropdownStyle: CSSProperties = {
    position: "absolute",
    top: "calc(100% + 8px)",
    right: 0,
    minWidth: 240,
    background: "#fff",
    color: "#0f172a",
    border: "1px solid #e2e8f0",
    borderRadius: 12,
    boxShadow: "0 12px 32px rgba(15,23,42,0.16)",
    padding: 10,
    zIndex: 50,
    fontSize: 13,
    textAlign: "left",
  };
  const itemStyle: CSSProperties = {
    display: "block",
    width: "100%",
    textAlign: "left",
    padding: "8px 10px",
    borderRadius: 8,
    background: "transparent",
    border: "none",
    cursor: "pointer",
  };

  function toggle(target: HeaderMenu) {
    setMenu((current) => (current === target ? "none" : target));
  }

  return (
    <header className="topbar">
      <button className="mobile-menu-button" type="button" aria-label="Ouvrir le menu" onClick={onMenuClick}>
        <Menu size={20} />
      </button>
      <div className="discussion-title">Analyse de marché et d'implantation à Casablanca</div>
      <div className="mode-toggle">
        <button
          type="button"
          aria-pressed={view === "intelligence"}
          className={view === "intelligence" ? "active" : ""}
          onClick={() => setView("intelligence")}
        >
          <FileSearch size={16} />
          Réponse
        </button>
        <button
          type="button"
          aria-pressed={view === "map"}
          className={view === "map" ? "active" : ""}
          onClick={() => setView("map")}
        >
          <MapPinned size={16} />
          Carte Interactive
        </button>
      </div>
      <div className="top-actions" ref={actionsRef} style={{ position: "relative" }}>
        <button className="share" type="button" onClick={handleShare}>
          <Share2 size={16} />
          Partager
        </button>
        <button
          className="icon-button"
          type="button"
          aria-label="Notifications"
          aria-expanded={menu === "notif"}
          onClick={() => toggle("notif")}
        >
          <Bell size={18} />
        </button>
        <button
          className="icon-button"
          type="button"
          aria-label="Plus d'options"
          aria-expanded={menu === "more"}
          onClick={() => toggle("more")}
        >
          <MoreVertical size={18} />
        </button>
        <button
          className="avatar profile-photo"
          type="button"
          aria-label="Profil"
          aria-expanded={menu === "profile"}
          onClick={() => toggle("profile")}
        >
          NB
        </button>

        {menu === "notif" && (
          <div style={dropdownStyle} role="menu">
            <strong style={{ display: "block", padding: "4px 10px 8px" }}>Notifications</strong>
            {HEADER_NOTIFICATIONS.map((n) => (
              <div key={n} style={{ padding: "8px 10px", borderTop: "1px solid #f1f5f9" }}>{n}</div>
            ))}
          </div>
        )}

        {menu === "more" && (
          <div style={dropdownStyle} role="menu">
            <button style={itemStyle} onClick={() => { setView("intelligence"); setMenu("none"); }}>Vue Réponse</button>
            <button style={itemStyle} onClick={() => { setView("map"); setMenu("none"); }}>Vue Carte</button>
            <button style={itemStyle} onClick={() => { handleShare(); }}>Partager le lien</button>
            <button style={itemStyle} onClick={() => { setMenu("none"); window.location.reload(); }}>Actualiser</button>
          </div>
        )}

        {menu === "profile" && (
          <div style={dropdownStyle} role="menu">
            <div style={{ padding: "4px 10px 8px" }}>
              <strong style={{ display: "block" }}>Dr. A. Benali</strong>
              <span style={{ color: "#64748b" }}>Casablanca · Mode démo</span>
            </div>
            <div style={{ padding: "8px 10px", borderTop: "1px solid #f1f5f9", color: "#64748b" }}>
              Déconnexion disponible dans la barre latérale.
            </div>
          </div>
        )}
      </div>

      {toast && (
        <div
          style={{
            position: "fixed",
            bottom: 24,
            right: 24,
            background: "#0f172a",
            color: "#fff",
            padding: "10px 16px",
            borderRadius: 10,
            boxShadow: "0 10px 30px rgba(15,23,42,0.25)",
            zIndex: 100,
            fontSize: 13,
          }}
        >
          {toast}
        </div>
      )}
    </header>
  );
}

function AnswerView({
  answers,
  onAsk,
  loading,
}: {
  answers: ChatAnswer[];
  onAsk: (question: string) => Promise<void>;
  loading: boolean;
}) {
  const latestTurnRef = useRef<HTMLElement>(null);
  const pendingTurnRef = useRef<HTMLElement>(null);
  const visibleAnswers = answers.length ? answers : loading ? [] : [fallbackAnswer];

  useEffect(() => {
    const target = loading ? pendingTurnRef.current : latestTurnRef.current;
    if (!target || (!loading && !answers.length)) return;
    const frame = window.requestAnimationFrame(() => {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [answers.length, loading]);

  return (
    <main className="workspace">
      <div className="content-shell conversation-stream">
        {visibleAnswers.map((answer, index) => {
          const topOpportunity =
            answer.related_opportunities.find((item) => item.zone === answer.top_zone) ||
            answer.related_opportunities[0];
          const isLatest = index === visibleAnswers.length - 1;
          const suggestedQuestions = isLatest
            ? answer.suggested_questions?.filter(Boolean) || []
            : [];

          return (
            <article
              className="conversation-turn"
              key={`${answer.query}-${index}`}
              ref={isLatest ? latestTurnRef : undefined}
            >
              <section className="query-block">
                <p className="eyebrow">Question {visibleAnswers.length > 1 ? index + 1 : ""}</p>
                <h2>{answer.query}</h2>
              </section>

              <section className="sources-row" aria-label="Sources utilisées">
                {answer.sources.map((source) => (
                  <SourceCardView source={source} key={source.title} />
                ))}
              </section>

              <section className="answer-panel">
                <div className="answer-label">
                  <Sparkles size={17} />
                  Invest Search Intelligence
                </div>
                <RagBadge answer={answer} />
                <div className="markdown-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                    {answer.answer_markdown}
                  </ReactMarkdown>
                </div>

                {suggestedQuestions.length ? (
                  <div className="suggested-questions" aria-label="Questions suggérées">
                    {suggestedQuestions.map((question) => (
                      <button key={question} type="button" onClick={() => onAsk(question)}>
                        <MessageSquarePlus size={15} />
                        <span>{question}</span>
                      </button>
                    ))}
                  </div>
                ) : null}

                <div className="insight-grid">
                  <article className="kpi-card">
                    <div className="kpi-title">
                      <TrendingUp size={21} />
                      <h3>KPIs de Marché</h3>
                    </div>
                    {answer.kpis.map((kpi) => (
                      <div className="kpi-row" key={kpi.label}>
                        <span>{kpi.label}</span>
                        <strong className={kpi.label.toLowerCase().includes("score") ? "pill-good" : ""}>
                          {kpi.value}
                        </strong>
                      </div>
                    ))}
                  </article>
                </div>

                {topOpportunity ? (
                  <div className="score-strip">
                    <span>Score d'opportunité</span>
                    <strong>{topOpportunity.score}%</strong>
                    <span>{topOpportunity.category}</span>
                  </div>
                ) : null}
              </section>
            </article>
          );
        })}
        {loading ? (
          <article className="conversation-turn conversation-turn-pending" ref={pendingTurnRef}>
            <div className="loading-stack conversation-loading">
              <Loader2 className="spin" size={24} />
              <p>Analyse des signaux de marché, sources locales et opportunités...</p>
              <div className="shimmer wide" />
              <div className="shimmer" />
            </div>
          </article>
        ) : null}
      </div>
    </main>
  );
}

function MapView({ answer }: { answer: ChatAnswer }) {
  const domainLabel = answer.subcategory_label || answer.sector || answer.category || "Opportunités d'implantation";

  return (
    <main className="workspace map-workspace">
      <div className="content-shell map-shell">
        <section className="query-block compact">
          <p className="eyebrow">Carte Interactive</p>
          <h2>
            {answer.map_focus.label} · {domainLabel}
          </h2>
        </section>
        <div className="large-map">
          <InvestMap
            focusLabel={answer.map_focus.label}
            focusLat={answer.map_focus.lat}
            focusLon={answer.map_focus.lon}
            focusZoom={answer.map_focus.zoom}
            answer={answer}
          />
        </div>
      </div>
    </main>
  );
}

function ReportsView({ answer }: { answer: ChatAnswer }) {
  return <InvestorReport answer={answer} />;
}

function LegacyReportsView({ answer }: { answer: ChatAnswer }) {
  const topOpportunity =
    answer.related_opportunities.find((item) => item.zone === answer.top_zone) ||
    answer.related_opportunities[0];

  const [copied, setCopied] = useState(false);

  function copyMarkdown() {
    navigator.clipboard.writeText(answer.answer_markdown).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  function downloadMarkdown() {
    const blob = new Blob([answer.answer_markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `invest-search-${answer.top_zone?.replace(/\s+/g, "-") || "report"}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="workspace">
      <div className="content-shell">
        <section className="query-block compact">
          <p className="eyebrow">Rapports</p>
          <h2>Pack décisionnel pour {answer.top_zone}</h2>
        </section>

        <section className="report-grid">
          <article className="report-card primary-report">
            <div className="report-icon">
              <FileSearch size={21} />
            </div>
            <span>Investor memo</span>
            <h3>Dernière analyse générée</h3>
            <p>
              Synthèse exécutive, KPIs, risques et sources issues de la dernière question posée.
            </p>
            <div className="report-actions">
              <button onClick={copyMarkdown} title="Copier en Markdown">
                {copied ? <CheckCircle2 size={16} /> : <Copy size={16} />}
                {copied ? "Copié !" : "Copier"}
              </button>
              <button onClick={downloadMarkdown} title="Télécharger .md">
                <Download size={16} />
                Exporter .md
              </button>
            </div>
          </article>

          <article className="report-card">
            <div className="report-icon soft">
              <ClipboardList size={21} />
            </div>
            <span>Due diligence</span>
            <h3>Checklist terrain</h3>
            <p>
              Accessibilité patient, loyers, autorisations sanitaires, parking,
              flux piéton et concurrence directe.
            </p>
          </article>

          <article className="report-card">
            <div className="report-icon warning">
              <AlertTriangle size={21} />
            </div>
            <span>Risk brief</span>
            <h3>Risques et hypothèses</h3>
            <p>
              Angles morts de données, hypothèses RAG et validations nécessaires
              avant investissement.
            </p>
          </article>
        </section>

        <section className="report-metric-grid">
          <div>
            <span>Zone prioritaire</span>
            <strong>{answer.top_zone}</strong>
          </div>
          <div>
            <span>Score</span>
            <strong>
              {topOpportunity
                ? `${topOpportunity.score}%`
                : answer.score > 0
                  ? `${answer.score}%`
                  : "Non calculé"}
            </strong>
          </div>
          <div>
            <span>Type recommandé</span>
            <strong>{topOpportunity?.category || answer.category}</strong>
          </div>
          <div>
            <span>Moteur</span>
            <strong>{answer.rag_status?.includes("ollama") || answer.rag_status?.includes("api_") || answer.rag_status === "llm_rag" ? "RAG + LLM" : "Recherche sémantique"}</strong>
          </div>
        </section>
      </div>
    </main>
  );
}

function SourcesView({ answer }: { answer: ChatAnswer }) {
  return (
    <main className="workspace">
      <div className="content-shell">
        <section className="query-block compact">
          <p className="eyebrow">Sources</p>
          <h2>Bibliothèque de données utilisée par l'analyse</h2>
        </section>

        <section className="source-library">
          {sourceInventory.map((source) => {
            const Icon = source.icon;
            return (
              <article className="source-library-card" key={source.title}>
                <div className="source-library-top">
                  <div className="source-icon">
                    <Icon size={16} />
                  </div>
                  <span>{source.status}</span>
                </div>
                <h3>{source.title}</h3>
                <p>{source.description}</p>
              </article>
            );
          })}
        </section>

        <section className="context-panel">
          <div className="context-header">
            <Sparkles size={17} />
            <div>
              <h3>Passages récupérés pour cette réponse</h3>
              <p>Ces extraits servent de couche de justification pour les réponses RAG.</p>
            </div>
          </div>

          {answer.retrieved_contexts?.length ? (
            <div className="context-list">
              {answer.retrieved_contexts.slice(0, 4).map((context, index) => (
                <article className="context-item" key={`${context.title}-${index}`}>
                  <span>{context.kind} · {context.source_path}</span>
                  <h4>{context.title}</h4>
                  <p>{context.text}</p>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty-context">
              <Database size={20} />
              <p>
                Aucune trace RAG détaillée n'est disponible pour cette réponse. Lancez une nouvelle
                question pour voir les passages récupérés.
              </p>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

type RagStatus = {
  ollama_available: boolean;
  chat_model: string;
  embedding_model: string;
  chunk_count: number;
  indexed_at: number | null;
  installed_models: string[];
};

const helpQuestions = [
  "Où ouvrir une pharmacie à faible concurrence ?",
  "Comparer Anfa et Maarif pour un restaurant",
  "Où ouvrir une école privée à Casablanca ?",
  "Quelle zone pour une salle de sport ?",
  "J'ai 800 000 DH pour ouvrir un commerce",
];

function OverlayPanel({
  kind,
  onClose,
  onAsk,
}: {
  kind: Exclude<OverlayKind, null>;
  onClose: () => void;
  onAsk?: (q: string) => void;
}) {
  const isSettings = kind === "settings";
  const [ragStatus, setRagStatus] = useState<RagStatus | null>(null);
  const [dataStatus, setDataStatus] = useState<AdminDataStatus | null>(null);
  const [adminToken, setAdminToken] = useState(() => localStorage.getItem("invest-search-admin-token") || "");
  const [useLiveOsm, setUseLiveOsm] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState("");

  useEffect(() => {
    if (!isSettings) return;
    fetch("/api/rag/status").then(r => r.json()).then(setRagStatus).catch(() => {});
    getAdminDataStatus().then(setDataStatus).catch(() => {});
  }, [isSettings]);

  function formatUpdated(timestamp?: number | null) {
    if (!timestamp) return "Jamais";
    return new Date(timestamp * 1000).toLocaleString("fr");
  }

  async function handleAdminRefresh() {
    if (!adminToken.trim()) {
      setRefreshMessage("Token admin requis.");
      return;
    }
    localStorage.setItem("invest-search-admin-token", adminToken.trim());
    setRefreshing(true);
    setRefreshMessage("Mise à jour en cours...");
    try {
      const result = await refreshAdminData(adminToken.trim(), {
        use_cache: !useLiveOsm,
        rebuild_rag: true,
      });
      setDataStatus(result.status || null);
      setRefreshMessage(
        result.ok
          ? `Données mises à jour en ${result.elapsed_seconds}s. RAG: ${result.rag?.chunk_count ?? "n/a"} chunks.`
          : `Échec à l'étape: ${result.failed_step || "inconnue"}`,
      );
    } catch (error) {
      setRefreshMessage(error instanceof Error ? error.message : "Erreur de mise à jour.");
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <div className="overlay-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="overlay-panel"
        role="dialog"
        aria-modal="true"
        aria-label={isSettings ? "Paramètres" : "Aide"}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="overlay-header">
          <div>
            <span>{isSettings ? "Configuration" : "Centre d'aide"}</span>
            <h2>{isSettings ? "Settings Invest Search" : "Aide et bonnes questions"}</h2>
          </div>
          <button className="overlay-close" onClick={onClose} aria-label="Fermer">
            <X size={18} />
          </button>
        </div>

        {isSettings ? (
          <>
            <div className="settings-grid">
              <article className="setting-row">
                {ragStatus?.ollama_available ? <Wifi size={19} /> : <WifiOff size={19} />}
                <div>
                  <strong>Ollama</strong>
                  <span>{ragStatus?.ollama_available ? "Connecté et opérationnel" : "Non disponible — mode scoring"}</span>
                </div>
                <span className={`toggle-pill ${ragStatus?.ollama_available ? "active" : ""}`}>
                  {ragStatus?.ollama_available ? "En ligne" : "Hors ligne"}
                </span>
              </article>
              <article className="setting-row">
                <Bot size={19} />
                <div>
                  <strong>Modèle chat</strong>
                  <span>{ragStatus?.chat_model || "Chargement..."}</span>
                </div>
                <span className="toggle-pill">Local</span>
              </article>
              <article className="setting-row">
                <Database size={19} />
                <div>
                  <strong>Index RAG</strong>
                  <span>
                    {ragStatus ? `${ragStatus.chunk_count} chunks indexés` : "Chargement..."}
                    {ragStatus?.indexed_at ? ` · ${new Date(ragStatus.indexed_at * 1000).toLocaleDateString("fr")}` : ""}
                  </span>
                </div>
                <span className="toggle-pill active">{ragStatus?.embedding_model || "..."}</span>
              </article>
              <article className="setting-row">
                <CheckCircle2 size={19} />
                <div>
                  <strong>Mode investisseur</strong>
                  <span>Scores, risques, hypothèses et sources</span>
                </div>
                <span className="toggle-pill active">Activé</span>
              </article>
            </div>
            {ragStatus?.installed_models?.length ? (
              <div className="settings-models">
                <span>Modèles installés</span>
                <div>{ragStatus.installed_models.filter(m => !m.includes("cloud")).join(" · ")}</div>
              </div>
            ) : null}
            <div className="admin-refresh-panel">
              <div className="admin-refresh-header">
                <div>
                  <span>Admin data tool</span>
                  <strong>Sources, OpenStreetMap et RAG</strong>
                </div>
                <span className="toggle-pill active">Admin</span>
              </div>
              <div className="admin-data-grid">
                <div>
                  <span>GeoJSON carte</span>
                  <strong>{formatUpdated(dataStatus?.files.geojson?.updated_at)}</strong>
                </div>
                <div>
                  <span>Facilities clean</span>
                  <strong>{formatUpdated(dataStatus?.files.clean_facilities?.updated_at)}</strong>
                </div>
                <div>
                  <span>Area indicators</span>
                  <strong>{formatUpdated(dataStatus?.files.area_indicators?.updated_at)}</strong>
                </div>
              </div>
              <label className="admin-token-field">
                <span>Admin token</span>
                <input
                  type="password"
                  value={adminToken}
                  onChange={(event) => setAdminToken(event.target.value)}
                  placeholder="Token admin"
                />
              </label>
              <label className="admin-refresh-option">
                <input
                  type="checkbox"
                  checked={useLiveOsm}
                  onChange={(event) => setUseLiveOsm(event.target.checked)}
                />
                <span>Interroger OpenStreetMap / Overpass en direct plutôt que le cache local</span>
              </label>
              <button className="admin-refresh-button" disabled={refreshing || !adminToken.trim()} onClick={handleAdminRefresh}>
                {refreshing ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
                {refreshing ? "Mise à jour..." : "Mettre à jour les données"}
              </button>
              {refreshMessage ? <p className="admin-refresh-message">{refreshMessage}</p> : null}
              <p className="admin-refresh-note">
                Cette action relance la collecte OSM, la normalisation, le scoring, l'export GeoJSON et la réindexation RAG.
              </p>
            </div>
            <div className="overlay-actions">
              <button onClick={onClose}>Terminé</button>
            </div>
          </>
        ) : (
          <>
            <div className="help-list">
              {helpQuestions.map((q) => (
                <article key={q} onClick={() => { onAsk?.(q); onClose(); }} style={{ cursor: "pointer" }}>
                  <HelpCircle size={18} />
                  <span>{q}</span>
                  <ArrowRight size={14} style={{ opacity: 0.4, marginLeft: "auto" }} />
                </article>
              ))}
            </div>
            <div className="help-note">
              <strong>À propos</strong>
              <p>
                Invest Search combine des données OpenStreetMap, HCP et Ministère de la Santé avec un
                moteur de scoring propriétaire. Les recommandations sont des filtres décisionnels
                initiaux — elles ne constituent pas un conseil financier ou juridique. Toute décision
                d'investissement doit être validée par une visite terrain et une due diligence complète.
              </p>
            </div>
            <div className="help-note">
              <strong><AlertTriangle size={14} /> Limites connues</strong>
              <p>
                87 établissements sont en district « Unknown ». Les comptages par zone peuvent
                sous-estimer la concurrence réelle. Les données OSM ne couvrent pas les acteurs informels.
              </p>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function Composer({
  onAsk,
  onWebSearch,
  loading,
  resetSignal,
}: {
  onAsk: (question: string) => Promise<void>;
  onWebSearch?: (question: string) => void;
  loading: boolean;
  resetSignal: number;
}) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const canSubmit = value.trim().length > 2 && !loading;
  const canWeb = value.trim().length > 2 && !loading;

  function runWebSearch() {
    const question = value.trim();
    if (!question || loading) return;
    setValue("");
    onWebSearch?.(question);
  }

  useEffect(() => {
    setValue("");
    inputRef.current?.focus();
  }, [resetSignal]);

  async function submit() {
    if (!canSubmit) return;
    const question = value.trim();
    setValue("");
    await onAsk(question);
  }

  return (
    <div className="composer-wrap">
      <div className="composer">
        <button className="ghost-icon" aria-label="Joindre des données">
          <Paperclip size={21} />
        </button>
        <input
          ref={inputRef}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") submit();
          }}
          placeholder="Poser une question de suivi ou affiner la zone..."
        />
        <button
          className="web-chip"
          onClick={runWebSearch}
          disabled={!canWeb}
          title="Lancer une recherche web (sources externes, non vérifiées) sur la question saisie"
        >
          <Globe2 size={15} />
          Recherche Web
        </button>
        <button className="send" disabled={!canSubmit} onClick={submit} aria-label="Envoyer">
          {loading ? <Loader2 className="spin" size={20} /> : <ArrowRight size={24} />}
        </button>
      </div>
      <div className="quick-prompts">
        {quickPrompts.map((prompt) => (
          <button key={prompt} onClick={() => onAsk(prompt)} disabled={loading}>
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

const SESSION_KEY = "invest-search-authed";

function DeterministicBanner() {
  const [deterministic, setDeterministic] = useState(false);
  useEffect(() => {
    let alive = true;
    getRagStatus().then((s) => {
      if (!alive || !s) return;
      const llm = s.llm_available ?? s.ollama_available;
      setDeterministic(llm === false);
    });
    return () => {
      alive = false;
    };
  }, []);
  if (!deterministic) return null;
  return (
    <div
      role="status"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        background: "#fffbeb",
        color: "#92400e",
        borderBottom: "1px solid #fde68a",
        padding: "8px 16px",
        fontSize: 13,
        lineHeight: 1.35,
      }}
    >
      <AlertTriangle size={15} style={{ flexShrink: 0 }} />
      <span>
        <strong>Mode déterministe</strong> — le modèle local (qwen2.5) n'est pas connecté. Réponses
        par moteur de scoring + recherche par mots-clés ; les analyses narratives sont en version
        simplifiée.
      </span>
    </div>
  );
}

function Dashboard({ onLogout }: { onLogout: () => void }) {
  const [view, setView] = useState<WorkspaceView>("intelligence");
  const [overlay, setOverlay] = useState<OverlayKind>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>(() => loadConversations());
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [newChatSignal, setNewChatSignal] = useState(0);
  const requestSeq = useRef(0);

  const activeConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === activeConversationId),
    [activeConversationId, conversations],
  );
  const conversationAnswers = activeConversation?.turns.map((turn) => turn.answer) || [];
  const answer = conversationAnswers.at(-1) || fallbackAnswer;
  const sourceTitles = useMemo(() => answer.sources.map((source) => source.title).join(" · "), [answer]);

  async function handleAsk(question: string, conversationIdOverride?: string, webSearch = false) {
    const trimmed = question.trim();
    if (!trimmed) return;

    const conversationId = conversationIdOverride || activeConversationId || createId();
    setActiveConversationId(conversationId);
    setView("intelligence");
    const requestId = requestSeq.current + 1;
    requestSeq.current = requestId;
    setLoading(true);
    try {
      const contextConversation = conversations.find((item) => item.id === conversationId);
      const previousTurns = contextConversation?.turns || [];
      const history = previousTurns.slice(-6).flatMap((turn) => [
        { role: "user" as const, content: turn.question },
        { role: "assistant" as const, content: turn.answer.answer_markdown },
      ]);
      const investorProfile = previousTurns.at(-1)?.answer.investor_profile;
      const result = await askInvestSearch(trimmed, { history, investorProfile, webSearch });
      if (requestSeq.current !== requestId) return;
      const turn: ConversationTurn = {
        id: createId(),
        question: trimmed,
        answer: result,
        createdAt: Date.now(),
      };
      setConversations((current) => {
        const existing = current.find((conversation) => conversation.id === conversationId);
        const updated: Conversation = existing
          ? {
              ...existing,
              turns: [...existing.turns, turn].slice(-MAX_TURNS_PER_CONVERSATION),
              updatedAt: Date.now(),
              legacyQuestion: undefined,
            }
          : {
              id: conversationId,
              title: trimmed,
              turns: [turn],
              updatedAt: Date.now(),
            };
        const next = [updated, ...current.filter((conversation) => conversation.id !== conversationId)]
          .slice(0, MAX_CONVERSATIONS);
        saveConversations(next);
        return next;
      });
      const nextView = REPORT_INTENT_RE.test(trimmed) ? "reports" : result.suggested_view;
      if (nextView === "map" || nextView === "reports" || nextView === "sources" || nextView === "intelligence") {
        setView(nextView);
      }
    } finally {
      if (requestSeq.current === requestId) {
        setLoading(false);
      }
    }
  }

  function handleSelectConversation(conversation: Conversation) {
    requestSeq.current += 1;
    setActiveConversationId(conversation.id);
    setView("intelligence");
    setOverlay(null);
    setLoading(false);
    setNewChatSignal((value) => value + 1);
    if (!conversation.turns.length && conversation.legacyQuestion) {
      void handleAsk(conversation.legacyQuestion, conversation.id);
    }
  }

  function handleDeleteConversation(id: string) {
    const next = conversations.filter((conversation) => conversation.id !== id);
    setConversations(next);
    saveConversations(next);
    if (activeConversationId === id) handleNewChat();
  }

  function handleClearConversations() {
    setConversations([]);
    saveConversations([]);
    handleNewChat();
  }

  function handleNewChat() {
    requestSeq.current += 1;
    setActiveConversationId(null);
    setView("intelligence");
    setOverlay(null);
    setLoading(false);
    setNewChatSignal((value) => value + 1);
  }

  return (
    <div className={`app-shell ${sidebarOpen ? "sidebar-open" : ""}`}>
      <button
        className="sidebar-scrim"
        type="button"
        aria-label="Fermer le panneau latéral"
        onClick={() => setSidebarOpen(false)}
      />
      <Sidebar
        conversations={conversations}
        activeConversationId={activeConversationId}
        view={view}
        open={sidebarOpen}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={handleDeleteConversation}
        onClearConversations={handleClearConversations}
        onNewChat={handleNewChat}
        onNavigate={setView}
        onOpenOverlay={setOverlay}
        onLogout={onLogout}
        onRequestClose={() => setSidebarOpen(false)}
      />
      <div className="main-area">
        <Header view={view} setView={setView} onMenuClick={() => setSidebarOpen(true)} />
        <DeterministicBanner />
        <div className="source-ribbon" title={sourceTitles}>
          <Database size={14} />
          {sourceTitles}
        </div>
        {view === "map" ? (
          <MapView answer={answer} />
        ) : view === "reports" ? (
          <ReportsView answer={answer} />
        ) : view === "sources" ? (
          <SourcesView answer={answer} />
        ) : (
          <AnswerView answers={conversationAnswers} onAsk={handleAsk} loading={loading} />
        )}
        <Composer
          onAsk={handleAsk}
          onWebSearch={(q) => handleAsk(q, undefined, true)}
          loading={loading}
          resetSignal={newChatSignal}
        />
      </div>
      {overlay ? <OverlayPanel kind={overlay} onClose={() => setOverlay(null)} onAsk={handleAsk} /> : null}
    </div>
  );
}

type AppPage = "landing" | "auth" | "about" | "app";

const PATH_MAP: Record<string, AppPage> = {
  "/": "landing",
  "/login": "auth",
  "/about": "about",
  "/app": "app",
};
const PAGE_PATH: Record<AppPage, string> = {
  landing: "/",
  auth: "/login",
  about: "/about",
  app: "/app",
};

function pageFromPath(): AppPage {
  const path = window.location.pathname;
  return PATH_MAP[path] ?? "landing";
}

function App() {
  const [page, setPage] = useState<AppPage>(() => {
    const fromUrl = pageFromPath();
    if (fromUrl === "app" && !sessionStorage.getItem(SESSION_KEY)) return "auth";
    return fromUrl;
  });

  useEffect(() => {
    function applyRouteFromUrl() {
      const target = pageFromPath();
      if (target === "app" && !sessionStorage.getItem(SESSION_KEY)) {
        setPage("auth");
        if (window.location.pathname !== PAGE_PATH.auth) {
          window.history.replaceState({ page: "auth" }, "", PAGE_PATH.auth);
        }
        return;
      }
      setPage(target);
    }

    applyRouteFromUrl();

    function onPop() {
      applyRouteFromUrl();
    }

    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  function navigate(target: AppPage) {
    if (target === "app") sessionStorage.setItem(SESSION_KEY, "1");
    setPage(target);
    const path = PAGE_PATH[target];
    if (window.location.pathname !== path) {
      window.history.pushState({ page: target }, "", path);
    }
    window.scrollTo(0, 0);
  }

  function handleLogout() {
    sessionStorage.removeItem(SESSION_KEY);
    navigate("landing");
  }

  if (page === "auth") return <AuthPage onNavigate={navigate} />;
  if (page === "about") return <AboutPage onNavigate={navigate} />;
  if (page === "app") return <Dashboard onLogout={handleLogout} />;
  return <LandingPage onNavigate={navigate} />;
}

export default App;
