#!/usr/bin/env python3
import os
import json
import socket
import threading
import requests
import websocket
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN', '')
SUPERVISOR_HEADERS = {
    'Authorization': f'Bearer {SUPERVISOR_TOKEN}',
    'Content-Type': 'application/json'
}
SUPERVISOR_URL = 'http://supervisor'
HA_URL = 'http://homeassistant:8123'
ECHKO_API = 'https://api.echko.app'
HA_CONFIG_PATH = '/config/configuration.yaml'

# ── Modbus templates ───────────────────────────────────────────────────────────

# Brands without standard Modbus TCP (require dedicated HA integration — manual setup)
# solaredge → SunSpec with dynamic scale factors
# enphase   → Envoy HTTP API
# abb       → proprietary Aurora protocol

MODBUS_TEMPLATES = {
    'fronius': {
        # Fronius GEN24 / Symo — SunSpec float32, port 1502
        # Daily energy not in a direct register → productionJournaliere sera null
        # Echko dérive le quotidien depuis les snapshots total_increasing
        'default_slave': 1,
        'port': 1502,
        'sensors': [
            {'name': 'Fronius_Inverter_AC_Power',        'address': 40089, 'data_type': 'float32', 'input_type': None, 'scale': None,  'precision': 1,    'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',     'scan_interval': 30},
            {'name': 'Fronius_Inverter_Energy_Total',    'address': 40099, 'data_type': 'float32', 'input_type': None, 'scale': 0.001, 'precision': 3,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'Fronius_Inverter_Grid_Voltage',    'address': 40083, 'data_type': 'float32', 'input_type': None, 'scale': None,  'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',     'scan_interval': 60},
            {'name': 'Fronius_Inverter_Temperature',     'address': 40107, 'data_type': 'float32', 'input_type': None, 'scale': None,  'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',     'scan_interval': 60},
        ]
    },
    'sma': {
        'default_slave': 3,
        'sensors': [
            {'name': 'SMA_Puissance_AC',            'address': 30775, 'data_type': 'int32',   'input_type': None, 'scale': None,  'precision': None, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',     'scan_interval': 30},
            {'name': 'SMA_Production_Journaliere',   'address': 30517, 'data_type': 'uint64',  'input_type': None, 'scale': 0.001, 'precision': 3,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'SMA_Production_Totale',        'address': 30513, 'data_type': 'uint64',  'input_type': None, 'scale': 0.001, 'precision': 3,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'SMA_Tension_Reseau',           'address': 30783, 'data_type': 'uint32',  'input_type': None, 'scale': 0.01,  'precision': 2,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',     'scan_interval': 60},
            {'name': 'SMA_Temperature',              'address': 30953, 'data_type': 'int32',   'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',     'scan_interval': 60},
        ]
    },
    'growatt': {
        'default_slave': 1,
        'sensors': [
            # Growatt MOD/MAX series — input registers
            {'name': 'Growatt_Output_Power',         'address': 35,   'data_type': 'uint16',  'input_type': 'input', 'scale': None,  'precision': None, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',     'scan_interval': 30},
            {'name': "Growatt_Today_s_Generation",   'address': 53,   'data_type': 'uint16',  'input_type': 'input', 'scale': 0.1,   'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'Growatt_Total_Energy',         'address': 55,   'data_type': 'uint32',  'input_type': 'input', 'scale': 0.1,   'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'Growatt_Grid_Voltage',         'address': 38,   'data_type': 'uint16',  'input_type': 'input', 'scale': 0.1,   'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',     'scan_interval': 60},
            {'name': 'Growatt_Inverter_Temperature', 'address': 93,   'data_type': 'int16',   'input_type': 'input', 'scale': 0.1,   'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',     'scan_interval': 60},
        ]
    },
    'huawei': {
        'default_slave': 1,
        'sensors': [
            # Huawei SUN2000 series — holding registers
            {'name': 'SUN2000_Active_Power',         'address': 32080, 'data_type': 'int32',  'input_type': None, 'scale': None,  'precision': None, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',     'scan_interval': 30},
            {'name': 'SUN2000_Daily_Yield_Energy',   'address': 32114, 'data_type': 'uint32', 'input_type': None, 'scale': 0.01,  'precision': 2,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'SUN2000_Total_Yield_Energy',   'address': 32106, 'data_type': 'uint32', 'input_type': None, 'scale': 0.01,  'precision': 2,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'SUN2000_Phase_A_Voltage',      'address': 32069, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',     'scan_interval': 60},
            {'name': 'SUN2000_Internal_Temperature', 'address': 32087, 'data_type': 'int16',  'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',     'scan_interval': 60},
        ]
    },
    'sungrow': {
        'default_slave': 1,
        'sensors': [
            # Sungrow SG/RS series — holding registers
            {'name': 'Sungrow_Output_Power',         'address': 5031, 'data_type': 'uint16',  'input_type': None, 'scale': None,  'precision': None, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',     'scan_interval': 30},
            {'name': 'Sungrow_Daily_PV_Generation',  'address': 5003, 'data_type': 'uint16',  'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'Sungrow_Total_PV_Generation',  'address': 5004, 'data_type': 'uint32',  'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'Sungrow_Phase_A_Voltage',      'address': 5018, 'data_type': 'uint16',  'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',     'scan_interval': 60},
            {'name': 'Sungrow_Internal_Temperature', 'address': 5008, 'data_type': 'int16',   'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',     'scan_interval': 60},
        ]
    },
    'goodwe': {
        'default_slave': 247,
        'sensors': [
            # GoodWe ET/EH series — holding registers
            {'name': 'Goodwe_AC_Output_Power',           'address': 35121, 'data_type': 'int32',  'input_type': None, 'scale': None,  'precision': None, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',     'scan_interval': 30},
            {'name': 'Goodwe_Energy_Generation_Today',   'address': 35191, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'Goodwe_Total_Energy_Generation',   'address': 35195, 'data_type': 'uint32', 'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'Goodwe_Grid_Voltage_L1',           'address': 35123, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',     'scan_interval': 60},
            {'name': 'Goodwe_Inverter_Temperature',      'address': 35174, 'data_type': 'int16',  'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',     'scan_interval': 60},
        ]
    },
    'solax': {
        'default_slave': 1,
        'sensors': [
            # Solax X3 series — holding registers
            {'name': 'Solax_Inverter_AC_Power',          'address': 181, 'data_type': 'int16',  'input_type': None, 'scale': None,  'precision': None, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',     'scan_interval': 30},
            {"name": "Solax_Today_s_Solar_Energy",       'address': 108, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'Solax_Total_Solar_Energy',         'address': 82,  'data_type': 'uint32', 'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'Solax_Grid_Voltage',               'address': 160, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',     'scan_interval': 60},
            {'name': 'Solax_Inverter_Temperature',       'address': 60,  'data_type': 'int16',  'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',     'scan_interval': 60},
        ]
    },
    'deye': {
        'default_slave': 1,
        'sensors': [
            # Deye/Solarman SUN-* series — holding registers
            {'name': 'Deye_AC_Power',                    'address': 630, 'data_type': 'int16',  'input_type': None, 'scale': None,  'precision': None, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',     'scan_interval': 30},
            {'name': 'Deye_Daily_Production',            'address': 108, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'Deye_Total_Production',            'address': 534, 'data_type': 'uint32', 'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'Deye_Grid_Voltage',                'address': 598, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',     'scan_interval': 60},
            {'name': 'Deye_Temperature',                 'address': 540, 'data_type': 'int16',  'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',     'scan_interval': 60},
        ]
    },
    'sofar': {
        'default_slave': 1,
        'sensors': [
            # Sofar Solar KTLX-G3 series — holding registers
            {'name': 'Sofar_Active_Power',               'address': 16,   'data_type': 'int16',  'input_type': None, 'scale': 10,    'precision': None, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',     'scan_interval': 30},
            {'name': 'Sofar_Today_Generation',           'address': 533,  'data_type': 'uint16', 'input_type': None, 'scale': 0.01,  'precision': 2,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'Sofar_Total_Generation',           'address': 538,  'data_type': 'uint32', 'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'Sofar_Grid_Voltage',               'address': 3082, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',     'scan_interval': 60},
            {'name': 'Sofar_Internal_Temperature',       'address': 1048, 'data_type': 'int16',  'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',     'scan_interval': 60},
        ]
    },
    'kostal': {
        'default_slave': 71,
        'sensors': [
            # Kostal PLENTICORE series — holding registers (float32 = 2 regs each)
            {'name': 'Kostal_Piko_Actual_AC_Generation', 'address': 100,  'data_type': 'float32', 'input_type': None, 'scale': None,  'precision': 1,    'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',     'scan_interval': 30},
            {'name': 'Kostal_Piko_Daily_Yield',          'address': 320,  'data_type': 'float32', 'input_type': None, 'scale': None,  'precision': 2,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'Kostal_Piko_Total_Yield',          'address': 322,  'data_type': 'float32', 'input_type': None, 'scale': None,  'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'Kostal_Piko_Grid_Voltage',         'address': 2,    'data_type': 'float32', 'input_type': None, 'scale': None,  'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',     'scan_interval': 60},
            {'name': 'Kostal_Piko_Temperature',          'address': 214,  'data_type': 'float32', 'input_type': None, 'scale': None,  'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',     'scan_interval': 60},
        ]
    },
    'victron': {
        # Victron Cerbo GX — Modbus TCP port 502
        # Unit ID 239 = premier onduleur PV grid-tied (com.victronenergy.pvinverter.pv0)
        # Unit ID configurable dans Cerbo GX → Settings → Modbus TCP
        'default_slave': 239,
        'sensors': [
            {'name': 'Victron_PV_Power',             'address': 1026, 'data_type': 'int16',  'input_type': None, 'scale': None,  'precision': None, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',     'scan_interval': 30},
            {'name': 'Victron_PV_Yield_Today',        'address': 1029, 'data_type': 'uint16', 'input_type': None, 'scale': 0.01,  'precision': 2,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'Victron_PV_Yield_Total',        'address': 2600, 'data_type': 'uint32', 'input_type': None, 'scale': 0.01,  'precision': 2,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'name': 'Victron_Grid_Voltage',          'address': 1030, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',     'scan_interval': 60},
        ]
    },
}

MODBUS_INVERTERS = set(MODBUS_TEMPLATES.keys())

def build_sensor_block(sensor, slave_id):
    lines = [f"        - name: {sensor['name']}"]
    lines.append(f"          unit_of_measurement: \"{sensor['unit']}\"")
    lines.append(f"          device_address: {slave_id}")
    lines.append(f"          address: {sensor['address']}")
    if sensor.get('input_type'):
        lines.append(f"          input_type: {sensor['input_type']}")
    if sensor.get('scale') is not None:
        lines.append(f"          scale: {sensor['scale']}")
    if sensor.get('precision') is not None:
        lines.append(f"          precision: {sensor['precision']}")
    lines.append(f"          data_type: {sensor['data_type']}")
    lines.append(f"          scan_interval: {sensor['scan_interval']}")
    lines.append(f"          device_class: {sensor['device_class']}")
    lines.append(f"          state_class: {sensor['state_class']}")
    return '\n'.join(lines)

def generate_modbus_block(inverter_type, host, slave_id):
    template = MODBUS_TEMPLATES.get(inverter_type)
    if not template:
        return None
    port = template.get('port', 502)
    sensors_yaml = '\n'.join(build_sensor_block(s, slave_id) for s in template['sensors'])
    return f"""
modbus:
  - name: {inverter_type.upper()}
    type: tcp
    host: {host}
    port: {port}
    sensors:
{sensors_yaml}
"""

def configure_inverter(inverter_type, host, slave_id):
    if inverter_type not in MODBUS_INVERTERS or not host:
        print(f'[SETUP] Inverter {inverter_type} — skip modbus config (no host or not modbus)')
        return True

    effective_slave = int(slave_id) if slave_id else MODBUS_TEMPLATES[inverter_type].get('default_slave', 1)
    modbus_block = generate_modbus_block(inverter_type, host, effective_slave)
    if not modbus_block:
        return True

    try:
        with open(HA_CONFIG_PATH, 'r') as f:
            content = f.read()

        # Remove existing modbus block if present
        import re
        content = re.sub(r'\nmodbus:[\s\S]*?(?=\n\w|\Z)', '', content)

        # Append recorder/history includes if not present
        recorder_block = """
recorder:
  include:
    entities:
"""
        history_block = """
history:
  include:
    entities:
"""
        template = MODBUS_TEMPLATES[inverter_type]
        for s in template['sensors']:
            entity_id = f"sensor.{s['name'].lower()}"
            if 'journaliere' in entity_id or 'totale' in entity_id or 'daily' in entity_id or 'total' in entity_id:
                recorder_block += f"      - {entity_id}\n"
                history_block  += f"      - {entity_id}\n"

        # Only add recorder/history if not already present
        if 'recorder:' not in content:
            content += recorder_block
        if 'history:' not in content:
            content += history_block

        content += modbus_block

        with open(HA_CONFIG_PATH, 'w') as f:
            f.write(content)

        print(f'[SETUP] configuration.yaml updated for {inverter_type}')

        # Reload HA core config
        requests.post(f'{HA_URL}/api/config/core/restart', headers=SUPERVISOR_HEADERS, timeout=5)
        return True
    except Exception as e:
        print(f'[SETUP] ERROR writing configuration.yaml: {e}')
        return False

# ── Network ────────────────────────────────────────────────────────────────────

def has_network():
    try:
        socket.setdefaulttimeout(3)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(('8.8.8.8', 53))
        s.close()
        return True
    except Exception:
        return False

def configure_wifi(ssid, password):
    payload = {
        'enabled': True,
        'wifi': {
            'ssid': ssid,
            'auth': 'wpa-psk',
            'psk': password,
            'mode': 'infrastructure'
        }
    }
    r = requests.post(
        f'{SUPERVISOR_URL}/network/interface/wlan0/update',
        headers=SUPERVISOR_HEADERS,
        json=payload,
        timeout=10
    )
    print(f'[WIFI] configure response: {r.status_code} {r.text}')
    return r.status_code == 200

# ── HA / Cloudflared ───────────────────────────────────────────────────────────

def create_ha_token():
    try:
        ws = websocket.create_connection('ws://homeassistant:8123/api/websocket', timeout=10)
        ws.recv()  # auth_required
        ws.send(json.dumps({'type': 'auth', 'access_token': SUPERVISOR_TOKEN}))
        auth = json.loads(ws.recv())
        if auth.get('type') != 'auth_ok':
            ws.close()
            print('[SETUP] create_ha_token: auth failed')
            return None
        ws.send(json.dumps({'id': 1, 'type': 'auth/long_lived_access_token', 'client_name': 'Echko', 'lifespan': 3650}))
        result = json.loads(ws.recv())
        ws.close()
        if result.get('success'):
            print('[SETUP] create_ha_token: ok')
            return result['result']
        print(f'[SETUP] create_ha_token error: {result}')
        return None
    except Exception as e:
        print(f'[SETUP] create_ha_token exception: {e}')
        return None

def configure_cloudflared(tunnel_token):
    # Configure addon options
    r = requests.post(
        f'{SUPERVISOR_URL}/addons/cloudflared/options',
        headers=SUPERVISOR_HEADERS,
        json={'tunnel_token': tunnel_token},
        timeout=10
    )
    print(f'[SETUP] cloudflared options: {r.status_code}')
    if r.status_code != 200:
        return False
    # Start addon
    r = requests.post(
        f'{SUPERVISOR_URL}/addons/cloudflared/start',
        headers=SUPERVISOR_HEADERS,
        timeout=15
    )
    print(f'[SETUP] cloudflared start: {r.status_code}')
    return r.status_code == 200

def notify_echko(site_id, echko_secret, ha_token, ha_url):
    r = requests.post(
        f'{ECHKO_API}/api/sites/{site_id}/setup-complete',
        headers={
            'Authorization': f'Bearer {echko_secret}',
            'Content-Type': 'application/json'
        },
        json={'haToken': ha_token, 'haUrl': ha_url},
        timeout=15
    )
    print(f'[SETUP] notify_echko: {r.status_code}')
    return r.status_code == 200

# ── Setup flow ─────────────────────────────────────────────────────────────────

def run_setup(tunnel_token, subdomain, ha_local_url, site_id, echko_secret, inverter_type, inverter_host, inverter_slave_id):
    print(f'[SETUP] Starting for site {site_id} — inverter: {inverter_type} @ {inverter_host}')
    try:
        ha_token = create_ha_token()
        if not ha_token:
            print('[SETUP] ERROR: Could not create HA token')
            return

        configure_inverter(inverter_type, inverter_host, inverter_slave_id or '3')

        if not configure_cloudflared(tunnel_token):
            print('[SETUP] ERROR: Could not configure Cloudflared')
            return

        ha_url = f'https://{subdomain}.echko.app'
        if notify_echko(site_id, echko_secret, ha_token, ha_url):
            print('[SETUP] Done!')
        else:
            print('[SETUP] ERROR: Could not notify Echko')
    except Exception as e:
        print(f'[SETUP] Exception: {e}')

# ── HTML ───────────────────────────────────────────────────────────────────────

STYLE = """
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0f0f1a; color: #fff; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; }
  .card { background: #1a1a2e; border-radius: 16px; padding: 32px; width: 100%; max-width: 400px; }
  .logo { color: #6c63ff; font-weight: 700; font-size: 1.1rem; margin-bottom: 20px; display: block; }
  h1 { font-size: 1.3rem; margin-bottom: 8px; }
  p { color: #888; font-size: 0.9rem; margin-bottom: 24px; line-height: 1.5; }
  label { display: block; font-size: 0.85rem; color: #aaa; margin-bottom: 6px; }
  input { width: 100%; padding: 12px; background: #0f0f1a; border: 1px solid #333; border-radius: 8px; color: #fff; font-size: 1rem; margin-bottom: 16px; outline: none; }
  input:focus { border-color: #6c63ff; }
  button { width: 100%; padding: 14px; background: #6c63ff; border: none; border-radius: 8px; color: #fff; font-size: 1rem; font-weight: 600; cursor: pointer; }
  .icon { font-size: 2.5rem; margin-bottom: 16px; display: block; text-align: center; }
  .center { text-align: center; }
"""

WIFI_HTML = f"""<!DOCTYPE html>
<html lang="fr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Echko — Configuration WiFi</title>
<style>{STYLE}</style></head>
<body><div class="card">
  <span class="logo">echko.</span>
  <h1>Configuration WiFi</h1>
  <p>Connectez la box au réseau du client.</p>
  <form method="POST" action="/wifi">
    <label>Nom du réseau (SSID)</label>
    <input type="text" name="ssid" placeholder="Mon réseau WiFi" required autocomplete="off" />
    <label>Mot de passe</label>
    <input type="password" name="password" placeholder="••••••••" />
    <button type="submit">Connecter</button>
  </form>
</div></body></html>"""

WIFI_WAIT_HTML = f"""<!DOCTYPE html>
<html lang="fr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Echko — Connexion...</title>
<meta http-equiv="refresh" content="6;url=/" />
<style>{STYLE}</style></head>
<body><div class="card center">
  <span class="logo">echko.</span>
  <span class="icon">⏳</span>
  <h1>Connexion en cours...</h1>
  <p>La box rejoint le réseau. Cette page se rafraîchit automatiquement.</p>
</div></body></html>"""

SETUP_OK_HTML = f"""<!DOCTYPE html>
<html lang="fr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Echko — Setup OK</title>
<style>{STYLE}</style></head>
<body><div class="card center">
  <span class="logo">echko.</span>
  <span class="icon">✅</span>
  <h1>Box configurée !</h1>
  <p>Le tunnel est actif. Echko commence à surveiller l'installation solaire.</p>
</div></body></html>"""

SETUP_ERROR_HTML = f"""<!DOCTYPE html>
<html lang="fr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Echko — Erreur</title>
<style>{STYLE}</style></head>
<body><div class="card center">
  <span class="logo">echko.</span>
  <span class="icon">⚠️</span>
  <h1>Paramètres manquants</h1>
  <p>Ce QR code est invalide ou a expiré. Régénère-le depuis l'admin Echko.</p>
</div></body></html>"""

STATUS_HTML = f"""<!DOCTYPE html>
<html lang="fr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Echko Setup</title>
<style>{STYLE}</style></head>
<body><div class="card center">
  <span class="logo">echko.</span>
  <span class="icon">✅</span>
  <h1>Addon actif</h1>
  <p>Le portail de configuration est prêt.<br>Scanne le QR code généré depuis l'admin Echko pour configurer cette box.</p>
</div></body></html>"""

# ── HTTP Handler ───────────────────────────────────────────────────────────────

class SetupHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f'[HTTP] {format % args}')

    def send_html(self, html, status=200):
        data = html.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(data))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, obj, status=200):
        data = json.dumps(obj).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(data))
        self.end_headers()
        self.wfile.write(data)

    def get_path(self):
        parsed = urlparse(self.path)
        # Strip ingress prefix if behind HA ingress proxy
        base = self.headers.get('X-Ingress-Path', '')
        path = parsed.path
        if base and path.startswith(base):
            path = path[len(base):] or '/'
        return path, parsed.query

    def do_GET(self):
        path, query = self.get_path()
        params = parse_qs(query)

        if path == '/health':
            self.send_json({'status': 'ok', 'network': has_network()})
            return

        # No network → WiFi portal
        if not has_network():
            self.send_html(WIFI_HTML)
            return

        if path == '/setup':
            tunnel_token      = params.get('tunnelToken',    [None])[0]
            subdomain         = params.get('subdomain',      [None])[0]
            ha_local_url      = params.get('haLocalUrl',     ['http://homeassistant.local:8123'])[0]
            site_id           = params.get('siteId',         [None])[0]
            echko_secret      = params.get('echkoSecret',    [None])[0]
            inverter_type     = params.get('inverterType',   ['sma'])[0]
            inverter_host     = params.get('inverterHost',   [''])[0]
            inverter_slave_id = params.get('inverterSlaveId',['3'])[0]

            if not all([tunnel_token, subdomain, site_id, echko_secret]):
                self.send_html(SETUP_ERROR_HTML, 400)
                return

            threading.Thread(
                target=run_setup,
                args=(tunnel_token, subdomain, ha_local_url, site_id, echko_secret, inverter_type, inverter_host, inverter_slave_id),
                daemon=True
            ).start()

            self.send_html(SETUP_OK_HTML)
            return

        # Sidebar status page
        self.send_html(STATUS_HTML)

    def do_POST(self):
        path, _ = self.get_path()

        if path == '/wifi':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            params = parse_qs(body)
            ssid     = params.get('ssid',     [None])[0]
            password = params.get('password', [''])[0]

            if not ssid:
                self.send_html(WIFI_HTML, 400)
                return

            configure_wifi(ssid, password)
            self.send_html(WIFI_WAIT_HTML)
            return

        self.send_json({'error': 'Not found'}, 404)

# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = 7080
    print(f'[ECHKO] Echko Setup starting on port {port}')
    server = HTTPServer(('0.0.0.0', port), SetupHandler)
    print(f'[ECHKO] Listening — network: {has_network()}')
    server.serve_forever()
