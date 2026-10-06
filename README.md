# Strom-Wächter (AI Developer Challenge - Phase A)

A terminal-based CLI tool for energy and cost optimization designed for industrial SMEs. It analyzes day-ahead electricity prices and calculates the most cost-efficient time windows for flexible loads based on machine-specific consumption profiles.

## 🚀 Quickstart

This project uses modern Python packaging (`pyproject.toml`). No manual script-path routing is required—it installs as a native global command.

```bash
# 1. Clone the repository and navigate into the directory
git clone https://github.com/yahelbaduch96/strom-waechter.git
cd strom-waechter

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Mac/Linux
# .venv\Scripts\activate   # Windows

# 3. Install the tool 
pip install -e .

```

## 📂 Project Structure

* **`dev/`**: Core application code and modules.
  * `strom_waechter.py`: The Math Engine and main CLI controller.
  * `ui.py`: The presentation layer (pure "paint" layer).
  * `extract_apcs.py`: Utility script used to process standard load profiles.
  * `tests/`: Unit tests using Python's native `unittest`.
* **`data/`**: Inputs, price datasets, and SME profiles.
  * `examples/profil_*.json`: Example profiles for energy-intensive SMEs.
  * `baselines/slp_weights.json`: Austrian Standard Load Profile (SLP) weight vectors (APCS data).
* **`pyproject.toml`**: The build and dependency configuration that packages the CLI globally.
* **`code_review.md`**: The code review for Phase B


## 🛠 Usage & CLI Arguments

Once installed, use the `strom-waechter` command followed by a profile ID.

### Available Arguments:

| Argument | Type | Description |
| --- | --- | --- |
| `profile` | Positional | The ID of the profile to load (e.g., `1`, `4`). |
| `--prices` | Optional | Path to a custom prices JSON file. |
| `--working-hours` | Optional | Override the shift constraints (e.g., `"06:00-18:00"`). |
| `--discrete` | Flag | Finds the cheapest *non-consecutive* hours instead of a rolling block. |
| `--baseline` | Optional | Baseline comparison method: `average` (default) or `apcs`. |

### Examples:

```bash
# Basic execution (uses default profile data)
strom-waechter 1

# Continuous process overriding specific working hours
strom-waechter 4 --working-hours "06:00-18:00"

# Discrete (non-consecutive) hours using the APCS baseline
strom-waechter 2 --discrete --baseline apcs

```

## 🧪 Tests

This project utilizes Python's native `unittest` module.

```bash
python -m unittest discover dev/tests -v
```


## 🧠 Decision Log & AI Collaboration

**Key Architecture Decisions:**

* **Continuous vs. Discrete:** The math engine supports both contiguous rolling windows (e.g., for ovens) and independent discrete hours (e.g., for pumps) to reflect real SME operations.
* **Dynamic Fallbacks:** CLI flags smoothly override JSON profile defaults, prioritizing a fast user experience without polluting the required raw data schemas.
* **Strict MVC Compliance & Separation of Concerns:** To ensure enterprise-grade maintainability, data processing and presentation are cleanly decoupled. All Pandas data manipulation, rolling windows, and calculations are strictly handled within the Math Engine layer. The UI presentation module (`ui.py`) operates as a pure "paint" layer—performing zero calculations and only receiving pre-calculated primitive dictionaries.
* **Defensive Input Validation & Error Handling:** Explicit input checking is enforced before execution. The engine validates data types, handles boundary conditions, and provides clear, actionable user feedback and fallbacks for missing configurations or malformed inputs.

**🔑 Key AI Prompts that made the difference:**

**1. Strategic Planning & Alignment**
Prevented premature code generation and hallucination by forcing architectural discussions before implementation.
> *"Let's continue to phase 3... Don't write any code yet, let's discuss it first."*

**2. Enforcing Clean Architecture**
Rejected AI shortcuts like hardcoded values and monolithic scripts, enforcing the Single Responsibility Principle and dynamic, data-driven solutions.
> *"This function is misleading. Each workspace has its own working hours and we should integrate it and not use magic numbers."*
> *"These are again massive functions. Let's chunk them... we should divide it to smaller helper functions."*

**3. Strict Workflow & State Control**
Established rigorous development hygiene, stopping the AI from rushing ahead to guarantee that testing, debugging, and version control were secured sequentially.
> *"Regarding our workflow... 1. We design the code... 6. Update git 7. Only then continue to the code of the next phase."*


## ⏱️ Approximate Working Hours
**Total time spent: ~8 hours**
While the core math engine was generated relatively fast using AI, the majority of the time was invested in architectural planning, implementing new features while enforcing separation of code, writing tests, and packaging the CLI.