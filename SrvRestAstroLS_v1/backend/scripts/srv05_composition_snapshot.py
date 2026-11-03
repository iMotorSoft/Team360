"""Deterministic source composition evidence; no lifespan or external I/O."""
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def snapshot(app):
    from validate_team360_full_stack import inventory
    return {
        'routes': inventory(app),
        'openapi': app.openapi_schema.to_schema(),
        'startup': [f'{h.__module__}.{h.__name__}' for h in app.on_startup],
        'shutdown': [f'{h.__module__}.{h.__name__}' for h in app.on_shutdown],
        'cors': app.cors_config.to_dict() if hasattr(app.cors_config, 'to_dict') else {
            'origins': app.cors_config.allow_origins,
            'methods': app.cors_config.allow_methods,
            'headers': app.cors_config.allow_headers,
        },
    }


if __name__ == '__main__':
    import importlib
    import socket
    from unittest.mock import patch
    def forbidden(*args, **kwargs):
        raise AssertionError('Snapshot attempted network I/O')
    with patch.object(socket.socket, 'connect', forbidden):
        app = importlib.import_module(sys.argv[1]).app
        print(json.dumps(snapshot(app), indent=2, sort_keys=True))
