# SmartThings Find pour Home Assistant

Intégration personnalisée (custom component) permettant de **localiser** et de
**faire sonner** vos appareils Samsung Galaxy — téléphones, montres, écouteurs
et **SmartTags** — depuis Home Assistant, via le service **SmartThings Find**.

C'est un fork modernisé et maintenu de l'excellent travail de reverse-engineering
de [`Vedeneb/HA-SmartThings-Find`](https://github.com/Vedeneb/HA-SmartThings-Find)
(archivé). La mécanique d'authentification et les endpoints sont repris
fidèlement ; le code a été mis à jour pour les API Home Assistant récentes.

> ⚠️ **Avertissement — intégration NON officielle.**
> Elle s'appuie sur le **reverse-engineering** de l'API privée SmartThings Find
> de Samsung. Il n'existe aucune API publique. **Samsung peut modifier ou casser
> cette API à tout moment, sans préavis**, ce qui rendrait l'intégration
> inopérante. Utilisez-la à vos risques. Elle n'est ni affiliée ni approuvée par
> Samsung.

## Fonctionnalités

Pour chaque appareil de votre compte SmartThings Find, l'intégration crée :

- un **`device_tracker`** — position GPS (latitude, longitude, précision) ;
- un **`sensor`** de **batterie** (sauf pour les écouteurs) ;
- un **`button`** « **Faire sonner** » (déclenche la sonnerie de l'appareil).

Les écouteurs de type « CANAL2 » (Galaxy Buds) exposent en plus un tracker par
oreillette (gauche / droite).

## Prérequis

- Home Assistant **2024.12** ou plus récent.
- Un compte **Samsung** avec au moins un appareil enregistré dans SmartThings
  Find, et un appareil Galaxy pour scanner le QR code de connexion.
- Pour la sonnerie : un appareil Galaxy à proximité connecté en **Bluetooth**
  (contrainte de l'API Samsung).

## Installation

### Via HACS (recommandé)

1. HACS → menu (⋮) → **Dépôts personnalisés**.
2. Ajoutez `https://github.com/juliewaymel/ha-smartthings-find`, catégorie
   **Intégration**.
3. Recherchez **SmartThings Find**, installez, puis **redémarrez** Home Assistant.

### Manuelle

Copiez le dossier `custom_components/smartthings_find/` dans le répertoire
`config/custom_components/` de votre Home Assistant, puis redémarrez.

## Configuration (authentification par QR code)

1. **Paramètres → Appareils et services → Ajouter une intégration →
   SmartThings Find**.
2. Un **QR code** s'affiche. Deux options :
   - le **scanner** avec l'appareil photo / SmartThings de votre Galaxy ;
   - ou ouvrir le lien fourni, ou saisir le code sur
     [signin.samsung.com/key](https://signin.samsung.com/key/).
3. Validez la connexion sur votre téléphone. L'intégration récupère alors un
   cookie de session (`JSESSIONID`) et charge vos appareils.

### Durée de session / ré-authentification

La durée exacte de validité de la session **n'est pas connue** : elle peut
expirer de façon imprévisible. Le cas échéant, Home Assistant déclenche
automatiquement un flux de **ré-authentification** (nouveau scan de QR code).

## Options

Via **Configurer** sur l'intégration :

| Option | Description | Défaut |
| --- | --- | --- |
| Intervalle de mise à jour | Période de rafraîchissement (≥ 30 s) | `120` s |
| Mode actif — SmartTags | Force une mise à jour de position à chaque cycle (↑ conso batterie du tag) | activé |
| Mode actif — autres appareils | Idem pour téléphones/montres… (↑↑ conso batterie) | désactivé |

En **mode passif**, l'intégration lit la dernière position connue sans solliciter
l'appareil. En **mode actif**, elle demande une position fraîche à chaque cycle.

## Limitations connues

- API reverse-engineered → **susceptible de casser** si Samsung change son service.
- La sonnerie nécessite un appareil Galaxy à proximité, connecté en Bluetooth.
- **Impossible d'arrêter** la sonnerie d'un SmartTag (limitation de l'API).
- Les localisations **chiffrées** (souvent `OFFLINE_LOC`) sont ignorées.

## Dépannage

Activez les journaux détaillés dans `configuration.yaml` :

```yaml
logger:
  default: info
  logs:
    custom_components.smartthings_find: debug
```

## Crédits & licence

- Travail original : **Benedikt Frey** — [`Vedeneb/HA-SmartThings-Find`](https://github.com/Vedeneb/HA-SmartThings-Find).
- Fork modernisé : **Julie Waymel**.
- Licence : **MIT** (voir [`LICENSE`](LICENSE)).
