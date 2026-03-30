# Echko Setup

Cet addon configure automatiquement votre box Home Assistant pour le monitoring solaire Echko.

## Fonctionnement

1. Créez un site dans l'admin Echko et obtenez le QR code de configuration.
2. Depuis un téléphone **connecté au même réseau** que la box, scannez le QR code.
3. L'addon configure automatiquement :
   - Le tunnel Cloudflare (accès distant sécurisé)
   - L'intégration Modbus de l'onduleur dans `configuration.yaml`
4. **Dernière étape manuelle** : créez un token d'accès dans HA et collez-le dans l'admin Echko.

## Créer un token d'accès Home Assistant

Home Assistant ne permet pas la création automatique de tokens longue durée depuis un addon. Vous devez le faire manuellement une seule fois :

1. Dans Home Assistant, cliquez sur votre **avatar** (bas à gauche) → **Profil**
2. Faites défiler jusqu'à la section **Sécurité**
3. Cliquez **Créer un token** sous *Tokens d'accès longue durée*
4. Donnez-lui un nom (ex: `Echko`) et copiez le token affiché
5. Dans l'admin Echko, ouvrez le site → **Modifier** → collez le token dans le champ **Token HA**

> Le token ne s'affiche qu'une seule fois. Copiez-le immédiatement.

## Marques d'onduleurs supportées (Modbus TCP)

| Marque | Configuration automatique |
|--------|--------------------------|
| SMA | ✅ |
| Growatt | ✅ |
| Huawei / SUN2000 | ✅ |
| Fronius | ✅ (port 1502) |
| Sungrow | ✅ |
| GoodWe | ✅ |
| SolarX | ✅ |
| Deye | ✅ |
| Sofar | ✅ |
| Kostal | ✅ |
| Victron (Cerbo GX) | ✅ |
| SolarEdge | 🔑 Clé API requise — l'addon ouvre automatiquement l'intégration dans HA |
| Enphase | 🔑 Credentials requis — l'addon ouvre automatiquement l'intégration dans HA |
| ABB | ❌ Pas d'intégration HA native — protocole Aurora propriétaire |

Pour SolarEdge et Enphase, l'addon déclenche automatiquement le wizard d'intégration dans HA. L'utilisateur doit simplement entrer ses identifiants (clé API SolarEdge ou IP/credentials Envoy). ABB Aurora n'est pas supporté nativement par HA.

## WiFi

Si la box n'est pas encore connectée au réseau au moment du scan :

1. La box crée un point d'accès WiFi temporaire
2. Connectez votre téléphone à ce réseau
3. Ouvrez `http://homeassistant.local:7080` — le portail WiFi s'affiche
4. Entrez le SSID et le mot de passe du réseau client
5. La box se connecte et le setup reprend automatiquement

## Support

[admin.echko.app](https://admin.echko.app) — [buddytech.be](https://buddytech.be)
