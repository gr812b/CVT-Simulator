# FastAPI Python Backend
This is a super lightweight backend API to expose the python code. It makes use of the CVT simulation module.

## Setup
1. Create and activate a virtual environment
```bash
python -m venv venv
venv\Scripts\activate # or `source venv/bin/activate` on Mac
```
2. Install the dependencies and setup package
```bash
pip install -r requirements.txt
```
3. Start the server
```bash
uvicorn app.main:app --reload
```
> The API will be hosted at localhost:8000, while the interactive docs will be hosted at localhost:8000/docs

4. Manually run linter and formatter
```bash
black app/
flake8 app/
```
