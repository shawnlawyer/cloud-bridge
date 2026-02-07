# Contributing to Cloud Bridge

Thank you for contributing.

**Principles**
- Deterministic behavior only
- Fail-closed defaults
- No side effects
- Instrument + Substrate layers only
- Operator behavior is prohibited

**Development Setup**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

**Rules**
- No background threads
- No schedulers
- No write-to-world operations
- No hidden state
- All state must be inspectable

**Tests**
- New logic requires tests
- Tests must be deterministic
- No flaky or time-dependent tests

**Reviews**
- One logical change per PR
- Keep diffs small
- Prefer clarity over cleverness
