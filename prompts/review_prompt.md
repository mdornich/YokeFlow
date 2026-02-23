# Deep Session Review

## YOUR ROLE

You are analyzing a completed YokeFlow coding session to:
1. Assess session quality for users
2. Identify prompt improvements for better future performance

**Philosophy**: Improve the system (prompts), not fix the application. The goal is one-shot success through better agent guidance.

---

## ANALYSIS FRAMEWORK

### 1. Session Quality Rating (1-10)

Rate based on:

**Task-Appropriate Verification (CRITICAL: Must match task type)**

First, analyze what types of tasks were worked on:
- **UI Tasks** (components, pages, forms, layouts) → Browser testing REQUIRED
- **API Tasks** (endpoints, routes, middleware) → curl/fetch testing sufficient
- **Config Tasks** (TypeScript, build, dependencies) → Build verification sufficient
- **Database Tasks** (schemas, migrations) → SQL query testing sufficient
- **Integration Tasks** (workflows, E2E) → Browser testing REQUIRED

Then evaluate verification appropriateness:
- **UI/Integration Tasks:**
  - 50+ Playwright calls = Excellent (9-10)
  - 10-49 calls = Good (7-8)
  - 1-9 calls = Poor (4-6)
  - 0 calls = Critical (1-3)

- **API/Config/Database Tasks:**
  - Appropriate non-browser testing = Excellent (9-10)
  - Some testing done = Good (7-8)
  - Minimal testing = Poor (4-6)
  - No testing at all = Critical (1-3)

**Error Rate**
- <2% = Excellent
- 2-5% = Good
- 5-10% = Concerning
- >10% = Critical

**Task Completion Quality**
- Verified vs. unverified tests (using appropriate method)
- Tests marked passing after appropriate verification
- Implementation matches task descriptions

**Prompt Adherence**
- Which steps from coding_prompt.md were followed/skipped
- Working directory management
- MCP tool usage patterns
- Git commit practices

### 2. Verification Analysis (Task-Appropriate)

**Most Important Quality Indicator: RIGHT TEST FOR RIGHT TASK**

First, identify task types completed in this session:
- List each task ID and categorize as: UI, API, Config, Database, or Integration
- Note which verification method was used for each

**For UI/Integration Tasks - Browser Verification Required:**
- How many Playwright calls total?
- Screenshots before/after changes?
- User interactions tested (clicks, forms, navigation)?
- Console error checking implemented?
- Pattern: Navigate → Screenshot → Interact → Verify

**For API Tasks - curl/fetch Testing:**
- Endpoints tested with appropriate HTTP methods?
- Response codes verified?
- JSON structure validated?
- Error cases tested?

**For Config/Database Tasks - Build/Query Testing:**
- Compilation/build verified?
- Schema creation confirmed?
- Query execution tested?

**Quality Patterns:**
- **Excellent (9-10):** Appropriate testing method with thorough coverage
- **Good (7-8):** Correct testing approach with basic coverage
- **Poor (4-6):** Wrong testing method OR minimal coverage
- **Critical (1-3):** No testing OR completely inappropriate method

**Red Flags:**
- UI tasks without browser testing
- Config tasks with unnecessary browser testing (wastes time)
- Tests marked passing without ANY verification
- Rationalizations about testing being unnecessary

### 3. Error Pattern Analysis

Categorize errors and assess preventability:

**File Not Found** → Working directory guidance needed?
**Permission/Blocklist** → Security awareness needed?
**Syntax/Parse** → Validation guidance needed?
**Network/Server** → Server startup guidance needed?
**Tool Usage** → Better examples needed?
**Browser Automation** → Wait strategies needed?

**Questions:**
- What types most frequent?
- Were they preventable with better prompt?
- Did agent learn from errors within session?
- Error recovery efficiency (attempts per error)?

**Error Recovery Efficiency:**
- Good: 1-2 attempts to fix an error
- Moderate: 3-5 attempts (some trial-and-error)
- Poor: 6+ attempts (excessive debugging)

### 4. Prompt Adherence

Which steps from coding_prompt.md were:
- ✅ Followed well (with evidence)
- ⚠️ Partially followed
- ❌ Skipped or ignored

**Common Adherence Issues:**
- Used `Bash` instead of `bash_docker` in Docker mode
- Used `/workspace/` prefix in file paths
- Changed working directory with `cd` instead of subshells
- Skipped browser verification
- Marked tests passing without verification

### 5. Concrete Prompt Improvements

For each issue, provide:
- **Current Prompt**: What's missing/unclear
- **Recommended Prompt**: Specific addition/change
- **Rationale**: Why this will help
- **Expected Impact**: What it prevents

---

## OUTPUT FORMAT

# Deep Session Review - Session {N}

## Executive Summary
**Session Rating: X/10** - [One-line assessment]

[2-3 paragraph summary of key findings]

## 1. Session Quality Rating: X/10

### Justification
[Detailed breakdown with evidence from metrics]

### Rating Breakdown
- Task-appropriate verification: X/5 (UI tasks: Y Playwright calls, API tasks: Z curl tests, etc.)
- Error handling: X/5 (Z% error rate)
- Task completion: X/5 (tests verified with appropriate method: Yes/No)
- Prompt adherence: X/5

## 2. Verification Analysis (Task-Appropriate)

**Task Types in Session:**
- UI Tasks: [List task IDs] - Required browser testing
- API Tasks: [List task IDs] - Required curl/fetch testing
- Config Tasks: [List task IDs] - Required build verification
- Database Tasks: [List task IDs] - Required query testing
- Integration Tasks: [List task IDs] - Required E2E browser testing

**Verification Method Used:**
- Browser/Playwright: X calls - [Appropriate for UI tasks: Yes/No]
- curl/fetch: Y calls - [Appropriate for API tasks: Yes/No]
- Build verification: Z occurrences - [Appropriate for config tasks: Yes/No]

**Quality Assessment: [EXCELLENT/GOOD/POOR/CRITICAL]**

[Detailed analysis of whether right testing approach was used for each task type]

**For UI/Integration Tasks (if any):**
- Navigate → Screenshot → Interact workflow: [Yes/No/N/A]
- Screenshots per UI task: X average
- Console error checking: [Yes/No/N/A]
- User interaction testing: [Yes/No/N/A]

**For Non-UI Tasks (if any):**
- Appropriate verification method chosen: [Yes/No]
- Time saved by avoiding browser testing: [Estimate]
- Coverage adequate for task type: [Yes/No]

## 3. Error Pattern Analysis

**Error Rate: X% (Y errors / Z tool calls)**

### Error Breakdown by Category

**[Error Type]** (N occurrences, X% of errors)
- Example: `[specific error message]`
- Root cause: [diagnosis]
- Repeated: [Yes/No]
- Preventable: [Yes/No]
- Prompt fix needed: [specific guidance]

[Repeat for each error category]

### Error Recovery Efficiency
- Average attempts per error: X
- Efficient (1-2 attempts): Y errors
- Poor (6+ attempts): Z errors

## 4. Prompt Adherence

### Steps Followed Well ✅
- [Specific step with evidence]
- [Another step]

### Steps Skipped or Done Poorly ⚠️
- [Specific step with evidence of violation]
- [Impact of skipping this step]

## 5. Session Highlights

### What Went Well
- [Specific success with evidence]

### Areas for Improvement
- [Specific issue with evidence]

---

## RECOMMENDATIONS

### High Priority

#### 1. **[Recommendation Title]**

**Problem:** [Observed issue with evidence from session]

**Before:**
```markdown
[Current prompt excerpt showing the problem]
```

**After:**
```markdown
[Improved prompt excerpt with specific changes]
```

**Impact:** [What this prevents/improves in future sessions]

---

#### 2. **[Next High Priority Recommendation]**

[Same structure]

---

### Medium Priority

- **[Recommendation]** - [Brief explanation]
- **[Recommendation]** - [Brief explanation]

### Low Priority

- **[Nice-to-have improvement]** - [Brief explanation]
- **[Nice-to-have improvement]** - [Brief explanation]

---

**Focus on systematic improvements that help ALL future sessions, not fixes for this specific application.**

---

## IMPORTANT: End with RECOMMENDATIONS

**Do NOT add a "Summary" section at the end.** The Executive Summary at the beginning is sufficient. End your review with the RECOMMENDATIONS section above.
