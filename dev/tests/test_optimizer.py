import unittest
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from strom_waechter import find_optimal_window, validate_profile_inputs

class TestValidation(unittest.TestCase):
    """Tests strictly for the full JSON schema validation logic."""
    
    def setUp(self):
        # A perfectly valid profile based on the official documentation
        self.valid_profile = {
            "branche": "Druckerei",
            "verschiebbare_last_kwh": 150,
            "flexibilitaet_stunden": 2,
            "region": "Wien",
            "bundesland": "Wien",
            "_hinweis": "synthetisch"
        }

    def test_missing_required_keys(self):
        """Test if missing keys like 'branche' raise a KeyError."""
        invalid_profile = self.valid_profile.copy()
        del invalid_profile["branche"]
        
        with self.assertRaises(KeyError):
            validate_profile_inputs(invalid_profile)

    def test_invalid_string_types(self):
        """Test if 'branche', 'region', 'bundesland', and '_hinweis' strictly require strings."""
        string_fields = ["branche", "region", "bundesland", "_hinweis"]
        
        for field in string_fields:
            invalid_profile = self.valid_profile.copy()
            invalid_profile[field] = 123  # Injecting an integer instead of a string
            
            with self.assertRaises(TypeError) as context:
                validate_profile_inputs(invalid_profile)
            self.assertTrue("must be a string" in str(context.exception).lower(), f"Failed on field: {field}")

    def test_invalid_type_flex_hours(self):
        invalid_profile = self.valid_profile.copy()
        invalid_profile["flexibilitaet_stunden"] = "2" # String instead of int
        with self.assertRaises(TypeError) as context:
            validate_profile_inputs(invalid_profile)
        self.assertTrue("must be an integer" in str(context.exception).lower())

    def test_zero_hour_flexibility(self):
        invalid_profile = self.valid_profile.copy()
        invalid_profile["flexibilitaet_stunden"] = 0
        with self.assertRaises(ValueError) as context:
            validate_profile_inputs(invalid_profile)
        self.assertTrue("must be greater than 0" in str(context.exception).lower())

    def test_invalid_type_load(self):
        invalid_profile = self.valid_profile.copy()
        invalid_profile["verschiebbare_last_kwh"] = "150" # String instead of number
        with self.assertRaises(TypeError) as context:
            validate_profile_inputs(invalid_profile)
        self.assertTrue("must be a number" in str(context.exception).lower())

    def test_negative_load(self):
        invalid_profile = self.valid_profile.copy()
        invalid_profile["verschiebbare_last_kwh"] = -50.0
        with self.assertRaises(ValueError) as context:
            validate_profile_inputs(invalid_profile)
        self.assertTrue("must be a positive number" in str(context.exception).lower())


class TestOptimizer(unittest.TestCase):
    """Tests strictly for the Pandas rolling math."""
    
    def setUp(self):
        data = {
            'ts': pd.date_range(start='2026-06-08T00:00:00', periods=5, freq='h'),
            'preis_eur_kwh': [10.0, 5.0, 2.0, 3.0, 8.0]
        }
        self.df = pd.DataFrame(data).set_index('ts')

    def test_standard_rolling_window(self):
        # Note: Because find_optimal_window calls validate_profile_inputs internally, 
        # we now need to mock validate_profile_inputs or skip it for pure math tests.
        # But for now, we will see how it fails!
        result = find_optimal_window(self.df, flex_hours=2, load_kwh=10.0)
        self.assertEqual(result['optimal_avg_price'], 2.5)
        self.assertEqual(result['start_ts'], pd.to_datetime('2026-06-08T02:00:00'))

    def test_window_larger_than_data(self):
        with self.assertRaises(ValueError) as context:
            find_optimal_window(self.df, flex_hours=10, load_kwh=10.0)
        self.assertTrue("larger than the available dataset" in str(context.exception))

if __name__ == '__main__':
    unittest.main()