"""DEV HTTP composition for the existing authenticated Luna bridge.

TEAM360_TELCHI_CONSOLE_CONFIG points to reviewed server-only JSON containing
organization, workspace, issuer, public_keys_by_id, policies (SourcePolicy dicts),
and evidence_directory. No issuer private key or caller-defined grants are used.
"""
import json
import os
from pathlib import Path
import stat
from uuid import uuid4

from modules.db.pool import get_pool
from .datalake.foundation_reader import FoundationReader
from .exploratory_sql.authorized_foundation import SourcePolicy
from .exploratory_sql.console_bridge import ConsoleResearchService

class AccreditedReader(FoundationReader):
    """CURRENT is chosen by the accredited succession contract, not a literal.

    The reader already fails closed when CURRENT disappeared and validates the
    read-binding receipt. Each investigation binding then pins publication+snapshot
    for that turn, so an advancing CURRENT cannot swap data mid-investigation.
    An operator may still pin an expected publication from private configuration;
    no publication id is hardcoded in source.
    """
    def __init__(self, publication=None):
        super().__init__()
        if publication is not None and (not isinstance(publication, str)
                                        or not publication.startswith('foundation_')):
            raise ValueError('accredited_publication_required')
        self.publication = publication

    def resolve_on(self, connection):
        access = super().resolve_on(connection)
        if self.publication is not None and access.foundation_publication_id != self.publication:
            raise ValueError('accredited_current_changed')
        return access


def evidence_directory(config):
    """Owner-only, outside the repository; shared by every channel composition."""
    path = Path(config['evidence_directory']).resolve(strict=True)
    repo = Path(__file__).resolve().parents[4]
    mode = path.stat()
    if (not path.is_dir() or path.is_relative_to(repo)
            or mode.st_uid != os.getuid() or stat.S_IMODE(mode.st_mode) & 0o077):
        raise ValueError('private_evidence_directory_required')
    return path


def evidence_sink(directory):
    """Unique owner-only append log: interruption cannot truncate prior evidence."""
    path = Path(directory) / (str(uuid4()) + '.jsonl')

    def save(report):
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'a') as stream:
            stream.write(json.dumps(report, ensure_ascii=False, default=str) + '\n')
    return save


class ConsoleHTTPRuntime:
    def __init__(self, config, *, pool=None):
        if not config.get('public_keys_by_id'):
            raise ValueError('explicit_console_public_keys_required')
        self.service = ConsoleResearchService(
            pool=get_pool() if pool is None else pool, public_keys_by_id=config['public_keys_by_id'],
            issuer=config['issuer'], organization=config['organization'],
            workspace=config['workspace'],
            policies=tuple(SourcePolicy(**p) for p in config['policies']),
            reader=AccreditedReader(config.get('foundation_publication_id')), enabled=True,
            environment=os.environ.get('TEAM360_ENV', ''))
        self.evidence_directory = evidence_directory(config)

    def evidence_sink(self):
        return evidence_sink(self.evidence_directory)


def load_config():
    config_path = os.environ.get('TEAM360_TELCHI_CONSOLE_CONFIG')
    if not config_path:
        raise ValueError('telchi_console_configuration_required')
    path = Path(config_path)
    mode = path.lstat()
    if (not stat.S_ISREG(mode.st_mode) or mode.st_uid != os.getuid()
            or stat.S_IMODE(mode.st_mode) & 0o077):
        raise ValueError('owner_only_server_configuration_required')
    return json.loads(path.read_text())


def get_runtime(request):
    runtime = getattr(request.app.state, 'telchi_console_runtime', None)
    if runtime is None:
        runtime = ConsoleHTTPRuntime(load_config())
        request.app.state.telchi_console_runtime = runtime
    return runtime
