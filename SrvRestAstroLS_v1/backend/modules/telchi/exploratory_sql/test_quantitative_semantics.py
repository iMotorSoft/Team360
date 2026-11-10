"""General intent/operation and scope regressions on executed controlled data."""
from decimal import Decimal

import duckdb
import pytest

from .test_authorized_foundation import setup
from .authorized_foundation import ResearchBinding, DiscoveredSource, SourcePolicy, AuthorizedFoundationExecutor
from .contracts import Column, ExploratoryQueryProposal
from .ask_verifier import AskRegistry
from .validator import validate


@pytest.fixture
def quantitative(setup, tmp_path):
    with duckdb.connect(str(tmp_path/'fixture.duckdb'), config={'threads':'1'}) as db:
        db.execute('CREATE TABLE docs(doc_entry VARCHAR, doc_date VARCHAR, currency VARCHAR, '
                   'branch VARCHAR, product VARCHAR, category VARCHAR, channel VARCHAR, doc_total DECIMAL(18,2))')
        db.execute("INSERT INTO docs VALUES ('1','2026-02-01','BS','North','P1','C','A',60),"
                   "('2','2026-02-01','BS','South','P2','C','B',40),"
                   "('3','2026-01-01','BS','North','P1','C','A',30),"
                   "('4','2026-01-01','USD','North','P1','C','A',90)")
        columns=tuple(Column(r[0],r[1]) for r in db.execute('DESCRIBE docs').fetchall())
    scope=setup.state[0]
    binding=ResearchBinding(resolve_scope=lambda:setup.state[0],scope=scope,
        publication='fixture_published',snapshot=7,
        sources=(DiscoveredSource('sales_document','telchi.main.docs',columns,()),),
        policies=(SourcePolicy('sales_document','existing.sales.read','org1','w1',None,True),),
        investigation_id='controlled-quantitative')
    def executor(context, **_):return AuthorizedFoundationExecutor(context,reader=setup.reader)
    registry=AskRegistry(binding.context,executor_factory=executor)
    def execute(expressions, where="currency='BS' AND doc_date='2026-02-01'"):
        p=ExploratoryQueryProposal('SELECT '+expressions+' FROM sales_document WHERE '+where,
            'controlled regression','controlled source evidence',('sales_document',),'aggregate','observed')
        decision,q=validate(p,binding.context);assert q is not None,decision
        with executor(binding.context) as ex:_,result=ex.execute(p,binding.context)
        assert result.status=='COMPLETED'
        manifest=registry.register(q,result,result.rows)
        return [dict(kind='executed_cell',result_id=manifest['result_id'],row_id=manifest['row_ids'][0],
                     column_id=c['column_id']) for c in manifest['columns']]
    try:yield registry,execute
    finally:registry.close();binding.close()


def calculation(op,a,b):return dict(kind='calculation',operation=op,dependencies=[a,b])


@pytest.mark.parametrize('question,expr,op,expected,label',[
    ('Participación de la sucursal Norte en ventas totales',
     "sum(CASE WHEN branch='North' THEN doc_total ELSE 0 END),sum(doc_total)",'share','60.00','Participación'),
    ('Variación de ventas entre febrero y enero',
     "sum(CASE WHEN doc_date='2026-02-01' THEN doc_total ELSE 0 END),sum(CASE WHEN doc_date='2026-01-01' THEN doc_total ELSE 0 END)",
     'percent_change','233.33','Variación porcentual'),
    ('Participación del producto P1 dentro de la categoría C',
     "sum(CASE WHEN product='P1' THEN doc_total ELSE 0 END),sum(doc_total)",'share','60.00','Participación'),
    ('Diferencia absoluta de facturación entre los canales A y B',
     "sum(CASE WHEN channel='A' THEN doc_total ELSE 0 END),sum(CASE WHEN channel='B' THEN doc_total ELSE 0 END)",
     'subtract','20.00','Diferencia'),
    ('Proporción entre los importes de los canales A y B',
     "sum(CASE WHEN channel='A' THEN doc_total ELSE 0 END),sum(CASE WHEN channel='B' THEN doc_total ELSE 0 END)",
     'ratio','1.5','Proporción'),
])
def test_business_operation_distinction(quantitative,question,expr,op,expected,label):
    registry,execute=quantitative
    where="currency='BS'" if op=='percent_change' else "currency='BS' AND doc_date='2026-02-01' AND category='C'"
    a,b=execute(expr,where)
    registry.question=question
    claim=calculation(op,a,b);check=registry.verify(claim)
    assert check['match'],check
    assert Decimal(check['value'])==Decimal(expected)
    assert registry.final_feedback([claim]) is None
    assert label in registry.render([check])
    if op=='share':
        wrong=registry.verify(calculation('percent_change',a,b))
        assert not wrong['match'] and wrong['reason']=='calculation_does_not_answer_requested_operation'


def test_simultaneous_share_and_variation_and_followup_without_sql(quantitative):
    registry,execute=quantitative
    a,total,prior=execute("sum(CASE WHEN doc_date='2026-02-01' AND branch='North' THEN doc_total ELSE 0 END),"
        "sum(CASE WHEN doc_date='2026-02-01' THEN doc_total ELSE 0 END),"
        "sum(CASE WHEN doc_date='2026-01-01' AND branch='North' THEN doc_total ELSE 0 END)","currency='BS'")
    registry.question='Participación de Norte y variación frente al período anterior'
    share=calculation('share',a,total);change=calculation('percent_change',a,prior)
    assert registry.final_feedback([share]) is not None
    assert registry.final_feedback([share,change]) is None
    assert all(registry.verify(c)['match'] for c in (share,change))
    entries=len(registry.entries)
    registry.question='Sobre los resultados anteriores, ahora la diferencia absoluta'
    diff=calculation('subtract',a,prior)
    assert registry.verify(diff)['value']=='30.00'
    assert registry.final_feedback([diff]) is None
    assert len(registry.entries)==entries  # No executor or SQL needed for arithmetic.


def test_denominator_period_currency_and_subset_fail_closed(quantitative):
    registry,execute=quantitative
    registry.question='Participación sobre el total'
    a,b=execute("sum(CASE WHEN branch='North' THEN doc_total ELSE 0 END),sum(CASE WHEN branch='South' THEN doc_total ELSE 0 END)")
    assert not registry.verify(calculation('share',a,b))['match']
    other=execute('sum(doc_total)',"currency='USD' AND doc_date='2026-01-01'")[0]
    assert registry.verify(calculation('share',a,other))['reason']=='calculation_units_or_currency_scope_mismatch'
    wrong_period=execute('sum(doc_total)',"currency='BS' AND doc_date='2026-01-01'")[0]
    assert registry.verify(calculation('share',a,wrong_period))['reason']=='share_requires_part_within_same_scoped_total'
    zero=execute("sum(CASE WHEN branch='absent' THEN doc_total ELSE 0 END)")[0]
    assert registry.verify(calculation('share',a,zero))['reason']=='nonzero_denominator_required'


@pytest.mark.parametrize('question,required',[
    ('Facturación de enero y febrero, mostrame los dos importes por separado',True),
    ('Dame el importe desglosado por mes',True),
    ('Compará mes a mes la facturación',True),
    ('Facturación total de enero y febrero',False),
])
def test_period_separation_is_read_from_the_request_shape(question,required):
    from .ask_verifier import AskRegistry
    intent=object.__new__(AskRegistry)
    intent.question=question
    assert intent.requires_period_separation() is required
    assert ('period_separation' in intent.requested_scope()) is required


def test_separated_period_amounts_need_one_executed_scope_each(quantitative):
    registry,execute=quantitative
    registry.question='Facturación de enero y febrero por separado'
    merged=execute('sum(doc_total)',"currency='BS'")[0]
    assert 'shown separately' in registry.final_feedback([merged])
    february=execute('sum(doc_total)',"currency='BS' AND doc_date='2026-02-01'")[0]
    assert 'shown separately' in registry.final_feedback([february])
    january=execute('sum(doc_total)',"currency='BS' AND doc_date='2026-01-01'")[0]
    # Same publication, distinct executed period scope: the request is covered.
    assert registry.final_feedback([february,january]) is None
