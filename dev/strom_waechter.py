import pandas as pd

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
    search_df = _filter_working_hours(df, working_hours, flex_hours)

    if is_continuous:
        scheduled_blocks, best_avg_price, legacy_start_ts, legacy_end_ts = _calculate_continuous_blocks(search_df, flex_hours)
    else:
        scheduled_blocks, best_avg_price, legacy_start_ts, legacy_end_ts = _calculate_discrete_blocks(search_df, flex_hours)

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
# LAYER 3: API CONTROLLER
# ==========================================
def _parse_working_hours(ui_working_hours: str, profile: dict) -> dict:
    """Merges working hours, prioritizing UI input over JSON profile."""
    working_hours = ui_working_hours or profile.get("working_hours")
    if working_hours:
        try:
            start, end = working_hours.split('-')
            return {"start": start.strip(), "end": end.strip()}
        except ValueError:
            raise ValueError("Invalid working-hours format. Use HH:MM-HH:MM")
    return None
    
def _resolve_apcs_weights(ui_baseline: str, profile: dict, apcs_data: dict) -> list:
    """Dynamically determines APCS weights by mapping the profile industry to the Kategorien data."""
    baseline_type = ui_baseline or profile.get("default_baseline", "average")
    
    if baseline_type.lower() == "apcs" and apcs_data:
        branche = profile.get('branche', '').lower()
        mapping = apcs_data.get("mapping", {})
        weights = apcs_data.get("weights", {})
        
        for kat_name, typnummer in mapping.items():
            if branche in kat_name or kat_name in branche:
                return weights.get(typnummer)
        
        fallback_code = mapping.get("gewerbe allgemein")
        if fallback_code:
            return weights.get(fallback_code)
            
        if weights:
            return next(iter(weights.values()))
            
    return None
        
def run_optimization(
    profile: dict, 
    df_prices: pd.DataFrame,
    apcs_data: dict = None,
    ui_working_hours: str = None,
    ui_discrete: bool = False,
    ui_baseline: str = None
) -> dict:
    """Core orchestrator processing in-memory data for the frontend."""
    try:
        # 1. Validate Schema
        validate_profile_inputs(profile)

        # 2. Merge Configurations
        working_hours = _parse_working_hours(ui_working_hours, profile)
        is_continuous = False if ui_discrete else profile.get("continuous_process", True)
        apcs_weights = _resolve_apcs_weights(ui_baseline, profile, apcs_data)

        # 3. Execute Core Math Engine
        result = find_optimal_window(
            df=df_prices,
            flex_hours=profile['flexibilitaet_stunden'],
            load_kwh=profile['verschiebbare_last_kwh'],
            working_hours=working_hours,
            is_continuous=is_continuous,
            apcs_weights=apcs_weights
        )

        hourly_prices_dict = df_prices['preis_eur_kwh'].groupby(df_prices.index.hour).mean().to_dict()

        # 4. Return Unified Payload
        return {
            "status": "success",
            "branche": profile.get('branche', 'Unknown'),
            "data": result,
            "mode": "Continuous" if is_continuous else "Discrete",
            "baseline_used": "APCS" if apcs_weights else "Daily Average",
            "raw_df": hourly_prices_dict,
            "working_hours": working_hours
        }
        
    # 5. Error Handling
    except KeyError as e:
        return {"status": "error", "type": "schema_error", "message": f"Missing required field {e} in profile."}
    except (TypeError, ValueError) as e:
        return {"status": "error", "type": "constraint_error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "type": "unknown_error", "message": str(e)}