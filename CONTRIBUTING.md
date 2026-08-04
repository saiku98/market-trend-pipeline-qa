# Contributing

This is a personal portfolio project. Workflow used while building it:

1. Work happens on a feature branch (`feat/<area>`).
2. Open a PR into `main` with a short description of what changed and how it was tested.
3. CI (lint + unit tests + data validation checks) must pass before merging.
4. Squash-merge into `main`.

## Local setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest
```
