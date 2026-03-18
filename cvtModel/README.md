## Python setup

1. Create and activate a virtual environment
```bash
python -m venv venv
venv\Scripts\activate # or 'source venv/bin/activate' on Mac
```
2. Install the dependencies and setup package
```bash
pip install -e .[dev]
```
3. Run the tests
```bash
coverage run -m unittest discover -s test/simulations -s test/utils
```
4. Manually run linter and formatter
```bash
black src/ test/
flake8 src/ test/
```
5. If you want to setup the pre-commit, run:
```bash
pre-commit install
```

## Local Simulation + Graph Validation

1. Generate a simulation CSV
```bash
python -c "from cvt_simulator import simulate_cvt_model, SimulationArgs; simulate_cvt_model(SimulationArgs(), out_csv='simulation_output.csv')"
```

2. Generate validation graphs from the CSV
```bash
python src/cvt_simulator/utils/generate_graphs.py --csv simulation_output.csv --out-dir generated_graphs
```

3. Optional: show interactive plots while generating files
```bash
python src/cvt_simulator/utils/generate_graphs.py --csv simulation_output.csv --out-dir generated_graphs --show
```
