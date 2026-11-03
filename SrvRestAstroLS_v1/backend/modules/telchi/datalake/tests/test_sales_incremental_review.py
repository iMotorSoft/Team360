from modules.telchi.datalake.sales_incremental_review import compare_tables,business_checks


def test_amounts_normalized_but_native_codes_exact():
    old=[dict(doc_entry='1',card_code='001',doc_total='10.000',raw_extraction_id='old')]
    incoming=[dict(doc_entry='1',card_code='001',doc_total='10',raw_extraction_id='new')]
    assert compare_tables(incoming,old)['counts']['identical']==1
    incoming[0]['card_code']='1'
    assert compare_tables(incoming,old)['changed_fields']=={'card_code':1}


def test_whole_document_removed_added_changed_lines_and_cancellation():
    previous=[dict(doc_entry='1',line_num='0',quantity='1'),dict(doc_entry='1',line_num='1',quantity='2')]
    incoming=[dict(doc_entry='1',line_num='0',quantity='3'),dict(doc_entry='1',line_num='2',quantity='2')]
    assert compare_tables(incoming,previous,lines=True)['counts']==dict(new=1,modified=1,identical=0,removed=1)
    assert compare_tables([dict(doc_entry='1',canceled='Y')],[dict(doc_entry='1',canceled='N')])['changed_fields']=={'canceled':1}


def test_all_seven_business_questions_fail_closed_for_partial_unpublished_coverage():
    responses=business_checks('existing-current','2026-10-29')
    assert len(responses)==7
    assert all(r['status']=='BLOCKED_FOR_GENERAL_PERIOD_ANSWER' and r['candidate'] is None for r in responses)
    assert all(r['coverage']=='PARTIAL_SAMPLE_ONLY' and r['publication']=='existing-current' for r in responses)
