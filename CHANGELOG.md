# Changelog

## [Unreleased]

### Added

- CI workflow (pytest + ruff on Python 3.11/3.12, dashboard build).
- `.env.example`, Code of Conduct, pull request template, bug and feature issue templates.
- Package metadata: project URLs, classifiers, keywords.

### Fixed

- `dashboard/src/lib/` was excluded by `.gitignore`, so the dashboard could not build from a
  fresh clone.
- `mcp` and `websockets` are now declared dependencies (`honeymoon mcp` and `honeymoon serve`
  failed on a clean install).
- `honeymoon.__version__` and the task banner reported 4.5.0 instead of the package version.

## Earlier

### Added

- Introduced surgical mode to Honeymoon, enabling a focused minimal fix pipeline.
- Added `--surgical` CLI option to `run` and `interactive` commands.
- Added profile support in config loading to overlay surgical pipeline configuration.
- Controller run logic updated to support surgical mode execution path with limited fix attempts and no planning step.

### Changed

- RunContext now includes a `surgical` boolean flag to track surgical mode state.

### Version Bump

- Minor version bump due to new feature addition.
