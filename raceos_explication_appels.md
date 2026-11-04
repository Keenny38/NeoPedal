# NeoPedal et RaceControl : ce que l'application demande, et à quelle fréquence

Document à joindre à la demande de revue du compte « Keenny Hess » (SteamID64 76561198796471594).
Chiffres relevés dans le code (la version publiée **0.29.0** demande plus que ce qui suit : voir « Ce qui change avec la 0.29.1 » ; la 0.29.1 est prête mais pas encore publiée) (https://github.com/Keenny38/NeoPedal, code source ouvert, fichiers `neopedal/process/raceos.py` et `neopedal/race_schedule_info.py`).

## 1. Ce qu'est NeoPedal

Application gratuite et open source (fork de TinyPedal, cité dans le wiki officiel de TinyPedal), qui affiche des overlays, des statistiques et une page « Courses à venir » pour Le Mans Ultimate. Elle ne modifie pas le jeu et ne contourne aucune protection.

## 2. Comment elle parle à RaceControl

Exactement comme le menu du jeu, et seulement si le jeu tourne :

1. Elle demande au jeu, sur son API locale (`/rest/profile/getAuthSessionTicket`), le ticket de session Steam du joueur.
2. Elle se connecte à `https://raceos.gg/authenticate` avec ce ticket (même requête que le jeu), puis envoie ce jeton dans l'en-tête `Game-Authorization`.
3. Elle s'annonce par un `User-Agent: NeoPedal`.

Le ticket et le jeton restent en mémoire : ils ne sont ni enregistrés ni écrits dans les journaux. Il n'y a pas de websocket (celui du jeu n'est jamais dupliqué). Aucune donnée n'est envoyée à un autre service.

## 3. Ce qui est lu, et à quelle fréquence

| Demande | Fréquence maximale |
|---|---|
| Connexion `authenticate` (rangs Driver Rank / Safety Rank du joueur) | au démarrage, après la fin d'une session **en ligne** (0.29.1 ; 0.29.0 : après toute session), puis au plus toutes les 30 min ; une connexion de moins de 10 min est réutilisée ; bouton « Actualiser » limité à une fois par 5 min |
| Calendrier courses quotidiennes (3 niveaux) | toutes les 30 min en arrière-plan ; page « Courses à venir » ouverte : 0.29.1 une fois par créneau de course (15, 20 ou 30 min selon le niveau), 0.29.0 toutes les 10 min |
| Calendrier du jour, hebdomadaire, spécial | hebdomadaire 1 fois par heure ; calendrier du jour après minuit UTC ou toutes les 6 h (0.29.1 ; 0.29.0 : 1 fois par heure) ; spécial : l'absence d'événement est retenue 1 h (0.29.1) ; **0.29.0 le redemandait à chaque lecture** (réponse 500 quand il n'y en a pas) |
| Championnats, co-op | co-op 1 fois par heure ; championnats actifs à la fin de la manche courante (le mardi 05:00 UTC) ou toutes les 6 h (0.29.1 ; 0.29.0 : 1 fois par heure) ; uniquement si la page est ouverte |
| Serveurs hébergés | toutes les 10 min, uniquement si l'onglet est affiché |
| Rangs des pilotes d'une session (`api/v1/players`, 50 noms par requête) | un pilote n'est relu qu'au bout d'1 h ; les arrivées sont groupées (1 requête par 15 s au plus) |
| Serveur de votre course (`event/my-split`) | 1 fois par minute, uniquement pour une course où le joueur s'est inscrit, de 1 min avant le départ jusqu'à 30 min après, 4 courses suivies au plus, arrêt après 5 lectures sans réponse |
| Place du joueur dans les classements hebdomadaires (`leaderboards/results-for-users`, 2 requêtes par classement) | **automatique page ouverte** (je l'avais omis dans une première version de ce document) : 0.29.1 pour les pistes roulées dans les 8 derniers jours seulement, toutes les 2 h ; 0.29.0 pour tous les classements suivis (une quinzaine), toutes les 30 min |
| Plateau d'une course (`event/entries`) | page ouverte, 0.29.1 : une lecture par départ dans les 10 min avant le départ ; 0.29.0 : toutes les 10 min dans les 15 min avant |
| Détails, autres classements, résultats | seulement quand le joueur ouvre l'écran correspondant |
| Inscription / désinscription (`event/register`, `event/unregister`) | seulement quand le joueur clique dessus |

Ordre de grandeur, jeu ouvert (mesuré le 2026-11-03 avec le vrai code, un faux serveur et des réponses réelles) : **environ 10 à 12 requêtes par heure** en arrière-plan ; page « Courses à venir » ouverte : **59 à 70 par heure avec la 0.29.0 publiée**, **environ 20 par heure avec la 0.29.1**.

## 4. Les limites qui s'appliquent quoi qu'il arrive

- 12 requêtes par minute et 120 par heure au maximum, tous modules confondus, avec au moins 1 seconde entre deux requêtes. Au-delà, la requête n'est pas envoyée.
- Les lectures d'arrière-plan s'arrêtent avant d'utiliser toute la réserve (4 requêtes par minute restent aux gestes du joueur).
- Quand RaceControl répond une erreur (5xx) ou ne répond pas (0.29.1) : la lecture s'arrête après 3 routes sans réponse de suite, et recommence après 5 min, puis 10, 20, 40 et au plus toutes les heures (0.29.0 : toutes les routes toutes les 5 min, jusqu'à 57 requêtes par heure).
- Réponse 429 : l'application attend le délai indiqué par `Retry-After`, ou 5 min doublées à chaque nouveau 429.
- Réponse 403 : plus aucune requête pendant au moins 1 h, puis 2 h, 4 h, jusqu'à 6 h à chaque nouveau refus. Cette attente est écrite sur le disque : redémarrer l'application ne la raccourcit pas.
- Le joueur peut tout couper avec l'option `enable_online_driver_ranks` (Paramètres, groupe « Online ») : plus aucune requête vers raceos.gg.

## 5. L'incident du 2 novembre

Pendant mes tests de la page « Courses à venir », une version de développement lisait le calendrier toutes les 2 minutes, se reconnectait toutes les 5 minutes et lisait en plus les inscrits et les classements, en rafales de requêtes parallèles. C'est ce qui a déclenché votre protection : c'est ma faute, et seulement la mienne. Cette version n'a jamais été publiée.

Les versions publiées jusqu'à 0.28.1 se reconnectaient toutes les 5 minutes (rangs seuls, sans la page « Courses à venir »). La version 0.29.0 corrige cela avec toutes les limites ci-dessus.

## 6. Ce que je propose

- Respecter tout plafond ou toute règle que vous fixeriez pour les outils tiers, et le faire appliquer dans NeoPedal par une mise à jour.
- Toute information utile pour que NeoPedal se comporte au mieux avec votre service (clé d'identification, routes à éviter, limites propres) : je m'en tiens à vos consignes.
- Une revue de mon dossier par un membre de l'équipe, ou par Studio 397, vu que le problème est identifié, corrigé et expliqué.

Steven Vezzu (Keenny Hess) — contact : steven.vezzu@gmail.com

---

# NeoPedal and RaceControl: what the app asks for, and how often (English summary)

Free, open-source companion app for Le Mans Ultimate (https://github.com/Keenny38/NeoPedal, version 0.29.0). It signs in to raceos.gg exactly like the game menu (Steam session ticket from the game's local REST API, `User-Agent: NeoPedal`), keeps ticket and token in memory only, opens no websocket and sends nothing to any other service.

Read frequency (version 0.29.1, ready but not yet published; the published 0.29.0 asks more, see the figures at the end of this paragraph): driver/safety ranks at start, after an online session, then at most every 30 min (a sign-in under 10 min old is reused); daily race lists every 30 min in the background (once per race slot, 15 to 30 min, while the Upcoming Races page is open); daily schedule after midnight UTC; championships when their round ends; other routes once an hour; the player's own place in the weekly leaderboards (2 requests each) for tracks driven in the last 8 days, every 2 hours while the page is open; other drivers' ranks once an hour per driver (50 names per request); the split server of a race the player registered to once a minute from 1 min before the start to 30 min after; registrations only when the player clicks. Measured with the real code, a fake server and real answers: about 10 to 12 requests an hour in the background and about 20 with the page open on 0.29.1; **59 to 70 an hour with the page open on the published 0.29.0** (it read every leaderboard place, and the special-events route that answers an error at every read). When RaceControl answers errors, 0.29.1 stops after 3 routes and waits 5, 10, 20, 40, then 60 minutes.

Hard limits: 12 requests/minute, 120/hour, 1 s between requests; 429 → wait for `Retry-After`; 403 → nothing sent for 1 h, doubling up to 6 h, persisted across restarts; one option turns every RaceControl request off.

The 2 November incident came from an unreleased development build of mine (schedule every 2 min, sign-in every 5 min, parallel bursts). It was fixed the same day. I will follow any rule you set for third-party tools, and I ask for my account to be reviewed by a team member or Studio 397.
