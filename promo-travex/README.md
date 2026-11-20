# Travex Global Forwarding — film promo 16:9

Film de présentation des services de **Travex Global Forwarding** (Renchen, Allemagne · Douala, Cameroun).
Format **1920 × 1080 (16:9)**, **1 min 17**, **voix off française**, sous-titres incrustés, textes issus du site
`travex-global-forwarding.com`.

## Voir le film

```bash
cd promo-travex
python3 -m http.server 8080
# → http://localhost:8080
```

Le lecteur a : lecture / pause, scrub sur la timeline, chapitres, mode muet,
plein écran (`f`), navigation `←` `→` (2 s).

## Découpage

| # | Durée | Plan | Images | Voix off |
|---|---|---|---|---|
| 01 | 14,0 s | Ouverture + route Renchen → Douala | `06-douala.jpg` | « Vos marchandises méritent mieux qu'un simple transport… » |
| 02 | 10,4 s | Fret aérien | `01-air-freight.jpg` | « Quand chaque heure compte, vos envois urgents… » |
| 03 | 9,6 s | Fret maritime, conteneurs & groupage | `02-sea-containers.jpg` | « Des solutions adaptées à vos volumes… » |
| 04 | 7,9 s | Ro-Ro & véhicules | `04-roro-vehicles.jpg` | « Vos véhicules, embarqués à bord… » |
| 05 | 13,8 s | Logistique & entrepôt — Renchen | `03-warehouse.jpg`, `05-truck-europe.jpg` | « Réceptionner, stocker, préparer… » |
| 06 | 9,0 s | Notre différence (humain) | `07-trust-team.jpg` | « Un interlocuteur. Pas un guichet. » |
| 07 | 12,4 s | Appel à l'action + contacts | `05-truck-europe.jpg` | « Demandez votre cotation gratuite… » |

## Texte de la voix off (à relire avant diffusion)

1. Vos marchandises méritent mieux qu'un simple transport. De l'Allemagne au Cameroun, et partout dans le monde, Travex Global Forwarding organise vos expéditions, du premier kilomètre jusqu'à la livraison finale.
2. Fret aérien. Quand chaque heure compte, vos envois urgents et vos marchandises de valeur arrivent vite, en toute sécurité, grâce à nos partenaires spécialisés.
3. Fret maritime, conteneurs et groupage. Des solutions flexibles et maîtrisées, adaptées à vos volumes comme à vos destinations.
4. Véhicules et engins. Embarquement Ro-Ro vers l'international, en collaboration avec des compagnies maritimes spécialisées.
5. À Renchen, en Allemagne, notre plateforme logistique réceptionne, stocke et prépare vos marchandises. Import, export, formalités douanières : nous pilotons chaque étape, de bout en bout.
6. Et surtout, un interlocuteur. Pas un guichet. Nous apprenons à vous connaître, et nous nous adaptons à vos besoins. Pas l'inverse.
7. Demandez votre cotation gratuite. Travex Global Forwarding. Renchen, Allemagne. Douala, Cameroun. Plus de performance, plus de succès.

## Ce qu'il faut vérifier avant publication

- **Chiffres et promesses** : aucun délai ni tarif n'est annoncé, uniquement des formulations du site
  (« marchandises urgentes », « envois de valeur », réseau de partenaires). Rien d'inventé à valider, sauf
  si vous voulez ajouter des chiffres réels (délais, volumes, années d'expérience).
- **Visuels générés par IA** : ce ne sont pas de vraies photos Travex. Le jour où vous avez des photos de
  vos entrepôts, véhicules et équipes, elles se substituent telles quelles dans `assets/img/`.
- **Coordonnées** : `+49 176 506 18495`, `info@travexglobalforwarding.com`, Im Brünnel 2, 77871 Renchen,
  Douala · Bonamoussadi — reprises du site, à confirmer.
- **Bandeau départs** (Francfort → Douala, 30 septembre 2026, 180 € / 23 kg) : volontairement absent du film,
  une offre datée se périme. Peut être ajouté en plan 3 s si vous le voulez.

## Personnaliser

| Je veux… | Où |
|---|---|
| Changer la couleur d'accent | `:root{ --orange:#ff6a1a }` |
| Changer une image | remplacer le fichier dans `assets/img/` (garder le nom) |
| Changer une durée de plan | tableau `SCENES` dans le `<script>` **et** le `--dur` du `.bg` de la scène |
| Changer un texte à l'écran | directement dans la section `<section id="s2">` … |
| Changer la voix off | remplacer `assets/audio/vo-0X.mp3`, réajuster la durée de la scène |
| Changer les sous-titres | bloc `.cap` de chaque scène |

## Fichier vidéo (MP4)

Le film est rendu en vrai fichier vidéo, prêt à publier :

```
promo-travex/export/travex-promo-16x9.mp4
```

1920 × 1080 · 30 i/s · H.264 High / AAC 192 kb/s · ~1 min 17 · voix off mixée (-16 LUFS).

Il est aussi téléchargeable depuis la page de preview (bouton « ↓ Télécharger le .mp4 » en haut à droite).

**Le mettre sur un disque local (D:)** : depuis le navigateur, clic droit sur le bouton de téléchargement →
« Enregistrer le lien sous… », ou glisser le fichier depuis le dossier « Téléchargements » vers `D:`.
Aucun agent ne peut écrire directement sur le disque de votre machine : le fichier doit passer par un
téléchargement.

### Re-rendre après une modification

```bash
pip install --break-system-packages pillow numpy imageio-ffmpeg   # une seule fois
python3 promo-travex/render.py                                    # 4 à 6 min
python3 promo-travex/render.py --stills 3,30,70                   # 3 images de contrôle
```

Tout le montage vidéo est piloté par `render.py` (scènes, durées, textes, cadrages, zoom).
`index.html` est la version « lecteur web » du même film : les deux partagent les mêmes images,
la même voix off et le même minutage.

### Autres formats

Un 9:16 (Reels / TikTok / Shorts) ou un 30 s se dérivent du même `render.py` : changer `W, H` et
réécrire les positions du bloc de texte (titre centré, marges plus larges), les durées de scène étant
déjà pilotées par la voix off.

## Texte d'accompagnement (réseaux sociaux)

> De l'Allemagne au Cameroun, et partout dans le monde. 🇩🇪→🇨🇲
> Fret aérien, maritime, Ro-Ro, entreposage, import-export et douane : Travex Global Forwarding prend vos
> marchandises en charge du premier kilomètre à la livraison finale, avec un interlocuteur qui s'adapte à
> vos besoins — pas l'inverse.
> Demandez votre cotation gratuite → travex-global-forwarding.com

## Crédits

Images : générées pour ce film. Voix off : synthèse vocale française. Textes : site Travex Global Forwarding.
