# Contributing to YokeFlow

Thank you for your interest in contributing to YokeFlow! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Documentation](#documentation)
- [Community](#community)

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/yokeflow.git
   cd yokeflow
   ```
3. **Add upstream remote**:
   ```bash
   git remote add upstream https://github.com/ms4inc/yokeflow.git
   ```
4. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Setup

Follow the setup instructions in [README.md](README.md) to get YokeFlow running locally:

### Prerequisites
- Node.js 20+ (for web UI and MCP server)
- Python 3.9+ (for core platform)
- Docker (for PostgreSQL and sandboxing)
- Claude API token

### Quick Setup
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install web UI dependencies
cd web-ui
npm install
cd ..

# Build MCP task manager
cd mcp-task-manager
npm install
npm run build
cd ..

# Start PostgreSQL
docker-compose up -d

# Initialize database
python scripts/init_database.py --docker

# Configure environment
cp .env.example .env
# Edit .env with your Claude API token
```

## How to Contribute

### Reporting Bugs

Before creating a bug report, please:
1. **Search existing issues** to avoid duplicates
2. **Check the troubleshooting section** in README.md
3. **Test with the latest version** from the main branch

When creating a bug report, include:
- **Clear title** describing the issue
- **Steps to reproduce** the bug
- **Expected behavior** vs. actual behavior
- **Environment details** (OS, Python/Node versions, Docker version)
- **Logs** from `generations/[project]/logs/` if applicable
- **Screenshots** if relevant

Use the bug report template when creating issues.

### Suggesting Enhancements

Enhancement suggestions are welcome! Please:
1. **Check [TODO-FUTURE.md](TODO-FUTURE.md)** to see if it's already planned
2. **Create an issue** using the feature request template
3. **Describe the use case** and why it's valuable
4. **Provide examples** if applicable

### Contributing Code

We welcome contributions in these areas:

**High Priority:**
- Bug fixes
- Documentation improvements
- Test coverage expansion
- Performance optimizations

**Medium Priority:**
- New features (discuss in an issue first)
- UI/UX improvements
- Integration with new services

**Lower Priority:**
- Refactoring (unless it improves performance/maintainability significantly)
- Cosmetic changes

## Pull Request Process

### Before Submitting

1. **Update from upstream**:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run tests**:
   ```bash
   # Security tests
   python tests/test_security.py

   # Database tests
   python tests/test_database_abstraction.py

   # MCP tests
   python tests/test_mcp.py
   ```

3. **Check code style**:
   ```bash
   # Python: Follow PEP 8
   # TypeScript: Use project's ESLint config
   cd web-ui && npm run lint
   ```

4. **Update documentation** if you've changed:
   - API endpoints (update api/README.md)
   - Configuration options (update docs/configuration.md)
   - User-facing features (update README.md, CLAUDE.md)
   - Database schema (update schema/postgresql/)

### Submitting the PR

1. **Push your branch**:
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create Pull Request** on GitHub

3. **Fill out the PR template** completely:
   - Clear description of changes
   - Link to related issues
   - Screenshots/demos if applicable
   - Testing performed
   - Documentation updates

4. **Respond to review feedback** promptly

### PR Requirements

- ✅ All tests pass
- ✅ No merge conflicts
- ✅ Documentation updated
- ✅ Follows coding standards
- ✅ Commit messages are clear
- ✅ PR description is complete

## Coding Standards

### Python

- **Follow PEP 8** style guide
- **Use type hints** for function signatures
- **Write docstrings** for modules, classes, and functions
- **Keep functions focused** (single responsibility)
- **Use async/await** for database operations

Example:
```python
async def get_project_status(project_id: str) -> Dict[str, Any]:
    """
    Get the current status of a project.

    Args:
        project_id: UUID of the project

    Returns:
        Dictionary containing project status information

    Raises:
        ValueError: If project_id is invalid
        DatabaseError: If database query fails
    """
    # Implementation
```

### TypeScript/React

- **Use TypeScript** for all new code
- **Follow React best practices** (hooks, functional components)
- **Use proper types** (avoid `any`)
- **Components should be focused** and reusable
- **Use Tailwind CSS** for styling

Example:
```typescript
interface ProjectStatusProps {
  projectId: string;
  onUpdate?: (status: ProjectStatus) => void;
}

export function ProjectStatus({ projectId, onUpdate }: ProjectStatusProps) {
  // Implementation
}
```

### Commit Messages

Follow conventional commits format:

```
type(scope): brief description

Detailed explanation of what changed and why.

Fixes #123
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding/updating tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(api): add endpoint for project duplication

Add POST /api/projects/{id}/duplicate endpoint that creates
a copy of an existing project with a new name.

Fixes #456

---

fix(web-ui): prevent session logs infinite scroll bug

The logs viewer was continuously fetching when scrolled to
bottom. Added debouncing to prevent excessive API calls.

Fixes #789
```

## Testing Guidelines

### Manual Testing

Before submitting, test these scenarios:

1. **Create a new project** via Web UI
2. **Run initialization session** (Session 0)
3. **Run a coding session** (Session 1+)
4. **Verify real-time updates** work in Web UI
5. **Check session logs** are readable
6. **Test error handling** (stop/restart sessions)

### Automated Testing

Add tests for:
- **New API endpoints** (integration tests)
- **Database operations** (unit tests)
- **Security validations** (security tests)
- **UI components** (component tests - future)

See [tests/README.md](tests/README.md) for testing details.

## Documentation

### User Documentation

Update these files when changing user-facing features:
- **README.md** - Main user guide
- **CLAUDE.md** - Quick reference for AI agents
- **QUICKSTART.md** - Getting started guide
- **docs/** - Detailed documentation

### Developer Documentation

Update these files when changing architecture/APIs:
- **docs/developer-guide.md** - Technical architecture
- **docs/mcp-usage.md** - MCP integration details
- **api/README.md** - API documentation
- **Code comments** - Inline documentation

### Writing Style

- **Be concise** but complete
- **Use examples** to illustrate concepts
- **Include code snippets** where helpful
- **Link to related docs** for context
- **Keep formatting consistent** with existing docs

## Community

### Getting Help

- **GitHub Discussions** - Ask questions, share ideas
- **GitHub Issues** - Report bugs, request features
- **Documentation** - Check docs/ directory first

### Communication

- **Be respectful** and constructive
- **Assume good intentions** from others
- **Stay on topic** in discussions
- **Help others** when you can
- **Give credit** where it's due

### Recognition

Contributors will be:
- Listed in release notes
- Acknowledged in documentation
- Invited to collaborate on future features

---

**Questions?** Open a discussion on GitHub or create an issue.

**Thank you for contributing to YokeFlow!** 🚀
