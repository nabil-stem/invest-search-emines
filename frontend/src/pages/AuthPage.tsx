import { useState } from "react";
import { ArrowLeft, ArrowRight, Eye, EyeOff, Mail, Lock, User, TrendingUp, Info } from "lucide-react";

type Props = {
  onNavigate: (page: "landing" | "app") => void;
};

export default function AuthPage({ onNavigate }: Props) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [showPw, setShowPw] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      onNavigate("app");
    }, 600);
  }

  return (
    <div className="auth-page">
      <div className="auth-left">
        <button className="auth-back" onClick={() => onNavigate("landing")}>
          <ArrowLeft size={18} />
          Retour
        </button>

        <div className="auth-left-content">
          <div className="auth-logo">
            <TrendingUp size={28} />
          </div>
          <h1>Invest Search</h1>
          <p>Intelligence de marché et d'implantation pour Casablanca</p>

          <div className="auth-features">
            <div>
              <strong>4 105</strong>
              <span>Points OSM</span>
            </div>
            <div>
              <strong>5</strong>
              <span>Domaines</span>
            </div>
            <div>
              <strong>16</strong>
              <span>Districts</span>
            </div>
          </div>

          <blockquote className="auth-quote">
            « Invest Search permet de comparer rapidement plusieurs zones et activités avant
            de lancer une validation terrain. »
            <cite>— N. Benali, Consultant en implantation</cite>
          </blockquote>
        </div>
      </div>

      <div className="auth-right">
        <div className="auth-form-wrap">
          {/* Demo CTA — primary path */}
          <div className="demo-cta">
            <button className="auth-demo-primary" onClick={() => onNavigate("app")}>
              <ArrowRight size={18} />
              Accéder en mode démo
            </button>
            <p>Explorez la plateforme avec les données de Casablanca — aucun compte requis.</p>
          </div>

          <div className="auth-divider">
            <span>ou connectez-vous</span>
          </div>

          <div className="auth-tabs">
            <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
              Connexion
            </button>
            <button className={mode === "signup" ? "active" : ""} onClick={() => setMode("signup")}>
              Inscription
            </button>
          </div>

          <form onSubmit={handleSubmit} className="auth-form">
            {mode === "signup" && (
              <label className="auth-field">
                <User size={18} />
                <input
                  type="text"
                  placeholder="Nom complet"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </label>
            )}

            <label className="auth-field">
              <Mail size={18} />
              <input
                type="email"
                placeholder="Adresse email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </label>

            <label className="auth-field">
              <Lock size={18} />
              <input
                type={showPw ? "text" : "password"}
                placeholder="Mot de passe"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
              />
              <button type="button" className="pw-toggle" onClick={() => setShowPw(!showPw)}>
                {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </label>

            {mode === "login" && (
              <div className="auth-extras">
                <label className="auth-remember">
                  <input type="checkbox" defaultChecked />
                  <span>Se souvenir de moi</span>
                </label>
                <button type="button" className="auth-forgot">Mot de passe oublié ?</button>
              </div>
            )}

            <button type="submit" className="auth-submit" disabled={loading}>
              {loading
                ? "Chargement…"
                : mode === "login"
                  ? "Se connecter"
                  : "Créer le compte"}
            </button>
          </form>

          <div className="auth-proto-note">
            <Info size={14} />
            <span>Authentification réelle à connecter — prototype en mode démo.</span>
          </div>

          <p className="auth-switch">
            {mode === "login" ? "Pas encore de compte ?" : "Déjà un compte ?"}
            <button onClick={() => setMode(mode === "login" ? "signup" : "login")}>
              {mode === "login" ? "S'inscrire" : "Se connecter"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
