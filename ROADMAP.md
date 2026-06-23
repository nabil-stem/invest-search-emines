# Roadmap Invest Search

Objectif: transformer Invest Search en démonstrateur solide pour une revue produit, puis en outil crédible d'aide à la décision pour l'implantation d'activités médicales à Casablanca.

## Position actuelle

Invest Search dispose déjà d'un socle présentable:

- Interface web React/Vite inspirée de Perplexity.
- API FastAPI pour chat, carte, RAG, scoring et administration.
- RAG local avec Ollama / Qwen.
- Carte interactive MapLibre avec points OSM et frontières de zones.
- Scoring par domaine: pharmacie, clinique, dentaire, vétérinaire, laboratoire, radiologie, etc.
- Rapports investisseurs exportables.
- Pipeline data: collecte OSM, nettoyage, scoring, GeoJSON, index RAG.

État data actuel:

- 775 points médicaux dans `data/processed/medical_facilities_clean.csv`.
- 16 zones analysées.
- 146 établissements en district `Unknown`, soit environ 18.8%.
- Forte couverture pharmacie: 532 points.
- Couverture faible pour vétérinaire: 4 points.
- Couverture très faible pour radiologie: 1 point.

Conclusion: bon prototype de marché médical, mais enrichissement nécessaire avant de défendre des recommandations comme réellement fiables.

## Avancées récentes à conserver pour la démonstration

Statut: implémenté et testé localement.

- Garde-fou hors domaine: une question comme "chercher la mère de Cristiano Ronaldo" ne génère plus une recommandation médicale fictive.
- Garde-fou commandes externes: une demande comme "ouvrir youtube.com" est refusée sans lancer le RAG ni recommander Anfa.
- Garde-fou ton / messages non exploitables: une insulte courte déclenche une demande de reformulation au lieu d'une analyse inventée.
- Priorité à la zone demandée: si l'utilisateur écrit "supply gap en Maarif", la réponse reste sur Maarif au lieu de recommander automatiquement Anfa.
- Tolérance aux fautes: `maariff`, `sidi moumene`, `ben msik`, `ain chok` et plusieurs variantes sont corrigées par résolution fuzzy.
- Clarification au lieu d'hallucination: une demande vague comme "je veux investir" déclenche des questions de précision et des suggestions cliquables.
- Lieux hors périmètre: Marrakech, Bouskoura, Rabat, Tanger, Fès, Agadir et Mohammedia sont reconnus sans inventer de score Casablanca.
- Alias local: Sidi Maarouf est rattaché à Ain Chock pour éviter une réponse vide lorsque le client utilise ce nom de quartier.
- Test d'acceptation: `python scripts/evaluate_chat_guardrails.py` couvre 20 scénarios critiques et doit rester vert avant toute démo.

Critère de validation: montrer que l'assistant sait corriger les fautes, demander des précisions et refuser les questions non fiables.

## Priorité 0 - Fiabilité de la discussion

Statut: socle implémenté / à maintenir.

- Bloquer les questions hors périmètre pour éviter une réponse médicale sur une question non médicale.
- Ne jamais transformer une question people, sport, divertissement ou générale en recommandation d'investissement.
- Réponse attendue: message clair "hors périmètre Invest Search" + exemples de questions valides.
- Ajouter des tests de non-régression:
  - "chercher la mère de Cristiano Ronaldo" => hors périmètre.
  - "qui est Messi ?" => hors périmètre.
  - "bonjour" => greeting.
  - "où ouvrir une pharmacie ?" => analyse médicale.
  - "où existe Marrakech ?" => réponse géographique sans score inventé.

Critère de validation: le chatbot sait dire non quand la question sort du domaine.

## Priorité 1 - Enrichissement officiel des données

Objectif: réduire la dépendance à OpenStreetMap seul.

Sources à intégrer ou documenter:

- HCP RGPH 2024 pour population officielle par commune / préfecture: https://www.hcp.ma/Population-legale-du-Royaume-du-Maroc-repartie-par-regions-provinces-et-prefectures-et-communes-selon-les-resultats-du_a3974.html
- Direction régionale HCP Casablanca-Settat: https://www.hcp.ma/reg-casablanca/
- Carte sanitaire du Ministère de la Santé: https://www.sante.gov.ma/EtsSante/pages/default.aspx
- Santé en chiffres 2023: https://www.sante.gov.ma/Documents/2025/01/Sante%20en%20chiffre%202023%20VF.pdf
- Plan d'action communal Casablanca 2023-2028 pour contexte urbain et priorités publiques.
- OpenStreetMap / Overpass pour points géolocalisés.
- Google Places API ou équivalent pour existence réelle, horaires, avis, téléphone et site web.

Actions:

- Créer `data/manual/population_by_zone_2024.csv`.
- Créer `data/manual/official_health_facilities.csv`.
- Créer `data/manual/purchasing_power_proxy.csv` documenté.
- Ajouter `source_name`, `source_year`, `source_url`, `last_verified_at` aux exports critiques.
- Ajouter un score de fraîcheur par source.

Critère de validation: chaque chiffre important peut être relié à une source.

## Priorité 2 - Data Quality Center

Objectif: rendre les limites visibles et professionnelles.

À implémenter dans l'interface admin:

- Nombre total de points.
- Part des districts `Unknown`.
- Répartition par catégorie.
- Couverture par zone.
- Confiance moyenne.
- Nombre de points sans nom, téléphone, adresse ou source URL.
- Dernière mise à jour de chaque fichier.
- Alertes:
  - plus de 10% de points `Unknown`;
  - moins de 10 points pour une catégorie critique;
  - données officielles non synchronisées;
  - RAG non indexé après refresh.

Critère de validation: l'équipe montre qu'elle connaît les limites de son modèle.

## Priorité 3 - Amélioration du pipeline admin

Objectif: un bouton admin doit reconstruire tout ce qui alimente l'app.

Pipeline cible:

1. Collecte OSM.
2. Import sources officielles / manuelles.
3. Collecte ou vérification des frontières de zones.
4. Nettoyage / normalisation.
5. Déduplication.
6. Assignation des zones par polygones.
7. Recalcul des indicateurs.
8. Recalcul des recommandations par domaine.
9. Export GeoJSON.
10. Réindexation RAG.
11. Rapport qualité automatique.

Critère de validation: on peut expliquer comment les données passent de la source brute à la recommandation.

## Priorité 4 - Qualité des recommandations

Objectif: rendre le scoring défendable.

À ajouter:

- Justification des poids par domaine.
- Scoring séparé:
  - pharmacie;
  - clinique de jour;
  - cabinet dentaire;
  - clinique vétérinaire;
  - laboratoire;
  - radiologie;
  - centre de kinésithérapie.
- Sensibilité du score:
  - que se passe-t-il si le poids du pouvoir d'achat augmente ?
  - que se passe-t-il si OSM sous-estime la concurrence ?
- Afficher un intervalle de confiance:
  - score central;
  - risque data;
  - recommandation "à valider terrain".

Critère de validation: le score n'est pas présenté comme une vérité absolue, mais comme un outil de tri.

## Priorité 5 - UX de soutenance

Objectif: démonstration fluide en présentation.

Scénario recommandé:

1. Landing page: expliquer le problème.
2. Login demo.
3. Question simple: "bonjour".
4. Question métier: "où ouvrir une pharmacie à faible concurrence ?"
5. Carte interactive: vérifier les points et la zone.
6. Rapport investisseur.
7. Question hors domaine: "chercher la mère de Cristiano Ronaldo" pour montrer le garde-fou.
8. Data Quality Center: montrer limites et sérieux méthodologique.
9. Admin refresh: expliquer la boucle de mise à jour.

Critère de validation: le produit raconte une histoire claire, de la donnée à la décision.

## Priorité 6 - Performance et robustesse

À faire:

- Streaming des réponses LLM.
- Cache des réponses RAG fréquentes.
- Timeout explicite avec réponse fallback propre.
- Tests API automatiques.
- Tests UI avec navigateur pour:
  - login demo;
  - nouvelle discussion;
  - carte;
  - rapport;
  - hors périmètre;
  - historique.

Critère de validation: le site ne donne pas l'impression d'être fragile.

## Priorité 7 - Authentification et rôles

À faire après la démo si le temps manque:

- Auth réelle.
- Rôle `admin`: refresh data, statut sources.
- Rôle `analyst`: chat, carte, rapports.
- Journal des actions admin.
- Masquage des tokens côté UI.

Critère de validation: architecture prête pour une vraie équipe.

## Limites à assumer pendant la présentation

- OSM est incomplet et peut sous-estimer la concurrence.
- Les données de pouvoir d'achat sont encore des proxys.
- Les recommandations ne remplacent pas une visite terrain.
- Les autorisations sanitaires dépendent de la réglementation et du type d'établissement.
- Le modèle ne traite pas de données patient ou personnelles.

Formulation recommandée:

> Invest Search n'est pas un oracle d'investissement. C'est un système d'aide à la décision qui combine sources publiques, cartographie, scoring et RAG pour prioriser les zones à investiguer sur le terrain.

## Definition of Done avant présentation

- Les questions hors domaine sont bloquées.
- La page nouvelle discussion est propre.
- Les rapports s'ouvrent et s'exportent.
- La carte filtre correctement par domaine.
- Les frontières de zones sont visibles.
- Le README et la méthodologie ne contiennent plus d'informations obsolètes.
- Le roadmap explique clairement les enrichissements à venir.
- Un script de tests vérifie les principaux scénarios de démo.
