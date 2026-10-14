from scripts.migrate_pdl1_st_labels_flat5 import convert_cell
import pytest

@pytest.mark.parametrize('old_id,name,new_id,new_name', [
 ('0','Negative Epithelial','0','Negative Tumor(Epithelial)'),
 ('1','Negative Lymphocyte','1','Negative Immune'),
 ('2','Negative Macrophage','1','Negative Immune'),
 ('3','Positive Epithelial','2','Positive Tumor(Epithelial)'),
 ('4','Positive Lymphocyte','3','Positive Immune'),
 ('5','Positive Macrophage','3','Positive Immune'),
 ('other','Other','4','Other'),
])
def test_conversion_preserves_geometry_and_is_idempotent(old_id,name,new_id,new_name):
 cell={'id':'cell1','class_id':old_id,'class_name':name,'x':1.2,'y':4.5,'bbox':{'x0':1,'y0':2},'coordinates':[[1,2],[3,4]],'source':'manual','confidence':0.42}
 converted=convert_cell(cell,True)
 assert converted=={**cell,'class_id':new_id,'class_name':new_name}
 assert convert_cell(converted,False)==converted
 assert cell['class_id']==old_id

def test_custom_class_preserved():
 cell={'class_id':'class_8','class_name':'Tumor','x':20}
 assert convert_cell(cell,True)==cell

def test_ambiguous_legacy_class_fails_instead_of_guessing():
 with pytest.raises(ValueError):
  convert_cell({'class_id':'2','class_name':'Unknown custom'},True)
