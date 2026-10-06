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


class TestWorkingHours(unittest.TestCase):
    """Tests strictly for the IoT vs Human Shift constraints."""
    
    def setUp(self):
        # Mock a full 24-hour day with a default price of 10.0
        self.df = pd.DataFrame({
            'ts': pd.date_range(start='2026-06-08T00:00:00', periods=24, freq='h'),
            'preis_eur_kwh': [10.0] * 24
        }).set_index('ts')
        
        # 1. IoT Minimum (Outside shift) -> Absolute cheapest (1.0 EUR) at 02:00 - 04:00
        self.df.loc['2026-06-08 02:00:00', 'preis_eur_kwh'] = 1.0
        self.df.loc['2026-06-08 03:00:00', 'preis_eur_kwh'] = 1.0
        
        # 2. Human Shift Minimum -> Cheapest inside shift (5.0 EUR) at 10:00 - 12:00
        self.df.loc['2026-06-08 10:00:00', 'preis_eur_kwh'] = 5.0
        self.df.loc['2026-06-08 11:00:00', 'preis_eur_kwh'] = 5.0

    def test_daytime_working_hours(self):
        """Test that the optimizer ignores cheaper nighttime hours if a shift is provided."""
        working_hours = {"start": "08:00", "end": "16:00"}
        
        # Pass the new parameter to the engine
        result = find_optimal_window(
            self.df, 
            flex_hours=2, 
            load_kwh=10.0,
            working_hours=working_hours 
        )
        
        # The engine must pick 10:00 AM (5.0 EUR), NOT 02:00 AM (1.0 EUR)
        expected_start = pd.to_datetime('2026-06-08T10:00:00')
        self.assertEqual(result['start_ts'], expected_start)
        self.assertEqual(result['optimal_avg_price'], 5.0)

    def test_overnight_working_hours(self):
        """Test that the optimizer handles shifts crossing midnight (e.g., 22:00-06:00)."""
        working_hours = {"start": "22:00", "end": "06:00"}
        
        # The 02:00-04:00 block (1.0 EUR) is inside this overnight shift.
        result = find_optimal_window(
            self.df, 
            flex_hours=2, 
            load_kwh=10.0,
            working_hours=working_hours 
        )
        
        expected_start = pd.to_datetime('2026-06-08T02:00:00')
        self.assertEqual(result['start_ts'], expected_start)
        self.assertEqual(result['optimal_avg_price'], 1.0)


class TestDiscreteOutputs(unittest.TestCase):
    """Tests for discrete (non-continuous) processing mode."""
    
    def setUp(self):
        self.df = pd.DataFrame({
            'ts': pd.date_range(start='2026-06-08T00:00:00', periods=24, freq='h'),
            'preis_eur_kwh': [10.0] * 24
        }).set_index('ts')
        
        # Two very cheap hours, completely separated
        self.df.loc['2026-06-08 02:00:00', 'preis_eur_kwh'] = 1.0
        self.df.loc['2026-06-08 14:00:00', 'preis_eur_kwh'] = 2.0

    def test_discrete_process_selection(self):
        """Test that discrete mode picks the cheapest isolated hours."""
        
        # Notice the new flag: is_continuous=False
        result = find_optimal_window(
            self.df, 
            flex_hours=2, 
            load_kwh=10.0,
            is_continuous=False
        )
        
        # We expect a new 'scheduled_blocks' list in the output
        self.assertIn('scheduled_blocks', result)
        blocks = result['scheduled_blocks']
        
        self.assertEqual(len(blocks), 2)
        
        # The engine should find 02:00 and 14:00, order doesn't strictly matter
        # but we expect it to be sorted by time
        start_times = [block['start'] for block in blocks]
        self.assertIn('2026-06-08 02:00:00', str(start_times[0]))
        self.assertIn('2026-06-08 14:00:00', str(start_times[1]))
        
        # Average price should be (1.0 + 2.0) / 2 = 1.5
        self.assertEqual(result['optimal_avg_price'], 1.5)


class TestAPCSBaselines(unittest.TestCase):
    """Tests strictly for weighted baseline calculations."""
    
    def setUp(self):
        self.df = pd.DataFrame({
            'ts': pd.date_range(start='2026-06-08T00:00:00', periods=24, freq='h'),
            'preis_eur_kwh': [10.0] * 24
        }).set_index('ts')
        
        # Make the early morning (02:00 - 05:00) very expensive: 50 EUR/kWh
        for i in range(2, 6):
            self.df.iloc[i, 0] = 50.0

    def test_weighted_baseline_calculation(self):
        """Test that the APCS weights correctly inflate the baseline for a bakery."""
        
        # 1. Calculate what the simple average baseline would be
        # 20 hours at 10.0 + 4 hours at 50.0 = 400.0 / 24 = 16.66 EUR/kWh
        simple_avg_price = self.df['preis_eur_kwh'].mean()
        
        # 2. Provide the G5 Bakery weights
        g5_weights = [
            0.034, 0.034, 0.080, 0.080, 0.080, 0.080, 0.034, 0.034,
            0.034, 0.034, 0.034, 0.034, 0.034, 0.034, 0.034, 0.034,
            0.034, 0.034, 0.034, 0.034, 0.034, 0.034, 0.034, 0.034
        ]
        
        result = find_optimal_window(
            self.df, 
            flex_hours=2, 
            load_kwh=10.0,
            apcs_weights=g5_weights  # NEW ARGUMENT
        )
        
        # The weighted baseline should be significantly higher than 16.66 
        # because the G5 profile concentrates 32% of its load during the 50 EUR peak hours.
        # Math: (20 * 10.0 * 0.034) + (4 * 50.0 * 0.08) = 6.8 + 16.0 = 22.8 EUR/kWh
        self.assertAlmostEqual(result['baseline_avg_price'], 22.8, places=2)
        self.assertGreater(result['baseline_avg_price'], simple_avg_price)

if __name__ == '__main__':
    unittest.main()