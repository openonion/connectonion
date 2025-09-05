# ConnectOnion Versioning Rules

## Version Format
We follow semantic versioning: `MAJOR.MINOR.PATCH`

Example: `0.0.2`

## Update Rules

### 1. **PATCH Version (0.0.X)**
- Increment by 1 for each release
- When PATCH reaches 10, roll over to MINOR version
- Examples: 
  - 0.0.1 → 0.0.2 → 0.0.3 ... → 0.0.9 → 0.1.0

### 2. **MINOR Version (0.X.0)**
- Increment when PATCH reaches 10
- Reset PATCH to 0
- When MINOR reaches 10, roll over to MAJOR version
- Examples:
  - 0.0.9 → 0.1.0
  - 0.9.9 → 1.0.0

### 3. **MAJOR Version (X.0.0)**
- Increment when MINOR reaches 10
- Reset MINOR and PATCH to 0
- Reserved for major breaking changes or stable releases

## Current Version History
- 0.0.1b1 → 0.0.1b2 → ... → 0.0.1b8 (Beta releases)
- 0.0.2 (First post-beta release, production ready)

## Files to Update When Versioning

When updating version, these files must be changed:

### Python Package Files
1. `/connectonion/__init__.py` - `__version__` variable
2. `/setup.py` - `version` parameter

### Documentation Files
3. `/docs-site/app/page.tsx` - Version badge
4. `/README.md` - Any version references
5. `/docs-site/README.md` - Any version references

### Configuration Files (if present)
6. `/pyproject.toml` - version field (if exists)
7. `/package.json` - version field (if exists)

## Version Update Checklist

- [ ] Update `__version__` in `/connectonion/__init__.py`
- [ ] Update `version` in `/setup.py`
- [ ] Update version badge in `/docs-site/app/page.tsx`
- [ ] Update any version references in README files
- [ ] Create git tag: `git tag v0.0.2`
- [ ] Push tag: `git push origin v0.0.2`
- [ ] Update PyPI package: `python setup.py sdist bdist_wheel && twine upload dist/*`

## Example Version Progression

```
0.0.1 → 0.0.2 → 0.0.3 → 0.0.4 → 0.0.5 →
0.0.6 → 0.0.7 → 0.0.8 → 0.0.9 → 0.1.0 →
0.1.1 → 0.1.2 → ... → 0.1.9 → 0.2.0 →
...
0.9.9 → 1.0.0 (Major release)
```

## Notes
- We moved from beta (0.0.1bX) to production (0.0.2)
- Each update increments the last digit by 1
- When last digit reaches 10, it rolls over to the next level
- This ensures predictable, incremental versioning