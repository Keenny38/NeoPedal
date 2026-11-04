# Mission : audit du cache et des appels API de NeoPedal (RaceControl, REST du jeu, GitHub, sources web)

Contexte. NeoPedal parle à plusieurs services : RaceControl (raceos.gg), l'API REST locale de LMU (localhost:6397), GitHub (mises à jour, notes de version, captures du changelog), une feuille Google (temps de référence), le serveur d'images du menu du jeu. Le 2026-11-02, RaceControl a bloqué mon IP après des rafales de requêtes de la page Courses à venir, puis a suspendu mon compte le 2026-11-03 (« outils tiers », trop d'appels en peu de temps). Depuis, les requêtes RaceControl sont plafonnées (`process/raceos.py` : 12/min, 120/h, 1 s d'écart, blocage 1 h doublé après un 403), mais la politique de cache reste empirique : des durées posées au jugé (`READ_SECONDS` 1800 s, `LIVE_READ_SECONDS` 600 s, `SLOW_ROUTE_SECONDS` 3600 s, `KEEP_SECONDS` 3600 s, `ONLINE_SECONDS` 1800 s…) sans lien avec le rythme réel de changement des données.

Idée à vérifier, pas à croire : « les courses changent tous les mardis, donc on peut économiser beaucoup d'appels ». Elle est peut-être vraie pour une partie des routes (courses hebdomadaires `weekly`/`special`, championnats), sûrement fausse pour d'autres (`daily/schedule` ne couvre qu'un jour UTC, les inscriptions, les places, les champs de pilotes et les serveurs hébergés bougent en continu). Rien dans le code ne connaît aujourd'hui un « jour de renouvellement » (aucune logique de mardi). Ta première tâche est de dire, route par route, ce qui change vraiment et quand, avec des preuves.

## Interdits absolus pendant cet audit

1. Aucun appel réel à raceos.gg, depuis cette machine ou ce compte. Mon compte est suspendu et mon IP a déjà été bannie une fois. Tout se fait hors ligne : code, `.race_schedule.json`, captures déjà présentes dans le dépôt (`audit_bugs_upcoming_races_2026-11-02.md`, `tests/`, fixtures), bundle du jeu (`Bin/UI.zip`, `start/assets/app-*.js`, lecture hors ligne). Si une vérification exige un vrai appel, tu ne le fais pas : tu la mets dans « À vérifier par Steven » avec la commande exacte.
2. Aucun appel REST du jeu à effet de bord (voir la liste « Never call » de la mémoire `lmu-rest-game-endpoints`) ; jamais `startRace`. Le jeu peut tourner pendant l'audit : lecture seule, pas de commande caméra/replay/HUD.
3. Aucune augmentation de débit, de fréquence ou de parallélisme vers un service externe, même « petite ». Tout changement va dans le sens de moins de requêtes ou du même nombre.

## Phases (étanches : aucun fichier de code touché avant la phase qui l'autorise)

### Phase 0 : liste des fichiers
1. Liste les fichiers que tu lis (déjà repérés : `race_schedule_info.py`, `process/race_schedule.py`, `process/raceos.py`, `process/field_ranks.py`, `process/driver_ranks.py`, `rank_info.py`, `game_rest_cache.py`, `game_rest.py`, `game_rest_poll.py`, `adapter/restapi_connector.py`, `http_limits.py`, `update.py`, `release_manifest.py`, `userfile/lap_reference.py`, `userfile/badge_icons.py`, `stream_overlay.py`, `widget/_modern/pit_stop_estimate.py`, `ui/quick/schedule_backend.py`, `ui/quick/race_watch.py`, `ui/quick/schedule_reminders.py`, `ui/quick/home_backend.py`, `ui/quick/online_results.py`, `ui/release_notes.py`, `ui/quick/release_backend.py`) et ceux que tu ajoutes en route. Les sessions éditent l'arbre en direct : fichiers partagés par remplacement exact, jamais par restauration d'un fichier entier.

### Phase 1 : cartographie (lecture seule)
1. Inventaire de TOUS les appels sortants, un tableau : service, route, déclencheur (démarrage, minuteur, page affichée, action du joueur, jeu en session), fréquence réelle, plafond, cache (mémoire / disque / aucun), durée de vie, invalidation, comportement hors ligne / 403 / 429 / 500, qui d'autre lit la même donnée (doublons entre Accueil, page Courses à venir, Driver Stats, race watch, rappels, résultats en ligne).
2. Pour RaceControl : rythme de changement réel de chaque route de `rs.ROUTES` (`daily/schedule`, `daily/list/<tier>`, `special-events/weekly|special`, `championships/active|upcoming`, `championship/<id>`, `coop/event/*`, `event/entries`, `hosted`, `practice/servers`, `leaderboards/results-for-users`, `results`, `players`, `friends-list`, sign-in). Pour chacune : ce qui la fait changer (minuit UTC, renouvellement hebdomadaire, début de course, inscription d'un autre joueur, fin de course), preuve (code du parseur, heures UTC observées dans les réponses déjà enregistrées, bundle du jeu). Dis explicitement si le « mardi » est confirmé, infirmé ou non démontrable, et pour quelles routes.
3. Pour les sign-ins (`authenticate`, ~30 min de jeton, `SIGN_IN_SECONDS` 600) : combien par heure dans chaque scénario (jeu fermé, jeu ouvert menu, en session, page Courses à venir ouverte, app laissée 8 h).
4. Pour le REST local : routes lues par le connecteur et par les pages, intervalles (`restapi_update_interval`, `MAX_UPDATE_INTERVAL`, `SHARED_MAX_AGE`, `STALE_AGE` 30 s), doublons entre `game_rest_cache`, `RoutePoller` et les lectures directes qui contournent le cache. Routes dont les données sont statiques par session ou par installation (pilotes, pistes, voitures, `getAuthSessionTicket`, trackmaps) et lues trop souvent.
5. Pour GitHub et les sources web : fréquence de vérification des mises à jour (`number_of_hours_between_update_checks` 12 h), limites de l'API GitHub non authentifiée (60/h par IP : jamais d'appel inutile), ETag / `If-None-Match` / `If-Modified-Since` utilisés ou non, notes de version et captures re-téléchargées ou non, feuille Google de référence (cache disque, ETag), icônes du serveur d'images.
6. Vérifie la qualité des caches existants : une réponse en erreur (403, 429, 500, `null`) est-elle mise en cache comme une réponse valide ? Un cache disque périmé est-il affiché comme frais ? Les entrées sont-elles bornées (mémoire et disque) ? Quel est le comportement au changement de compte, de langue, de jeu lancé/fermé, de passage hors ligne ? Les caches survivent-ils bien à un redémarrage (aucune requête au lancement si la copie disque est récente) ?
7. Mesure sur du réel quand c'est possible sans appeler raceos.gg : compte de requêtes par scénario avec les tests de rejeu et un faux client (`tests/test_raceos_fewer_requests.py` montre la méthode), et compteur `MAX_PER_HOUR` / journal « HOUR_WARNING ». Chiffre le « avant » de chaque scénario : requêtes par heure, par jour, au démarrage.

### Phase 2 : rapport
1. Fichier `audit_cache_api_<date>.md` à la racine (ignoré par git), preuves dans `audit_cache_api_preuves/` supprimé à la fin.
2. Chaque point numéroté C-001, C-002… sans trou, justifié par `file:ligne` + chemin d'exécution, ou vu en direct (journal, réponse enregistrée) ; doute → « À vérifier ». Une catégorie par point : Correction, Optimisation, Amélioration, Ajout, Refonte. Pour chaque point : gain chiffré (requêtes évitées par heure/jour, ms, Mo), risque (jeu, RaceControl, données périmées affichées), effort, fichiers, tests à écrire.
3. Une liste finale classée par priorité, avec cette grille :
   - **P0 Critique** : tout ce qui peut faire bloquer l'IP ou le compte d'un joueur (rafales, boucles de nouvelle tentative, sign-ins répétés, absence de plafond, réponses d'erreur re-demandées sans attente, plusieurs instances de l'app derrière la même IP, comportement sur 403/429/500 à froid), les caches qui servent des données fausses ou périmées sans le dire, les fuites de mémoire ou de disque.
   - **P1 Gros gains** : les économies réelles de requêtes par une politique de cache fondée sur le rythme de changement (par exemple un « prochain renouvellement connu » par route, au lieu d'une durée fixe ; plus aucune lecture tant que la donnée ne peut pas avoir changé ; rafraîchissement ancré sur la prochaine heure de course ; conditional requests ETag/Last-Modified quand le serveur les accepte), la mutualisation des doublons entre pages.
   - **P2 Améliorations** : mode hors ligne propre, indicateur « donnée lue il y a X min » partout, bouton Actualiser limité mais explicite, réglage unique de la fréquence, journal de requêtes lisible, compteur dans un panneau de diagnostic.
   - **P3 Confort et refontes** : ce qui simplifie (fusion de caches parallèles en un seul service de cache à clés/TTL/invalidation, une seule file d'attente de requêtes externes, une seule source de vérité des intervalles), ajouts non urgents.
4. Un tableau « Avant / Après » du nombre de requêtes par scénario (démarrage à froid, 1 h jeu fermé, 1 h page Courses à venir ouverte, 3 h de course en ligne, journée entière app ouverte) pour RaceControl, REST du jeu, GitHub.
5. Une section « Décisions à prendre » (pour la phase 4) et une section « À vérifier par Steven » (tout ce qui exigerait un vrai appel RaceControl ou un test en jeu).
6. Rien n'est « bug » si c'est du style ou du refactor sans effet visible : l'optimisation, l'UI et la refonte vont dans leur propre catégorie. Une croissance de RAM/CPU/disque non bornée ou un risque de blocage RaceControl comptent comme bugs.

### Phase 3 : corrections sûres automatiques
1. Uniquement les points P0 « Correction » dont la cause est démontrée par le code ou un test qui échoue, qui ne changent aucun comportement visible par le joueur et ne touchent aucun fichier modifié par une autre session non commitée. Pour chacun : test de régression qui échoue sans le correctif, une ligne dans CHANGELOG.md et CHANGELOG.fr.md (mêmes sections), commit local propre (voir règles).
2. Tout le reste attend la phase 4.

### Phase 4 : sélection
1. Tu t'arrêtes. Tu me présentes les décisions avec AskUserQuestion (4 questions × 4 options maximum, ta recommandation en premier) : quels lots P1/P2/P3 appliquer, ordre, et les points à effet visible ou sensibles pour RaceControl (nouvelles durées de cache, réglage exposé ou non, lecture au démarrage).
2. Je réponds avant que tu touches au code de ces lots.

## Règles du projet (non négociables)

1. Git : commits locaux uniquement, jamais de `git push` (c'est moi qui décide de pousser sur master). Un commit par point ou par lot cohérent, seulement quand tout est validé : tests passés, vraie app lancée, README (EN), wiki et changelogs (EN et FR) à jour. Si quelque chose n'est pas validé, tu ne commites pas et tu me poses la question avec AskUserQuestion. CONTRIBUTING.md l'emporte sur ce prompt (dis-le-moi si conflit). Ne commite pas les fichiers d'une autre session.
2. Vie privée et données : jamais de nom de joueur ni d'adresse de serveur dans les caches disque (déjà le cas pour `.race_schedule.json`, `practice` avec mot de passe jamais gardé). Ne touche pas à mes vrais fichiers de données (stats, tours, config) : APPDATA jetable pour tous les lancements.
3. Les options existantes gardent leur sens : `enable_online_driver_ranks` et les fonctions RaceControl restent activables ; ne les désactive pas par défaut sans me poser la question (ma décision du 2026-11-02 est en cours de réexamen depuis la suspension). Toute nouvelle option : OFF si elle touche au système, migration de réglages si besoin, `option_help` et `fr_options.json` (jamais `tools/gen_fr_options.py`).
4. QML : tokens `space*/pad*/row*`, composants Tp, jamais dimensionner depuis `.visible` ; chaque chaîne visible via `tr(text, ctx)` avec traduction dans `i18n/fr.py` (U+00A0 avant `:`). Tout changement visible : captures avant/après, `make_change_visual.py --scan`.
5. Pas de mode sans échec. Je n'ai ni casque VR ni Windows 10 : ne me demande aucun test là-dessus, dis seulement ce qui reste non vérifié.
6. Les durées doivent vivre dans un seul module de constantes (pas de nouveau chiffre magique éparpillé) et chaque durée de cache doit citer sa raison (rythme de changement de la donnée, limite du service).
7. Un cache qui répond doit toujours dire son âge à l'interface, et jamais présenter comme frais une copie lue après un échec.

## Vérification

1. Tests depuis un worktree propre de HEAD (les autres sessions modifient l'arbre), pytest lancé depuis la racine ; `--self-test` avec un APPDATA jetable ; jamais de test qui appelle le vrai raceos.gg (faux client et horloge simulée : tu peux faire avancer le temps de plusieurs jours pour prouver qu'aucune requête n'est envoyée avant l'heure de renouvellement et qu'une est envoyée juste après).
2. Pour chaque lot appliqué : le compte de requêtes « avant » et « après » dans les mêmes scénarios, avec le faux client.
3. Avant de rendre la main : liste ce qui est vérifié, ce qui ne l'est pas, et ce qui dépend d'un test en jeu ou d'un vrai appel RaceControl de ma part (et que je ne ferai pas avant d'avoir des nouvelles du support).

## Rendu

Réponds en français. Numérote chaque point pour que je puisse répondre « points 1 2 4 ». Envoie le rapport final avec SendUserFile. Si je ne suis pas devant le PC : fais les phases 0 à 3 seul, prends la décision la plus prudente et note-la dans une section « Décisions prises seul », puis arrête-toi avant la phase 4.
