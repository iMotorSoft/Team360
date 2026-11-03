"""Parameterized operational persistence. Caller owns connection and transaction."""
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


async def rows(conn, sql, params=()):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        return [dict(r) for r in await cur.fetchall()]


class BusinessConceptRepository:
    async def connection_identity(self, conn):
        return (await rows(conn, '''SELECT current_user AS role,rolsuper,rolbypassrls
            FROM pg_roles WHERE rolname=current_user'''))[0]

    async def scope(self, conn, workspace_id, tenant_code=None):
        result = await rows(conn, """SELECT w.organization_id::text, w.id::text AS workspace_id,
            o.organization_code FROM core_workspaces w JOIN core_organizations o ON o.id=w.organization_id
            WHERE w.id=%s AND w.status IN ('active','testing') AND o.status='active'
            AND (%s::text IS NULL OR o.organization_code=%s)""", (workspace_id, tenant_code, tenant_code))
        if not result:
            raise PermissionError('business_semantics_scope_denied')
        return result[0]

    async def authorize(self, conn, organization_id, workspace_id, actor_id, *, admin=False):
        result = await rows(conn, """SELECT u.id FROM core_users u JOIN core_workspaces w ON w.id=u.workspace_id
            WHERE u.id=%s AND u.workspace_id=%s AND u.status='active' AND w.organization_id=%s
            AND w.status IN ('active','testing')""", (actor_id, workspace_id, organization_id))
        if not result:
            raise PermissionError('business_semantics_identity_denied')
        if admin:
            result = await rows(conn, """SELECT m.id FROM core_organization_members m
                JOIN core_organization_member_roles r ON r.organization_member_id=m.id
                WHERE m.organization_id=%s AND m.user_id=%s AND m.status='active'
                AND r.role_code='organization_admin' AND r.status='active'""", (organization_id, actor_id))
            if not result:
                raise PermissionError('business_semantics_admin_required')

    async def catalog(self, conn, organization_id, workspace_id, module):
        return await rows(conn, """SELECT c.id::text AS concept_id,c.semantic_code,c.workspace_id::text,
            c.module_code,v.version,v.canonical_name,v.definition,v.concept_type,v.operational_context,
            v.source,v.approval_status,
            COALESCE((SELECT jsonb_agg(a.original_text ORDER BY a.normalized_text)
                FROM business_concept_aliases a WHERE a.concept_id=c.id AND a.version=v.version),'[]') AS aliases,
            COALESCE((SELECT jsonb_agg(jsonb_build_object('code',l.capability_code,'maturity',l.maturity))
                FROM business_concept_capability_links l WHERE l.concept_id=c.id AND l.version=v.version),'[]') AS capability_links
            FROM business_concepts c JOIN business_concept_versions v ON v.concept_id=c.id AND v.version=c.current_version
            WHERE c.organization_id=%s AND (c.workspace_id IS NULL OR c.workspace_id=%s)
            AND (c.module_code IS NULL OR c.module_code=%s) AND c.status='published'
            AND v.approval_status='published' ORDER BY c.semantic_code LIMIT 500""",
            (organization_id, workspace_id, module))

    async def admin_catalog(self, conn, organization_id, workspace_id, module):
        return await rows(conn,"""SELECT c.id::text AS concept_id,c.semantic_code,c.status,c.current_version,
            v.version AS latest_version,v.approval_status AS latest_approval_status,v.canonical_name,v.source
            FROM business_concepts c JOIN LATERAL (SELECT version,approval_status,canonical_name,source
                FROM business_concept_versions WHERE concept_id=c.id ORDER BY version DESC LIMIT 1) v ON true
            WHERE c.organization_id=%s AND c.workspace_id IS NOT DISTINCT FROM %s::uuid
            AND c.module_code IS NOT DISTINCT FROM %s ORDER BY c.semantic_code LIMIT 500""",(organization_id,workspace_id,module))

    async def text_search(self, conn, organization_id, workspace_id, module, text, limit):
        return await rows(conn, """SELECT c.id::text AS concept_id,
            ts_rank_cd(to_tsvector('spanish',v.canonical_name || ' ' || v.definition),
                       websearch_to_tsquery('spanish',%s)) AS score
            FROM business_concepts c JOIN business_concept_versions v ON v.concept_id=c.id AND v.version=c.current_version
            WHERE c.organization_id=%s AND (c.workspace_id IS NULL OR c.workspace_id=%s)
            AND (c.module_code IS NULL OR c.module_code=%s) AND c.status='published' AND v.approval_status='published'
            AND to_tsvector('spanish',v.canonical_name || ' ' || v.definition) @@ websearch_to_tsquery('spanish',%s)
            ORDER BY score DESC,c.semantic_code LIMIT %s""", (text,organization_id,workspace_id,module,text,limit))

    async def vector_search(self, conn, organization_id, workspace_id, module, vector, config, limit):
        return await rows(conn, """SELECT c.id::text AS concept_id,1-(e.embedding <=> %s::vector) AS score
            FROM business_concept_embeddings e JOIN business_concepts c ON c.id=e.concept_id
            JOIN business_concept_versions v ON v.concept_id=c.id AND v.version=c.current_version
            WHERE c.organization_id=%s AND (c.workspace_id IS NULL OR c.workspace_id=%s)
            AND (c.module_code IS NULL OR c.module_code=%s) AND c.status='published' AND v.approval_status='published'
            AND e.version=c.current_version AND e.model_alias=%s AND e.model_revision=%s AND e.dimension=%s
            ORDER BY e.embedding <=> %s::vector,c.semantic_code LIMIT %s""",
            (str(vector),organization_id,workspace_id,module,config.alias,config.revision,config.dimension,str(vector),limit))

    async def propose(self, conn, organization_id, workspace_id, module, actor_id, spec):
        result = await rows(conn, """INSERT INTO business_concepts(organization_id,workspace_id,module_code,semantic_code)
            VALUES(%s,%s,%s,%s) ON CONFLICT (organization_id,workspace_id,module_code,semantic_code)
            DO UPDATE SET updated_at_utc=now() RETURNING id::text""",
            (organization_id,workspace_id,module,spec['code']))
        cid = result[0]['id']
        previous = (await rows(conn, 'SELECT max(version) AS version FROM business_concept_versions WHERE concept_id=%s', (cid,)))[0]['version']
        version = (previous or 0)+1
        await conn.execute("""INSERT INTO business_concept_versions(concept_id,version,previous_version,canonical_name,
            definition,concept_type,operational_context,source,reason,actor_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (cid,version,previous,spec['name'],spec['definition'],spec['type'],Jsonb(spec['context']),spec['source'],spec['reason'],actor_id))
        from .resolver import normalize
        for alias in spec['aliases']:
            await self.add_alias(conn,cid,version,alias,normalize(alias))
        for link in spec.get('capability_links',[]):
            await conn.execute('INSERT INTO business_concept_capability_links VALUES(%s,%s,%s,%s)',
                               (cid,version,link['code'],link['maturity']))
        return dict(concept_id=cid,version=version)

    async def add_alias(self, conn, concept_id, version, original, normalized):
        await conn.execute("""INSERT INTO business_concept_aliases VALUES(%s,%s,%s,%s)
            ON CONFLICT DO NOTHING""", (concept_id,version,original,normalized))

    async def owned(self, conn, organization_id, workspace_id, module, concept_id):
        found = await rows(conn, """SELECT id FROM business_concepts WHERE id=%s AND organization_id=%s
            AND workspace_id IS NOT DISTINCT FROM %s::uuid AND module_code IS NOT DISTINCT FROM %s FOR UPDATE""",
            (concept_id,organization_id,workspace_id,module))
        if not found:
            raise PermissionError('business_semantics_concept_not_owned')

    async def publish(self, conn, concept_id, version, actor_id):
        result = await rows(conn, """UPDATE business_concept_versions SET approval_status='published',approved_by=%s,
            published_at_utc=now() WHERE concept_id=%s AND version=%s AND approval_status='proposed' RETURNING version""",
            (actor_id,concept_id,version))
        if not result:
            raise ValueError('proposed_version_required')
        await conn.execute("UPDATE business_concepts SET status='published',current_version=%s,updated_at_utc=now() WHERE id=%s", (version,concept_id))

    async def retire(self, conn, concept_id):
        await conn.execute("UPDATE business_concepts SET status='retired',updated_at_utc=now() WHERE id=%s",(concept_id,))

    async def history(self, conn, concept_id):
        return await rows(conn,'SELECT * FROM business_concept_versions WHERE concept_id=%s ORDER BY version',(concept_id,))

    async def embedding_source(self, conn, concept_id, version):
        found = await rows(conn,"""SELECT v.*,COALESCE((SELECT jsonb_agg(original_text ORDER BY normalized_text)
            FROM business_concept_aliases WHERE concept_id=v.concept_id AND version=v.version),'[]') AS aliases
            FROM business_concept_versions v WHERE v.concept_id=%s AND v.version=%s AND approval_status='published'""",(concept_id,version))
        if not found:
            raise ValueError('published_version_required')
        return found[0]

    async def embedding_exists(self, conn, cid, version, config, digest):
        return bool(await rows(conn,"""SELECT 1 FROM business_concept_embeddings WHERE concept_id=%s AND version=%s
            AND model_alias=%s AND model_revision=%s AND dimension=%s AND content_hash=%s""",
            (cid,version,config.alias,config.revision,config.dimension,digest)))

    async def save_embedding(self, conn, cid, version, config, digest, vector):
        await conn.execute("""INSERT INTO business_concept_embeddings(concept_id,version,model_alias,model_revision,
            dimension,content_hash,embedding) VALUES(%s,%s,%s,%s,%s,%s,%s::vector)
            ON CONFLICT(concept_id,version,model_alias,model_revision,dimension) DO UPDATE SET
            content_hash=EXCLUDED.content_hash,embedding=EXCLUDED.embedding,generated_at_utc=now()""",
            (cid,version,config.alias,config.revision,config.dimension,digest,str(vector)))

    async def observe(self, conn, organization_id, workspace_id, module, digest):
        await conn.execute("""INSERT INTO business_concept_observations(organization_id,workspace_id,module_code,expression_hash)
            VALUES(%s,%s,%s,%s) ON CONFLICT(organization_id,workspace_id,module_code,expression_hash)
            DO UPDATE SET occurrences=business_concept_observations.occurrences+1,last_seen_at_utc=now()""",
            (organization_id,workspace_id,module,digest))

    async def add_entity_evidence(self, conn, cid, version, actor, evidence):
        await conn.execute("""INSERT INTO business_concept_entity_links(concept_id,version,entity_type,source_namespace,
            entity_key,entity_label,relationship,validation_status,valid_from,valid_to,evidence,actor_id)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (cid,version,evidence['entity_type'],evidence['source_namespace'],evidence.get('entity_key'),
             evidence['entity_label'],evidence['relationship'],evidence['validation_status'],
             evidence.get('valid_from'),evidence.get('valid_to'),Jsonb(evidence['evidence']),actor))

    async def add_rule_evidence(self, conn, cid, version, actor, rule):
        await conn.execute("""INSERT INTO business_concept_classification_rules(concept_id,version,rule_code,
            description,input_fields,source,validation_status,valid_from,valid_to,limitations,actor_id)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (cid,version,rule['rule_code'],rule['description'],Jsonb(rule['input_fields']),rule['source'],
             rule['validation_status'],rule.get('valid_from'),rule.get('valid_to'),Jsonb(rule['limitations']),actor))

    async def relation_evidence(self, conn, cid, version):
        entities = await rows(conn,"""SELECT entity_type,source_namespace,entity_key,entity_label,relationship,
            validation_status,valid_from::text,valid_to::text,evidence FROM business_concept_entity_links
            WHERE concept_id=%s AND version=%s ORDER BY entity_label""",(cid,version))
        rules = await rows(conn,"""SELECT rule_code,description,input_fields,source,validation_status,
            valid_from::text,valid_to::text,limitations FROM business_concept_classification_rules
            WHERE concept_id=%s AND version=%s ORDER BY rule_code""",(cid,version))
        return dict(entities=entities,rules=rules)

    async def seed_existing(self, conn, organization_id, workspace_id, module):
        return await rows(conn,"""SELECT semantic_code,status,current_version FROM business_concepts
            WHERE organization_id=%s AND workspace_id=%s AND module_code=%s""",(organization_id,workspace_id,module))

    async def audit(self, conn, workspace_id, actor_id, action, payload):
        await conn.execute("""INSERT INTO core_events(workspace_id,actor_user_id,event_name,entity_type,payload_jsonb)
            VALUES(%s,%s,%s,'business_concept',%s)""",(workspace_id,actor_id,'business_semantics.'+action,Jsonb(payload)))
