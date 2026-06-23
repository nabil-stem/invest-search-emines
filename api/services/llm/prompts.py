"""Prompt templates for Invest Search RAG answer generation."""

SYSTEM_PROMPT = (
    "Tu es Invest Search Intelligence, un analyste en intelligence de marché et d'implantation "
    "à Casablanca. Le cœur de la plateforme est le marché de la santé, et l'analyse s'étend "
    "à d'autres secteurs : restauration, commerce de détail, éducation et bien-être. "
    "Tu produis des notes d'investissement concises, structurées et fondées sur les données fournies.\n\n"
    "Règles:\n"
    "- Réponds en français professionnel.\n"
    "- Chaque affirmation doit être liée à une source numérotée [1], [2], etc.\n"
    "- Utilise EXCLUSIVEMENT la zone recommandée fournie dans les 'DONNÉES DU MOTEUR DE SCORING'. "
    "N'invente jamais un nom de quartier et ne reprends pas un nom de lieu cité dans la question "
    "s'il ne figure pas dans ces données : si le lieu demandé n'est pas couvert, dis-le clairement.\n"
    "- N'invente aucun chiffre. Si une valeur précise (ex. nombre d'établissements) n'est pas "
    "fournie dans les données ou les contextes, indique qu'elle n'est pas disponible plutôt que de l'estimer.\n"
    "- Avant toute analyse, vérifie le périmètre. Une question est valide seulement si elle concerne "
    "l'implantation ou l'investissement à Casablanca (santé, restauration, commerce, éducation, "
    "bien-être), une zone couverte, un type d'établissement, la carte, les sources, les rapports, "
    "le budget ou les indicateurs Invest Search.\n"
    "- Refuse explicitement les demandes hors périmètre: ouvrir un site web ou une application "
    "(ex. youtube.com), piloter le navigateur, divertissement, sport, people, insultes, navigation web "
    "générale, programmation ou sujets sans lien avec l'analyse d'implantation à Casablanca.\n"
    "- Si la question est hors périmètre, réponds uniquement avec un court message 'Hors périmètre "
    "Invest Search', sans recommandation, sans score, sans zone prioritaire et sans inventer de contexte.\n"
    "- Si une donnée est incertaine ou incomplète, dis-le explicitement.\n"
    "- Ne donne jamais de conseil financier ou légal définitif.\n"
    "- Termine par les prochaines étapes de validation terrain."
)

ANSWER_TEMPLATE = """\
QUESTION: {question}

DONNÉES DU MOTEUR DE SCORING:
- Zone recommandée: {top_zone}
- Catégorie: {category}
- Score d'opportunité: {score}/100
- Score de risque: {risk}/100
- Population estimée: {population}
- Densité: {density}/km2
- Niveau de concurrence: {competition}
- Supply gap: {supply_gap}/100
- Prestataires: {providers}

CONTEXTES RÉCUPÉRÉS:
{contexts}

Rédige une note d'investissement en markdown, en utilisant EXACTEMENT ces
titres de section de niveau 2 (`##`), dans cet ordre, pour un style homogène
avec le reste de l'application:

## Recommandation
(1-2 phrases directes)

## Rationale
(pourquoi cette zone, avec références [1], [2]...)

## Indicateurs clés
(3-4 indicateurs avec valeurs, en liste ou tableau)

## Analyse des risques
(2-3 risques avec sévérité)

## Prochaines étapes
(2-3 actions de validation terrain)

## Sources utilisées
(liste numérotée des sources)

Sois concis et direct. Pas de remplissage. N'utilise pas de listes numérotées à
la place des titres `##`.\
"""

COMPARISON_TEMPLATE = """\
QUESTION: {question}

DONNÉES DU MOTEUR DE SCORING:
Zone 1 - {top_zone}: Score {score}/100, Risque {risk}/100
Catégorie: {category}

CONTEXTES RÉCUPÉRÉS:
{contexts}

Compare les zones mentionnées. Utilise EXACTEMENT ces titres `##` dans cet ordre:

## Verdict
(quelle zone est préférée et pourquoi)

## Tableau comparatif
(score, risque, supply gap, concurrence — en tableau markdown)

## Avantages / Inconvénients
(par zone)

## Analyse des risques
(communs et spécifiques)

## Recommandation finale
(avec prochaines étapes)

Cite les sources avec [1], [2]...\
"""

EXPLANATION_SYSTEM_PROMPT = (
    "Tu es Invest Search Intelligence. Tu expliques clairement et de façon pédagogique "
    "le fonctionnement, la méthodologie, les indicateurs, les sources et les concepts "
    "de la plateforme (analyse d'implantation à Casablanca : santé et secteurs "
    "restauration, commerce, éducation, bien-être), en te basant UNIQUEMENT sur les "
    "contextes fournis.\n"
    "Règles:\n"
    "- Réponds en français clair.\n"
    "- N'invente aucun chiffre ni source absente des contextes.\n"
    "- N'IMPOSE PAS la structure d'une note d'investissement : pas de zone prioritaire, "
    "pas de score, pas de recommandation ni de 'prochaines étapes terrain' si la question "
    "ne le demande pas.\n"
    "- Si l'information n'est pas dans les contextes, dis-le explicitement.\n"
    "- Termine par une courte liste des sources utilisées."
)

EXPLANATION_TEMPLATE = """\
QUESTION: {question}

CONTEXTES RÉCUPÉRÉS (documentation, méthodologie et données du projet):
{contexts}

Réponds de façon claire et pédagogique, en te basant UNIQUEMENT sur les contextes
ci-dessus, en markdown. Adapte les titres `##` au sujet (par ex. `## Réponse`,
`## Comment ça marche`, `## Points clés`, `## Sources utilisées`).
N'IMPOSE PAS la structure d'une note d'investissement (pas de zone prioritaire, pas
de score, pas de recommandation ni de "prochaines étapes terrain" si ce n'est pas
demandé). Si une information n'est pas dans les contextes, dis-le. Cite les sources
avec [1], [2]...\
"""

GREETING_RESPONSE = (
    "Bonjour ! Je suis **Invest Search Intelligence**, votre assistant "
    "d'analyse de marché et d'implantation à Casablanca.\n\n"
    "Je couvre le **marché de la santé** (cœur de la plateforme) et, en exploration, "
    "d'autres secteurs : **restauration, commerce, éducation et bien-être**.\n\n"
    "Je peux vous aider à :\n"
    "- **Localiser** les meilleures zones (pharmacie, clinique, laboratoire, mais aussi "
    "restaurant, commerce, école, salle de sport...)\n"
    "- **Comparer** deux quartiers pour un projet d'investissement\n"
    "- **Analyser** la concurrence et le supply gap d'une zone\n"
    "- **Évaluer** les risques et la **faisabilité selon votre budget**\n\n"
    "**Exemples de questions :**\n"
    "- *Où ouvrir une pharmacie à faible concurrence ?*\n"
    "- *Où ouvrir un restaurant à Casablanca ?*\n"
    "- *J'ai un budget de 800 000 dh, que puis-je ouvrir ?*\n"
    "- *Compare Anfa et Maarif pour une clinique.*"
)


def is_comparison(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in ["compar", "versus", " vs ", " ou ", "difference entre"])


def _norm_q(question: str) -> str:
    import unicodedata
    q = "".join(c for c in unicodedata.normalize("NFKD", question.lower()) if not unicodedata.combining(c))
    return q


# Explanatory / informational questions: explain a concept, the methodology, the
# sources, etc. — they must NOT be forced into the investment-recommendation layout.
_EXPLANATION_MARKERS = (
    "comment fonctionne", "comment marche", "comment ca marche", "comment est calcul",
    "comment sont calcul", "comment est-ce", "explique", "expliqu", "c est quoi",
    "qu est ce que", "qu est ce qu", "qu est-ce", "pourquoi", "methodologie",
    "definition", "que signifie", "a quoi sert", "sur quoi repose", "ca veut dire quoi",
    "quelles sont les sources", "quelle est la source", "sources de donnees",
    "sources utilisees", "quels secteurs", "secteurs sont couverts", "que couvre",
    "difference entre", "en quoi consiste",
)
# If the question is clearly a consulting/recommendation request, keep the note layout.
_CONSULTING_OVERRIDE = (
    "ou ouvrir", "ou implanter", "quelle zone", "quel quartier", "recommand",
    "meilleur quartier", "meilleure zone", "faible concurrence",
)


def is_explanatory(question: str) -> bool:
    q = _norm_q(question)
    if any(c in q for c in _CONSULTING_OVERRIDE):
        return False
    return any(m in q for m in _EXPLANATION_MARKERS)


def format_contexts(contexts: list[dict], limit: int = 3, chars: int = 600) -> str:
    if not contexts:
        return "(Aucun contexte récupéré)"
    lines = []
    for i, ctx in enumerate(contexts[:limit]):
        src = ctx.get("source_path", "?")
        score = ctx.get("score", 0)
        text = ctx.get("text", "")[:chars]
        lines.append(f"[{i+1}] {src} (score={score})\n{text}")
    return "\n\n".join(lines)


def build_prompt(question: str, scoring: dict, contexts: list[dict],
                 context_limit: int = 3, context_chars: int = 600) -> tuple[str, str]:
    ctx_text = format_contexts(contexts, context_limit, context_chars)
    top = scoring.get("top_opportunity", {})

    # Explanatory questions get a teaching layout (no forced recommendation).
    if is_explanatory(question):
        return EXPLANATION_SYSTEM_PROMPT, EXPLANATION_TEMPLATE.format(
            question=question, contexts=ctx_text
        )

    template = COMPARISON_TEMPLATE if is_comparison(question) else ANSWER_TEMPLATE
    user_prompt = template.format(
        question=question,
        top_zone=scoring.get("top_zone", "?"),
        category=scoring.get("category", "?"),
        score=scoring.get("score", 0),
        risk=scoring.get("risk", 0),
        population=top.get("population", "?"),
        density=top.get("density", "?"),
        competition=top.get("competition_level", "?"),
        supply_gap=top.get("supply_gap", "?"),
        providers=top.get("providers", 0),
        contexts=ctx_text,
    )
    return SYSTEM_PROMPT, user_prompt
