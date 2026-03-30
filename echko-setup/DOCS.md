# Echko Setup

This add-on automatically configures your Home Assistant box for Echko solar monitoring.

## How it works

1. Create a site in the Echko admin and get the setup QR code.
2. From a phone **connected to the same network as the box**, scan the QR code.
3. The add-on automatically configures:
   - The Cloudflare tunnel (secure remote access)
   - The inverter Modbus integration in `configuration.yaml`
   - The HA integration wizard for non-Modbus inverters (SolarEdge, Enphase, ABB)
4. **One manual step**: create a long-lived access token in HA and paste it in the Echko admin.

## Creating a Home Assistant access token

Home Assistant does not allow add-ons to create long-lived tokens automatically. You only need to do this once:

1. In Home Assistant, click your **avatar** (bottom left) → **Profile**
2. Scroll down to the **Security** section
3. Click **Create token** under *Long-lived access tokens*
4. Name it (e.g. `Echko`) and copy the token displayed
5. In the Echko admin, open the site → **Edit** → paste the token in the **HA Token** field

> The token is only shown once. Copy it immediately.

## Supported inverter brands

| Brand | Auto-configuration |
|-------|-------------------|
| SMA | ✅ Modbus TCP |
| Growatt | ✅ Modbus TCP |
| Huawei / SUN2000 | ✅ Modbus TCP |
| Fronius | ✅ Modbus TCP (port 1502) |
| Sungrow | ✅ Modbus TCP |
| GoodWe | ✅ Modbus TCP |
| SolarX | ✅ Modbus TCP |
| Deye | ✅ Modbus TCP |
| Sofar | ✅ Modbus TCP |
| Kostal | ✅ Modbus TCP |
| Victron (Cerbo GX) | ✅ Modbus TCP |
| SolarEdge | 🔑 API key required — integration wizard opened automatically |
| Enphase | 🔑 Credentials required — integration wizard opened automatically |
| ABB PowerOne | 🔌 RS485 required — Aurora integration wizard opened automatically |

## WiFi setup

If the box is not yet connected to a network when scanned:

1. The box creates a temporary Wi-Fi access point
2. Connect your phone to that network
3. Open `http://homeassistant.local:7080` — the Wi-Fi portal appears
4. Enter the client network SSID and password
5. The box connects and the setup resumes automatically

## Support

[admin.echko.app](https://admin.echko.app) — [buddytech.be](https://buddytech.be)
