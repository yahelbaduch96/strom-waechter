import pandas as pd
import json
import os

def generate_slp_weights():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    
    data_csv = os.path.join(project_root, "data", "baselines", "synthload2027", "synthload2027.csv")
    kat_csv = os.path.join(project_root, "data", "baselines", "synthload2027", "Kategorien.csv")
    output_json = os.path.join(project_root, "data", "baselines", "slp_weights.json")

    try:
        # 1. Process Weights (Added encoding='latin1')
        df = pd.read_csv(data_csv, sep=';', decimal=',', parse_dates=['Zeit'], encoding='latin1')
        df['Hour'] = df['Zeit'].dt.hour
        hourly_averages = df.groupby(['Typnummer', 'Hour'])['Wert'].mean().unstack(level=0)
        normalized_weights = hourly_averages.div(hourly_averages.sum(axis=0))
        weights_dict = {str(col): normalized_weights[col].tolist() for col in normalized_weights.columns}
        
        # 2. Process the Mapping (Added encoding='latin1')
        df_kat = pd.read_csv(kat_csv, sep=None, engine='python', encoding='latin1')
        
        mapping_dict = {}
        for _, row in df_kat.iterrows():
            # Save the Typtext (e.g., "bäckerei mit backstube") in lowercase for easy searching
            industry_name = str(row['Typtext']).lower()
            mapping_dict[industry_name] = str(row['Typnummer'])
            
        # 3. Combine into a single smart payload
        final_payload = {
            "mapping": mapping_dict,
            "weights": weights_dict
        }
            
        os.makedirs(os.path.dirname(output_json), exist_ok=True)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(final_payload, f, indent=2)
            
        print("✅ Successfully generated dynamic mapping and weights!")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    generate_slp_weights()