import unittest

from tools.bootstrap_smoke import run_bootstrap


class RC7BootstrapTests(unittest.TestCase):
    def test_zero_supply_bootstrap_reaches_food_and_fire(self):
        row = run_bootstrap('rc7-release-bootstrap')
        self.assertTrue(row['empty_start'])
        self.assertTrue(row['campfire'])
        self.assertGreater(row['wood'], 0)
        self.assertGreater(row['hide'], 0)
        self.assertGreater(row['bone'], 0)
        self.assertGreater(row['diet_events'], 0)


if __name__ == '__main__':
    unittest.main()
