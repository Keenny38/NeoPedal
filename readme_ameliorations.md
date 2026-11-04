# README : améliorations, corrections, optimisations (2026-11-04)

## Fait dans la refonte

1. **Bandeau d'en-tête** : nouvelle image `images/readme_banner.png` (1600x910, 382 Ko) avec logo, nom, accroche, 6 pastilles et 8 overlays posés comme sur un écran de jeu. Générée par le nouveau script `tools/make_readme_banner.py`, sur les mêmes données de course simulée que l'aperçu.
2. **Mur de texte supprimé** : 5 paragraphes « New in 0.29.0 / 0.28.1 / 0.28.0 » en haut de page, remplacés par le lien Changelog.
3. **Longueur** : de 356 lignes à environ 190. Le détail de chaque fonction renvoie au wiki.
4. **Fonctions en galerie** : 6 blocs image + texte en alternance (overlays, télémétrie, calculateur, stats, résultats, Régie et stream).
5. **Image des 93 overlays** (1920x2878) repliée dans un « See all 93 overlays » au lieu d'écraser le haut de page.
6. **Bouton « Download for Windows »** bien visible, et badges en grand format.
7. **Section « Safe to use »** : pas de triche, plus d'appel à RaceOS depuis la 0.29.1, bouton Requêtes, mises à jour signées. Elle répond directement à l'issue #17.
8. **Présentation selon ta règle** : projet perso fait sur ton temps libre, avec l'aide de l'IA, basé sur TinyPedal (approuvé par son développeur, listé dans le wiki TinyPedal), et pas « juste une app d'overlays ».
9. **Démarrage rapide** en 4 étapes, avec le réglage du jeu inclus au lieu d'un tableau séparé.
10. **Section Soutenir** : Patreon et Ko-fi, avec les emoji uniquement sur les lignes de lien.

## Corrections d'erreurs de l'ancien README

11. `cd ModernTinyPedals` était faux : le dossier cloné s'appelle `NeoPedal`.
12. La légende d'image citait des thèmes supprimés (`Modern Light`, `Legacy Dark`, `Legacy Light`).
13. Le texte « New in 0.29.0 » vantait ce que la 0.29.1 retire : courses hebdomadaires, spéciales et championnats, `Register…` depuis l'app, rangs des autres pilotes, avis de serveur prêt.
14. « 93 % du code couvert » est retiré : chiffre non vérifié. Les 6 331 tests sont comptés, d'où « plus de 6 000 ».

## Fait dans la deuxième passe

15. **README français** `README.fr.md`, avec le lien `English · Français` en haut des deux pages.
16. **Wiki Home** corrigé : 93 overlays, les quatre thèmes actuels, la ligne Courses à venir conforme à la 0.29.1, le bandeau et le GIF à la place du vieil aperçu.
17. **GIF animé** `images/readme_animation.gif` (960x300, 6 s en boucle, 636 Ko) sous le bandeau : Dashboard HUD, carte, forces G, pédales, rapport, delta, trace des pédales, volant. Généré par `tools/make_readme_animation.py` (images en Qt, puis GIF avec Pillow, qui n'est pas une dépendance de l'app).
18. **Image sociale** `images/social_preview.png` (1280x640), faite par le même script que le bandeau. À installer toi-même : GitHub > Settings > General > Social preview > Edit > Upload an image.
19. **Discord** : ton pseudo `keenny` dans la section Contribuer des deux README.
20. **Images allégées sans perte** (oxipng, pixels vérifiés identiques) : de 15 à 25 % de moins sur les 13 images de la page.
21. **3 captures neuves** en Moderne sombre dans `images/readme/` : télémétrie (Le Mans, 2 tours superposés), calculateur (course de 4 h, 2 pilotes, voiture de sécurité), Régie (course simulée à Road Atlanta). Pilotes fictifs, aucun nom réel.
22. **Test des liens** `tests/test_readme_links.py` : chaque image et chaque lien local existe, chaque ancre `#...` pointe sur un titre, et les deux README ont les mêmes images dans le même ordre.
23. **Version** : `tools/next_version.py` compte `README.fr.md` et les nouvelles images du README comme de la documentation, pour qu'un commit qui ne touche qu'elles ne crée pas de version de l'app (test ajouté).

## Reste à faire

24. **Vraie capture en jeu** (overlays sur une image de LMU) : il me faut une capture de toi et ton accord pour la mettre dans le dépôt.
25. **Image sociale** : à installer à la main dans les réglages GitHub (point 18).
26. **Captures restantes** : les stats pilote (2026-10-20) et Résultats & replays (2026-10-14) datent d'avant la barre de titre moderne.
27. **Régénérer l'aperçu** : `tools/make_readme_preview.py` réécrit `readme_preview.png` sans optimisation (+200 Ko) ; il faudra repasser oxipng après chaque génération.
