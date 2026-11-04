# Mission : charte graphique complète NeoPedal + thème Modern Grey + refonte graphique

J'ai le temps : je veux un travail complet, de fond en comble, pas un ravalement. Tu avances par phases, tu me montres chaque phase finie, et tu continues à proposer des améliorations, des optimisations et des refontes tout au long du travail.

## Point de départ à lire en entier avant tout

1. `audit_ui_ux_2026-11-03.md` (racine du dépôt) et la page https://claude.ai/artifact/ArCkHesG1GA1MqMmYyuntw (Artifact, action read) : 49 constats, 32 simplifications, 8 lots, décisions D-1 à D-7, palette proposée avec contrastes, maquettes des 4 espaces. Ce travail est la base : tu l'améliores, tu ne le refais pas de zéro. Dis-moi ce que tu gardes, ce que tu changes et pourquoi.
2. Les audits précédents `audit_ui_ux_2026-10-18.md`, `audit_ui_ux_2026-10-29.md`, `audit_ui_ux_incoherences_2026-10-29.md`.
3. Le code des tokens et des thèmes : l'objet `theme` dans `neopedal/ui/quick/__init__.py`, `tokens.py`, les composants Tp* en QML (TpText, TpTable, TpSectionCard, TpButton, TpMenu, TpDialog, TpToast…), `set_style_window` pour les widgets Qt, les overlays modernes dans `widget/_modern`, le tableau de bord web et les overlays de stream. Repère-les toi-même avec Glob et Grep.
4. Vérifie `git status` : d'autres sessions modifient l'arbre en direct (la page Accueil en particulier). Ne touche à rien qui n'est pas dans ton périmètre.

## Phase 1 : inventaire mesuré

1. Capture chaque page de l'app et chaque overlay, dans chaque thème existant, depuis la vraie app avec un APPDATA de travail jetable.
2. Extrais du code toutes les valeurs réelles : couleurs (y compris les valeurs codées en dur), tailles de police, espacements, rayons, ombres, durées d'animation, icônes. Donne les chiffres et l'écart à la règle (nombre de valeurs hors tokens, par fichier).
3. Liste les composants Tp* avec leurs états (repos, survol, appui, focus, désactivé, erreur, chargement, vide).
4. Rends-moi ça en rapport court, puis passe à la phase 2 sauf si je t'arrête.

## Phase 2 : la charte graphique

Un document complet, publié en page Artifact (en français) et copié dans `docs/design-system.md` (en anglais, comme le reste de la doc du dépôt). Il couvre :

1. Principes et ton de l'app (lisible à un mètre, calme, une seule identité entre l'app, les overlays, le web et le stream).
2. Couleur : échelle de gris neutre complète, accent, couleurs sémantiques (succès, avertissement, erreur, info), couleurs de statut alignées sur `setting_status_colors` (Hypercar rouge, GT3 vert, GTE jaune, purple pour le meilleur de classe, vert pour le record perso, jaune pour plus lent). Chaque paire texte/fond avec son contraste calculé par un script, objectif AA minimum partout, AAA pour le texte principal. Variante daltonienne des overlays.
3. Typographie : familles (Barlow pour les overlays), échelle de tailles, graisses, hauteurs de ligne, chiffres tabulaires pour les temps.
4. Espacement, grille, rayons, bordures, élévation et ombres, densité (compact, normal), tout en tokens nommés.
5. Mouvement : durées, courbes, ce qui s'anime et ce qui ne s'anime jamais, respect du taux de rafraîchissement (`animation_rate.py`).
6. Iconographie : jeu unique, tailles, épaisseurs, glyphes Segoe vérifiés, drapeaux.
7. Catalogue des composants avec tous leurs états, des maquettes de chaque page type (tableau, formulaire, carte, graphique, assistant), les états vides, de chargement et d'erreur, le ton des messages.
8. Les overlays en jeu : fond, opacité, lisibilité sur circuits clairs et sombres, relation avec le thème de l'app.
9. Règles d'accessibilité : contraste, focus visible, navigation au clavier, cibles de clic minimales.

Fais valider la charte avant de l'appliquer.

## Phase 3 : le thème Modern Grey, complet

1. Décision prise (2026-11-03), elle remplace celle d'octobre (quatre thèmes Modern/Legacy × Dark/Light) : il y a quatre thèmes et uniquement ceux-là : **Modern Dark, Modern Grey, Modern White et Legacy Grey**. Modern Light devient Modern White, Legacy Dark et Legacy Light disparaissent. Le mode daltonien des overlays reste. Pas de High Contrast, pas d'éditeur de thème, pas de thème « System ». Les réglages `window_color_theme` et `overlay_theme` restent deux réglages séparés, chacun avec ces quatre valeurs.
2. Écris la migration : un ancien Modern Light devient Modern White, un ancien Legacy Dark ou Legacy Light devient Legacy Grey, Modern Dark ne change pas. Vérifie ce que font les presets et les imports/exports de réglages qui citent un ancien nom.
3. Legacy Grey garde l'esprit TinyPedal d'origine (overlays à la mise en page classique, couleurs classiques, application avec la palette 2.50), mais passe par la même charte : mêmes tokens, mêmes contrastes minimum, seule l'identité change.
4. Chaque thème doit exister dans toutes les couches, sinon il n'est pas complet :
   - tokens QML et toutes les pages ;
   - widgets Qt restants (menus du ☰, tray, boîtes de dialogue, sélecteurs de fichiers) ;
   - overlays modernes (`widget/_modern`) et overlays classiques s'il y a lieu ;
   - tableau de bord web, overlays de stream (OBS), captures et visuels du dépôt ;
   - barre de titre et rail (fond uni, pas de Mica : décision D-7 du 2026-11-03).
5. Un seul endroit définit les valeurs. Aucune couleur en dur ne doit rester ; ajoute ou durcis le test de ratchet existant sur les tokens pour que ça ne régresse pas.
6. Le sélecteur de thème, les réglages, les presets et l'import/export gèrent les quatre thèmes. Mets à jour la doc, le wiki, les tests de migration et les changelogs (EN et FR) avec le lot concerné, avant de le commiter.

## Phase 4 : la refonte page par page

1. Applique la charte aux lots de l'audit dans l'ordre que nous validons ensemble : composants partagés d'abord, puis le shell (rail, barre de titre, les 4 espaces si D-x le valide), puis chaque page, puis les dialogues et les mots (lot H).
2. Pour chaque page : capture avant/après dans chaque thème, temps d'ouverture mesuré (budget 150 ms), et ce que tu as simplifié ou supprimé. Les suppressions attendent mon accord explicite.
3. Optimise en même temps : mémoire, démarrage, rendu (MSAA, couches), pages chargées à la demande. Chiffre avant/après.

## Propositions continues

Tiens à jour une liste `P-001, P-002…` de tout ce que tu repères en route : amélioration, optimisation, refonte, simplification, incohérence. Chaque entrée a une catégorie, un gain, un coût et un risque. À la fin de chaque phase, présente les nouvelles propositions avec AskUserQuestion et laisse-moi choisir. Ne les implémente pas sans mon choix.

## Règles du projet

1. Git : tu commites uniquement en local et tu ne pousses jamais (ni master ni aucune branche) : c'est moi qui décide de pousser sur master. Tu ne commites un lot ou une page que lorsqu'il est entièrement validé : tests passés, vraie app lancée, captures avant/après faites, README (EN), wiki et changelogs (EN et FR) à jour, `make_change_visual.py --scan` lancé pour un changement visuel (le contrôle visuel de la CI veut un PNG dans `docs/changes` ou `[visual]` dans le message). Un commit par lot ou par page, avec un message clair. Si quelque chose n'est pas validé (test rouge, vérification impossible, doute), tu ne commites pas et tu me poses la question avec AskUserQuestion : on corrige, on commite quand même en le disant, ou on laisse de côté. Hors de ce cas, pas de question avant de commiter.
2. QML : tokens `space*/pad*/row*`, `tint()/tone()`, composants Tp ; ne jamais dimensionner depuis `.visible` ; pas de propriété nommée comme une ancre ; Échap ferme les pages ; jamais `setSource(QUrl())` avec un fournisseur d'images asynchrone ; les pages ne défilent jamais d'elles-mêmes.
3. Français : toute chaîne visible passe par `tr(text, ctx)` avec sa traduction dans `i18n/fr.py` (espace insécable avant `:`). Ne jamais lancer `tools/gen_fr_options.py`.
4. Édite l'arbre partagé par remplacement exact, jamais par restauration d'un fichier entier. Teste et lance l'app depuis un worktree propre de HEAD, avec un APPDATA de travail jetable, pytest depuis la racine.
5. Je n'ai ni casque VR ni Windows 10 : ne me demande aucun test là-dessus, dis seulement ce qui reste non vérifié. Les graphiques de la Régie restent dans la Régie. Pas de mode sans échec.
6. Tout code qui touche au système est désactivé par défaut et testé par moi.

## Rendu

Réponds en français. Numérote chaque point pour que je puisse répondre « points 1 2 4 ». Après chaque phase, envoie un rapport avec SendUserFile : ce qui est fait, ce qui est vérifié, ce qui ne l'est pas, et les propositions P-xxx nouvelles.
