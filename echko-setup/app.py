#!/usr/bin/env python3
import os
import json
import socket
import threading
import subprocess
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN', '')
SUPERVISOR_HEADERS = {
    'Authorization': f'Bearer {SUPERVISOR_TOKEN}',
    'Content-Type': 'application/json'
}
SUPERVISOR_URL = 'http://supervisor'
HA_URL = 'http://homeassistant'
ECHKO_API = 'https://api.echko.app'
HA_CONFIG_PATH = '/config/configuration.yaml'

# ── Modbus templates ───────────────────────────────────────────────────────────

# Brands without standard Modbus TCP (require dedicated HA integration — manual setup)
# solaredge → SunSpec with dynamic scale factors
# enphase   → Envoy HTTP API
# abb       → proprietary Aurora protocol

MODBUS_TEMPLATES = {
    'fronius': {
        'default_slave': 1,
        'port': 1502,
        'sensors': [
            {'suffix': 'ac_power',       'address': 40089, 'data_type': 'float32', 'input_type': None, 'scale': None,  'precision': 1,    'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',      'scan_interval': 30},
            {'suffix': 'energy_total',   'address': 40099, 'data_type': 'float32', 'input_type': None, 'scale': 0.001, 'precision': 3,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'grid_voltage',   'address': 40083, 'data_type': 'float32', 'input_type': None, 'scale': None,  'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',      'scan_interval': 60},
            {'suffix': 'temperature',    'address': 40107, 'data_type': 'float32', 'input_type': None, 'scale': None,  'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',      'scan_interval': 60},
        ]
    },
    'sma': {
        'default_slave': 3,
        'sensors': [
            {'suffix': 'puissance_ac',           'address': 30775, 'data_type': 'int32',  'input_type': None, 'scale': None,  'precision': None, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',      'scan_interval': 30},
            {'suffix': 'production_journaliere', 'address': 30517, 'data_type': 'uint64', 'input_type': None, 'scale': 0.001, 'precision': 3,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'production_totale',      'address': 30513, 'data_type': 'uint64', 'input_type': None, 'scale': 0.001, 'precision': 3,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'tension_reseau',         'address': 30783, 'data_type': 'uint32', 'input_type': None, 'scale': 0.01,  'precision': 2,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',      'scan_interval': 60},
            {'suffix': 'temperature',            'address': 30953, 'data_type': 'int32',  'input_type': None, 'scale': 0.1,   'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',      'scan_interval': 60},
        ]
    },
    'growatt': {
        'default_slave': 1,
        'sensors': [
            {'suffix': 'output_power',          'address': 35, 'data_type': 'uint16', 'input_type': 'input', 'scale': None, 'precision': None, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',      'scan_interval': 30},
            {'suffix': 'today_s_generation',    'address': 53, 'data_type': 'uint16', 'input_type': 'input', 'scale': 0.1,  'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'total_energy',          'address': 55, 'data_type': 'uint32', 'input_type': 'input', 'scale': 0.1,  'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'grid_voltage',          'address': 38, 'data_type': 'uint16', 'input_type': 'input', 'scale': 0.1,  'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',      'scan_interval': 60},
            {'suffix': 'inverter_temperature',  'address': 93, 'data_type': 'int16',  'input_type': 'input', 'scale': 0.1,  'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',      'scan_interval': 60},
        ]
    },
    'huawei': {
        'default_slave': 1,
        'sensors': [
            {'suffix': 'active_power',         'address': 32080, 'data_type': 'int32',  'input_type': None, 'scale': None, 'precision': None, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',      'scan_interval': 30},
            {'suffix': 'daily_yield_energy',   'address': 32114, 'data_type': 'uint32', 'input_type': None, 'scale': 0.01, 'precision': 2,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'total_yield_energy',   'address': 32106, 'data_type': 'uint32', 'input_type': None, 'scale': 0.01, 'precision': 2,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'phase_a_voltage',      'address': 32069, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',      'scan_interval': 60},
            {'suffix': 'internal_temperature', 'address': 32087, 'data_type': 'int16',  'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',      'scan_interval': 60},
        ]
    },
    'sungrow': {
        'default_slave': 1,
        'sensors': [
            {'suffix': 'output_power',         'address': 5031, 'data_type': 'uint16', 'input_type': None, 'scale': None, 'precision': None, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',      'scan_interval': 30},
            {'suffix': 'daily_pv_generation',  'address': 5003, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'total_pv_generation',  'address': 5004, 'data_type': 'uint32', 'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'phase_a_voltage',      'address': 5018, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',      'scan_interval': 60},
            {'suffix': 'internal_temperature', 'address': 5008, 'data_type': 'int16',  'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',      'scan_interval': 60},
        ]
    },
    'goodwe': {
        'default_slave': 247,
        'sensors': [
            {'suffix': 'ac_output_power',          'address': 35121, 'data_type': 'int32',  'input_type': None, 'scale': None, 'precision': None, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',      'scan_interval': 30},
            {'suffix': 'energy_generation_today',  'address': 35191, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'total_energy_generation',  'address': 35195, 'data_type': 'uint32', 'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'grid_voltage_l1',          'address': 35123, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',      'scan_interval': 60},
            {'suffix': 'inverter_temperature',     'address': 35174, 'data_type': 'int16',  'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',      'scan_interval': 60},
        ]
    },
    'solax': {
        'default_slave': 1,
        'sensors': [
            {'suffix': 'inverter_ac_power',      'address': 181, 'data_type': 'int16',  'input_type': None, 'scale': None, 'precision': None, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',      'scan_interval': 30},
            {'suffix': 'today_s_solar_energy',   'address': 108, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'total_solar_energy',     'address': 82,  'data_type': 'uint32', 'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'grid_voltage',           'address': 160, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',      'scan_interval': 60},
            {'suffix': 'inverter_temperature',   'address': 60,  'data_type': 'int16',  'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',      'scan_interval': 60},
        ]
    },
    'deye': {
        'default_slave': 1,
        'sensors': [
            {'suffix': 'ac_power',          'address': 630, 'data_type': 'int16',  'input_type': None, 'scale': None, 'precision': None, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',      'scan_interval': 30},
            {'suffix': 'daily_production',  'address': 108, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'total_production',  'address': 534, 'data_type': 'uint32', 'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'grid_voltage',      'address': 598, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',      'scan_interval': 60},
            {'suffix': 'temperature',       'address': 540, 'data_type': 'int16',  'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',      'scan_interval': 60},
        ]
    },
    'sofar': {
        'default_slave': 1,
        'sensors': [
            {'suffix': 'active_power',         'address': 16,   'data_type': 'int16',  'input_type': None, 'scale': 10,   'precision': None, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',      'scan_interval': 30},
            {'suffix': 'today_generation',     'address': 533,  'data_type': 'uint16', 'input_type': None, 'scale': 0.01, 'precision': 2,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'total_generation',     'address': 538,  'data_type': 'uint32', 'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'grid_voltage',         'address': 3082, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',      'scan_interval': 60},
            {'suffix': 'internal_temperature', 'address': 1048, 'data_type': 'int16',  'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',      'scan_interval': 60},
        ]
    },
    'kostal': {
        'default_slave': 71,
        'sensors': [
            {'suffix': 'actual_ac_generation', 'address': 100, 'data_type': 'float32', 'input_type': None, 'scale': None, 'precision': 1, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',      'scan_interval': 30},
            {'suffix': 'daily_yield',          'address': 320, 'data_type': 'float32', 'input_type': None, 'scale': None, 'precision': 2, 'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'total_yield',          'address': 322, 'data_type': 'float32', 'input_type': None, 'scale': None, 'precision': 1, 'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'grid_voltage',         'address': 2,   'data_type': 'float32', 'input_type': None, 'scale': None, 'precision': 1, 'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',      'scan_interval': 60},
            {'suffix': 'temperature',          'address': 214, 'data_type': 'float32', 'input_type': None, 'scale': None, 'precision': 1, 'unit': '°C',  'device_class': 'temperature', 'state_class': 'measurement',      'scan_interval': 60},
        ]
    },
    'victron': {
        'default_slave': 239,
        'sensors': [
            {'suffix': 'pv_power',            'address': 1026, 'data_type': 'int16',  'input_type': None, 'scale': None, 'precision': None, 'unit': 'W',   'device_class': 'power',       'state_class': 'measurement',      'scan_interval': 30},
            {'suffix': 'pv_yield_today_daily', 'address': 1029, 'data_type': 'uint16', 'input_type': None, 'scale': 0.01, 'precision': 2,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'pv_yield_total',      'address': 2600, 'data_type': 'uint32', 'input_type': None, 'scale': 0.01, 'precision': 2,    'unit': 'kWh', 'device_class': 'energy',      'state_class': 'total_increasing', 'scan_interval': 60},
            {'suffix': 'grid_voltage',        'address': 1030, 'data_type': 'uint16', 'input_type': None, 'scale': 0.1,  'precision': 1,    'unit': 'V',   'device_class': 'voltage',     'state_class': 'measurement',      'scan_interval': 60},
        ]
    },
}

MODBUS_INVERTERS = set(MODBUS_TEMPLATES.keys())
INVERTERS_STATE_PATH = '/data/echko_inverters.json'

def load_inverters_state():
    try:
        with open(INVERTERS_STATE_PATH, 'r') as f:
            return json.loads(f.read())
    except Exception:
        return []

def save_inverters_state(inverters):
    with open(INVERTERS_STATE_PATH, 'w') as f:
        f.write(json.dumps(inverters, indent=2))

def build_sensor_block(sensor, slave_id, prefix):
    name = f"{prefix}_{sensor['suffix']}"
    lines = [f"        - name: {name}"]
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

def generate_modbus_hub(inverter_type, host, slave_id, prefix):
    template = MODBUS_TEMPLATES.get(inverter_type)
    if not template:
        return None
    port = template.get('port', 502)
    sensors_yaml = '\n'.join(build_sensor_block(s, slave_id, prefix) for s in template['sensors'])
    return (
        f"  - name: echko_{prefix}\n"
        f"    type: tcp\n"
        f"    host: {host}\n"
        f"    port: {port}\n"
        f"    sensors:\n"
        f"{sensors_yaml}"
    )

def rebuild_modbus_config():
    import re
    inverters = load_inverters_state()
    if not inverters:
        print('[SETUP] No inverters in state — nothing to write')
        return True

    try:
        with open(HA_CONFIG_PATH, 'r') as f:
            content = f.read()

        content = re.sub(r'\nmodbus:[\s\S]*?(?=\n\w|\Z)', '', content)

        hubs = []
        recorder_entities = []
        for inv in inverters:
            inv_type = inv.get('type')
            if inv_type not in MODBUS_INVERTERS or not inv.get('host'):
                continue
            template = MODBUS_TEMPLATES[inv_type]
            slave = int(inv.get('slave') or template.get('default_slave', 1))
            prefix = inv['prefix']
            hub = generate_modbus_hub(inv_type, inv['host'], slave, prefix)
            if hub:
                hubs.append(hub)
            for s in template['sensors']:
                entity_id = f"sensor.{prefix}_{s['suffix']}"
                if any(kw in s['suffix'] for kw in ('journaliere', 'totale', 'daily', 'total', 'generation', 'yield', 'energy')):
                    recorder_entities.append(entity_id)

        if hubs:
            modbus_block = "\nmodbus:\n" + "\n".join(hubs) + "\n"
            content += modbus_block

        if recorder_entities:
            if 'recorder:' not in content:
                lines = ''.join(f"      - {e}\n" for e in recorder_entities)
                content += f"\nrecorder:\n  include:\n    entities:\n{lines}"
            if 'history:' not in content:
                lines = ''.join(f"      - {e}\n" for e in recorder_entities)
                content += f"\nhistory:\n  include:\n    entities:\n{lines}"

        with open(HA_CONFIG_PATH, 'w') as f:
            f.write(content)

        print(f'[SETUP] configuration.yaml updated — {len(hubs)} modbus hub(s)')
        requests.post(f'{HA_URL}/api/config/core/restart', headers=SUPERVISOR_HEADERS, timeout=5)
        return True
    except Exception as e:
        print(f'[SETUP] ERROR writing configuration.yaml: {e}')
        return False

def add_inverter(inverter_type, host, slave_id, prefix):
    if inverter_type not in MODBUS_INVERTERS or not host or not prefix:
        print(f'[SETUP] add_inverter skip — type={inverter_type} host={host} prefix={prefix}')
        return False
    inverters = load_inverters_state()
    inverters = [inv for inv in inverters if inv.get('prefix') != prefix]
    template = MODBUS_TEMPLATES[inverter_type]
    inverters.append({
        'type': inverter_type,
        'host': host,
        'slave': int(slave_id) if slave_id else template.get('default_slave', 1),
        'prefix': prefix,
    })
    save_inverters_state(inverters)
    return rebuild_modbus_config()

def configure_inverter(inverter_type, host, slave_id, prefix=None):
    if inverter_type not in MODBUS_INVERTERS or not host:
        print(f'[SETUP] Inverter {inverter_type} — skip modbus config (no host or not modbus)')
        return True
    effective_prefix = (prefix or MODBUS_TEMPLATES[inverter_type].get('defaultPrefix', inverter_type)).lower()
    return add_inverter(inverter_type, host, slave_id, effective_prefix)

def add_power_entity_to_recorder(entity_ids):
    if not entity_ids:
        return
    try:
        import re
        with open(HA_CONFIG_PATH, 'r') as f:
            content = f.read()

        lines_to_add = ''.join(f"      - {eid}\n" for eid in entity_ids)

        if 'recorder:' in content:
            content = re.sub(
                r'(recorder:.*?include:.*?entities:\n)(.*?)(\n\S|\Z)',
                lambda m: m.group(1) + m.group(2) + lines_to_add + m.group(3),
                content, flags=re.DOTALL
            )
        else:
            content += f"\nrecorder:\n  include:\n    entities:\n{lines_to_add}"

        with open(HA_CONFIG_PATH, 'w') as f:
            f.write(content)
        print(f'[SETUP] Recorder updated for power entities: {entity_ids}')
    except Exception as e:
        print(f'[SETUP] add_power_entity_to_recorder error: {e}')

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

def create_ha_token(ha_local_url=None):
    candidates = [f'{HA_URL}/api/auth/long_lived_access_token']
    if ha_local_url:
        candidates.append(f'{ha_local_url}/api/auth/long_lived_access_token')
    for url in candidates:
        try:
            r = requests.post(
                url,
                headers=SUPERVISOR_HEADERS,
                json={'client_name': 'Echko', 'lifespan': 3650},
                timeout=10
            )
            print(f'[SETUP] create_ha_token ({url}): {r.status_code}')
            if r.status_code == 200:
                return r.json().get('token')
        except Exception as e:
            print(f'[SETUP] create_ha_token ({url}): {e}')
    return None

_cloudflared_proc = None

def configure_cloudflared(tunnel_token):
    global _cloudflared_proc
    # Save token to persistent storage
    token_path = '/data/echko_tunnel_token.txt'
    try:
        with open(token_path, 'w') as f:
            f.write(tunnel_token)
    except Exception as e:
        print(f'[SETUP] Could not save tunnel token: {e}')
        return False
    return start_cloudflared(tunnel_token)

def start_cloudflared(tunnel_token):
    global _cloudflared_proc
    if _cloudflared_proc and _cloudflared_proc.poll() is None:
        _cloudflared_proc.terminate()
    try:
        _cloudflared_proc = subprocess.Popen(
            ['/usr/local/bin/cloudflared', 'tunnel', '--no-autoupdate', 'run', '--token', tunnel_token],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        print(f'[SETUP] cloudflared started (pid {_cloudflared_proc.pid})')
        # Log output in background
        def _log():
            for line in _cloudflared_proc.stdout:
                print(f'[CF] {line.decode().rstrip()}')
        threading.Thread(target=_log, daemon=True).start()
        return True
    except Exception as e:
        print(f'[SETUP] cloudflared start error: {e}')
        return False

def notify_echko(site_id, echko_secret, ha_token, ha_url):
    r = requests.post(
        f'{ECHKO_API}/api/setup/complete/{site_id}',
        headers={
            'Authorization': f'Bearer {echko_secret}',
            'Content-Type': 'application/json'
        },
        json={'haToken': ha_token, 'haUrl': ha_url},
        timeout=15
    )
    print(f'[SETUP] notify_echko: {r.status_code}')
    return r.status_code == 200

def configure_ha_http():
    """Ajoute use_x_forwarded_for + trusted_proxies dans configuration.yaml si absent."""
    try:
        with open(HA_CONFIG_PATH, 'r') as f:
            content = f.read()
        if 'use_x_forwarded_for' in content:
            print('[SETUP] HA http config already present')
            return True
        http_block = (
            '\nhttp:\n'
            '  use_x_forwarded_for: true\n'
            '  trusted_proxies:\n'
            '    - 127.0.0.1\n'
            '    - ::1\n'
            '    - 192.168.0.0/16\n'
            '    - 10.0.0.0/8\n'
            '    - 172.16.0.0/12\n'
        )
        with open(HA_CONFIG_PATH, 'a') as f:
            f.write(http_block)
        print('[SETUP] HA http config written')
        # Restart HA core via Supervisor
        try:
            requests.post(f'{SUPERVISOR_URL}/core/restart', headers=SUPERVISOR_HEADERS, timeout=30)
            print('[SETUP] HA restart requested')
        except Exception as e:
            print(f'[SETUP] HA restart request failed: {e}')
        return True
    except Exception as e:
        print(f'[SETUP] configure_ha_http error: {e}')
        return False

# ── Setup flow ─────────────────────────────────────────────────────────────────

def run_setup(tunnel_token, subdomain, ha_local_url, site_id, echko_secret, inverter_type, inverter_host, inverter_slave_id, inverter_prefix=None):
    print(f'[SETUP] Starting for site {site_id} — inverter: {inverter_type} @ {inverter_host} prefix={inverter_prefix}')
    try:
        if not configure_cloudflared(tunnel_token):
            print('[SETUP] ERROR: Could not configure Cloudflared')
            return

        configure_ha_http()
        configure_inverter(inverter_type, inverter_host, inverter_slave_id or '3', inverter_prefix)

        ha_token = create_ha_token(ha_local_url)
        if not ha_token:
            print('[SETUP] WARNING: Could not create HA token — tunnel is up but haToken not saved')

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

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == '/health':
            self.send_json({'status': 'ok', 'network': has_network()})
            return

        # No network → WiFi portal
        if not has_network():
            self.send_html(WIFI_HTML)
            return

        if parsed.path == '/setup':
            tunnel_token      = params.get('tunnelToken',    [None])[0]
            subdomain         = params.get('subdomain',      [None])[0]
            ha_local_url      = params.get('haLocalUrl',     ['http://homeassistant.local:8123'])[0]
            site_id           = params.get('siteId',         [None])[0]
            echko_secret      = params.get('echkoSecret',    [None])[0]
            inverter_type     = params.get('inverterType',   ['sma'])[0]
            inverter_host     = params.get('inverterHost',   [''])[0]
            inverter_slave_id = params.get('inverterSlaveId',['3'])[0]
            inverter_prefix   = params.get('inverterPrefix', [None])[0]

            if not all([tunnel_token, subdomain, site_id, echko_secret]):
                self.send_html(SETUP_ERROR_HTML, 400)
                return

            threading.Thread(
                target=run_setup,
                args=(tunnel_token, subdomain, ha_local_url, site_id, echko_secret, inverter_type, inverter_host, inverter_slave_id, inverter_prefix),
                daemon=True
            ).start()

            self.send_html(SETUP_OK_HTML)
            return

        if parsed.path == '/inverters':
            self.send_json(load_inverters_state())
            return

        self.send_json({'status': 'ready', 'network': True})

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == '/wifi':
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

        # POST /add-inverter — ajoute un onduleur Modbus à la config HA
        if parsed.path == '/add-inverter':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                data = json.loads(body)
                inv_type = data.get('type', 'sma')
                host = data.get('host', '')
                slave = data.get('slave', '')
                prefix = data.get('prefix', '')
                if not host or not prefix:
                    self.send_json({'error': 'host and prefix are required'}, 400)
                    return
                ok = add_inverter(inv_type, host, slave, prefix.lower())
                self.send_json({'ok': ok, 'prefix': prefix.lower(), 'type': inv_type})
            except Exception as e:
                self.send_json({'error': str(e)}, 500)
            return

        # POST /remove-inverter — retire un onduleur par prefix
        if parsed.path == '/remove-inverter':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                data = json.loads(body)
                prefix = data.get('prefix', '')
                if not prefix:
                    self.send_json({'error': 'prefix is required'}, 400)
                    return
                inverters = load_inverters_state()
                inverters = [inv for inv in inverters if inv.get('prefix') != prefix]
                save_inverters_state(inverters)
                rebuild_modbus_config()
                self.send_json({'ok': True})
            except Exception as e:
                self.send_json({'error': str(e)}, 500)
            return

        # POST /recorder — ajoute des entities au recorder HA
        if parsed.path == '/recorder':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                data = json.loads(body)
                entities = data.get('entities', [])
                if isinstance(entities, list) and entities:
                    add_power_entity_to_recorder(entities)
                    self.send_json({'ok': True})
                else:
                    self.send_json({'error': 'entities must be a non-empty list'}, 400)
            except Exception as e:
                self.send_json({'error': str(e)}, 500)
            return

        self.send_json({'error': 'Not found'}, 404)

# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = 7080
    print(f'[ECHKO] Echko Setup starting on port {port}')

    # Resume cloudflared if token was saved from a previous setup
    token_path = '/data/echko_tunnel_token.txt'
    if os.path.exists(token_path):
        try:
            with open(token_path) as f:
                saved_token = f.read().strip()
            if saved_token:
                print('[ECHKO] Resuming cloudflared from saved token...')
                start_cloudflared(saved_token)
        except Exception as e:
            print(f'[ECHKO] Could not resume cloudflared: {e}')

    server = HTTPServer(('0.0.0.0', port), SetupHandler)
    print(f'[ECHKO] Listening — network: {has_network()}')
    server.serve_forever()
