"""Two documented candidates only. Never published by historical extraction."""
SOURCE='data/reports/telchi/historical_business_query_inventory_v1/business_semantics.md'
CANDIDATES=[
 {'code':'telchi.stock.available','name':'Stock disponible','type':'BUSINESS_RULE',
  'definition':'Candidato histórico: disponible = OnHand − IsCommited; OnOrder es abastecimiento abierto, no existencia física.',
  'aliases':['stock disponible','existencia disponible'],'context':{'validation':'proposal_requires_owner_review',
  'dimension':'inventory','capability_status':'pending','limitations':['Conservar negativos, fecha de snapshot y unidades compatibles. OITW as_of no demuestra stock histórico.'],
  'proposed_relationships':['telchi.procurement.import_recommendations']},'source':SOURCE,
  'reason':'Focal historical extraction; not explicit approval for semantic publication'},
 {'code':'telchi.stock.coverage','name':'Cobertura de stock','type':'ANALYTICAL_INTENT',
  'definition':'Candidato histórico: analizar cuánto abastecimiento cubre el stock frente a necesidades o demanda bajo factores, unidades y validez temporal acreditados.',
  'aliases':['cobertura de stock','cobertura de inventario'],'context':{'validation':'proposal_requires_owner_review',
  'dimension':'inventory','capability_status':'pending','limitations':['No hay fórmula ni horizonte empresarial aprobados en esta extracción. Demanda equivalente requiere dependencias y factores verificados.'],
  'proposed_relationships':['telchi.procurement.import_recommendations']},'source':SOURCE,
  'reason':'Inventory marks coverage CONDITIONAL; preserve proposal, not approved truth'}
]


async def seed_proposals(conn, admin, *, actor_id, workspace_id):
    repo=admin.repository;scope=await repo.scope(conn,workspace_id,'telchi')
    await repo.authorize(conn,scope['organization_id'],workspace_id,actor_id,admin=True)
    existing={c['semantic_code'] for c in await repo.seed_existing(conn,scope['organization_id'],workspace_id,'telchi')}
    result=[]
    for spec in CANDIDATES:
        if spec['code'] in existing:
            result.append({'code':spec['code'],'changed':False});continue
        result.append(await admin.execute(conn,actor_id=actor_id,workspace_id=workspace_id,module='telchi',action='propose',payload=spec))
    return {'proposals':result,'auto_published':False}
