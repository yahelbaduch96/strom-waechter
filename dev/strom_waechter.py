import os
import argparse
import json
import sys
import pandas as pd


def resolve_profile_path(profile_identifier: str) -> str:
    """Resolves the smart path for a profile identifier. Raises FileNotFoundError if missing."""
    profile_path = profile_identifier
    if os.path.exists(profile_path):
        return profile_path

    raw_input = profile_path.strip().lower()
    if raw_input.endswith('.json'):
        raw_input = raw_input[:-5]
        
    identifier = raw_input.replace("profile ", "").replace("profil ", "").replace("profile_", "").replace("profil_", "")
    filename = f"profil_{identifier}.json"
    
    smart_path = os.path.join("data", "examples", filename)
    dev_smart_path = os.path.join("..", "data", "examples", filename)
    
    if os.path.exists(smart_path):
        return smart_path
    elif os.path.exists(dev_smart_path):
        return dev_smart_path
    else:
        raise FileNotFoundError(f"Could not locate a profile matching '{profile_identifier}'.")

def load_profile(filepath: str) -> dict:
    """Loads the SME consumption profile. Raises FileNotFoundError or JSONDecodeError."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_prices(filepath: str) -> pd.DataFrame:
    """Loads day-ahead prices and converts to EUR/kWh. Raises FileNotFoundError or JSONDecodeError."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    df = pd.DataFrame(data)
    df['ts'] = pd.to_datetime(df['ts'])
    df['preis_eur_kwh'] = df['preis_eur_mwh'] / 1000
    df.set_index('ts', inplace=True)
    return df

def validate_profile_inputs(profile: dict):
    """Validates that the SME profile contains all required fields and correct data types."""
    required_string_keys = ["branche", "region", "bundesland", "_hinweis"]
    
    # 1. Check if all required keys exist
    required_keys = required_string_keys + ["flexibilitaet_stunden", "verschiebbare_last_kwh"]
    for key in required_keys:
        if key not in profile:
            raise KeyError(key)
            
    # 2. Check string types
    for key in required_string_keys:
        if not isinstance(profile[key], str):
            raise TypeError(f"Field '{key}' must be a string.")
            
    # 3. Check hours (must be int and > 0)
    flex_hours = profile["flexibilitaet_stunden"]
    if not isinstance(flex_hours, int):
        raise TypeError("Field 'flexibilitaet_stunden' must be an integer.")
    if flex_hours <= 0:
        raise ValueError(f"Invalid flexibility window: {flex_hours} hours. Must be greater than 0.")
        
    # 4. Check load (must be a number and >= 0)
    load_kwh = profile["verschiebbare_last_kwh"]
    if not isinstance(load_kwh, (int, float)):
        raise TypeError("Field 'verschiebbare_last_kwh' must be a number.")
    if load_kwh < 0:
        raise ValueError(f"Invalid load: {load_kwh} kWh. Must be a positive number.")

def find_optimal_window(df: pd.DataFrame, flex_hours: int, load_kwh: float) -> dict:
    """Calculates the cheapest continuous block using a forward-rolling window."""
    # Notice: Validation is removed from here! This is now pure math.
    
    indexer = pd.api.indexers.FixedForwardWindowIndexer(window_size=flex_hours)
    df['window_avg'] = df['preis_eur_kwh'].rolling(window=indexer, min_periods=flex_hours).mean()    
    df_valid = df.dropna(subset=['window_avg']).copy()
    
    if df_valid.empty:
        raise ValueError("The flexibility window is larger than the available dataset.")

    best_start_ts = df_valid['window_avg'].idxmin()
    best_avg_price = df_valid.loc[best_start_ts, 'window_avg']
    daily_avg_price = df['preis_eur_kwh'].mean()
    
    baseline_cost = load_kwh * daily_avg_price
    optimal_cost = load_kwh * best_avg_price
    savings_eur = baseline_cost - optimal_cost

    return {
        "start_ts": best_start_ts,
        "end_ts": best_start_ts + pd.Timedelta(hours=flex_hours),
        "optimal_avg_price": best_avg_price,
        "baseline_avg_price": daily_avg_price,
        "savings_eur": savings_eur,
        "savings_percent": (savings_eur / baseline_cost) * 100
    }

def execute_optimization_pipeline(profile_identifier: str, prices_path: str) -> dict:
    """Bridges I/O and domain logic, translating Python exceptions into API-friendly dict responses."""
    try:
        # 1. Resolve and Load Data
        profile_path = resolve_profile_path(profile_identifier)
        profile = load_profile(profile_path)
        df_prices = load_prices(prices_path)
        
        # 2. Validate the entire profile dictionary
        validate_profile_inputs(profile)

        # 3. If it passes, hand the raw numbers to the math engine
        result = find_optimal_window(
            df=df_prices,
            flex_hours=profile['flexibilitaet_stunden'],
            load_kwh=profile['verschiebbare_last_kwh']
        )
        
        return {
            "status": "success",
            "profile_name": os.path.basename(profile_path),
            "branche": profile.get('branche', 'Unknown'),
            "data": result
        }
        
    except FileNotFoundError as e:
        return {"status": "error", "type": "file_not_found", "message": str(e)}
    except json.JSONDecodeError as e:
        return {"status": "error", "type": "json_error", "message": f"Corrupted JSON file. Details: {e}"}
    except KeyError as e:
        return {"status": "error", "type": "schema_error", "message": f"Missing required field {e} in profile."}
    except (TypeError, ValueError) as e:
        return {"status": "error", "type": "constraint_error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "type": "unknown_error", "message": str(e)}

def main():
    parser = argparse.ArgumentParser(description="Strom-Wächter: Energy Optimization CLI")
    parser.add_argument('profile', type=str, help='Profile identifier (e.g., "1", "profile 1", or "profil_1.json")')
    parser.add_argument('--prices', type=str, default='data/prices.json', help='Path to prices.json')
    args = parser.parse_args()

    # Call the controller
    response = execute_optimization_pipeline(args.profile, args.prices)

    # Handle errors cleanly via UI
    if response["status"] == "error":
        print(f"\n❌ Error: {response['message']}")
        
        if response["type"] == "file_not_found":
            print("\n💡 Examples of how to use the tool:")
            print("  python dev/strom_waechter.py 1")
            print("  python dev/strom_waechter.py \"profile 1\"")
            print("  python dev/strom_waechter.py data/examples/profil_1.json\n")
        elif response["type"] == "constraint_error":
            print("Please check the constraints in your JSON profile.\n")
            
        sys.exit(1)

    # Handle Success cleanly via UI
    print(f"Loading data for {response['profile_name']}...")
    result = response["data"]
    
    print("\n--- STROM-WÄCHTER REPORT ---")
    print(f"Industry: {response['branche']}")
    print(f"Optimal Window: {result['start_ts'].strftime('%H:%M')} - {result['end_ts'].strftime('%H:%M')}")
    print(f"Avg Price in Window: {result['optimal_avg_price']:.4f} EUR/kWh")
    print(f"Baseline (Daily Average): {result['baseline_avg_price']:.4f} EUR/kWh")
    print(f"Estimated Savings: {result['savings_eur']:.2f} EUR ({result['savings_percent']:.1f}%)")


if __name__ == "__main__":
    main()