# Mission : appliquer l'audit UI/UX 0.30 (refonte du shell NeoPedal)

Contexte. Une session d'audit (« On enfile le costume ») a produit l'audit UI/UX 0.30, sans toucher au code : 49 constats (U-001 à U-049), 32 simplifications (S-01 à S-32), 8 lots (A à H), des maquettes et des décisions D-1 à D-7. Source de vérité : `audit_ui_ux_2026-11-03.md` (racine du dépôt) et la page https://claude.ai/artifact/ArCkHesG1GA1MqMmYyuntw (à lire avec l'outil Artifact, action read). Lis les deux en entier avant tout.

## Avant de coder

1. Pose-moi les décisions D-1 à D-7 avec AskUserQuestion (un seul appel, boutons clairs, ta recommandation en premier). Ne commence aucun lot tant que je n'ai pas répondu.
2. Pose aussi, dans le même appel ou le suivant, le choix sur les 6 suppressions : S-06, S-08, S-13, S-21, S-25, S-32. Aucune suppression sans mon accord explicite.
3. Propose l'ordre des lots avec une estimation de risque. Je valide.

## Périmètre

1. Lots A à H de l'audit : composants partagés (TpSectionCard : élévation au survol des cartes cliquables, U-048), shell (rail, barre de titre, regroupement des 15 pages en 4 espaces si D-x le valide), voile « Déposez un preset ou un plugin » pendant le survol d'un fichier dans `app.py` (dragEnterEvent, U-049), dialogues et mots (lot H : QMessageBox/confirm_action restants vers le pont `quick/dialogs.py`, titres « Confirm », ordre des boutons, vocabulaire Refresh/Reload/Read Again, Enable/Turn On, Delete/Remove, trash/recycle bin), temps d'ouverture des pages contre le budget de 150 ms, contrastes (texte blanc sur bleu à 3,2:1).
2. La page Accueil est déjà faite par une autre session (code terminé, non commité). Ne la modifie pas. Réutilise `relative_date(timestamp)` et `long_date_time(timestamp)` de `quick/formatting.py` pour les dates relatives des autres pages (d'abord la ligne « lu il y a 12 min » des Courses à venir).
3. Une session ne touche que les fichiers de son lot. Les fichiers partagés (TpSectionCard, `quick/__init__.py`, `app.py`, `i18n/fr.py`) se modifient par remplacement exact, jamais par restauration d'un fichier entier : d'autres sessions éditent le même arbre en direct.

## Règles du projet (non négociables)

1. Git : tu commites uniquement en local et tu ne pousses jamais (ni master ni aucune branche) : c'est moi qui décide de pousser sur master. Tu ne commites un lot que lorsqu'il est entièrement validé : tests passés, vraie app lancée, captures avant/après faites, README (EN), wiki et changelogs (EN et FR) à jour, `make_change_visual.py --scan` lancé pour un changement visuel (`[visual]` dans le message sinon). Un commit par lot, avec un message clair. Si quelque chose n'est pas validé (test rouge, vérification impossible, doute), tu ne commites pas et tu me poses la question avec AskUserQuestion : on corrige, on commite quand même en le disant, ou on laisse de côté. Hors de ce cas, pas de question avant de commiter. Ne commite pas les fichiers de l'Accueil ni ceux d'une autre session.
2. Thèmes : quatre seulement depuis le 2026-11-03 : Modern Dark, Modern Grey, Modern White et Legacy Grey (plus daltonien pour les overlays). Modern Light devient Modern White, Legacy Dark et Legacy Light disparaissent, avec migration des réglages. Pas de High Contrast, pas d'éditeur de thème, pas de « System ».
3. Pas de mode sans échec, ne jamais le rajouter. Les graphiques de la Régie restent dans la Régie.
4. QML : tokens `space*/pad*/row*`, `tint()/tone()`, composants Tp ; ne jamais dimensionner depuis `.visible` ; pas de propriété nommée comme une ancre ; Échap ferme les pages ; jamais `setSource(QUrl())` avec un fournisseur d'images asynchrone.
5. Français : toute chaîne visible passe par `tr(text, ctx)` avec sa traduction dans `i18n/fr.py` (espace insécable U+00A0 avant `:`). Ne jamais lancer `tools/gen_fr_options.py`.
6. Je n'ai ni casque VR ni Windows 10 : ne me demande aucun test là-dessus, dis seulement ce qui reste non vérifié.
7. Tout code qui touche au système est désactivé par défaut et testé par moi.

## Vérification

1. Tests, lancés depuis un worktree propre de HEAD (les autres sessions modifient l'arbre en direct) avec un APPDATA de travail jetable ; pytest depuis la racine. Ne conclus pas « terminé » sans les avoir passés.
2. Lance la vraie app (`--self-test` d'abord), prends des captures avant/après pour chaque page touchée, sur les deux thèmes, et mesure le temps d'ouverture des pages concernées.
3. Avant de me rendre la main : liste ce qui est vérifié, ce qui ne l'est pas, et ce qui dépend d'un test en jeu de ma part.

## Rendu

Réponds en français. Numérote chaque point pour que je puisse répondre « points 1 2 4 ». Envoie le rapport final avec SendUserFile.
