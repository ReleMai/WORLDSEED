from worldseed.ui.widgets import select_menu, view_text


class FeatureTerm:
    def __init__(self, keys):
        self.keys=list(keys)
        self.feature_menu_calls=[]
        self.feature_doc_calls=[]
    def size(self):
        return (100, 30)
    def read_key(self):
        return self.keys.pop(0) if self.keys else 'ESC'
    def present(self, text):
        self.last=text
    def present_feature_menu(self, presentation, title, rows, selected, **kwargs):
        self.feature_menu_calls.append((presentation,title,[r.key for r in rows],selected,kwargs.get('data',{})))
    def present_feature_document(self, presentation, title, lines, **kwargs):
        self.feature_doc_calls.append((presentation,title,list(lines),kwargs.get('data',{})))


def test_feature_menu_hook_receives_structured_data():
    term=FeatureTerm(['\r'])
    choice=select_menu(term,'INVENTORY // ITEMS',[('core:stone','Stone x2')],presentation='inventory_items',presentation_data={'items':{'core:stone':{'count':2}}})
    assert choice=='core:stone'
    assert term.feature_menu_calls
    kind,title,keys,selected,data=term.feature_menu_calls[0]
    assert kind=='inventory_items'
    assert keys==['core:stone']
    assert data['items']['core:stone']['count']==2


def test_feature_document_hook_receives_structured_data():
    term=FeatureTerm(['ESC'])
    view_text(term,'+-- TECH --+\n| known |\n+--------+',presentation='crafting_tree',presentation_data={'nodes':[{'id':'r1'}]})
    assert term.feature_doc_calls
    kind,title,lines,data=term.feature_doc_calls[0]
    assert kind=='crafting_tree'
    assert data['nodes'][0]['id']=='r1'
