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
python -m unittest discover -s tests
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
