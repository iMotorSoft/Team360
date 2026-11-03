"""Five meanings explicitly approved by project owner; analytical capabilities pending."""
SOURCE='project-owner:TEAM360-BUSINESS-SEMANTICS-PGVECTOR-V1'


def spec(code,name,definition,kind,aliases,dimension,limits):
    return dict(code=code,name=name,definition=definition,type=kind,aliases=aliases,
                context=dict(dimension=dimension,validation='business_meaning_confirmed',
                             capability_status='pending',limitations=limits),
                source=SOURCE,reason='Initial explicitly approved business meaning')


CONCEPTS=[
 spec('telchi.sales.pharmacy_branches','Ventas de farmacia',
      'Ventas realizadas en sucursales que Telchi clasifica como farmacias.', 'ENTITY_SCOPE',
      ['Dame ventas de farmacia','ventas de farmacia','ventas en sucursales farmacia'], 'branches',
      ['No son productos farmacéuticos ni ventas a clientes farmacias.',
       'Clasificación de sucursales → IDs reales → documentos comerciales. No inventar sucursales.']),
 spec('telchi.sales.menona_customers','Ventas de menona',
      'Ventas a clientes incluidos por Telchi en su segmento comercial denominado menona.', 'ENTITY_SCOPE',
      ['¿Cuánto le vendimos a menona?','ventas de menona','dame ventas de menona'], 'customers',
      ['No buscar productos menona. La pertenencia debe constar en información comercial autorizada.',
       'No inferir religión o comunidad a partir de nombres, apellidos o domicilios.']),
 spec('telchi.procurement.import_recommendations','Qué hay que importar',
      'Evaluar qué materias primas, productos u otros artículos convendría importar para satisfacer las necesidades operativas y comerciales de Telchi.',
      'ANALYTICAL_INTENT',['¿Qué hay que importar?','qué conviene importar','recomendaciones de importación'],'supply_analysis',
      ['Factores potenciales: stock, demanda, consumo de producción, OC abiertas, lead time, cobertura y clasificación de abastecimiento.',
       'No existe fórmula aprobada ni capability de recomendación. Stock bajo por sí solo no justifica importar. No generar órdenes de compra.']),
 spec('telchi.receivables.outstanding','Deuda pendiente',
      'La deuda pendiente de clientes incluye deuda vencida y deuda corriente aún no vencida: deuda pendiente = deuda vencida + deuda corriente, ambos saldos abiertos a la misma fecha de corte y alcance.',
      'COMPOSITE_METRIC',['dame las deudas','cuánto nos deben','deuda pendiente','cuentas por cobrar pendientes'],'receivables',
      ['No equivale a morosidad. No confundir cuentas por cobrar con cuentas por pagar.',
       'Si el contexto no distingue deudas de clientes y deudas a proveedores, solicitar aclaración.',
       'Reutilizar contratos Receivables & Collections; no inventar saldos.']),
 spec('telchi.sales.lost_opportunities','Ventas perdidas',
      'Listado de oportunidades comerciales no concretadas que el área de ventas prepara para dirección usando información de vendedores. Una lógica histórica es presupuestos o cotizaciones no transformados en ventas.',
      'ANALYTICAL_INTENT',['Mostrame las ventas perdidas','ventas perdidas','dame ventas perdidas'], 'sales_opportunities',
      ['Una cotización sin factura no demuestra pérdida definitiva: distinguir pendiente, no convertida, conversión parcial y pérdida confirmada.',
       'Cliente desde presupuesto cuando exista relación. Productos, cantidades, importes, vendedor, fechas y evidencia de estado; no inventar causas.',
       'Clasificación definitiva necesita evidencia empresarial adicional.'])
]


CONCEPTS += [
 spec('telchi.sales.horizontal_channel','Venta horizontal',
      'En Telchi, en general, ventas de vendedores que operan mediante DMS, habitualmente ventas de calle.',
      'ENTITY_SCOPE',['venta horizontal','ventas horizontales','Dame las ventas horizontales de septiembre',
                      'Compará ventas corporativas y horizontales'], 'commercial_channel',
      ['Origen DMS por sí solo no determina canal. Clasificación de vendedor, cliente y documento son dimensiones diferentes.',
       'No hay filtro de canal horizontal habilitado para consultas generales. No inventar período o importes.']),
 spec('telchi.sales.corporate_channel','Venta corporativa',
      'Modalidad comercial corporativa de Telchi. La reconstrucción histórica distingue canal comercial del cliente y categoría corporativa del vendedor: no son equivalentes.',
      'ENTITY_SCOPE',['venta corporativa','ventas corporativas','¿Cuánto vendió el canal corporativo en mayo?',
                      'Compará ventas corporativas y horizontales'],
      'commercial_channel',
      ['Investigación: regla legacy PriceTypeCode + ClientSegmentationCode; luego OCRD.U_CANAL_VENTAS para canal del cliente y OSLP.U_CATVENDEDOR para vendedor.',
       'No sumar canales 2 y 3 ni proyectar clasificación actual a toda la historia. Vigencia y excepciones pendientes de acreditación runtime.']),
 spec('telchi.sales.online_channel','Venta online',
      'Modalidad comercial online de Telchi, que puede estar identificada comercialmente mediante el vendedor asignado.',
      'ENTITY_SCOPE',['venta online','ventas online','ventas por internet'], 'commercial_channel',
      ['El ejemplo empresarial aportado no autoriza clasificar retrospectivamente operaciones de un vendedor.',
       'Relaciones e identificadores están en evidencia estructurada; no hay filtro online validado.']),
 spec('telchi.sales.seller_classification','Clasificación comercial de vendedores',
      'Clasificación empresarial de vendedores y consulta de sus ventas. La categoría del vendedor no determina por sí sola el canal comercial de cada documento o cliente.',
      'ENTITY_SCOPE',['¿Cuáles son los vendedores corporativos?','Mostrame las ventas de Selva Rojas',
                      '¿Cuánto vendió la Dra. Luz?'], 'salespersons',
      ['Resolver identidad real del vendedor y documentos relacionados con vigencia y excepciones.',
       'No inventar IDs ni importes. Evidencia de un snapshot no demuestra clasificación histórica de todas las operaciones.'])
]


async def seed(conn, administration, *, actor_id, workspace_id):
    """Idempotent, conflict-sensitive. Never overwrite a newer business definition."""
    repo=administration.repository
    scope=await repo.scope(conn,workspace_id,'telchi')
    await repo.authorize(conn,scope['organization_id'],workspace_id,actor_id,admin=True)
    await conn.execute("SELECT pg_advisory_xact_lock(hashtext('business-semantics-telchi-seed-v1'))")
    existing={c['semantic_code']:c for c in await repo.catalog(conn,scope['organization_id'],workspace_id,'telchi')}
    all_existing={c['semantic_code']:c for c in await repo.seed_existing(conn,scope['organization_id'],workspace_id,'telchi')}
    result=[]
    for item in CONCEPTS:
        if item['code'] in existing:
            c=existing[item['code']]
            if c['definition']!=item['definition'] or c['source']!=SOURCE or set(c['aliases'])!=set(item['aliases']):
                raise ValueError('seed_conflict_requires_review')
            result.append(dict(concept_id=c['concept_id'],version=c['version'],changed=False))
            continue
        if item['code'] in all_existing:
            raise ValueError('seed_existing_proposed_or_retired_requires_review')
        c=await administration.execute(conn,actor_id=actor_id,workspace_id=workspace_id,module='telchi',action='propose',payload=item)
        await administration.execute(conn,actor_id=actor_id,workspace_id=workspace_id,module='telchi',action='publish',payload=c)
        result.append(dict(c,changed=True))
    return result
