"""Managed reversible channel retirement and operational exclusivity (no history writes)."""
from .contract import require


class BindingAdministration:
    def operative(self, conn, instance):
        """Use the same status boundary as MessagingRepository.binding, not row existence."""
        return conn.execute('''SELECT c.id::text,c.workspace_id::text,c.channel_alias,c.status,w.slug
            FROM communication_channels c JOIN core_workspaces w ON w.id=c.workspace_id
            JOIN communication_providers p ON p.id=c.provider_id
            WHERE p.code='evolution' AND c.channel_type='whatsapp'
              AND c.metadata_jsonb->>'provider_instance'=%s
              AND c.metadata_jsonb->>'dev_only'='true'
              AND c.status IN ('active','testing') AND w.status IN ('active','testing')
              AND p.status IN ('active','testing') ORDER BY c.id''', (instance,)).fetchall()

    def require_exclusive(self, conn, instance, channel_id):
        rows = self.operative(conn, instance)
        require(len(rows) == 1 and rows[0]['id'] == channel_id, 'operative_binding_not_exclusive')
        return rows[0]

    def deactivate_historical(self, conn, *, channel_id, workspace_slug, alias, instance,
                              expected_status, expected_events, evidence_ref):
        """Caller attests consumer absence; lock/recheck exact DEV row and history count.

        Preserve the complete old row in private operational evidence for rollback.
        Never changes a workspace/provider, event, thread or transport revision.
        """
        require(bool(evidence_ref), 'consumer_absence_evidence_required')
        conn.execute("SET LOCAL lock_timeout='3s'")
        row = conn.execute('''SELECT c.* FROM communication_channels c
            JOIN core_workspaces w ON w.id=c.workspace_id JOIN communication_providers p ON p.id=c.provider_id
            WHERE c.id=%s AND w.slug=%s AND c.channel_alias=%s AND p.code='evolution'
              AND c.metadata_jsonb->>'provider_instance'=%s AND c.metadata_jsonb->>'dev_only'='true'
            FOR UPDATE OF c''', (channel_id, workspace_slug, alias, instance)).fetchone()
        require(row and row['status'] == expected_status and expected_status in ('active','testing'),
                'historical_binding_changed')
        count = conn.execute('SELECT count(*) AS n FROM message_events WHERE channel_id=%s', (channel_id,)).fetchone()['n']
        require(count == expected_events, 'historical_events_changed')
        pending = conn.execute('''SELECT 1 FROM message_events WHERE channel_id=%s
            AND (status IN ('pending','running') OR transport_status IN ('pending','unknown')) LIMIT 1''',
            (channel_id,)).fetchone()
        require(not pending, 'historical_work_pending')
        conn.execute("UPDATE communication_channels SET status='inactive',updated_at_utc=now() WHERE id=%s", (channel_id,))
        return dict(row)
