#!/usr/bin/env python3
"""
Test coverage runner for YokeFlow.

Runs all tests with coverage reporting and generates detailed reports.
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path
from typing import List, Tuple


def get_python_command():
    """Get the appropriate python command for the system."""
    # Try python3 first, then python
    for cmd in ['python3', 'python', sys.executable]:
        try:
            result = subprocess.run(
                [cmd, '--version'],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                return cmd
        except FileNotFoundError:
            continue
    return sys.executable  # Fallback to current interpreter


def setup_test_environment():
    """Set up the test environment."""
    # Ensure we're in the project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    # Set up test database URL
    os.environ["TEST_DATABASE_URL"] = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://agent:agent_dev_password@localhost:5432/yokeflow_test"
    )

    # Also ensure main DATABASE_URL is set if not already
    if "DATABASE_URL" not in os.environ:
        os.environ["DATABASE_URL"] = "postgresql://agent:agent_dev_password@localhost:5432/yokeflow"

    # Get python command
    python_cmd = get_python_command()

    # Ensure test database exists
    print("Setting up test database...")
    try:
        # Try to create test database using psql
        subprocess.run(
            ["psql", os.environ["DATABASE_URL"], "-c", "CREATE DATABASE yokeflow_test;"],
            check=False,
            capture_output=True,
            timeout=5
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("Warning: Could not create test database via psql. Assuming it exists.")

    # Initialize test database schema
    init_script = Path("scripts/init_database.py")
    if init_script.exists():
        try:
            result = subprocess.run(
                [python_cmd, str(init_script), "--database-url", os.environ["TEST_DATABASE_URL"]],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0 and result.stderr:
                print(f"Warning: Database initialization had issues: {result.stderr[:200]}")
        except Exception as e:
            print(f"Warning: Could not initialize test database: {e}")
    else:
        print("Warning: Database initialization script not found. Assuming database is ready.")


def run_tests_with_coverage(
    test_path: str = "tests/",
    verbose: bool = False,
    markers: str = None,
    html_report: bool = True
) -> Tuple[int, str]:
    """
    Run tests with coverage reporting.

    Args:
        test_path: Path to tests to run
        verbose: Enable verbose output
        markers: Pytest markers to filter tests
        html_report: Generate HTML coverage report

    Returns:
        Tuple of (exit code, coverage report)
    """
    # Build pytest command
    cmd = [
        "pytest",
        test_path,
        "--cov=core",
        "--cov=api",
        "--cov=review",
        "--cov-report=term-missing",
        "--cov-report=json",
        "--asyncio-mode=auto"
    ]

    if html_report:
        cmd.append("--cov-report=html")

    if verbose:
        cmd.append("-v")

    if markers:
        cmd.extend(["-m", markers])

    print(f"Running tests: {' '.join(cmd)}")
    print("=" * 80)

    # Run tests
    result = subprocess.run(cmd, capture_output=False, text=True)

    # Generate summary report
    if result.returncode == 0:
        print("\n" + "=" * 80)
        print("✅ All tests passed!")
        generate_coverage_summary()
    else:
        print("\n" + "=" * 80)
        print("❌ Some tests failed.")

    return result.returncode, ""


def generate_coverage_summary():
    """Generate a coverage summary from the JSON report."""
    try:
        import json

        coverage_file = Path("coverage.json")
        if not coverage_file.exists():
            return

        with open(coverage_file) as f:
            data = json.load(f)

        print("\n📊 Coverage Summary:")
        print("-" * 40)

        # Overall statistics
        total = data["totals"]
        percent_covered = total.get("percent_covered", 0)

        print(f"Overall Coverage: {percent_covered:.1f}%")
        print(f"Lines Covered: {total.get('covered_lines', 0)}/{total.get('num_statements', 0)}")
        print(f"Branches Covered: {total.get('covered_branches', 0)}/{total.get('num_branches', 0)}")

        # Module breakdown
        print("\n📁 Module Coverage:")
        print("-" * 40)

        modules = {}
        for file_path, file_data in data["files"].items():
            # Group by module
            if file_path.startswith("core/"):
                module = "core"
            elif file_path.startswith("api/"):
                module = "api"
            elif file_path.startswith("review/"):
                module = "review"
            else:
                continue

            if module not in modules:
                modules[module] = {
                    "files": 0,
                    "covered_lines": 0,
                    "total_lines": 0
                }

            modules[module]["files"] += 1
            modules[module]["covered_lines"] += file_data["summary"].get("covered_lines", 0)
            modules[module]["total_lines"] += file_data["summary"].get("num_statements", 0)

        for module, stats in sorted(modules.items()):
            if stats["total_lines"] > 0:
                coverage = (stats["covered_lines"] / stats["total_lines"]) * 100
                print(f"{module:10} {coverage:5.1f}% ({stats['covered_lines']}/{stats['total_lines']} lines)")

        # Files with low coverage
        print("\n⚠️  Files with Low Coverage (<50%):")
        print("-" * 40)

        low_coverage_files = []
        for file_path, file_data in data["files"].items():
            percent = file_data["summary"].get("percent_covered", 0)
            if percent < 50:
                low_coverage_files.append((file_path, percent))

        for file_path, percent in sorted(low_coverage_files, key=lambda x: x[1]):
            print(f"{percent:5.1f}% {file_path}")

        if html_report_exists():
            print("\n📈 Detailed HTML report available at: htmlcov/index.html")
            print("   Open with: open htmlcov/index.html")

    except Exception as e:
        print(f"Could not generate coverage summary: {e}")


def html_report_exists() -> bool:
    """Check if HTML coverage report exists."""
    return Path("htmlcov/index.html").exists()


def run_specific_test_suites(suites: List[str], verbose: bool = False):
    """Run specific test suites."""
    suite_mapping = {
        "api": "tests/test_api_integration.py",
        "database": "tests/test_database_abstraction.py",
        "session": "tests/test_session_lifecycle.py",
        "orchestrator": "tests/test_orchestrator.py",
        "websocket": "tests/test_websocket.py",
        "concurrency": "tests/test_concurrency_performance.py",
        "security": "tests/test_security.py",
        "intervention": "tests/test_intervention.py tests/test_intervention_system.py",
        "checkpoint": "tests/test_checkpoint.py",
        "errors": "tests/test_errors.py",
        "logging": "tests/test_structured_logging.py",
        "retry": "tests/test_database_retry.py",
        "manager": "tests/test_session_manager.py"
    }

    for suite in suites:
        if suite in suite_mapping:
            print(f"\n🧪 Running {suite} tests...")
            print("=" * 80)
            test_path = suite_mapping[suite]
            run_tests_with_coverage(test_path, verbose=verbose, html_report=False)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run YokeFlow tests with coverage")
    parser.add_argument(
        "suites",
        nargs="*",
        help="Specific test suites to run (api, database, session, etc.)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "-m", "--markers",
        help="Run tests with specific markers (e.g., 'not slow')"
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Skip HTML coverage report generation"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only fast tests (skip slow/performance tests)"
    )
    parser.add_argument(
        "--integration",
        action="store_true",
        help="Run only integration tests"
    )
    parser.add_argument(
        "--unit",
        action="store_true",
        help="Run only unit tests"
    )

    args = parser.parse_args()

    # Setup environment
    setup_test_environment()

    # Determine markers
    markers = args.markers
    if args.quick:
        markers = "not slow"
    elif args.integration:
        markers = "integration"
    elif args.unit:
        markers = "unit"

    # Run tests
    if args.suites:
        run_specific_test_suites(args.suites, verbose=args.verbose)
    else:
        exit_code, _ = run_tests_with_coverage(
            verbose=args.verbose,
            markers=markers,
            html_report=not args.no_html
        )
        sys.exit(exit_code)


if __name__ == "__main__":
    main()