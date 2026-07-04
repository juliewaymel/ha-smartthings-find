# SmartThings Find pour Home Assistant

Intégration personnalisée (custom component) permettant de **localiser** et de
**faire sonner** vos appareils Samsung Galaxy et **SmartTags** depuis Home
Assistant, via le service **SmartThings Find**.

Cette version utilise une authentification **OAuth 2.0 avec PKCE** (comme les
applications officielles Samsung) : une **connexion navigateur unique**, puis une
session **persistante qui se renouvelle automatiquement**. Plus de re-connexion
régulière ni d'expiration imprévisible.

C'est un fork de la lignée
[`Vedeneb`](https://github.com/Vedeneb/HA-SmartThings-Find) (archivé) →
[`tomskra`](https://github.com/tomskra/HA-SmartThings-Find) →
[`PixelShober`](https://github.com/PixelShober/HA-SmartThings-Find), dont provient
l'implémentation OAuth reprise ici.

> ⚠️ **Avertissement — intégration NON officielle.**
> Elle s'appuie sur le **reverse-engineering** de l'API privée de Samsung. Il
> n'existe aucune API publique pour la localisation SmartThings Find. **Samsung
> peut modifier ou casser cette API à tout moment, sans préavis.** Utilisez-la à
> vos risques. Elle n'est ni affiliée ni approuvée par Samsung.

## Fonctionnalités

Pour chaque appareil compatible de votre compte SmartThings Find, l'intégration
crée :

- un **`device_tracker`** — position GPS (latitude, longitude, précision) ;
- un **`sensor`** de **batterie** (selon l'appareil) ;
- un **`switch`** « **Faire sonner** » (déclenche/arrête la sonnerie).

Le périmètre exact des appareils exposés dépend de ce que le backend SmartThings
Find renvoie pour votre compte.

## Prérequis

- Home Assistant **2024.12** ou plus récent.
- Un compte **Samsung** avec au moins un appareil enregistré dans SmartThings
  Find.
- Un **navigateur** pour effectuer la connexion initiale (une seule fois).
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

## Configuration (connexion OAuth)

1. **Paramètres → Appareils et services → Ajouter une intégration →
   SmartThings Find** (à ne pas confondre avec l'intégration SmartThings native).
2. **Connexion** : cliquez sur le lien fourni pour vous connecter à votre compte
   Samsung dans le navigateur.
3. **Redirection** : après la connexion, le navigateur tente d'ouvrir un lien
   `ms-app://…`. Annulez l'éventuelle invite d'ouverture d'application externe.
4. **Récupérez l'URL `ms-app://`** : ouvrez les outils de développement (**F12**),
   onglet **Réseau** ou **Console**, et copiez l'URL **complète** commençant par
   `ms-app://` (⚠️ pas l'URL de la page d'erreur visible).
5. **Collez** cette URL dans le dialogue Home Assistant. L'intégration échange le
   code contre des jetons et charge vos appareils.

### Récupérer l'URL `ms-app://` — méthode fiable (onglet Réseau)

C'est la méthode qui marche à tous les coups :

1. Avant de cliquer sur le lien, ouvrez les outils de développement (**F12**) →
   onglet **Réseau** (Network).
2. Cochez **Conserver le journal** (Preserve log).
3. Connectez-vous à votre compte Samsung.
4. Dans la liste des requêtes, repérez la ligne commençant par **`ms-app`**
   (souvent affichée en rouge / échouée).
5. **Clic droit** dessus → **Copier** → **Copier l'URL** (Copy → Copy URL).
6. Collez l'URL complète dans le dialogue Home Assistant.

> ⚠️ Ne collez **pas** l'URL de la page d'erreur visible dans la barre d'adresse :
> elle ne contient pas les paramètres nécessaires. Seule l'entrée `ms-app://…` du
> journal Réseau est la bonne.

### Astuce : copier l'URL `ms-app://` automatiquement (Console)

Si la redirection est pilotée en JavaScript (cas fréquent), ce petit script copie
l'URL tout seul. **Collez-le dans la Console (F12 → Console) _avant_ de cliquer sur
le lien de connexion**, puis connectez-vous :

```js
(() => {
  const grab = (u) => {
    u = String(u || "");
    if (!u.startsWith("ms-app://")) return false;
    navigator.clipboard.writeText(u).catch(() => {});
    console.log("%cURL ms-app copiée :\n" + u, "color:green;font-size:16px");
    alert("URL ms-app copiée dans le presse-papier !\n\n" + u);
    return true;
  };
  const L = Location.prototype, assign = L.assign, replace = L.replace;
  L.assign = function (u) { if (grab(u)) return; return assign.apply(this, arguments); };
  L.replace = function (u) { if (grab(u)) return; return replace.apply(this, arguments); };
  try {
    const d = Object.getOwnPropertyDescriptor(L, "href");
    Object.defineProperty(location, "href", {
      get() { return d.get.call(location); },
      set(u) { if (grab(u)) return; d.set.call(location, u); },
    });
  } catch (e) {}
  const open = window.open;
  window.open = function (u) { if (grab(u)) return null; return open.apply(this, arguments); };
  console.log("%cInterception ms-app active — connecte-toi maintenant.", "color:#06c;font-size:14px");
})();
```

L'URL est copiée dans le presse-papier **et** affichée (alerte + Console). Si la
connexion traverse plusieurs pages complètes, le script peut être réinitialisé :
dans ce cas, utilisez la **méthode Réseau** ci-dessus (toujours fiable).

### Session / ré-authentification

La session OAuth se **renouvelle automatiquement** grâce à un jeton de
rafraîchissement (`offline.access`). En cas de révocation côté Samsung, Home
Assistant déclenche un flux de **ré-authentification** (même procédure).

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
- L'état du `switch` de sonnerie est **optimiste** : l'API OAuth ne permet pas de
  relire l'état réel de la sonnerie.
- L'arrêt de sonnerie n'est pas garanti sur tous les appareils (dépend du backend).

## Dépannage

Activez les journaux détaillés dans `configuration.yaml` :

```yaml
logger:
  default: info
  logs:
    custom_components.smartthings_find: debug
```

## Crédits & licence

- Travail original de reverse-engineering : **Benedikt Frey** —
  [`Vedeneb/HA-SmartThings-Find`](https://github.com/Vedeneb/HA-SmartThings-Find).
- Implémentation OAuth 2.0 / PKCE :
  [`PixelShober/HA-SmartThings-Find`](https://github.com/PixelShober/HA-SmartThings-Find)
  (via [`tomskra`](https://github.com/tomskra/HA-SmartThings-Find)).
- Fork : **Julie Waymel**.
- Licence : **MIT** (voir [`LICENSE`](LICENSE)).
