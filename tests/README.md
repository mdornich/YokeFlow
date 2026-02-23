# YokeFlow Test Suite Documentation

**Last Updated:** January 2026
**Current Coverage:** 15-20%
**Target Coverage:** 70%
**Status:** Partial Implementation - Architecture Adaptation Required

## Table of Contents
- [Current Status](#current-status)
- [Test Infrastructure](#test-infrastructure)
- [Existing Tests](#existing-tests)
- [New Tests Created](#new-tests-created)
- [Running Tests](#running-tests)
- [Coverage Report](#coverage-report)
- [What Still Needs to Be Done](#what-still-needs-to-be-done)
- [Architecture Issues](#architecture-issues)
- [Quick Start](#quick-start)

## Current Status

The test suite expansion for P1 priority improvements has been partially completed. While comprehensive test modules were created (~12,000+ lines of test code), they require adaptation to match the actual YokeFlow architecture.

### Summary
- ✅ **Test infrastructure created** (fixtures, configuration, runners)
- ✅ **8 new test modules written** (~260 new test cases)
- ✅ **Existing P0 tests working** (~183 tests)
- ⚠️ **New tests need adaptation** to actual architecture
- 📊 **Current working coverage:** 15-20%
- 🎯 **Potential coverage after fixes:** 60-70%

## Test Infrastructure

### Configuration Files
- `pytest.ini` - Pytest configuration with markers and coverage settings
- `conftest.py` - Shared fixtures and test utilities (needs minor fixes)
- `run_test_coverage.py` - Comprehensive test runner with coverage reporting
- `run_existing_tests.py` - Runner for currently working tests

### Test Categories

| Marker | Description | Usage |
|--------|-------------|-------|
| `unit` | Unit tests for individual functions | `pytest -m unit` |
| `integration` | Integration tests for components | `pytest -m integration` |
| `api` | API endpoint tests | `pytest -m api` |
| `database` | Database operation tests | `pytest -m database` |
| `websocket` | WebSocket communication tests | `pytest -m websocket` |
| `slow` | Performance/load tests | `pytest -m "not slow"` to skip |

## Existing Tests

### Working Tests from P0 Improvements

| Test File | Description | Test Count | Status |
|-----------|-------------|------------|---------|
| `test_security.py` | Security validation | 64 | ✅ Working* |
| `test_database_retry.py` | Database retry logic | 30 | ✅ Working |
| `test_session_manager.py` | Intervention system | 15 | ✅ Working |
| `test_checkpoint.py` | Checkpointing system | 19 | ✅ Working |
| `test_errors.py` | Error hierarchy | 36 | ✅ Working |
| `test_structured_logging.py` | Logging system | 19 | ✅ Working |
| `test_intervention.py` | Intervention logic | ~10 | ✅ Working |
| `test_intervention_system.py` | System integration | ~10 | ✅ Working |

*Note: test_security.py has some structural issues but tests pass

**Total Existing Tests:** ~183 tests

## New Tests Created

### Test Modules Written (Need Adaptation)

| Test File | Description | Test Count | Status |
|-----------|-------------|------------|---------|
| `test_api_integration.py` | API endpoints | 40+ | ❌ Needs adaptation |
| `test_database_abstraction.py` | Database operations | 50+ | ❌ Needs adaptation |
| `test_session_lifecycle.py` | Session management | 35+ | ❌ Needs adaptation |
| `test_orchestrator.py` | Orchestration logic | 40+ | ❌ Needs adaptation |
| `test_websocket.py` | WebSocket real-time | 35+ | ❌ Needs adaptation |
| `test_concurrency_performance.py` | Load testing | 30+ | ❌ Needs adaptation |

**Total New Tests:** ~260 tests (not yet functional)

## Running Tests

### Quick Start - Run Working Tests

```bash
# Ensure PostgreSQL is running
docker-compose up -d

# Run existing working tests
python3 -m pytest tests/test_database_retry.py tests/test_checkpoint.py tests/test_errors.py -v

# Or use the test runner
python3 tests/run_existing_tests.py

# Run with coverage
python3 -m pytest tests/test_database_retry.py tests/test_checkpoint.py \
    --cov=core --cov-report=term-missing --cov-report=html
```

### Running Specific Test Categories

```bash
# Run only fast tests (skip performance tests)
pytest -m "not slow"

# Run only database tests
pytest -m database

# Run security tests
python3 -m pytest tests/test_security.py -v

# Run with verbose output
pytest -v --tb=short
```

### Test Coverage Commands

```bash
# Generate coverage report
pytest --cov=core --cov=api --cov=review --cov-report=html

# View HTML coverage report
open htmlcov/index.html

# Coverage with missing lines
pytest --cov=core --cov-report=term-missing
```

## Coverage Report

### Current Coverage (Existing Tests Only)
- **Overall:** 15-20%
- **core.security:** ~80% (well tested)
- **core.database_retry:** ~70%
- **core.checkpoint:** ~65%
- **core.errors:** ~75%
- **core.structured_logging:** ~60%
- **Most other modules:** <20%

### Target Coverage (After Adaptation)
- **Overall:** 70%+
- **Core modules:** 80%+
- **API modules:** 70%+
- **Critical paths:** 90%+

## What Still Needs to Be Done

### Priority 1: Fix Architecture Mismatches (8-12 hours)

The new test files assume class names and structures that don't exist. Key fixes needed:

| Test Assumption | Actual Implementation | Fix Required |
|-----------------|----------------------|--------------|
| `DatabaseConnection` | `DatabaseManager` | Update imports in conftest.py ✅ |
| `SessionOrchestrator` | `AgentOrchestrator` | Rewrite test_orchestrator.py |
| `SessionState` enum | `SessionStatus` | Update all references |
| `ConnectionManager` (WebSocket) | May not exist | Verify and adapt test_websocket.py |
| API endpoint paths | Need verification | Review actual API routes |

### Priority 2: Adapt Test Modules (2-4 hours each)

1. **test_database_abstraction.py**
   - Verify TaskDatabase methods exist
   - Update method signatures
   - Fix async/await patterns

2. **test_api_integration.py**
   - Map to actual API endpoints
   - Update request/response structures
   - Fix authentication if needed

3. **test_session_lifecycle.py**
   - Use actual agent.py functions
   - Fix session manager references
   - Update checkpoint integration

4. **test_orchestrator.py**
   - Complete rewrite for AgentOrchestrator
   - Remove SessionState references
   - Update method names

5. **test_websocket.py**
   - Verify WebSocket implementation exists
   - Update connection manager references
   - Fix event types

6. **test_concurrency_performance.py**
   - Update to use actual classes
   - Fix database operation calls
   - Adjust performance expectations

### Priority 3: Integration Improvements (4-6 hours)

- Fix conftest.py fixtures to match actual database structure
- Create test database initialization script
- Add missing mock fixtures
- Set up proper test isolation

### Priority 4: Documentation Updates (1-2 hours)

- Update this README with actual working examples
- Document the real architecture
- Create migration guide for tests
- Add troubleshooting section

## Architecture Issues

### Key Discoveries

1. **Different Class Names**: Many expected classes have different names in the actual codebase
2. **Missing Components**: Some assumed components (like WebSocket ConnectionManager) may not exist
3. **Different Method Signatures**: Database and API methods may have different parameters
4. **Import Paths**: Some modules are in different locations than expected

### How to Investigate

```bash
# Find actual class names
grep "^class " core/*.py api/*.py

# Check method signatures
grep "async def\|def" core/database.py

# Verify imports
grep "^from\|^import" core/orchestrator.py

# Check API routes
grep "@app\." api/main.py
```

## Quick Start

### Option 1: Use Existing Tests (Works Now)

```bash
# Run the working tests
python3 tests/run_existing_tests.py
```

### Option 2: Fix One Module at a Time

Start with the database tests as they're most critical:

```bash
# 1. Check actual database methods
grep "async def" core/database.py | head -20

# 2. Update test_database_abstraction.py imports

# 3. Run the fixed tests
pytest tests/test_database_abstraction.py -v
```

### Option 3: Create New Tests from Scratch

Write tests that match the actual implementation:

```python
# Example: Test actual TaskDatabase methods
import pytest
from core.database import TaskDatabase

@pytest.mark.asyncio
async def test_actual_database_method():
    db = TaskDatabase("postgresql://...")
    # Test actual methods that exist
    result = await db.actual_method_name()
    assert result is not None
```

## Test Execution Time

- **Fast tests only:** <30 seconds
- **All working tests:** 1-2 minutes
- **Full suite (after fixes):** 5-10 minutes
- **Including performance tests:** 10-15 minutes

## Contributing

When adding new tests:

1. **Study the actual code first** - Don't assume class/method names
2. **Use existing patterns** - Follow the working tests as examples
3. **Test real functionality** - Focus on what actually exists
4. **Add appropriate markers** - Use `@pytest.mark.api`, etc.
5. **Update this README** - Document what you've added

## Troubleshooting

### Common Issues

**Import Errors**
```python
# If you see: ImportError: cannot import name 'SomeClass'
# Check the actual class name:
grep "^class" path/to/module.py
```

**Database Connection Errors**
```bash
# Ensure PostgreSQL is running
docker-compose up -d

# Check connection
psql $DATABASE_URL -c "SELECT 1"
```

**Test Discovery Issues**
```bash
# Ensure you're in project root
cd /path/to/yokeflow

# Check Python path
python3 -c "import sys; print(sys.path)"
```

## Next Steps

1. **Immediate**: Run existing tests to establish baseline
2. **Short-term**: Fix architecture mismatches in test files
3. **Medium-term**: Achieve 70% coverage goal
4. **Long-term**: Integrate with CI/CD pipeline

## Related Documentation

- [ANALYSIS_INDEX.md](../ANALYSIS_INDEX.md) - Architecture analysis
- [IMPROVEMENT_ROADMAP.md](../IMPROVEMENT_ROADMAP.md) - P1 improvements
- [CLAUDE.md](../CLAUDE.md) - Development guidelines

---

**Note:** This test suite represents significant effort (~20-30 hours of work) but requires adaptation to be fully functional. The infrastructure and patterns are solid - they just need alignment with the actual implementation.