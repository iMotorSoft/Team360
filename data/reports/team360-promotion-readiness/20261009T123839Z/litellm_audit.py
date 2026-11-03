"""Read-only audit; strict output whitelist, never dump credentials/config/HTTP bodies."""
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
import yaml
import httpx
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'SrvRestAstroLS_v1/backend'))
from modules.automation_diagnosis.litellm_client import LiteLLMClient
pid = 14418
args = Path(f'/proc/{pid}/cmdline').read_bytes().decode().split('\0')
idx = args.index('--config')
config = Path(os.readlink(f'/proc/{pid}/cwd')) / args[idx + 1]
doc = yaml.safe_load(config.read_text())
aliases = {'openai_gpt-5.4-nano', 'openai_text_embedding_3_small'}
models = []
for m in doc.get('model_list', []):
    if m.get('model_name') in aliases:
        params = m.get('litellm_params', {})
        models.append({'alias': m['model_name'], 'upstream': params.get('model'),
                       'custom_api_base_present': bool(params.get('api_base'))})
fields = ['fallbacks', 'default_fallbacks', 'context_window_fallbacks', 'content_policy_fallbacks']
settings = {}
for section in ['router_settings', 'litellm_settings']:
    value = doc.get(section, {}) or {}
    settings[section] = {k: {'configured': k in value, 'nonempty': bool(value.get(k))} for k in fields}
r = {'timestamp': datetime.now(timezone.utc).isoformat(), 'config_path': str(config),
     'mode': 'read-only current process config path + authenticated management GETs',
     'models': models, 'fallback_configuration': settings,
     'limits': ['Config file is not proof of in-memory routing after dynamic changes.',
                'No upstream failure injected; no service restarted or routing changed.',
                'Classifier/generation/embedding success measured separately by Full Gate.']}
client = LiteLLMClient(base_url='http://127.0.0.1:4000')
with httpx.Client(timeout=10) as http:
    for endpoint in ['/model/info', '/router/settings']:
        response = http.get('http://127.0.0.1:4000' + endpoint,
                            headers={'Authorization': 'Bearer ' + client.api_key})
        entry = {'http_status': response.status_code}
        if response.status_code == 200:
            payload = response.json()
            if endpoint == '/model/info':
                entry['selected_models'] = [{'alias': m.get('model_name'),
                    'upstream': (m.get('litellm_params') or {}).get('model')}
                    for m in payload.get('data', []) if m.get('model_name') in aliases]
            elif isinstance(payload, dict):
                current = payload.get('current_values', {})
                entry['fallbacks'] = {k: {'present': k in current, 'nonempty': bool(current.get(k))} for k in fields}
                entry['routing_strategy'] = current.get('routing_strategy')
                entry['model_group_alias_nonempty'] = bool(current.get('model_group_alias'))
                entry['default_litellm_params_fallback_nonempty'] = bool((current.get('default_litellm_params') or {}).get('fallbacks'))
        r[endpoint] = entry
r['provider_failure_test'] = 'NOT_TESTED live upstream; deterministic adapter failure tests PASS in supplemental suite'
Path(__file__).with_name('litellm-audit.json').write_text(json.dumps(r, indent=2) + '\n')
print(json.dumps(r, indent=2))
