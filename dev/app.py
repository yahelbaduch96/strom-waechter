import streamlit as st
import json
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, time
import re

# --- CUSTOM MODULES ---
from data_loader import load_prices, load_apcs_weights
from strom_waechter import run_optimization

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Strom-Wächter", layout="wide")

# --- INITIALIZE SESSION STATE ---
if 'app_stage' not in st.session_state:
    st.session_state['app_stage'] = 'start'
if 'active_profile' not in st.session_state:
    st.session_state['active_profile'] = None

# --- HELPER FUNCTIONS ---
@st.cache_data
def get_backend_data():
    try:
        prices = load_prices("data/prices.json")
        weights = load_apcs_weights()
        return prices, weights
    except Exception as e:
        st.error(f"Failed to load backend datasets: {e}")
        return None, None

df_prices, apcs_data = get_backend_data()

# --- MAIN LAYOUT LOGIC ---
st.title("Strom-Wächter Optimizer")

# ==========================================
# STAGE 1: START PAGE
# ==========================================
if st.session_state['app_stage'] == 'start':
    st.markdown("""
    ### Welcome to the Industrial Energy Optimizer
    
    Strom-Wächter helps your business effortlessly cut energy costs. It checks daily electricity prices and automatically finds the cheapest times to run your high-energy machinery. 
    
    Whether your equipment needs to run continuously in one go (like an industrial oven) or can be paused and restarted throughout the day (like a water pump), this tool builds a schedule that fits perfectly within your staff's actual working hours.
    """)
    st.divider()
    
    # Added type="primary" so it picks up the green theme
    if st.button("Start Optimization", type="primary", use_container_width=True):
        st.session_state['app_stage'] = 'setup'
        st.rerun()

# ==========================================
# STAGE 2: PROFILE SETUP
# ==========================================
elif st.session_state['app_stage'] == 'setup':
    st.markdown("#### Step 1: Define Machine Parameters")
    tab1, tab2 = st.tabs(["Create Profile", "Upload Saved File"])

    with tab1:
        if apcs_data and "mapping" in apcs_data:
            industry_keys = list(apcs_data["mapping"].keys())
            industry_options = [k.title() for k in industry_keys]
            default_idx = industry_options.index("Gewerbe Allgemein") if "Gewerbe Allgemein" in industry_options else 0
        else:
            industry_options = ["Gewerbe Allgemein", "Bäckerei", "Metallverarbeitung"]
            default_idx = 0
            
        c1, c2, c3 = st.columns(3)
        with c1:
            gen_branche = st.selectbox("Industry", options=industry_options, index=default_idx, help="Choose your industry so we can estimate a standard energy usage pattern for comparison.")
            gen_load = st.number_input("Total Energy Needed (kWh)", min_value=1.0, value=150.0, step=10.0, help="How much total energy this machine will use during this job.")
            gen_region = st.selectbox("Region", options=["AT", "DE"], help="The country where your business is located.")
            gen_bundesland = st.text_input("State", value="Wien", help="Your specific state or province.")
        with c2:
            gen_window = st.slider("Running Time (Hours)", 1, 24, 5, help="How many hours the machine needs to run to finish its task.")
            
            use_wh = st.checkbox("Limit Working Hours", help="Check this if the machine can only run while staff are present.")
            if use_wh:
                wh_col1, wh_col2 = st.columns(2)
                start_time = wh_col1.time_input("Start Time", value=time(8, 0))
                end_time = wh_col2.time_input("End Time", value=time(16, 0))
                gen_working_hours = f"{start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}"
            else:
                gen_working_hours = None

        with c3:
            gen_mode = st.radio("Operation Type", ["Continuous", "Discrete"], help="Choose 'Continuous' if the machine cannot be stopped once started. Choose 'Discrete' if it can be paused and restarted later.")
            gen_baseline = st.selectbox("Standard Comparison", ["Average", "Industry Standard"], help="How we calculate your standard costs: 'Average' uses a flat daily rate, while 'Industry Standard' looks at typical usage patterns for your sector.")
            
        if st.button("Proceed to Results", type="primary", use_container_width=True):
            st.session_state['active_profile'] = {
                "branche": gen_branche.lower(),
                "region": gen_region,
                "bundesland": gen_bundesland,
                "flexibilitaet_stunden": gen_window,
                "verschiebbare_last_kwh": gen_load,
                "continuous_process": gen_mode == "Continuous",
                "working_hours": gen_working_hours,
                "default_baseline": "apcs" if gen_baseline == "Industry Standard" else "average",
                "_hinweis": "Generated via Web UI."
            }
            st.session_state['app_stage'] = 'results'
            st.rerun()

    with tab2:
        uploaded_file = st.file_uploader("Upload an existing machine configuration file", type=["json"], help="Upload a file you previously exported from this tool.")
        if uploaded_file is not None:
            try:
                temp_profile = json.load(uploaded_file)
                st.success("File loaded successfully. You can now view the results.")
                if st.button("Proceed to Results", key="proceed_json", type="primary", use_container_width=True):
                    st.session_state['active_profile'] = temp_profile
                    st.session_state['app_stage'] = 'results'
                    st.rerun()
            except Exception:
                st.error("We couldn't read this file. Please make sure it is a valid configuration file.")

# ==========================================
# STAGE 3: DASHBOARD & RESULTS
# ==========================================
elif st.session_state['app_stage'] == 'results':
    profile = st.session_state['active_profile']
    
    # --- SIDEBAR CONTROLS ---
    st.sidebar.header("Adjust Settings")
    curr_branche = profile.get("branche", "gewerbe allgemein").title()
    curr_load = float(profile.get("verschiebbare_last_kwh", 150.0))
    curr_window = int(profile.get("flexibilitaet_stunden", 5))
    curr_mode = "Continuous" if profile.get("continuous_process", True) else "Discrete"
    
    raw_base = profile.get("default_baseline", "average").lower()
    curr_baseline = "Industry Standard" if raw_base == "apcs" else "Average"
    
    curr_wh = profile.get("working_hours")

    if apcs_data and "mapping" in apcs_data:
        sidebar_industry_options = [k.title() for k in apcs_data["mapping"].keys()]
    else:
        sidebar_industry_options = ["Gewerbe Allgemein", "Bäckerei", "Metallverarbeitung"]
    if curr_branche not in sidebar_industry_options:
        sidebar_industry_options.append(curr_branche)

    new_branche = st.sidebar.selectbox("Industry", sidebar_industry_options, index=sidebar_industry_options.index(curr_branche), key="sb_ind")
    new_load = st.sidebar.number_input("Total Energy Needed (kWh)", min_value=1.0, value=curr_load, step=10.0, key="sb_load")
    new_window = st.sidebar.slider("Running Time (Hours)", 1, 24, curr_window, key="sb_win")
    
    # --- SIDEBAR WORKING HOURS ---
    default_start, default_end = time(8, 0), time(16, 0)
    if curr_wh:
        try:
            s, e = curr_wh.split('-')
            default_start = datetime.strptime(s.strip(), "%H:%M").time()
            default_end = datetime.strptime(e.strip(), "%H:%M").time()
        except ValueError:
            pass

    use_wh_sidebar = st.sidebar.checkbox("Limit Working Hours", value=bool(curr_wh), key="sb_use_wh")
    if use_wh_sidebar:
        new_start = st.sidebar.time_input("Start Time", value=default_start, key="sb_start")
        new_end = st.sidebar.time_input("End Time", value=default_end, key="sb_end")
        new_wh = f"{new_start.strftime('%H:%M')}-{new_end.strftime('%H:%M')}"
    else:
        new_wh = None

    new_mode = st.sidebar.radio("Operation Type", ["Continuous", "Discrete"], index=0 if curr_mode=="Continuous" else 1, key="sb_mode")
    new_baseline = st.sidebar.selectbox("Standard Comparison", ["Average", "Industry Standard"], index=0 if curr_baseline=="Average" else 1, key="sb_base")
    
    st.sidebar.divider()
    if st.sidebar.button("Start Over", type="primary", use_container_width=True):
        st.session_state['app_stage'] = 'setup'
        st.rerun()

    profile["branche"] = new_branche.lower()
    profile["verschiebbare_last_kwh"] = new_load
    profile["flexibilitaet_stunden"] = new_window
    profile["continuous_process"] = (new_mode == "Continuous")
    profile["default_baseline"] = "apcs" if new_baseline == "Industry Standard" else "average"
    profile["working_hours"] = new_wh
    st.session_state['active_profile'] = profile

    # --- RUN OPTIMIZATION ---
    if df_prices is not None:
        with st.spinner("Finding the best schedule..."):
            result = run_optimization(
                profile=profile, df_prices=df_prices, apcs_data=apcs_data,
                ui_discrete=(new_mode == "Discrete"), ui_baseline=profile["default_baseline"], ui_working_hours=profile["working_hours"]
            )

        if result.get("status") == "error":
            st.error(f"We encountered an issue creating the schedule: {result['message']}")
        else:
            data = result["data"]
            
            def _format_hours(blocks: list) -> str:
                if not blocks:
                    return ""
                groups = []
                current_group = [blocks[0]]
                for i in range(1, len(blocks)):
                    current_start = pd.to_datetime(blocks[i]['start'])
                    prev_end = pd.to_datetime(current_group[-1]['end'])
                    if current_start == prev_end:
                        current_group.append(blocks[i])
                    else:
                        groups.append(current_group)
                        current_group = [blocks[i]]
                groups.append(current_group)
                
                formatted_groups = []
                for g in groups:
                    start_str = pd.to_datetime(g[0]['start']).strftime('%H:%M')
                    end_str = pd.to_datetime(g[-1]['end']).strftime('%H:%M')
                    formatted_groups.append(f"**{start_str} to {end_str}**")
                return ", ".join(formatted_groups)
            
            written_hours_str = _format_hours(data["scheduled_blocks"])
            
            st.success(f"**Best Time to Run the Machine:** {written_hours_str}")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Optimized Cost", f"€{data['optimal_avg_price'] * profile['verschiebbare_last_kwh']:.2f}")
            m2.metric("Standard Cost", f"€{data['baseline_avg_price'] * profile['verschiebbare_last_kwh']:.2f}")
            m3.metric("Money Saved", f"€{data['savings_eur']:.2f}")
            m4.metric("Savings %", f"{data['savings_percent']:.1f}%")

            with st.expander("How are these values calculated?"):
                st.markdown(f"""
                * **Optimized Cost:** The total price you will pay if you run the machine exactly during the recommended {new_window} hours shown above.
                * **Standard Cost:** What you would typically pay on an average day if you did not use this tool to schedule the machine.
                * **Money Saved:** The difference between your standard cost and the optimized cost.
                """)

            # --- PROFILE EXTRACTION FOR VISUALIZATION ---
            weights_24h = [1.0] * 24
            profile_label = "Flat Average"
            
            if new_baseline == "Industry Standard" and apcs_data:
                mapping = apcs_data.get("mapping", {})
                weights_dict = apcs_data.get("weights", {})
                typnummer = next((t for k, t in mapping.items() if profile["branche"] in k or k in profile["branche"]), mapping.get("gewerbe allgemein"))
                
                if typnummer and typnummer in weights_dict:
                    weights_24h = weights_dict[typnummer]
                    profile_label = f"Industry Pattern ({typnummer})"

            # --- VISUALIZATION (DUAL AXIS) ---
            st.subheader("Price Overview & Schedule")
            vis_df = df_prices.head(48).copy()
            vis_df['consumption_weight'] = vis_df.index.hour.map(lambda h: weights_24h[h])
            
            fig = make_subplots(specs=[[{"secondary_y": True}]])

            fig.add_trace(go.Bar(
                x=vis_df.index, y=vis_df['preis_eur_kwh'],
                name="Market Price", marker_color="lightgrey",
                hovertemplate="Time: %{x}<br>Price: €%{y:.4f}/kWh<extra></extra>"
            ), secondary_y=False)
            
            optimal_x, optimal_y = [], []
            for block in data["scheduled_blocks"]:
                mask = (vis_df.index >= block["start"]) & (vis_df.index < block["end"])
                optimal_x.extend(vis_df.loc[mask].index)
                optimal_y.extend(vis_df.loc[mask, 'preis_eur_kwh'])

            fig.add_trace(go.Bar(
                x=optimal_x, y=optimal_y,
                name="Recommended Schedule", marker_color="#00CC96",
                hovertemplate="<b>RECOMMENDED</b><br>Time: %{x}<br>Price: €%{y:.4f}/kWh<extra></extra>"
            ), secondary_y=False)

            fig.add_trace(go.Scatter(
                x=vis_df.index, y=vis_df['consumption_weight'],
                name=profile_label, mode="lines",
                line=dict(color="#1f77b4", width=2, dash="dot"),
                hovertemplate="Time: %{x}<br>Relative Usage: %{y:.4f}<extra></extra>"
            ), secondary_y=True)

            fig.update_layout(
                barmode="overlay", hovermode="x unified", margin=dict(t=30, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            fig.update_yaxes(title_text="Price (€/kWh)", secondary_y=False)
            fig.update_yaxes(title_text="Standard Usage Pattern", showgrid=False, secondary_y=True)
            
            st.plotly_chart(fig, use_container_width=True)

            st.divider()
            st.subheader("Export Your Data")
            e1, e2 = st.columns(2)
            profile_json = json.dumps(profile, indent=4)
            e1.download_button("Download Machine Settings", data=profile_json, file_name=f"settings_{profile['branche'].replace(' ', '_')}.json", mime="application/json", type="primary", use_container_width=True)

            def datetime_handler(x):
                if isinstance(x, pd.Timestamp) or hasattr(x, 'isoformat'):
                    return x.isoformat()
                raise TypeError("Unknown format")
                
            report_json = json.dumps(result, default=datetime_handler, indent=4)
            e2.download_button("Download Full Report", data=report_json, file_name=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", mime="application/json", type="primary", use_container_width=True)