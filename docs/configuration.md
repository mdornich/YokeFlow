# Configuration File Guide

YokeFlow supports YAML configuration files for managing default settings. Configuration is primarily managed through the Web UI, but YAML files provide defaults.

## Quick Start

1. **Copy the example config:**
   ```bash
   cp .yokeflow.yaml.example .yokeflow.yaml
   ```

2. **Edit settings** in `.yokeflow.yaml`

3. **Settings are used by:**
   - Web UI (for default model selections)
   - API endpoints
   - Utility scripts

## Configuration File Locations

The system looks for configuration files in this order:

1. **Current directory**: `.yokeflow.yaml`
   - Project-specific settings
   - Checked first

2. **Home directory**: `~/.yokeflow.yaml`
   - Global defaults for all projects
   - Checked if no local config exists

3. **Built-in defaults**
   - Used if no config file found
   - See [core/config.py](../core/config.py) for default values

**Note**: Web UI settings (selected during project creation) override config file defaults.

## Configuration Options

### Models

Control which Claude models are used:

```yaml
models:
  initializer: claude-opus-4-5-20251101   # For planning/initialization
  coding: claude-sonnet-4-5-20250929      # For implementation
```

**Recommended:**
- **Opus** for initialization (better planning)
- **Sonnet** for coding (faster, more cost-effective)

### Timing

Control delays and intervals:

```yaml
timing:
  auto_continue_delay: 3      # Seconds between sessions
  web_ui_poll_interval: 5     # Web UI refresh interval
  web_ui_port: 3000           # Web dashboard port (Next.js default)
```

### Security

Add custom blocked commands:

```yaml
security:
  additional_blocked_commands:
    - my-dangerous-script
    - custom-deploy-tool
```

These are added to the built-in blocklist in [security.py](../security.py).

### Project

Project-level settings:

```yaml
project:
  default_generations_dir: generations   # Where to store projects
  max_iterations: null                    # Default iteration limit (null = unlimited)
```

## Priority Order

Settings are applied in this order (highest priority first):

1. **Web UI selections** (when creating/initializing projects)
   - Model selection dropdowns
   - Project-specific settings

2. **Configuration file** (provides defaults)
   ```yaml
   models:
     initializer: claude-opus-4-5-20251101
     coding: claude-sonnet-4-5-20250929
   ```

3. **Built-in defaults** (fallback)
   ```python
   # From core/config.py
   initializer: "claude-opus-4-5-20251101"
   coding: "claude-sonnet-4-5-20250929"
   ```

## Examples

### Example 1: Basic Config

Create `.yokeflow.yaml` in current directory:

```yaml
models:
  initializer: claude-opus-4-5-20251101
  coding: claude-sonnet-4-5-20250929

timing:
  auto_continue_delay: 5  # Slower pace between sessions

project:
  default_generations_dir: generations
```

The Web UI will use these as defaults when creating new projects.

### Example 2: Global Config

Create `~/.yokeflow.yaml` for global defaults:

```yaml
models:
  initializer: claude-opus-4-5-20251101
  coding: claude-sonnet-4-5-20250929
```

These defaults apply to all projects on this machine.

### Example 3: Development vs Production

You can use different configs for different scenarios by placing them in different directories:

**Development** (`.yokeflow.yaml`):
```yaml
models:
  initializer: claude-opus-4-5-20251101
  coding: claude-sonnet-4-5-20250929  # Fast, cost-effective

timing:
  auto_continue_delay: 1  # Quick iteration
```

**Production** (`~/.yokeflow.yaml`):
```yaml
models:
  initializer: claude-opus-4-5-20251101
  coding: claude-opus-4-5-20251101  # Higher quality

timing:
  auto_continue_delay: 5  # Slower, more stable
```

## Validation

The config system validates settings on load:

- Invalid YAML → error message shown in Web UI/API logs
- Missing file (auto-detect) → use built-in defaults
- Invalid model names → passed through (API will validate)

## Complete Example

See [.yokeflow.yaml.example](../.yokeflow.yaml.example) for a complete configuration file with all available options and comments.

## Best Practices

1. **Use global config** (`~/.yokeflow.yaml`) for personal defaults
2. **Use local config** (`.yokeflow.yaml`) for project-specific needs
3. **Add to .gitignore** if config contains sensitive paths
4. **Version control** `.yokeflow.yaml.example` as a template
5. **Document** any non-standard settings in project README

## See Also

- [config.py](../config.py) - Configuration implementation
- [.yokeflow.yaml.example](../.yokeflow.yaml.example) - Full example with comments

