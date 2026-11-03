"""Administrative SQL only. Caller supplies connection/transaction, never a DSN."""
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from psycopg.types.json import Jsonb

from .contract import authorize, digest, preparation, require, signature, unb64, single_owner


class Repository:
    def apply(self, conn, envelope, trust, side, key, *, environment=None):
        # Caller owns transaction. Inventory row also serializes admission/revocation.
        conn.execute("SET LOCAL lock_timeout='3s'")
        conn.execute("SET LOCAL statement_timeout='5s'")
        now = int(conn.execute('SELECT extract(epoch FROM clock_timestamp()) AS n').fetchone()['n'])
        m = authorize(envelope, trust, now, environment=environment)
        # Existing schema column is named approver; record the actual sole owner,
        # never fabricate a second actor. The complete signed mode is in envelope.
        actor = m['owner'] if single_owner(m) else m['approver']
        require(side in ('team360', 'evolution'), 'invalid_side')
        require(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw) ==
                unb64(trust['targets'][side]['public_key'], 32), 'wrong_target_signer')
        target = conn.execute('SELECT target_id::text,epoch::text FROM ot_target WHERE side=%s', (side,)).fetchone()
        require(target and dict(id=target['target_id'], epoch=target['epoch']) == m['targets'][side], 'database_target_mismatch')
        binding = m['scope']['binding_id']
        inventory = conn.execute('SELECT scope FROM ot_inventory WHERE side=%s AND binding_id=%s FOR UPDATE',
                                 (side, binding)).fetchone()
        require(inventory and inventory['scope'] == m['scope'], 'binding_not_accredited')
        old = conn.execute('SELECT envelope_hash,receipt FROM ot_operation WHERE side=%s AND operation_id=%s',
                           (side, m['operation_id'])).fetchone()
        if old:
            require(old['envelope_hash'] == digest(envelope), 'operation_replay_conflict')
            return {'disposition': 'already_applied', 'receipt': old['receipt']}
        require(not conn.execute('SELECT 1 FROM ot_operation WHERE side=%s AND approver=%s AND nonce=%s',
                                 (side, actor, m['nonce'])).fetchone(), 'nonce_reused')
        rows = conn.execute('SELECT revision,state FROM ot_revision WHERE side=%s AND binding_id=%s ORDER BY revision DESC',
                            (side, binding)).fetchall()
        latest = rows[0] if rows else None
        revision = m['revision']
        prepared = preparation(m, side)
        receipt = {'payload': prepared, 'signature': signature(key, 'team360.offline.preparation.v1', prepared)}
        if m['action'] == 'prepare':
            require(revision == (latest['revision'] + 1 if latest else 1), 'obsolete_revision')
            require(not latest or latest['state'] != 'prepared', 'unfinished_revision')
            conn.execute('''INSERT INTO ot_revision(side,binding_id,revision,scope,credential_hash,state,prepared_receipt)
                            VALUES (%s,%s,%s,%s,%s,'prepared',%s)''',
                         (side, binding, revision, Jsonb(m['scope']), m['credential_hash'], Jsonb(receipt)))
        else:
            local = conn.execute('SELECT * FROM ot_revision WHERE side=%s AND binding_id=%s AND revision=%s',
                                 (side, binding, revision)).fetchone()
            require(local and local['scope'] == m['scope'] and local['credential_hash'] == m['credential_hash'],
                    'revision_mismatch')
            if m['action'] == 'activate':
                require(local['state'] == 'prepared' and latest['revision'] == revision, 'activation_not_prepared')
                require(local['prepared_receipt'] == m['preparations'][side], 'local_preparation_mismatch')
                # Rotation permanently revokes older active revisions; no audit/attempt deletion.
                conn.execute("UPDATE ot_revision SET state='revoked' WHERE side=%s AND binding_id=%s AND state='active'",
                             (side, binding))
                conn.execute("UPDATE ot_revision SET state='active',activation_id=%s WHERE side=%s AND binding_id=%s AND revision=%s",
                             (m['operation_id'], side, binding, revision))
            else:
                conn.execute("UPDATE ot_revision SET state='revoked' WHERE side=%s AND binding_id=%s AND revision=%s",
                             (side, binding, revision))
            payload = {**prepared, 'action': m['action'], 'operation_id': m['operation_id']}
            receipt = {'payload': payload, 'signature': signature(key, 'team360.offline.operation.v1', payload)}
        conn.execute('''INSERT INTO ot_operation(side,operation_id,approver,nonce,envelope_hash,envelope,receipt)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)''',
                     (side, m['operation_id'], actor, m['nonce'], digest(envelope), Jsonb(envelope), Jsonb(receipt)))
        return {'disposition': 'applied', 'receipt': receipt}
