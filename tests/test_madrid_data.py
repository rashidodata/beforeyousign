from madrid_data import parse_address, record_matches, safe_excerpt, query_source

def test_parse_address():
    assert parse_address('Calle de Cáceres 41, Madrid')==('CACERES','41')
    assert parse_address('Travesía de los Cabestreros, 5, Madrid')==('CABESTREROS','5')

def test_exact_number_no_false_positive():
    assert record_matches({'DIRECCION':'CACERES','No':'41','TIPO':'license'},'Calle Caceres 41, Madrid')
    assert not record_matches({'DIRECCION':'CACERES','No':'411'},'Calle Caceres 41, Madrid')
    assert not record_matches({'DIRECCION':'OTHER STREET','No':'41'},'Calle Caceres 41, Madrid')

def test_safe_pii_fields():
    assert safe_excerpt({'PERSONA_INTERESADA':'private person', 'No_EXPEDIENTE':'2025/12','DIRECCION':'CACERES'})=={'No_EXPEDIENTE':'2025/12','DIRECCION':'CACERES'}

class FakeResponse:
    def raise_for_status(self):pass
    def json(self):return {'success':True,'result':{'records':[{'DIRECCION':'CÁCERES','No':'41','TIPO':'A'}, {'DIRECCION':'CÁCERES','No':'42','TIPO':'B'}]}}
class FakeSession:
    def get(self,*args,**kwargs):return FakeResponse()

def test_query_source_with_fake_api():
    result=query_source('Calle Caceres 41, Madrid','fake',session=FakeSession())
    assert len(result)==1 and result[0]['TIPO']=='A'