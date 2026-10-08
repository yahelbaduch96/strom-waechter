import os
import json
import pandas as pd

def _get_project_root() -> str:
    """Dynamically resolves the absolute path to the project root directory."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(current_dir)

def load_apcs_weights(filepath: str = None) -> dict:
    """Loads the APCS standard load profile weights using dynamic path resolution."""
    if filepath is None:
        filepath = os.path.join(_get_project_root(), "data", "baselines", "slp_weights.json")

    if not os.path.exists(filepath):
        filepath = "data/baselines/slp_weights.json"
        
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Could not locate APCS weights at {filepath}")
        
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_prices(filepath: str) -> pd.DataFrame:
    """Loads day-ahead prices with dynamic path fallback."""
    if not os.path.exists(filepath):
        # Attempt to resolve from the project root if the relative path fails
        fallback_path = os.path.join(_get_project_root(), "data", "prices.json")
        
        if os.path.exists(fallback_path):
            filepath = fallback_path
        else:
            raise FileNotFoundError(f"Could not locate prices file at {filepath}")
            
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    df = pd.DataFrame(data)
    df['ts'] = pd.to_datetime(df['ts'])
    df['preis_eur_kwh'] = df['preis_eur_mwh'] / 1000
    df.set_index('ts', inplace=True)
    return df