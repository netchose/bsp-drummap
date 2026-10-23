# bsp-drummap

*Version française. English version: [README.md](README.md).*

Sauvegarde et rappel en un clic des drum maps de l'Arturia BeatStep Pro (mode Drum, firmware 2.x).
Un preset contient le mode de la drum map, le canal Drum global et, pour chacun des 16 pads,
la note, le canal et une étiquette. L'envoi passe par SysEx USB grâce à
[beatstep-pro-handler](https://github.com/jamisonx-dev/beatstep-pro-handler).

## Installation (Windows 11)

- [uv](https://docs.astral.sh/uv/) installé, puis `uv sync` dans ce dossier.
  uv récupère Python 3.12 : la version est figée car python-rtmidi 1.5.8 n'a pas de wheel
  pour Python 3.13 et plus (il faudrait compiler avec MSVC).
- BSP branchée en **USB** : la BSP ignore les SysEx de réglage reçus sur les prises DIN.
- MIDI Control Center **fermé** pendant les envois.
- Si `uv sync` ne trouve pas beatstep-pro-handler sur PyPI, remplace la dépendance dans
  `pyproject.toml` par `beatstep-pro-handler @ git+https://github.com/jamisonx-dev/beatstep-pro-handler`.

## Utilisation

| Commande | Effet |
| --- | --- |
| `uv run invoke ui` | ouvre l'interface dans le navigateur |
| `uv run invoke send maschine` | rappelle un preset sans ouvrir l'interface |
| `uv run invoke dump "Kontakt 8"` | enregistre l'état actuel de la BSP comme preset |
| `uv run invoke presets` | liste les presets et les sauvegardes auto |
| `uv run invoke ports` | liste les ports MIDI et celui que « Auto » choisirait |
| `uv run invoke test` | lance les tests (BSP simulée, sans matériel) |

L'interface (en anglais) n'est accessible que depuis ce PC (http://localhost:8501), en thème sombre.
Elle a deux pages :

- **Recall** : un bouton par preset, un clic l'envoie à la BSP. Le dernier preset envoyé est mis en évidence.
- **Editor** : création et modification des presets dans une grille disposée comme la BSP
  (pad #1 en bas à gauche, #9 juste au-dessus), sauvegardes automatiques, identification des pads.

Chaque envoi relit d'abord la BSP et garde son état dans `presets/_backups/` (10 dernières),
puis relit les paramètres écrits pour vérifier qu'ils ont bien pris.

## Premier essai (une seule fois)

1. `uv run invoke ports` : la BSP doit apparaître. Sinon, choisis son port à la main dans l'interface.
2. Dans l'interface, **Test connection** doit afficher le mode et le canal Drum.
3. Page **Editor**, **Read BSP** : la grille doit montrer les mêmes valeurs que MCC
   (pad #1 = 60 … pad #13 = 72, canal 10). Si c'est le cas, la correspondance entre paramètres
   et numéros MCC est confirmée. Nomme cette drum map (par exemple « Avant ») et **Save**.
4. **Identify the pads** : **Load identification preset**, **Send editor to BSP**, passe la BSP en mode DRUM,
   clique sur **Listen** et tape les pads de gauche à droite, rangée du bas puis rangée du haut.
   Le tableau indique quel numéro porte chaque pad physique et si les canaux suivent le même ordre.
5. Si la disposition physique diffère de la grille, corrige `GRID_ROWS` dans `src/bsp_drummap/layout.py`
   (c'est le seul endroit à modifier).
6. Remets ta configuration : rappelle le preset « Avant » depuis la page **Recall**,
   ou restaure la sauvegarde la plus récente.
7. Éteins puis rallume la BSP et refais **Read BSP** : la drum map envoyée doit être toujours là.

## Format des presets

Un fichier JSON par preset dans `presets/`, un pad par ligne, modifiable à la main :

```json
{"pad": 1, "note": 36, "channel": 10, "label": "Kick"}
```

`channel` vaut 1 à 16, ou `"drum"` pour suivre le canal Drum global. Une étiquette vide ou absente
devient `Pad-1` … `Pad-16`. Les noms de notes suivent la convention Native Instruments (C3 = 60).
La variable d'environnement `BSP_PRESETS_DIR` permet de ranger les presets ailleurs
(dossier synchronisé, par exemple).

## Bon à savoir

- beatstep-pro-handler est un projet jeune et sa partie Drum est peu testée : d'où la relecture
  de contrôle après chaque envoi.
- La BSP perd des réponses quand on lui envoie trop de requêtes de lecture d'un coup :
  les lectures partent par groupes de 2 (`READ_CHUNK` dans `src/bsp_drummap/device.py`).
- Hors mode Custom, la BSP ignore les réglages par pad : seuls le mode et le canal Drum sont envoyés.
- Avec Windows MIDI Services (multi-client), Maschine peut rester ouvert pendant les envois.
  Sans lui, ferme les applications qui occupent le port de la BSP.
