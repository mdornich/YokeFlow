#!/usr/bin/env python3
"""
Recalculate quality metrics for existing sessions.

This script updates the session_quality_checks table with corrected
Playwright detection that includes Docker sandbox browser verifications.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from core.database import TaskDatabase
from review.review_metrics import analyze_session_logs, get_quality_rating, quick_quality_check


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def recalculate_session_metrics(project_name: str = "claude_ai"):
    """
    Recalculate quality metrics for all sessions in a project.

    Args:
        project_name: Name of the project to recalculate
    """
    import os
    # Get database URL from environment or use default
    db_url = os.getenv("DATABASE_URL", "postgresql://agent:agent_dev_password@localhost:5432/yokeflow")
    db = TaskDatabase(db_url)

    # Create the database connection pool
    await db.connect()

    try:
        # Get database connection
        async with db.acquire() as conn:
            # Get project ID
            project_id = await conn.fetchval(
                "SELECT id FROM projects WHERE name = $1",
                project_name
            )

            if not project_id:
                logger.error(f"Project '{project_name}' not found")
                return

            logger.info(f"Processing project: {project_name} (ID: {project_id})")

            # Get all sessions for this project
            sessions = await conn.fetch(
                """
                SELECT id, session_number, type
                FROM sessions
                WHERE project_id = $1
                ORDER BY session_number
                """,
                project_id
            )

            logger.info(f"Found {len(sessions)} sessions to process")

            # Process each session
            for session in sessions:
                session_id = session['id']
                session_num = session['session_number']
                session_type = session['type']

                # Find the JSONL log file
                log_dir = Path(f"generations/{project_name}/logs")
                pattern = f"session_{session_num:03d}_*.jsonl"
                log_files = list(log_dir.glob(pattern))

                if not log_files:
                    logger.warning(f"No log found for session {session_num}")
                    continue

                jsonl_path = log_files[0]
                logger.info(f"Processing session {session_num}: {jsonl_path.name}")

                # Analyze the log with our fixed metrics
                metrics = analyze_session_logs(jsonl_path)

                # Get quality rating and issues
                is_initializer = (session_type == 'initializer')
                issues = quick_quality_check(metrics, is_initializer=is_initializer)
                rating = get_quality_rating(metrics)

                # Log the Playwright detection results
                playwright_count = metrics.get('playwright_count', 0)
                logger.info(f"  - Playwright count: {playwright_count}")
                logger.info(f"  - Quality rating: {rating}/10")

                # Update or insert quality check
                # Convert critical issues and warnings to JSONB arrays
                critical_issue_list = [i for i in issues if i.startswith("❌")]
                warning_list = [i for i in issues if i.startswith("⚠️")]

                # Check if a quality check already exists for this session
                existing = await conn.fetchval(
                    "SELECT id FROM session_quality_checks WHERE session_id = $1",
                    session_id
                )

                if existing:
                    # Update existing record
                    await conn.execute(
                        """
                        UPDATE session_quality_checks
                        SET overall_rating = $2,
                            playwright_count = $3,
                            playwright_screenshot_count = $4,
                            total_tool_uses = $5,
                            error_count = $6,
                            error_rate = $7,
                            critical_issues = $8::jsonb,
                            warnings = $9::jsonb,
                            metrics = $10::jsonb,
                            created_at = NOW()
                        WHERE session_id = $1
                        """,
                        session_id,
                        rating,
                        playwright_count,
                        metrics.get('playwright_screenshot_count', 0),
                        metrics.get('total_tool_uses', 0),
                        metrics.get('error_count', 0),
                        metrics.get('error_rate', 0.0),
                        json.dumps(critical_issue_list),
                        json.dumps(warning_list),
                        json.dumps(metrics)
                    )
                else:
                    # Insert new record
                    await conn.execute(
                        """
                        INSERT INTO session_quality_checks (
                            session_id,
                            check_version,
                            overall_rating,
                            playwright_count,
                            playwright_screenshot_count,
                            total_tool_uses,
                            error_count,
                            error_rate,
                            critical_issues,
                            warnings,
                            metrics
                        ) VALUES ($1, '1.0', $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10::jsonb)
                        """,
                        session_id,
                        rating,
                        playwright_count,
                        metrics.get('playwright_screenshot_count', 0),
                        metrics.get('total_tool_uses', 0),
                        metrics.get('error_count', 0),
                        metrics.get('error_rate', 0.0),
                        json.dumps(critical_issue_list),
                        json.dumps(warning_list),
                        json.dumps(metrics)
                    )

                # Also update the browser_verifications in sessions table metrics JSONB
                # Count browser verifications from tool usage
                browser_verifs = playwright_count  # Use the fixed count

                await conn.execute(
                    """
                    UPDATE sessions
                    SET metrics = jsonb_set(metrics, '{browser_verifications}', $1::jsonb)
                    WHERE id = $2
                    """,
                    json.dumps(browser_verifs),  # Convert to JSON string
                    session_id
                )

            logger.info("✅ Recalculation complete!")

            # Show summary
            summary = await conn.fetch(
                """
                SELECT
                    AVG(playwright_count) as avg_playwright,
                    AVG(overall_rating) as avg_rating,
                    COUNT(*) FILTER (WHERE playwright_count > 0) as sessions_with_browser,
                    COUNT(*) as total_sessions
                FROM session_quality_checks
                WHERE session_id IN (
                    SELECT id FROM sessions WHERE project_id = $1
                )
                """,
                project_id
            )

            if summary:
                row = summary[0]
                logger.info("\n=== Summary ===")
                logger.info(f"Average Playwright count: {row['avg_playwright']:.1f}")
                logger.info(f"Average quality rating: {row['avg_rating']:.1f}/10")
                logger.info(f"Sessions with browser verification: {row['sessions_with_browser']}/{row['total_sessions']}")

    finally:
        await db.disconnect()


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Recalculate quality metrics for existing sessions"
    )
    parser.add_argument(
        "--project",
        default="claude_ai",
        help="Project name to recalculate (default: claude_ai)"
    )

    args = parser.parse_args()

    await recalculate_session_metrics(args.project)


if __name__ == "__main__":
    asyncio.run(main())