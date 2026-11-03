"""Sales-only extension of the approved local-owner DEV provisioning command."""
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row
from modules.db.settings import get_database_settings
from .admin_cli import private_json
from .live_cli import digest
from .repository import Conflict
from .sales_repository import SalesActivationRepository, AUTHORIZATION


async def run_sales(args):
    repository_type, expected_authorization = SalesActivationRepository, AUTHORIZATION
    monetary = getattr(args, 'monetary_activation', False)
    if monetary:
        from .monetary_repository import MonetaryActivationRepository, AUTHORIZATION as monetary_authorization
        repository_type, expected_authorization = MonetaryActivationRepository, monetary_authorization
        if args.rollback_sales_run:
            raise Conflict('sales rollback cannot withdraw monetary grants')
    product = getattr(args, 'product_activation', False)
    if product:
        from .product_repository import ProductActivationRepository, AUTHORIZATION as product_authorization
        repository_type, expected_authorization = ProductActivationRepository, product_authorization
        if args.rollback_sales_run:
            raise Conflict('sales rollback cannot withdraw product grants')
    invoice = getattr(args, 'invoice_activation', False)
    if invoice:
        from .invoice_repository import InvoiceActivationRepository, AUTHORIZATION as invoice_authorization
        repository_type, expected_authorization = InvoiceActivationRepository, invoice_authorization
        if args.rollback_sales_run:
            raise Conflict('sales rollback cannot withdraw invoice grants')
    manifest = private_json(args.manifest)
    if set(manifest) != {'authorization', 'environment', 'operator_uid', 'target', 'backup', 'backup_sha256', 'sources'}:
        raise Conflict('sales manifest fields differ')
    if manifest['authorization'] != expected_authorization or manifest['environment'] != 'dev' or manifest['operator_uid'] != os.getuid():
        raise Conflict('explicit local owner DEV sales authorization required')
    backup = Path(manifest['backup']).resolve()
    private = Path('/media/issajar/DEVELOP/Projects/iMotorSoft/ai/private/telchi').resolve()
    if not backup.is_relative_to(private):
        raise Conflict('backup outside PRIVATE_ROOT')
    before = private_json(backup)
    if digest(backup) != manifest['backup_sha256'] or before['target'] != manifest['target']:
        raise Conflict('recoverable backup integrity/target mismatch')
    sources = ('sales_repository.py', 'sales_cli.py', 'live_cli.py', 'admin_repository.py', 'repository.py', 'admin_service.py')
    if monetary or product or invoice:
        sources += ('monetary_repository.py',)
    if product or invoice:
        sources += ('product_repository.py',)
    if invoice:
        sources += ('invoice_repository.py',)
    for name in sources:
        if digest(Path(__file__).with_name(name)) != manifest['sources'].get(name):
            raise Conflict('reviewed provisioning sources changed')
    dsn = get_database_settings().dsn
    target = urlparse(dsn)
    if target.hostname not in ('localhost', '127.0.0.1') or target.port != 5432 or target.path != '/team360':
        raise Conflict('only approved local team360 DEV target allowed')
    if args.apply and not args.local_owner_bootstrap:
        raise Conflict('explicit local owner confirmation required')
    repo = repository_type()
    async with await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row, autocommit=True,
            connect_timeout=5, application_name='telchi-dev-sales-owner-provisioning') as conn:
        async with conn.transaction():
            await conn.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE' + ('' if args.apply else ' READ ONLY'))
            if await repo.target(conn) != manifest['target']:
                raise Conflict('actual target mismatch')
            identities = await repo.identities(conn)
            if identities != before['identities']:
                raise Conflict('identities changed since backup')
            if not args.apply:
                result = dict(mode='READ_ONLY_PLAN', identities=identities, limits=repo.sales_limits())
            elif args.rollback_sales_run:
                result = await repo.rollback_assignments(conn, args.rollback_sales_run)
            else:
                result = await repo.activate(conn, backup_sha256=manifest['backup_sha256'], authorization=manifest['authorization'])
    print(json.dumps(result, indent=2, default=str))
