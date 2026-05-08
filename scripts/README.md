# scripts

Repository maintenance entrypoints.

- `doctor.sh`: local regression baseline: dependency sync, lint, mypy, tests, coverage, audit, build, smoke test
- `dependency_health.sh`: development dependency review and vulnerability audit
- `lint.sh`: pre-commit wrapper
- `check_coverage.py`: coverage policy check
- `smoke_test_built_cli.sh`: validates the built CLI artifact can be installed
