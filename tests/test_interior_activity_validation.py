import copy
import unittest

from tests.test_interiors import sample_plan
from worldseed.persistence.validation import validate_sim_state


class InteriorActivityValidationTests(unittest.TestCase):
    def fixture(self):
        plan=sample_plan()
        reservation={'target_uid':plan.furniture[0].uid,'metadata':{
            'space_id':plan.uid,'door_uid':plan.door_uid,
            'interior_use_x':plan.entry_x,'interior_use_y':plan.entry_y}}
        return {'interiors':{plan.uid:plan.to_dict()},'activity_reservations':{'work:test':reservation}}

    def test_valid_space_bound_reservation_verifies_and_invalid_links_are_rejected(self):
        raw=self.fixture()
        self.assertFalse(validate_sim_state(raw))
        for key,value,expected in (
            ('space_id','interior:missing','orphan interior activity space'),
            ('door_uid','door:wrong','invalid interior activity door binding'),
            ('interior_use_x',1.5,'invalid interior activity position'),
            ('interior_use_y',-1,'invalid interior activity position')):
            broken=copy.deepcopy(raw)
            broken['activity_reservations']['work:test']['metadata'][key]=value
            self.assertTrue(any(expected in issue for issue in validate_sim_state(broken)))
        raw['activity_reservations']['work:test']['target_uid']='fixture:missing'
        self.assertTrue(any('orphan interior activity fixture' in issue for issue in validate_sim_state(raw)))


if __name__=='__main__':unittest.main()
