# Echko Setup

Cet addon configure automatiquement votre box Home Assistant pour le monitoring solaire Echko.

## Fonctionnement

1. Créez un site dans l'admin Echko et obtenez le QR code de configuration.
2. Depuis un téléphone **connecté au même réseau** que la box, scannez le QR code.
3. L'addon configure automatiquement :
   - Un token d'accès Home Assistant pour Echko
   - Le tunnel Cloudflare (accès distant sécurisé)
   - L'intégration Modbus de l'onduleur dans `configuration.yaml`

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
| SolarEdge | ⚠️ Manuel (SunSpec) |
| Enphase | ⚠️ Manuel (API HTTP) |
| ABB | ⚠️ Manuel (Aurora) |

## WiFi

Si la box n'est pas connectée au réseau, l'addon sert un portail WiFi sur le port 7080. Connectez-vous au réseau créé par la box et ouvrez `http://homeassistant.local:7080` pour configurer le WiFi.

## Support

[admin.echko.app](https://admin.echko.app) — [buddytech.be](https://buddytech.be)
