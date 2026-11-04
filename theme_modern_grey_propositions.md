# Thème Modern Grey : état, contrastes mesurés, propositions

## Fait dans ce lot (déjà dans l'arbre, non commité)

1. Palette de fenêtre grise neutre : fond `#1E1E1E`, cartes `#282828`, boutons `#303030`, survol `#3C3C3C`.
2. Accent gris `#A6A6A6` (sélection, boutons principaux, interrupteurs, focus, liens), messages d'information en gris, aperçus d'overlays en gris neutre.
3. Contours des champs et des contrôles à 3,1:1 sur les cartes (WCAG 1.4.11), bordures de cartes plus visibles (environ 1,9:1).
4. Les couleurs de statut (perte, violet, alerte) passent 4,5:1 sur toutes les surfaces, y compris menus et survols (la perte était à 4,2:1).
5. Overlays Modern Grey (gris neutres) et page web du tableau de bord grise avec ce thème.

## Contrastes mesurés (Modern Grey, après correction)

| Surface | Texte | Texte secondaire | Accent | Perte | Violet | Contour de contrôle |
|---|---|---|---|---|---|---|
| Page `#1E1E1E` | 14,1 | 9,2 | 6,8 | 6,0 | 6,3 | 3,5 |
| Carte `#282828` | 12,5 | 8,1 | 6,1 | 5,3 | 5,6 | 3,1 |
| Menu `#333333` | 10,7 | 7,0 | 5,2 | 4,6 | 4,8 | 2,7 |
| Survol `#313131` | 11,1 | 7,2 | 5,4 | 4,7 | 5,0 | 2,8 |
| Ligne sélectionnée `#3F3F3F` | 9,0 | 5,8 | - | - | - | - |

Texte blanc sur bouton principal gris `#757575` : 4,6:1 (juste au-dessus du minimum).

## Propositions

Légende : gain / coût / risque, de 1 (faible) à 3 (fort).

### Corrections

1. **Legacy Grey : accent à 4,4:1 sur les menus** (minimum 4,5:1). Éclaircir un peu le bleu d'accent. Gain 2, coût 1, risque 1.
2. **Modern Dark : contours des champs et boutons à 1,5:1** (minimum 3:1 pour un contrôle). Même méthode que Modern Grey (contour plus clair). Gain 3, coût 1, risque 2 (change l'aspect de tout le thème sombre).
3. **Interrupteur activé en Modern Grey** : actif et inactif ne se distinguent que par la clarté. Ajouter un repère (coche dans le bouton) ou un fond actif plus clair avec bouton sombre. Gain 3, coût 2, risque 1.
4. **Bouton principal gris peu marqué** : texte blanc sur gris `#757575` (4,6:1) devant des boutons secondaires voisins. Option : fond clair avec texte sombre (environ 9:1), ce qui demande de rendre `accentInk` dépendant du thème. Gain 3, coût 2, risque 2 (17 usages du blanc à revoir).
5. **Teintes bleu-ardoise en dur restantes** : badges et grisés du Rookie, couleur neutre des cartes de rang Silver, cartes de pneus (`#5A6472`), gris Tailwind des vues de tour (`#9CA3AF`), rapport HTML et image de stats. Les passer en gris neutre ou les lire dans la palette. Gain 2, coût 2, risque 1.
6. **Surbrillance du joueur dans les overlays** : en Modern Grey la ligne du joueur reste teintée cyan. Choisir : conserver (sens) ou version grise claire. Gain 1, coût 1, risque 1 (décision de design).

### Ajouts

7. **Test de contraste complet des quatre thèmes** : toutes les surfaces × tous les textes et statuts × accent et contours, généré depuis un seul tableau, qui échoue sous le minimum. Aujourd'hui seuls quelques cas sont testés. Gain 3, coût 2, risque 1.
8. **Outil `tools/theme_contrast.py`** : imprime le tableau ci-dessus pour les quatre thèmes (je l'ai utilisé en script jetable). Gain 2, coût 1, risque 1.
9. **Proposer de passer les overlays au même thème** : quand on choisit Modern Grey pour la fenêtre, l'overlay reste en Modern Dark (réglages séparés) et les aperçus restent bleu-ardoise. Une question à l'assistant et dans Réglages. Gain 3, coût 2, risque 1.
10. **Pages OBS de stream et du Director aux thèmes** : elles sont fixes en ardoise (`#0E1116`). Leur donner le thème d'overlay. Gain 2, coût 3, risque 2 (OBS à vérifier en vrai).
11. **Aperçu du thème dans le sélecteur de Réglages** : cartes de couleurs comme dans l'assistant, au lieu d'une liste de mots. Gain 2, coût 2, risque 1.
12. **Dialogues et boîtes natives** (sélecteur de fichiers, de couleurs, barre de titre) : vérifier le rendu en Modern Grey. Pas contrôlé à l'œil. Gain 2, coût 1, risque 1.

### Optimisations

13. **Une seule source des couleurs** : palettes en trois endroits (`ui/__init__.py`, `widget/_style.py`, `web_dashboard.py`). Un tableau par thème, lu partout. Gain 3, coût 3, risque 2.
14. **Changement de thème plus rapide** : la feuille de style de la fenêtre est reconstruite en entier. La mettre en cache par thème. À mesurer avant (budget 150 ms). Gain 1, coût 2, risque 1.
15. **Tableau de bord par variables CSS** au lieu du remplacement de texte (`themed_page`). Gain 1, coût 1, risque 1.
16. **`status_color` appelé souvent** : mise en cache par thème. Gain 1, coût 1, risque 1.

## Vérifié et non vérifié

- Vérifié : tests (9099 passent), captures de Accueil, Overlays, Stats, Calculateur, Réglages, Éditeurs de données en Modern Grey.
- Non vérifié : assistant de configuration, Courses à venir, Visionneuse de tours, dialogues natifs, barre de titre Windows, vrai OBS, Modern White après ces retouches (non touché).
