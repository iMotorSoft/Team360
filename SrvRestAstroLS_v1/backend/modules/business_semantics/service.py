"""Administrative operations gated by existing organization roles, not chat learning."""
from .repository import BusinessConceptRepository
from .resolver import normalize
from .embeddings import embedding_content


class BusinessConceptAdministration:
    def __init__(self, repository=None, embeddings=None):
        self.repository=repository or BusinessConceptRepository()
        self.embeddings=embeddings

    async def execute(self, conn, *, actor_id, workspace_id, module, action, payload):
        repo=self.repository
        scope=await repo.scope(conn,workspace_id)
        org=scope['organization_id']
        await repo.authorize(conn,org,workspace_id,actor_id,admin=True)
        if action=='propose':
            required={'code','name','definition','type','context','source','reason','aliases'}
            if not required<=payload.keys() or payload.keys()-required-{'capability_links'}:
                raise ValueError('invalid_concept_spec')
            if any(not isinstance(payload[k],str) or not 0<len(payload[k])<=6000 for k in required-{'context','aliases'}):
                raise ValueError('invalid_concept_text')
            if not isinstance(payload['context'],dict) or not isinstance(payload['aliases'],list) or len(payload['aliases'])>50:
                raise ValueError('invalid_concept_context')
            if any(not isinstance(a,str) or not 0<len(a)<=250 for a in payload['aliases']):
                raise ValueError('invalid_alias')
            result=await repo.propose(conn,org,workspace_id,module,actor_id,payload)
        elif action=='list':
            return await repo.admin_catalog(conn,org,workspace_id,module)
        else:
            cid=payload['concept_id']
            await repo.owned(conn,org,workspace_id,module,cid)
            if action=='history':
                return await repo.history(conn,cid)
            if action=='publish':
                await repo.publish(conn,cid,payload['version'],actor_id)
            elif action=='retire':
                await repo.retire(conn,cid)
            elif action=='alias':
                alias=payload['alias']
                if not isinstance(alias,str) or not 0<len(alias)<=250:
                    raise ValueError('invalid_alias')
                await repo.add_alias(conn,cid,payload['version'],alias,normalize(alias))
            elif action=='embed':
                if not self.embeddings:
                    raise ValueError('embedding_not_configured')
                source=await repo.embedding_source(conn,cid,payload['version'])
                content,digest=embedding_content(source)
                if await repo.embedding_exists(conn,cid,payload['version'],self.embeddings.config,digest):
                    return dict(changed=False,**payload)
                vector=await self.embeddings.embed(content)
                await repo.save_embedding(conn,cid,payload['version'],self.embeddings.config,digest,vector)
            else:
                raise ValueError('unsupported_semantics_operation')
            result=dict(changed=True,**payload)
        await repo.audit(conn,workspace_id,actor_id,action,result)
        return result
