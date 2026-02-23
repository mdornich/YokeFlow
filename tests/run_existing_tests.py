#!/usr/bin/env python3
"""
Runner for existing YokeFlow tests.

This script runs the tests that are already in the codebase and working.
"""

import subprocess
import sys
import os
from pathlib import Path


def setup_environment():
    """Set up test environment variables."""
    # Ensure we're in the project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    # Set database URLs if not already set
    if "DATABASE_URL" not in os.environ:
        os.environ["DATABASE_URL"] = "postgresql://agent:agent_dev_password@localhost:5432/yokeflow"

    if "TEST_DATABASE_URL" not in os.environ:
        os.environ["TEST_DATABASE_URL"] = "postgresql://agent:agent_dev_password@localhost:5432/yokeflow_test"


def run_existing_tests():
    """Run the existing tests that are confirmed to work."""

    print("=" * 80)
    print("Running YokeFlow Existing Test Suite")
    print("=" * 80)

    # List of existing test files that should work
    existing_tests = [
        "tests/test_security.py",
        "tests/test_database_retry.py",
        "tests/test_session_manager.py",
        "tests/test_checkpoint.py",
        "tests/test_errors.py",
        "tests/test_structured_logging.py",
        "tests/test_intervention.py",
        "tests/test_intervention_system.py"
    ]

    # Check which test files exist
    available_tests = []
    for test_file in existing_tests:
        if Path(test_file).exists():
            available_tests.append(test_file)
            print(f"✓ Found: {test_file}")
        else:
            print(f"✗ Missing: {test_file}")

    if not available_tests:
        print("\nNo test files found!")
        return 1

    print(f"\nRunning {len(available_tests)} test files...")
    print("-" * 80)

    # Run tests with coverage
    cmd = [
        sys.executable, "-m", "pytest",
        *available_tests,
        "--cov=core",
        "--cov-report=term-missing",
        "--cov-report=html",
        "-v",
        "--tb=short"
    ]

    print(f"Command: {' '.join(cmd)}\n")

    # Execute tests
    result = subprocess.run(cmd)

    if result.returncode == 0:
        print("\n" + "=" * 80)
        print("✅ All existing tests passed!")
        print("\n📊 HTML Coverage Report: htmlcov/index.html")
        print("   Open with: open htmlcov/index.html")
    else:
        print("\n" + "=" * 80)
        print("❌ Some tests failed. See output above for details.")

    return result.returncode


def main():
    """Main entry point."""
    setup_environment()
    sys.exit(run_existing_tests())


if __name__ == "__main__":
    main()