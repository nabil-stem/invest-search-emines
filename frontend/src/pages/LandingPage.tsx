import {
  ArrowRight,
  BarChart3,
  Globe2,
  Map,
  Search,
  Shield,
  Sparkles,
  TrendingUp,
  Zap,
} from "lucide-react";

const features = [
  {
    icon: Search,
    title: "Questions métier",
    desc: "Demandez où ouvrir, comparer deux quartiers, vérifier un budget ou préparer un rapport. La réponse reste liée aux données utilisées.",
  },
  {
    icon: Map,
    title: "Carte exploitable",
    desc: "Visualisez les points santé, cafés, restaurants, commerces, écoles et activités bien-être par zone. La carte sert à préparer les visites terrain.",
  },
  {
    icon: BarChart3,
    title: "Scores lisibles",
    desc: "Chaque zone est évaluée avec la population, la concurrence, le supply gap, l'offre publique, l'accessibilité et la fiabilité des données.",
  },
  {
    icon: Shield,
    title: "Sources assumées",
    desc: "Les analyses s'appuient sur OpenStreetMap, HCP RGPH 2024 et MSPS 2024. Les limites des données sont affichées au lieu d'être cachées.",
  },
];

const stats = [
  { value: "4 105", label: "Points OSM" },
  { value: "16", label: "Districts" },
  { value: "5", label: "Domaines" },
  { value: "Local", label: "RAG" },
];

type Props = {
  onNavigate: (page: "auth" | "about" | "app") => void;
};

export default function LandingPage({ onNavigate }: Props) {
  return (
    <div className="landing">
      <nav className="landing-nav">
        <div className="landing-brand">
          <div className="landing-logo">
            <TrendingUp size={20} />
          </div>
          <span>Invest Search</span>
        </div>
        <div className="landing-links">
          <button onClick={() => onNavigate("about")}>À propos</button>
          <button className="landing-login" onClick={() => onNavigate("auth")}>
            Connexion
          </button>
        </div>
      </nav>

      <section className="hero">
        <div className="hero-badge">
          <Sparkles size={14} />
          Données locales pour décisions d'implantation
        </div>
        <h1>
          Choisissez une zone avec <span className="hero-accent">des preuves</span>,
          pas avec une intuition
        </h1>
        <p className="hero-sub">
          Invest Search aide à comparer les quartiers de Casablanca pour un projet de santé,
          de restauration, de commerce, d'éducation ou de bien-être. L'outil rassemble les
          points OpenStreetMap, les données HCP et l'offre publique MSPS pour faire ressortir
          les zones à vérifier en priorité.
        </p>
        <div className="hero-actions">
          <button className="hero-cta" onClick={() => onNavigate("auth")}>
            Tester avec les données Casablanca
            <ArrowRight size={18} />
          </button>
          <button className="hero-secondary" onClick={() => onNavigate("about")}>
            Voir la méthode
          </button>
        </div>

        <div className="hero-preview">
          <div className="preview-bar">
            <div className="preview-dots"><span /><span /><span /></div>
            <span className="preview-url">invest-search.local/app</span>
          </div>
          <div className="preview-body">
            <div className="preview-sidebar" />
            <div className="preview-content">
              <div className="preview-q">Où ouvrir un café avec peu de concurrence ?</div>
              <div className="preview-answer">
                <div className="preview-line w80" />
                <div className="preview-line w60" />
                <div className="preview-line w90" />
                <div className="preview-line w40" />
              </div>
              <div className="preview-cards">
                <div className="preview-card" />
                <div className="preview-card" />
                <div className="preview-card" />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="landing-stats">
        {stats.map((s) => (
          <div key={s.label} className="stat-item">
            <strong>{s.value}</strong>
            <span>{s.label}</span>
          </div>
        ))}
      </section>

      <section className="landing-features">
        <div className="features-header">
          <span className="features-badge">
            <Zap size={14} />
            Ce que vous pouvez vérifier
          </span>
          <h2>Une première lecture du terrain avant de vous déplacer</h2>
          <p>
            L'objectif n'est pas de remplacer l'enquête terrain. C'est de réduire les zones
            à visiter, préparer les bonnes questions et documenter chaque hypothèse avant
            une décision d'investissement.
          </p>
        </div>
        <div className="features-grid">
          {features.map((f) => (
            <article key={f.title} className="feature-card">
              <div className="feature-icon">
                <f.icon size={22} />
              </div>
              <h3>{f.title}</h3>
              <p>{f.desc}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-cta">
        <div className="cta-inner">
          <Globe2 size={32} />
          <h2>Essayez-le sur une vraie question</h2>
          <p>
            Comparez une zone, choisissez un secteur ou demandez un rapport. Les données de
            Casablanca sont déjà prêtes.
          </p>
          <button onClick={() => onNavigate("auth")}>
            Accéder à la démo
            <ArrowRight size={18} />
          </button>
        </div>
      </section>

      <footer className="landing-footer">
        <div className="footer-brand">
          <TrendingUp size={16} />
          <span>Invest Search</span>
        </div>
        <p>
          Projet de recherche, Université Mohammed VI Polytechnique. Les recommandations
          servent d'aide à l'analyse et ne constituent pas un conseil financier.
        </p>
        <div className="footer-links">
          <button onClick={() => onNavigate("about")}>À propos</button>
          <button onClick={() => onNavigate("auth")}>Connexion</button>
        </div>
      </footer>
    </div>
  );
}
