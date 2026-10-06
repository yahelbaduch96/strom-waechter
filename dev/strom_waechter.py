import os
import argparse
import sys
import json
import pandas as pd

from ui import _print_report


# ==========================================
# LAYER 1: DATA INGESTION
# ==========================================
def _get_project_root() -> str:
    """Dynamically resolves the absolute path to the project root directory."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(current_dir)

def resolve_profile_path(profile_identifier: str) -> str:
    """Resolves the smart path for a profile identifier using dynamic pathing. Raises FileNotFoundError."""
    if os.path.exists(profile_identifier):
        return profile_identifier

    raw_input = profile_identifier.strip().lower()
    if raw_input.endswith('.json'):
        raw_input = raw_input[:-5]
        
    identifier = raw_input.replace("profile ", "").replace("profil ", "").replace("profile_", "").replace("profil_", "")
    filename = f"profil_{identifier}.json"
    
    # Use the centralized path helper
    smart_path = os.path.join(_get_project_root(), "data", "examples", filename)
    
    # Fallback for simple testing environments
    if not os.path.exists(smart_path):
        smart_path = os.path.join("data", "examples", filename)
        
    if os.path.exists(smart_path):
        return smart_path
    raise FileNotFoundError(f"Could not locate a profile matching '{profile_identifier}'.")

def load_profile(filepath: str) -> dict:
    """Loads the SME consumption profile. Raises FileNotFoundError or JSONDecodeError."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

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


# ==========================================
# LAYER 2: DOMAIN LOGIC (CORE ENGINE)
# ==========================================
def validate_profile_inputs(profile: dict):
    """Validates that the SME profile contains all required fields and correct data types."""
    required_string_keys = ["branche", "region", "bundesland", "_hinweis"]
    
    required_keys = required_string_keys + ["flexibilitaet_stunden", "verschiebbare_last_kwh"]
    for key in required_keys:
        if key not in profile:
            raise KeyError(key)
            
    for key in required_string_keys:
        if not isinstance(profile[key], str):
            raise TypeError(f"Field '{key}' must be a string.")
            
    flex_hours = profile["flexibilitaet_stunden"]
    if not isinstance(flex_hours, int):
        raise TypeError("Field 'flexibilitaet_stunden' must be an integer.")
    if flex_hours <= 0:
        raise ValueError(f"Invalid flexibility window: {flex_hours} hours. Must be greater than 0.")
        
    load_kwh = profile["verschiebbare_last_kwh"]
    if not isinstance(load_kwh, (int, float)):
        raise TypeError("Field 'verschiebbare_last_kwh' must be a number.")
    if load_kwh < 0:
        raise ValueError(f"Invalid load: {load_kwh} kWh. Must be a positive number.")

def _filter_working_hours(df: pd.DataFrame, working_hours: dict, flex_hours: int) -> pd.DataFrame:
    """Filters the DataFrame to only include rows within the specified shift."""
    if not working_hours:
        return df.copy()
        
    search_df = df.copy()
    start_time = pd.to_datetime(working_hours['start']).time()
    end_time = pd.to_datetime(working_hours['end']).time()
    
    if start_time < end_time:
        search_df = search_df[(search_df.index.time >= start_time) & (search_df.index.time < end_time)]
    else:
        search_df = search_df[(search_df.index.time >= start_time) | (search_df.index.time < end_time)]
        
    if len(search_df) < flex_hours:
        raise ValueError(f"Available operating hours ({len(search_df)}h) cannot fit a {flex_hours}h block.")
        
    return search_df

def _calculate_continuous_blocks(search_df: pd.DataFrame, flex_hours: int) -> tuple:
    """Finds the single cheapest contiguous block of time using a rolling window."""
    indexer = pd.api.indexers.FixedForwardWindowIndexer(window_size=flex_hours)
    search_df['window_avg'] = search_df['preis_eur_kwh'].rolling(window=indexer, min_periods=flex_hours).mean()    
    df_valid = search_df.dropna(subset=['window_avg'])
    
    if df_valid.empty:
        raise ValueError("The flexibility window is larger than the available dataset.")
        
    best_start_ts = df_valid['window_avg'].idxmin()
    best_avg_price = df_valid.loc[best_start_ts, 'window_avg']
    legacy_end_ts = best_start_ts + pd.Timedelta(hours=flex_hours)
    
    scheduled_blocks = [{"start": best_start_ts, "end": legacy_end_ts}]
    return scheduled_blocks, best_avg_price, best_start_ts, legacy_end_ts

def _calculate_discrete_blocks(search_df: pd.DataFrame, flex_hours: int) -> tuple:
    """Finds the cheapest isolated hours and returns them as individual blocks."""
    cheapest_hours = search_df['preis_eur_kwh'].nsmallest(flex_hours)
    best_avg_price = cheapest_hours.mean()
    
    scheduled_blocks = []
    for ts in cheapest_hours.index.sort_values():
        scheduled_blocks.append({"start": ts, "end": ts + pd.Timedelta(hours=1)})
        
    return scheduled_blocks, best_avg_price, None, None

def _calculate_baseline(df: pd.DataFrame, apcs_weights: list = None) -> float:
    """Calculates the baseline average price, using APCS weights if provided."""
    if apcs_weights and len(apcs_weights) == 24:
        hourly_weights = df.index.hour.map(lambda h: apcs_weights[h])
        return (df['preis_eur_kwh'] * hourly_weights).sum()
    
    return df['preis_eur_kwh'].mean()

# --- MAIN ENGINE ENTRY POINT ---
def find_optimal_window(df: pd.DataFrame, flex_hours: int, load_kwh: float, working_hours: dict = None, is_continuous: bool = True, apcs_weights: list = None) -> dict:
    """Calculates the cheapest operating blocks based on process constraints."""
    
    # 1. Time Slicing
    search_df = _filter_working_hours(df, working_hours, flex_hours)

    # 2. Mathematical Fork
    if is_continuous:
        scheduled_blocks, best_avg_price, legacy_start_ts, legacy_end_ts = _calculate_continuous_blocks(search_df, flex_hours)
    else:
        scheduled_blocks, best_avg_price, legacy_start_ts, legacy_end_ts = _calculate_discrete_blocks(search_df, flex_hours)

    # 3. Baseline & Savings Calculation
    daily_avg_price = _calculate_baseline(df, apcs_weights)
    
    baseline_cost = load_kwh * daily_avg_price
    optimal_cost = load_kwh * best_avg_price
    savings_eur = baseline_cost - optimal_cost

    return {
        "start_ts": legacy_start_ts,
        "end_ts": legacy_end_ts,
        "scheduled_blocks": scheduled_blocks,
        "optimal_avg_price": best_avg_price,
        "baseline_avg_price": daily_avg_price,
        "savings_eur": savings_eur,
        "savings_percent": (savings_eur / baseline_cost) * 100
    }


# ==========================================
# LAYER 3: CONTROLLER (ORCHESTRATOR)
# ==========================================
def _parse_working_hours(cli_working_hours: str, profile: dict) -> dict:
    """Merges working hours, prioritizing CLI input over JSON profile."""
    if cli_working_hours:
        try:
            start, end = cli_working_hours.split('-')
            return {"start": start.strip(), "end": end.strip()}
        except ValueError:
            raise ValueError("Invalid --working-hours format. Use HH:MM-HH:MM")
    return profile.get("working_hours")

def _resolve_apcs_weights(cli_baseline: str, profile: dict) -> list:
    """Dynamically determines APCS weights by mapping the profile industry to the Kategorien data."""
    baseline_type = cli_baseline or profile.get("baseline", "average")
    
    if baseline_type.lower() == "apcs":
        apcs_data = load_apcs_weights()
        branche = profile.get('branche', '').lower()
        
        mapping = apcs_data.get("mapping", {})
        weights = apcs_data.get("weights", {})
        
        # 1. Search the dynamic map for a direct match
        for kat_name, typnummer in mapping.items():
            if branche in kat_name or kat_name in branche:
                return weights.get(typnummer)
        
        # 2. Dynamic Fallback: Look up the General Commercial profile by name
        fallback_code = mapping.get("gewerbe allgemein")
        if fallback_code:
            return weights.get(fallback_code)
            
        # 3. Absolute Last Resort: Safely return the first available weight vector
        if weights:
            return next(iter(weights.values()))
            
    return None
        
def execute_optimization_pipeline(
    profile_identifier: str, 
    prices_path: str,
    cli_working_hours: str = None,
    cli_discrete: bool = False,
    cli_baseline: str = None
) -> dict:
    """Bridges I/O and domain logic, translating Python exceptions into API-friendly dict responses."""
    try:
        # 1. Load Data
        profile_path = resolve_profile_path(profile_identifier)
        profile = load_profile(profile_path)
        df_prices = load_prices(prices_path)
        
        # 2. Validate Schema
        validate_profile_inputs(profile)

        # 3. Merge Configurations
        working_hours = _parse_working_hours(cli_working_hours, profile)
        is_continuous = False if cli_discrete else profile.get("continuous_process", True)
        apcs_weights = _resolve_apcs_weights(cli_baseline, profile)

        # 4. Execute Core Math Engine
        result = find_optimal_window(
            df=df_prices,
            flex_hours=profile['flexibilitaet_stunden'],
            load_kwh=profile['verschiebbare_last_kwh'],
            working_hours=working_hours,
            is_continuous=is_continuous,
            apcs_weights=apcs_weights
        )
        
        # 5. Return Unified Payload
        return {
            "status": "success",
            "profile_name": os.path.basename(profile_path),
            "branche": profile.get('branche', 'Unknown'),
            "data": result,
            "mode": "Continuous" if is_continuous else "Discrete",
            "baseline_used": "APCS" if apcs_weights else "Daily Average",
            "raw_df": df_prices
        }
        
    # 6. Error Handling
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
    parser.add_argument('profile', type=str, help='Profile identifier (e.g., "1", "profile 1")')
    parser.add_argument('--prices', type=str, default='data/prices.json', help='Path to prices.json')
    parser.add_argument('--working-hours', type=str, help='Override shift constraints (e.g., "08:00-16:00")')
    parser.add_argument('--discrete', action='store_true', help='Find cheapest non-continuous hours')
    parser.add_argument('--baseline', type=str, choices=['average', 'apcs'], help='Select baseline calculation method')
    
    args = parser.parse_args()

    response = execute_optimization_pipeline(
        args.profile, args.prices, 
        cli_working_hours=args.working_hours, 
        cli_discrete=args.discrete, 
        cli_baseline=args.baseline
    )

    if response["status"] == "error":
        print(f"\n❌ Error: {response['message']}\n")
        sys.exit(1)

    _print_report(response)

if __name__ == "__main__":
    main()