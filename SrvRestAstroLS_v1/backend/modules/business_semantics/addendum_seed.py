"""Structured seller/channel evidence. No inference of as-of business classifications."""
from .telchi_seed import SOURCE

HISTORICAL_ROOT='SrvRestAstroLS_v1/backend/modules/telchi/investigation/validation/corporate_sales/'


async def seed_relations(conn, admin, *, actor_id, workspace_id, foundation_evidence):
    repo=admin.repository
    scope=await repo.scope(conn,workspace_id,'telchi')
    await repo.authorize(conn,scope['organization_id'],workspace_id,actor_id,admin=True)
    catalog={c['semantic_code']:c for c in await repo.catalog(conn,scope['organization_id'],workspace_id,'telchi')}
    verified=foundation_evidence['foundation_publication_id']=='foundation_afd08d9eca6a725be53cdc3f9d5709c9' and foundation_evidence['snapshot']==1408
    if not verified:
        raise ValueError('approved_foundation_evidence_required')
    classification=catalog['telchi.sales.seller_classification']
    existing=await repo.relation_evidence(conn,classification['concept_id'],classification['version'])
    existing_keys={(e['source_namespace'],e['entity_key'],e['relationship']) for e in existing['entities']}
    created=0
    for seller in foundation_evidence['seller_matches']:
        if seller['source_system']!='SAP_HANA' or seller['source_native_id'] not in {'11','13'}:
            continue
        relationship='snapshot_seller_category_corporate'
        key=('SAP_HANA.OSLP',seller['source_native_id'],relationship)
        if key in existing_keys:
            continue
        evidence={'entity_type':'salesperson','source_namespace':'SAP_HANA.OSLP',
                  'entity_key':seller['source_native_id'],'entity_label':seller['name'],
                  'relationship':relationship,'validation_status':'source_verified',
                  'evidence':{'foundation_publication_id':foundation_evidence['foundation_publication_id'],
                              'reference_version':foundation_evidence['reference_version'],
                              'foundation_entity_id':seller['salesperson_id'],'category_code':seller['salesperson_category_code'],
                              'source_extracted_at':seller['_source_extracted_at'],
                              'validity':'snapshot_only; no proven effective interval',
                              'warning':'Luz Guzman is NOT automatically the owner reference Dra. Luz; seller category is not document channel'}}
        await repo.add_entity_evidence(conn,classification['concept_id'],classification['version'],actor_id,evidence)
        created+=1
    online=catalog['telchi.sales.online_channel']
    online_evidence=await repo.relation_evidence(conn,online['concept_id'],online['version'])
    if not online_evidence['entities']:
        await repo.add_entity_evidence(conn,online['concept_id'],online['version'],actor_id,
            {'entity_type':'salesperson','source_namespace':'project_owner','entity_key':None,'entity_label':'Dra. Luz',
             'relationship':'business_example_online','validation_status':'proposed',
             'evidence':{'source':SOURCE+':addendum','identity_resolution':'pending',
                         'classification_validity':'pending; no retrospective document assignment'}})
        created+=1
    rules=[
        ('telchi.sales.horizontal_channel',{'rule_code':'legacy-price-segment-channel',
         'description':'Historical per-sale rule used PriceTypeCode=11 for HORIZONTAL. Other PriceTypeCode and customer segmentation rules classified other channels.',
         'input_fields':['TSSale.PriceTypeCode','ClientSegmentationCode'],
         'source':HISTORICAL_ROOT+'CORPORATE_SALES_FINAL_REPORT.md',
         'validation_status':'historical_evidence','limitations':['Era-specific legacy rule, not approved current mapping. DMS origin alone is insufficient.']}),
        ('telchi.sales.corporate_channel',{'rule_code':'customer-channel-versus-seller-category',
         'description':'Research CHANNEL-RULE-001 identifies customer OCRD.U_CANAL_VENTAS as commercial channel; seller OSLP.U_CATVENDEDOR is independent.',
         'input_fields':['OCRD.CardCode','OCRD.U_CANAL_VENTAS','OINV.CardCode','OINV.SlpCode','OSLP.SlpCode','OSLP.U_CATVENDEDOR'],
         'source':HISTORICAL_ROOT+'CHANNEL_RULE_FINAL_REPORT.md',
         'validation_status':'historical_evidence','limitations':['Historical follow-up CHANNEL_HISTORY_FINAL_REPORT corrects claimed 2022-2026 stability: channel bulk-loaded in 2026; no individual change history.',
          'Current Foundation customers do not publish U_CANAL_VENTAS; channels reference dataset absent. Do not group channel 2 and 3. No executable classification rule.']}),
        ('telchi.sales.seller_classification',{'rule_code':'document-seller-customer-relations',
         'description':'Foundation sales_document.slp_code links SAP OSLP.SlpCode; card_code links OCRD.CardCode. Reference namespace SAP_HANA differs from atomic SAP_B1_HANA and requires an explicit crosswalk.',
         'input_fields':['sales_document.slp_code','sales_document.card_code','sales_document.source_system','salespersons.source_native_id','customers.source_native_id'],
         'source':'channel_foundation_evidence.json:CURRENT-1408',
         'validation_status':'historical_evidence','limitations':['Verified fields and snapshot examples only; seller-client assignment master not published in customers.',
          'Source system is lineage, not proof of DMS/Retail One document origin or business channel. Validity and exceptions remain pending.']})]
    for code,rule in rules:
        concept=catalog[code]
        evidence=await repo.relation_evidence(conn,concept['concept_id'],concept['version'])
        if rule['rule_code'] not in {r['rule_code'] for r in evidence['rules']}:
            await repo.add_rule_evidence(conn,concept['concept_id'],concept['version'],actor_id,rule)
            created+=1
    if created:
        await repo.audit(conn,workspace_id,actor_id,'addendum_evidence',{'created_count':created,'source':SOURCE+':addendum'})
    return {'created_count':created,'operational_classification_published':False}
