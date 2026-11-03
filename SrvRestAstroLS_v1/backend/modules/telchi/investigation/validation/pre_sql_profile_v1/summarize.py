"""Regenerate derived statistics from saved samples, without queries or services."""
import json
from pathlib import Path
from .run_profile import OUT, save, stats


def labels(trace):
    return {s['label']:s for s in trace['spans']}


def derive():
    direct=json.loads((OUT/'direct.json').read_text())
    local=json.loads((OUT/'messaging-local.json').read_text())
    derived={}
    for name,samples in [('direct',direct),('messaging_local',local)]:
        individuals=[]
        for i,r in enumerate(samples,1):
            p=r['profile'];s=labels(p);parent=p['parent']
            pre=parent['worker_entry_ms']+s['duckdb_sql_execute']['start_ms']
            total=parent['total_ms']
            if name=='messaging_local':
                m=labels(r['messaging_profile'])
                pre+=m['messaging_capability_execute_including_format']['start_ms']
                total=r['messaging_profile']['pre_send_ms']
            after_fetch=pre+s['fetch']['end_ms']-s['duckdb_sql_execute']['start_ms']
            individuals.append({'sample':i,'pre_sql_ms':pre,'sql_execute_ms':s['duckdb_sql_execute']['duration_ms'],
               'fetch_ms':s['fetch']['duration_ms'],'post_sql_until_result_or_send_ms':total-after_fetch,'total_ms':total})
        derived[name]={'individuals':individuals,'statistics':{k:stats([v[k] for v in individuals])
          for k in ['pre_sql_ms','sql_execute_ms','fetch_ms','post_sql_until_result_or_send_ms','total_ms']},
          'sample_1':individuals[0],'warm_2_10':{k:stats([v[k] for v in individuals[1:]])
          for k in ['pre_sql_ms','sql_execute_ms','fetch_ms','post_sql_until_result_or_send_ms','total_ms']}}
    groups=[
      ('Config/auth/body/normalization/allowlist',['messaging_config','messaging_auth','messaging_body_decode','messaging_normalization','messaging_allowlist'],'REQUIRED'),
      ('Binding workspace/channel',['messaging_binding_lookup'],'REQUIRED'),
      ('Conversation/claim/commit',['messaging_claim_conversation_commit'],'REQUIRED'),
      ('Trigger/tenant/capability',['messaging_trigger_tenant_resolution','messaging_capability_resolution'],'REQUIRED'),
      ('SQL intent persistence',['messaging_sql_intent_persistence'],'REQUIRED'),
      ('Worker entry (includes spawn)',[],'ARCHITECTURAL / potentially AVOIDABLE'),
      ('Imports/configuration',['capability_imports','connector_configuration','duckdb_import'],'ARCHITECTURAL / potentially AVOIDABLE'),
      ('DuckDB connection',['duckdb_connect'],'ARCHITECTURAL'),
      ('Extension LOAD',['load_ducklake','load_postgres'],'ARCHITECTURAL / potentially AVOIDABLE'),
      ('Attachment + PostgreSQL catalog session',['attachment_open_including_catalog_session'],'ARCHITECTURAL / REQUIRED'),
      ('Query budget + readonly check',['query_budget_setup','read_only_verification'],'REQUIRED'),
      ('Foundation resolution/validation',['foundation_resolution'],'REQUIRED / ARCHITECTURAL'),
      ('Query preparation',['query_preparation'],'REQUIRED'),
      ('DuckDB execute (includes planning)',['duckdb_sql_execute'],'DATABASE / potentially AVOIDABLE cast work'),
      ('Fetch',['fetch'],'REQUIRED'),
      ('Materialization/hash',['materialization','result_hash'],'REQUIRED'),
      ('Attachment/connection close',['attachment_connection_close'],'REQUIRED / ARCHITECTURAL'),
      ('IPC/exit/decode residual',[],'ARCHITECTURAL / UNKNOWN internal split'),
      ('Formatting/result + outbound persistence',['messaging_formatting','messaging_sql_result_persistence','messaging_outbound_intent_persistence'],'REQUIRED / INSTRUMENTATION_ARTIFACT additional JSON'),
    ]
    values={name:[] for name,_,_ in groups}
    residual=[]
    totals=[]
    for r in local:
        s=labels(r['profile']);m=labels(r['messaging_profile']);merged=dict(s,**m)
        measured=0
        for name,keys,_ in groups:
            v=(r['profile']['parent']['worker_entry_ms'] if name.startswith('Worker entry') else
               r['profile']['parent']['ipc_exit_decode_residual_ms'] if name.startswith('IPC/') else
               sum(merged[k]['duration_ms'] for k in keys))
            values[name].append(v);measured+=v
        total=r['messaging_profile']['pre_send_ms'];totals.append(total)
        residual.append(total-measured)
    rows=[dict(component=name,metrics_ms=stats(values[name]),
       percent_pre_send=100*sum(values[name])/sum(totals),classification=classification)
       for name,_,classification in groups]
    rows.append(dict(component='Orchestration/unspanned paired residual',metrics_ms=stats(residual),
         percent_pre_send=100*sum(residual)/sum(totals),classification='UNKNOWN / INSTRUMENTATION_ARTIFACT'))
    derived['table']=rows
    derived['percent_method']='sum of component times / sum of pre_send times from SAME local samples; exclusive groups, no medians subtraction'
    derived['clock_alignment']='Linux perf_counter_ns across subprocesses; worker_entry anchors local elapsed spans; query lock/call micro-gap remains residual'
    save('analysis.json',derived)
    table='| Component | p50 ms | p95 ms | % pre-send | Classification |\n|---|---:|---:|---:|---|\n'
    for r in rows:
        table+=f"| {r['component']} | {r['metrics_ms']['p50']:.3f} | {r['metrics_ms']['p95']:.3f} | {r['percent_pre_send']:.2f} | {r['classification']} |\n"
    (OUT/'table.txt').write_text(table)


if __name__=='__main__':
    derive()
