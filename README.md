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

# 3. Install the tool (automatically installs dependencies like Pandas & Rich)
pip install -e .

# 4. Run the tool!
strom-waechter 1


*For a full list of available options, run: `strom-waechter --help`


```


## 🧠 Decision Log & AI Collaboration

**Decisions & Trade-offs:**
* **Ambiguity & Realism:** Implemented a Dual-Mode Math Engine (Continuous vs. Discrete) and Dual Baseline Calculation (Average vs. APCS) to accurately reflect diverse SME operations, trading code simplicity for highly flexible, realistic cost estimation.
* **UX vs. Strict Schemas:** Designed a Dynamic Working Hours & Fallback Pattern where CLI flags smoothly override JSON defaults, prioritizing a fast user experience without polluting the required raw data schemas.
* **Actionable Presentation:** Built a visually decoupled UI (Pre-attentive Sparklines & Alerts). This required pausing development to manually extract all Pandas logic out of the presentation layer, trading immediate feature velocity for a strictly testable MVC architecture.


## 🛠 Usage Examples

Once installed, you can use the CLI tool flexibly:

```bash
# Basic execution (uses default profile data from JSON)
strom-waechter 1

# Example: Continuous process overriding specific working hours
strom-waechter 4 --working-hours "06:00-18:00"

# Example: Discrete (non-consecutive) hours using the APCS baseline
strom-waechter 5 --discrete --baseline apcs

```

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

## 🧪 Tests

This project deliberately avoids external testing dependencies (like Pytest) and utilizes Python's native `unittest` module to ensure zero-dependency reliability across different environments.

```bash
python -m unittest discover dev/tests -v

```
