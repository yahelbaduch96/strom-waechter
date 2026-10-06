import pandas as pd
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.table import Table


def _generate_sparkline(hourly_prices: dict, scheduled_blocks: list) -> str:
    """Generates a 24-hour ASCII sparkline highlighting optimal and peak hours."""
    chars = ["_", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
    
    # Calculate min and max directly from the dictionary values
    min_val, max_val = min(hourly_prices.values()), max(hourly_prices.values())
    val_range = max_val - min_val if max_val > min_val else 1
    peak_threshold = max_val - (val_range * 0.20) 
    
    scheduled_hours = set()
    for block in scheduled_blocks:
        start_h = block['start'].hour
        end_h = block['end'].hour
        if start_h < end_h:
            scheduled_hours.update(range(start_h, end_h))
        elif start_h == end_h:
            scheduled_hours.add(start_h)
        else:
            scheduled_hours.update(range(start_h, 24))
            scheduled_hours.update(range(0, end_h))

    sparkline = []
    for hour in range(24):
        # Fetch directly from the dictionary
        price = hourly_prices.get(hour, min_val)
        char_idx = int(((price - min_val) / val_range) * 7)
        char = chars[max(0, min(7, char_idx))]
        
        if hour in scheduled_hours:
            sparkline.append(f"[bold green]{char}[/bold green]")
        elif price >= peak_threshold:
            sparkline.append(f"[bold red]{char}[/bold red]")
        else:
            sparkline.append(f"[dim]{char}[/dim]")
            
    axis = "\n00    06    12    18    23"
    return "".join(sparkline) + axis

def _format_discrete_hours(blocks: list) -> str:
    """Chunks consecutive discrete hours into readable ranges (e.g., 03:00-05:00)."""
    if not blocks:
        return ""
        
    groups = []
    current_group = [blocks[0]]
    
    for i in range(1, len(blocks)):
        if blocks[i]['start'] == current_group[-1]['end']:
            current_group.append(blocks[i])
        else:
            groups.append(current_group)
            current_group = [blocks[i]]
    groups.append(current_group)
    
    formatted_groups = []
    for g in groups:
        if len(g) == 1:
            formatted_groups.append(g[0]['start'].strftime('%H:%M'))
        else:
            formatted_groups.append(f"{g[0]['start'].strftime('%H:%M')}-{g[-1]['end'].strftime('%H:%M')}")
            
    return ", ".join(formatted_groups)


def _build_prompt_panel(blocks: list, mode: str):
    """Builds the actionable prompt directive."""
    if mode == "Continuous":
        start_time = blocks[0]['start'].strftime('%H:%M')
        end_time = blocks[0]['end'].strftime('%H:%M')
        flex_hours = int((blocks[0]['end'] - blocks[0]['start']).total_seconds() / 3600)
        prompt_text = f"ACTION REQUIRED: Schedule {flex_hours}h cycle for {start_time} – {end_time}"
    else:
        hours_str = _format_discrete_hours(blocks)
        flex_hours = len(blocks)
        prompt_text = f"ACTION REQUIRED: Schedule {flex_hours}h at {hours_str}"

    return Panel(f"[bold green]{prompt_text}[/bold green]", border_style="green")


def _build_ability_panel(hourly_prices: dict, blocks: list, working_hours: dict = None):
    """Builds the sparkline context and shift prep alerts."""
    sparkline = _generate_sparkline(hourly_prices, blocks)
    ability_text = Text.from_markup(f"24-Hour Market Context (Green = Target, Red = Peak Penalty):\n{sparkline}\n")
            
    return Panel(ability_text, border_style="blue")


def _build_motivation_table(result: dict, response: dict):
    """Builds the economic feedback table."""
    table = Table(show_header=False, box=None)
    table.add_column("Metric", style="dim")
    table.add_column("Value", justify="right")
    
    table.add_row(f"Baseline ({response['baseline_used']})", f"{result['baseline_avg_price']:.4f} EUR/kWh")
    table.add_row("Optimized Schedule", f"[bold green]{result['optimal_avg_price']:.4f} EUR/kWh[/bold green]")
    table.add_row("Cycle Savings", f"[bold green]€ {result['savings_eur']:.2f}[/bold green]")
    table.add_row("Reduction", f"[bold green]{result['savings_percent']:.1f}%[/bold green]")
    
    return Panel(table, border_style="magenta")


def _print_report(response: dict):
    """Orchestrates the modular UI components for the final report."""
    console = Console()
    result = response["data"]
    df = response["raw_df"]
    mode = response["mode"]
    blocks = result["scheduled_blocks"]
    working_hours = response.get("working_hours", None)
    
    # Header
    if working_hours:
        wh_str = f" | Working Hours: {working_hours['start']} – {working_hours['end']}"
    else:
        wh_str = ""
    console.print(f"\n[bold white]STROM-WÄCHTER[/bold white] | {response['profile_name'].upper()} ({response['branche']}) | {mode} {wh_str}\n")
    
    # Orchestrated Components
    console.print(_build_prompt_panel(blocks, mode))
    console.print(_build_ability_panel(df, blocks, working_hours))
    console.print(_build_motivation_table(result, response))