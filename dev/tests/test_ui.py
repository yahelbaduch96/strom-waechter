import sys
import os
import unittest
import pandas as pd
from datetime import datetime

# Ensure the test can find the strom_waechter module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ui import _format_discrete_hours, _generate_sparkline

class TestPresentationLayer(unittest.TestCase):
    
    # --- Tests for _format_discrete_hours (Chunking Logic) ---

    def test_format_discrete_empty_list(self):
        """Ensures an empty block list returns an empty string without crashing."""
        self.assertEqual(_format_discrete_hours([]), "")

    def test_format_discrete_single_hour(self):
        """Ensures a single hour is formatted just as a timestamp."""
        blocks = [{"start": datetime(2023, 1, 1, 4, 0), "end": datetime(2023, 1, 1, 5, 0)}]
        self.assertEqual(_format_discrete_hours(blocks), "04:00")

    def test_format_discrete_consecutive_hours(self):
        """Ensures fully consecutive hours are chunked into a continuous window."""
        blocks = [
            {"start": datetime(2023, 1, 1, 3, 0), "end": datetime(2023, 1, 1, 4, 0)},
            {"start": datetime(2023, 1, 1, 4, 0), "end": datetime(2023, 1, 1, 5, 0)},
            {"start": datetime(2023, 1, 1, 5, 0), "end": datetime(2023, 1, 1, 6, 0)}
        ]
        self.assertEqual(_format_discrete_hours(blocks), "03:00-06:00")

    def test_format_discrete_mixed_hours(self):
        """Ensures a mix of chunks and isolated hours are formatted correctly."""
        blocks = [
            {"start": datetime(2023, 1, 1, 3, 0), "end": datetime(2023, 1, 1, 4, 0)},
            {"start": datetime(2023, 1, 1, 4, 0), "end": datetime(2023, 1, 1, 5, 0)},
            {"start": datetime(2023, 1, 1, 12, 0), "end": datetime(2023, 1, 1, 13, 0)}
        ]
        self.assertEqual(_format_discrete_hours(blocks), "03:00-05:00, 12:00")

    # --- Tests for _generate_sparkline (Pre-attentive Visuals) ---

    def test_generate_sparkline_tagging(self):
        """Ensures optimal blocks are tagged green and peak blocks are tagged red."""
        # Build a simple dictionary of 24 hourly prices instead of a DataFrame
        prices = [0.10] * 24
        prices[18] = 0.50 # Artificial peak hour
        prices[4] = 0.05  # Artificial optimal hour
        
        hourly_prices = {i: prices[i] for i in range(24)}
        
        # Schedule the machine during the cheapest hour
        blocks = [{"start": datetime(2023, 1, 1, 4, 0), "end": datetime(2023, 1, 1, 5, 0)}]
        
        sparkline = _generate_sparkline(hourly_prices, blocks)
        
        # Assertions
        self.assertIn("[bold green]", sparkline, "Sparkline failed to highlight the target window in green.")
        self.assertIn("[bold red]", sparkline, "Sparkline failed to highlight the peak penalty hour in red.")
        self.assertIn("00    06    12    18    23", sparkline, "Sparkline axis is missing.")

if __name__ == '__main__':
    unittest.main()