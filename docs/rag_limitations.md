# Limites du RAG InvestSearch — à communiquer clairement

Document honnête des limites du système, basé sur la batterie de tests adverses
(`scripts/test_production.py`, 32 cas) et l'audit des intentions. À présenter
proactivement : une revue attentive les trouvera, autant les nommer en premier.

## 1. Couverture géographique
- **Casablanca uniquement** (~12 quartiers indexés). Toute autre ville (Rabat,
  Marrakech…) est routée vers `out_of_scope_region` — pas d'invention de données.
- Le grain est le **quartier**, pas la rue/le local. On ne peut pas dire « ce
  coin de Maarif » — seulement « Maarif globalement ».

## 2. Source et fraîcheur des données
- POIs issus d'**OpenStreetMap + scraping web** (instantané figé). La couverture
  OSM est inégale : un POI réel absent d'OSM n'est pas compté → concurrence
  potentiellement **sous-estimée**.
- Population / densité proviennent d'un **jeu de données fixe**, non mis à jour en
  temps réel.
- **Aucune donnée marché temps réel** : loyers, flux piéton, chiffre d'affaires,
  pouvoir d'achat fin ne sont pas dans le corpus. Chaque réponse le rappelle
  (« à confirmer sur le terrain »).

## 3. Modèle de coûts indicatif
- Les estimations CAPEX/OPEX sont des **heuristiques sectorielles**, pas des devis.
  Bon ordre de grandeur, pas une comptabilité.
- Budgets en chiffres (`800k`, `1,5M`) parsés ; **« cinquante mille » (en lettres)
  et < 10 000 DH ne sont pas reconnus** comme budget.

## 4. Couverture sectorielle inégale
- **Médical** = le plus riche. Food / retail / éducation / bien-être ajoutés via
  OSM mais avec une **taxonomie plus grossière**.
- Métier rare ou hors-catalogue (ex. « discothèque ») → `coverage_gap` assumé
  (on le dit, on n'invente pas).

## 5. Langue
- Optimisé **français**. Une question **100 % anglais** part en `out_of_scope`
  (pas de retrieval anglais). Le franglais passe partiellement.
- Correction orthographique : fuzzy + table des fautes fréquentes
  (`farmacie→pharmacie`, `klinik→clinique`…). Une faute **inédite** sur un mot
  hors-vocabulaire peut encore passer.

## 6. Retrieval et scoring
- Corpus **petit (~220 chunks)**, hybride BM25 + embeddings (nomic) + RRF. Le LLM
  **narre le contexte récupéré, il n'ajoute pas de savoir externe** → réponses
  bornées par les données.
- Les **scores sont des composites heuristiques** (concurrence, supply gap,
  densité…), **non validés contre des résultats réels d'implantation**. À lire
  comme une priorisation, pas une vérité.

## 7. Latence et déploiement
- Génération LLM longue/ouverte = **12–14 s** sur CPU local. Risque sur le
  **timeout proxy Vercel Hobby (10 s)** → mitigé par : réponses concises par
  défaut, `maxDuration=60` (Pro), et surtout le **fallback déterministe < 6 s**
  qui marche toujours (testé LLM coupé : 32/32 robustes).

## 8. État conversationnel
- Serveur **stateless** : la mémoire dépend du client qui renvoie
  `investor_profile` + `history`. Si le client les perd, le contexte est perdu.

## 9. Garde-fou hallucination
- Mode **déterministe = sûr** (templates ancrés data). Mode LLM peut broder →
  mitigé par un post-processeur qui **réinjecte les sections data** (population,
  densité, supply gap) si le modèle les omet.

---

## Faut-il ajouter 2 couches de traduction FR→EN→LLM→EN→FR ? — NON

Évalué à la demande. **Recommandation : ne pas le faire.**

- **Le goulot n'est pas la langue.** qwen2.5:7b comprend très bien le français.
  La traduction n'ajoute **aucune donnée** — or nos limites viennent du corpus et
  des scores, pas de la compréhension FR.
- **× ~2–3 la latence** : deux allers-retours LLM de plus. On passe de 12–14 s à
  potentiellement 30 s+ → aggrave franchement le problème de timeout Vercel.
- **2 points de panne en plus** + **dérive de sens** sur les termes métier (noms
  de quartiers, « supply gap », montants en MAD) ; risque de réintroduire les
  problèmes de locale/fautes qu'on vient de corriger.
- La réponse affichée doit rester en français : un aller-retour de traduction
  risque des contresens dans le texte vu par l'utilisateur.

**Meilleurs leviers d'accuracy à la place :**
1. Enrichir / nettoyer le corpus (plus de POIs, taxonomie sectorielle plus fine).
2. Régler le retrieval (plus de chunks, meilleure diversité par source).
3. Améliorer templates déterministes + modèle de coûts.
4. La correction de fautes qu'on vient de renforcer.
5. Si le matériel suit : passer à **qwen2.5:14b** (gain réel) plutôt qu'un
   sandwich de traduction.

**Si un jour tu veux vraiment l'anglais** : détecter l'anglais et traduire
**seulement la question** vers le FR (un seul sens), garder tout le pipeline FR,
répondre dans la langue de l'utilisateur. Bien moins cher qu'un sandwich 2 couches.
