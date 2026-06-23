import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Database,
  FileSearch,
  Globe2,
  Map,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";

const pipeline = [
  { step: "01", title: "Collecte", desc: "Extraction des données OpenStreetMap, HCP, MSPS et des secteurs restauration, commerce, éducation et bien-être pour Casablanca.", icon: Database },
  { step: "02", title: "Nettoyage", desc: "Normalisation, géocodage et assignation des établissements et POIs aux arrondissements de Casablanca.", icon: Globe2 },
  { step: "03", title: "Scoring", desc: "Calcul du score d'opportunité, supply gap, risque et concurrence avec des pondérations propres à chaque secteur et activité.", icon: BarChart3 },
  { step: "04", title: "Intelligence", desc: "Recherche sémantique RAG sur les documents du projet et génération de notes d'investissement sectorielles.", icon: FileSearch },
];

const sources = [
  { name: "OpenStreetMap", desc: "Points santé et multi-secteurs géocodés : pharmacies, cliniques, restaurants, commerces, écoles et bien-être.", color: "#047857" },
  { name: "HCP RGPH 2024", desc: "Populations et ménages officiels des 16 arrondissements de Casablanca.", color: "#0e7490" },
  { name: "MSPS 2024", desc: "117 structures de soins primaires et 13 hôpitaux publics affectés par arrondissement.", color: "#7c3aed" },
];

type Props = {
  onNavigate: (page: "landing" | "auth" | "app") => void;
};

export default function AboutPage({ onNavigate }: Props) {
  return (
    <div className="about-page">
      <nav className="landing-nav">
        <div className="landing-brand">
          <div className="landing-logo">
            <TrendingUp size={20} />
          </div>
          <span>Invest Search</span>
        </div>
        <div className="landing-links">
          <button onClick={() => onNavigate("landing")}>
            <ArrowLeft size={16} />
            Accueil
          </button>
          <button className="landing-login" onClick={() => onNavigate("auth")}>
            Connexion
          </button>
        </div>
      </nav>

      <section className="about-hero">
        <span className="features-badge">
          <ShieldCheck size={14} />
          À propos du projet
        </span>
        <h1>Intelligence de marché et d'implantation pour Casablanca</h1>
        <p>
          Invest Search est une plateforme de recherche développée à l'Université Mohammed VI
          Polytechnique. Elle combine des sources de données publiques avec un moteur de scoring
          multicritère et une couche RAG locale pour aider les investisseurs et porteurs de projet
          à identifier les zones à fort potentiel, quel que soit le secteur pris en charge.
        </p>
      </section>

      <section className="about-pipeline">
        <h2>Pipeline de traitement</h2>
        <div className="pipeline-grid">
          {pipeline.map((p) => (
            <article key={p.step} className="pipeline-card">
              <div className="pipeline-step">{p.step}</div>
              <div className="pipeline-icon">
                <p.icon size={22} />
              </div>
              <h3>{p.title}</h3>
              <p>{p.desc}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="about-sources">
        <h2>Sources de données</h2>
        <div className="about-source-grid">
          {sources.map((s) => (
            <article key={s.name} className="about-source-card">
              <div className="about-source-dot" style={{ background: s.color }} />
              <h3>{s.name}</h3>
              <p>{s.desc}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="about-disclaimer">
        <h2>Avertissement</h2>
        <div className="disclaimer-content">
          <p>
            <strong>Ce projet est un outil de recherche.</strong> Les scores, classements et
            recommandations sont des filtres décisionnels initiaux basés sur des données publiques
            qui peuvent être incomplètes ou obsolètes.
          </p>
          <ul>
            <li>87 établissements sont en district « Unknown » en raison de limites de géocodage.</li>
            <li>Les données OpenStreetMap ne couvrent pas les acteurs informels ou récemment ouverts.</li>
            <li>Les comptages par zone doivent être validés par une visite terrain.</li>
            <li>Ce projet ne constitue pas un conseil financier, juridique ou médical.</li>
          </ul>
        </div>
      </section>

      <section className="about-cta">
        <Map size={28} />
        <h2>Explorer la plateforme</h2>
        <button onClick={() => onNavigate("auth")}>
          Commencer
          <ArrowRight size={18} />
        </button>
      </section>

      <footer className="landing-footer">
        <div className="footer-brand">
          <TrendingUp size={16} />
          <span>Invest Search</span>
        </div>
        <p>Université Mohammed VI Polytechnique — Projet de recherche</p>
      </footer>
    </div>
  );
}
