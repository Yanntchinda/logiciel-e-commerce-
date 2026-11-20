# Fonds vidéo (rushes)

Déposez ici vos clips : ils remplacent automatiquement les photos de fond, scène par scène.

## Nommage

Un fichier par plan, nommé comme l'image correspondante :

| Fichier | Plan |
|---|---|
| `06-douala.mp4` | 01 · Ouverture (Douala / route Renchen → Douala) |
| `01-air-freight.mp4` | 02 · Fret aérien |
| `02-sea-containers.mp4` | 03 · Fret maritime, conteneurs & groupage |
| `04-roro-vehicles.mp4` | 04 · Ro-Ro & véhicules |
| `03-warehouse.mp4` | 05 · Logistique & entrepôt (Renchen) |
| `07-trust-team.mp4` | 06 · Notre différence (humain) |
| `05-truck-europe.mp4` | 07 · Appel à l'action |

Extensions acceptées : `.mp4`, `.mov`, `.m4v`, `.webm`, `.mkv`.

## Ce que fait le rendu

- recadrage automatique en 1920×1080 (le centre est conservé), 30 i/s ;
- le clip est **coupé à la durée du plan** ; s'il est plus court, il est rejoué en
  **ping-pong** (pas de saut visible) ;
- le dégradé de lisibilité, la brume, le grain et tous les textes sont appliqués par-dessus ;
- le son du clip est ignoré : seule la voix off française est mixée.

## Filigrane et rythme

- `ZOOM_IN = 1.12` (haut de `render.py`) recadre le clip de 12 % : un filigrane collé
  dans un angle sort du cadre. Monte à 1.2 si le logo est plus large.
- `SLOWMO = 1.6` ralentit le clip à l'extraction : un plan de 5 s tient alors 8 s
  (utile pour les plans longs, sans son).

## Recommandations

- 5 à 15 s de rushes par plan suffisent (le plus long plan fait 14 s).
- Plans stables ou travellings lents : évitez les zooms rapides et les coupes internes.
- Zones sombres ou peu chargées à gauche du cadre : les titres s'y posent.
- 1080p minimum, 25 ou 30 i/s, sans logo ni sous-titre incrusté.

Puis re-rendre :

```bash
python3 promo-travex/render.py
```

Le script affiche au démarrage : `fond vidéo : scène 2 <- 01-air-freight.mp4`.
Sans fichier, le plan utilise la photo animée (mouvement de caméra + atmosphère).
