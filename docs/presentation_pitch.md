# Invest Search — Présentation & Pitch

Tout ce qu'il faut dire, de la collecte des données au scoring, au RAG et à la
réponse générée par le LLM, en passant par le déploiement (Vercel + ngrok +
modèle local). Trois parties : **(1) le pitch** (texte à dire), **(2) les
scénarios de démo** (questions à poser en live), **(3) Q&A technique**.

---

## 1. Le pitch (texte complet)

### Le problème
« À Casablanca, un investisseur qui veut ouvrir une pharmacie, une clinique, un
restaurant, une école ou une salle de sport se pose toujours la même question :
**où, et avec quel budget ?** Aujourd'hui la réponse se fait à l'instinct, ou avec
des semaines d'étude terrain. **Invest Search** répond en quelques secondes, à
partir de données réelles, secteur par secteur, quartier par quartier. »

### La donnée (collecte)
« Nous combinons plusieurs sources publiques et traçables :
- **OpenStreetMap (Overpass API)** : ~**4 105 points** géolocalisés — 775 points
  santé + 3 330 points multi-secteurs (restauration, commerce, éducation,
  bien-être) collectés avec des requêtes par secteur.
- **HCP RGPH 2024** : population et ménages officiels des **16 arrondissements**.
- **Ministère de la Santé (MSPS 2024)** : 117 centres de soins primaires et
  13 hôpitaux publics, affectés par arrondissement.
- **Web scraping** (Wikipedia, sous licence ouverte) : la taxonomie officielle
  des arrondissements, qui a permis de détecter des zones manquantes. »

### Le nettoyage
« Les données brutes ne sont pas exploitables telles quelles. Le pipeline :
normalise les noms (FR/AR), **déduplique** les établissements proches (RapidFuzz),
**géocode**, **assigne chaque point à un arrondissement** par polygones OSM, et
corrige l'encodage. Chaque enregistrement porte un **score de confiance** selon
la source. Exemple de qualité que ça révèle : des *hammams* qui tombaient dans la
restauration à cause d'une regex non ancrée — corrigé. »

### Le moteur de scoring (le cœur)
« Pour chaque zone et chaque type d'établissement, on calcule un **score
d'opportunité 0–100** :
> 0.30·Demande + 0.25·Sous-offre (supply gap) + 0.15·Pouvoir d'achat +
> 0.10·Accessibilité + 0.10·Faible concurrence + 0.10·Confiance des données
- **Demande** = densité de population.
- **Supply gap** = 100 − (établissements du type / 100k hab.) → plus c'est élevé,
  plus la zone est sous-équipée.
- **Concurrence** = nombre de concurrents dans un rayon (0.5 à 5 km selon le type).
- Les **pondérations sont propres à chaque secteur** : une pharmacie, une clinique
  et un restaurant n'ont pas les mêmes moteurs (footfall, pouvoir d'achat…).
On en tire aussi un **score de risque** et un **niveau de saturation**. »

### L'assistant conversationnel (au-dessus du moteur)
« Le chat n'est pas un simple Q/R. Il a une **vraie mémoire** :
- un **profil investisseur structuré** (budget, secteur, type, zone, objectif) qui
  s'accumule au fil des messages ;
- quand vous dites juste *« Sidi Moumen »* après avoir parlé budget+pharmacie, il
  **comprend le contexte** au lieu de repartir de zéro ;
- une **réécriture de requête** transforme le tout en question autonome avant le
  RAG, mais on **affiche toujours ce que vous avez tapé** ;
- une **tolérance aux fautes** (« pharmacei » → « pharmacie ») ;
- et un **routage intelligent** par type de question :
  recommandation, comparaison, explication, donnée factuelle, faisabilité budget,
  estimation de coût, *« que puis-je ouvrir avec X DH »*, ou réponse honnête quand
  le métier/zone n'est pas couvert. »

### Le RAG (recherche augmentée)
« Pour les questions ouvertes (« où ouvrir… », « explique… »), on fait une
**recherche hybride** :
- **mots-clés (BM25)** pour la précision lexicale,
- **sémantique (embeddings nomic-embed)** pour le sens,
- fusionnées par **Reciprocal Rank Fusion** avec un **plafond par source** pour la
  diversité.
Cela a fait passer notre métrique de pertinence (Hit@5) de **0.20 à 0.90**. »

### Le LLM (génération)
« La rédaction finale est faite par **Qwen 2.5 (7B), en local via Ollama**. Choix
clé : on a **comparé qwen3:8B et qwen2.5:7B** sur notre propre jeu d'évaluation —
qwen2.5 est aussi précis, **plus fidèle aux chiffres** (il n'invente pas) et plus
rapide. **Anti-hallucination** : les faits (population, coûts, comptages) sont
**déterministes** (calculés, pas générés) ; le LLM ne fait que la narration,
ancrée sur les documents récupérés, avec citations. »

### Le déploiement (architecture gratuite)
« On voulait une démo publique **sans coût** tout en gardant le modèle. La solution :
```
Navigateur → Vercel (UI + proxy /api) → ngrok (tunnel) → mon PC (FastAPI + Ollama + Qwen2.5)
```
- **Vercel** sert le site et un proxy léger.
- **ngrok** expose mon PC, l'URL reste côté serveur, protégée par une clé.
- **Mon PC** fait tourner le modèle, le RAG et les données de Casablanca.
Si le PC est éteint, l'app bascule en **mode déterministe** (scoring + mots-clés)
avec une **bannière** qui le signale honnêtement. »

### La conclusion
« Invest Search, c'est un **moteur de décision d'implantation multi-secteurs pour
Casablanca** : données réelles, scoring transparent, assistant conversationnel
fiable, et zéro hallucination sur les chiffres. C'est un outil de recherche — pas
un conseil financier — mais il transforme des semaines d'étude en quelques
secondes. »

---

## 2. Scénarios de démo (à poser en live, dans l'ordre)

> Astuce : commencez modèle **connecté** (réponses RAG riches), gardez 1–2 cas pour
> montrer la robustesse.

| # | Question à taper | Ce que ça montre |
|---|---|---|
| 1 | `bonjour` | accueil, périmètre multi-secteurs |
| 2 | `Où ouvrir une pharmacie à faible concurrence ?` | **RAG + LLM** : reco structurée + sources |
| 3 | `Compare Anfa et Maarif pour une clinique` | comparaison de zones |
| 4 | `J'ai 800 000 DH pour un commerce à Maarif` | **budget ancré sur Maarif** + rang + meilleure alternative |
| 5 | `Quel budget faut-il pour ouvrir une pharmacie ?` | **estimation de coût** (CAPEX/OPEX) |
| 6 | `Que puis-je ouvrir avec 500 000 DH ?` | **affordabilité** : ce qui rentre dans le budget |
| 7 | `Quelle est la population d'Anfa ?` | **réponse factuelle** courte (donnée exacte) |
| 8 | `Comment fonctionne le scoring ?` | **RAG explication** (sans structure de reco) |
| 9 | `Je veux ouvrir un laboratoire` → `Sidi Moumen` → `Compare avec Maarif` | **mémoire conversationnelle** |
| 10 | `ou ouvrir une pharmacei a faible concurence` | **tolérance aux fautes** (corrige + répond) |
| 11 | `Qui va gagner la coupe du monde ?` | **garde-fou** : hors périmètre, refusé proprement |
| 12 | `Où ouvrir une bijouterie ?` | **honnêteté** : type non couvert, pas d'invention |

**Phrase de transition pour la #2 :** « Regardez le badge *RAG* et le panneau
*Sources* : la réponse est ancrée sur des passages réels, pas inventée. »

**Phrase pour la #4 :** « J'ai précisé *Maarif* — il évalue Maarif (rang 14/16) au
lieu de m'imposer la meilleure zone, et me propose de comparer. Il respecte ce que
je demande. »

---

## 3. Q&A technique (anticiper la revue)

- **« C'est fiable ? Ça hallucine ? »** → Les chiffres sont déterministes
  (calculés). Le LLM ne rédige que la narration, ancrée + citée. 25/25 tests de
  garde-fous, 32/32 scénarios, audit « respect de la zone » 10/10.
- **« Pourquoi qwen2.5 et pas un GPT cloud ? »** → Gratuit, local, privé, et notre
  A/B montre qu'il est plus fidèle aux chiffres. Le code est aussi prêt pour une
  API (Together/Groq) si besoin.
- **« Comment c'est hébergé gratuitement ? »** → Vercel (UI) + ngrok (tunnel) +
  mon PC (modèle). Diagramme ci-dessus.
- **« Et les autres secteurs / villes ? »** → Architecture en *sector packs* :
  ajouter un secteur = un fichier de config + une collecte OSM. Une autre ville =
  relancer le pipeline sur sa bounding box.
- **« Limites ? »** → Données OSM parfois incomplètes ; pouvoir d'achat est un
  proxy ; pas un conseil financier — validation terrain recommandée. On l'assume
  explicitement dans chaque réponse.

## 4. Déroulé express (5 min) — version courte

**Avant de présenter (warm-up, hors écran) :**
1. PC allumé : `ollama serve`, `uvicorn server:app --port 8000`, `ngrok http 8000`.
2. Ouvrir l'app, vérifier qu'il **n'y a pas la bannière « mode déterministe »**
   (= modèle connecté).
3. Taper une fois `Combien de cafés à Maarif ?` pour **réchauffer le cache**
   multi-secteurs (la 1ʳᵉ requête secteur prend ~5 s, les suivantes sont rapides).

**Le déroulé (5 interactions) :**
| Temps | Question | Le message à faire passer |
|---|---|---|
| 0:30 | `Où ouvrir une pharmacie à faible concurrence ?` | *« Réponse générée par Qwen 2.5 en local, ancrée sur des sources réelles — voyez le badge RAG et le panneau Sources. »* |
| 1:30 | `J'ai 800 000 DH pour un commerce à Maarif` | *« Je précise Maarif : il évalue Maarif (rang 14/16) au lieu de m'imposer la meilleure zone, et propose la comparaison. Il respecte ma demande. »* |
| 2:30 | `Je veux ouvrir un laboratoire` → `Sidi Moumen` → `Compare avec Maarif` | *« Mémoire conversationnelle : "Sidi Moumen" est compris dans le contexte, pas comme une nouvelle question. »* |
| 3:45 | `Comment fonctionne le scoring ?` | *« Transparence : il explique sa propre méthodologie à partir de la doc, sans inventer. »* |
| 4:30 | `Qui va gagner la coupe du monde ?` | *« Discipline : hors périmètre, refusé proprement — pas de bla-bla. »* |

## 5. Plan B (si le PC / le tunnel tombe en pleine démo)
- L'app affiche la **bannière « mode déterministe »** : annoncez-le franchement —
  *« le modèle tourne sur mon PC ; s'il se déconnecte, l'app bascule en moteur de
  scoring + recherche par mots-clés, sans rien casser. »*
- Les réponses **budget, factuel, comparaison, coût** marchent **toujours** (elles
  sont déterministes). Faites la démo avec celles-là.
- Montrez le **diagramme** et expliquez que la prod utiliserait un backend hébergé
  ou une API Qwen2.5 — le code est déjà prêt (variable d'environnement).

### Le diagramme à montrer
```
Sources (OSM / HCP / MSPS / scraping)
        │  collecte + nettoyage + géocodage + dédup
        ▼
Données structurées (établissements, indicateurs par zone)
        │  moteur de scoring (demande, supply gap, concurrence, risque)
        ▼
Assistant conversationnel  ──►  routage intelligent (reco / budget / coût / factuel / explication)
        │                              │
        │                              ▼
        │                       RAG hybride (BM25 + sémantique → RRF)
        │                              ▼
        └────────────────────►  Qwen 2.5 (local, Ollama) → réponse ancrée + sources
        ▲
   Déploiement : Vercel (UI + proxy) → ngrok → PC (modèle + données)
```
