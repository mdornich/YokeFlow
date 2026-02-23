# Docker Services Solution for YokeFlow Projects

## Problem Summary

When YokeFlow generates projects that need their own Docker services (PostgreSQL, Redis, MinIO, etc.), we encounter:

1. **Port conflicts:** Both YokeFlow and the project want port 5432 for PostgreSQL
2. **Docker-in-Docker issues:** Can't start containers from inside the sandbox container
3. **Service isolation:** Projects shouldn't interfere with YokeFlow's own services

## Recommended Solution: Host-Based Services with Port Shifting

### Overview

1. **Initialization creates services on HOST** with shifted ports
2. **Sandbox container connects via `host.docker.internal`**
3. **Each project gets unique port ranges** to avoid conflicts

### Implementation Steps

#### Step 1: Update Initialization Prompt

Add to `prompts/initializer_prompt_docker.md`:

```markdown
## Docker Services Rules

When creating docker-compose.yml for project services:

1. **ALWAYS use shifted ports** (never use default ports):
   ```yaml
   services:
     postgres:
       ports:
         - "5433:5432"  # Shifted from 5432 to avoid YokeFlow conflict
     redis:
       ports:
         - "6380:6379"  # Shifted from 6379
     minio:
       ports:
         - "9002:9000"  # Shifted from 9000
         - "9003:9001"  # Shifted from 9001
   ```

2. **Add unique container names** with project prefix:
   ```yaml
   container_name: ${PROJECT_NAME}-postgres
   ```

3. **Create .env.docker for container connections**:
   ```bash
   # .env.docker - For app running in Docker container
   DATABASE_URL=postgresql://user:pass@host.docker.internal:5433/dbname
   REDIS_URL=redis://host.docker.internal:6380
   ```

4. **In init.sh, start services BEFORE container work**:
   ```bash
   # Start services on host
   echo "Starting Docker services..."
   docker-compose up -d --wait
   ```
```

#### Step 2: Port Allocation Strategy

Assign port ranges per project to avoid conflicts:

| Service      | Default | YokeFlow | Project 1 | Project 2 | Project 3 |
|-------------|---------|----------|-----------|-----------|-----------|
| PostgreSQL  | 5432    | 5432     | 5433      | 5434      | 5435      |
| Redis       | 6379    | 6379     | 6380      | 6381      | 6382      |
| MinIO API   | 9000    | -        | 9002      | 9004      | 9006      |
| MinIO Console| 9001   | -        | 9003      | 9005      | 9007      |
| Meilisearch | 7700    | -        | 7701      | 7702      | 7703      |

#### Step 3: Connection from Container

The app in the Docker container connects to services on the host:

```typescript
// database.ts
const dbUrl = process.env.NODE_ENV === 'docker'
  ? 'postgresql://user:pass@host.docker.internal:5433/db'
  : 'postgresql://user:pass@localhost:5433/db';
```

### Alternative Solutions

#### Alternative 1: Firecracker MicroVMs

**Pros:**
- True isolation with lightweight VMs
- Better security than containers
- Network isolation built-in

**Cons:**
- Linux-only (no macOS/Windows support)
- Requires KVM virtualization
- More complex setup
- Not suitable for local development

**Verdict:** Good for production cloud deployment, not for local dev.

#### Alternative 2: E2B Cloud Sandboxes

**Pros:**
- Fully managed cloud sandboxes
- Complete isolation
- Can run Docker inside
- No local resource usage

**Cons:**
- Requires internet connection
- Costs money per sandbox hour
- Latency for file operations
- Privacy concerns (code runs in cloud)

**Verdict:** Good for production SaaS, expensive for development.

#### Alternative 3: Docker-in-Docker with Privileged Mode

**Pros:**
- Can run Docker inside containers
- Full Docker capabilities

**Cons:**
- Major security risk (privileged mode)
- Complex volume mounting
- Performance overhead
- Still has port conflict issues

**Verdict:** Not recommended due to security and complexity.

#### Alternative 4: Podman with Rootless Containers

**Pros:**
- No daemon, more secure
- Rootless by default
- Docker-compatible

**Cons:**
- Less mature ecosystem
- Some compatibility issues
- Learning curve for team

**Verdict:** Promising but needs more maturity.

## Recommended Approach for YokeFlow

### Phase 1: Host Services with Port Shifting (Current)
- Simple to implement
- Works with existing architecture
- No additional tools needed
- Clear port allocation strategy

### Phase 2: Network Namespaces (Future)
- Create isolated network namespaces per project
- Use Docker networks for isolation
- Implement port proxy/router

### Phase 3: Cloud Sandboxes (Future Production)
- Integrate E2B for production deployments
- Keep local Docker for development
- Hybrid approach based on environment

## Implementation Checklist

- [ ] Update initialization prompt with port shifting rules
- [ ] Create port allocation documentation
- [ ] Add helper scripts for service management
- [ ] Test with multiple concurrent projects
- [ ] Document troubleshooting steps
- [ ] Add service health checks
- [ ] Create cleanup scripts

## Example: Updated docker-compose.yml

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    container_name: ${PROJECT_NAME}-postgres
    ports:
      - "${POSTGRES_PORT:-5433}:5432"
    environment:
      POSTGRES_USER: ${PROJECT_NAME}
      POSTGRES_PASSWORD: ${PROJECT_NAME}_dev
      POSTGRES_DB: ${PROJECT_NAME}
    volumes:
      - ${PROJECT_NAME}_postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ['CMD-SHELL', 'pg_isready -U ${PROJECT_NAME}']
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: ${PROJECT_NAME}-redis
    ports:
      - "${REDIS_PORT:-6380}:6379"
    volumes:
      - ${PROJECT_NAME}_redis_data:/data

volumes:
  ${PROJECT_NAME}_postgres_data:
  ${PROJECT_NAME}_redis_data:
```

## Troubleshooting

### Port Already in Use
```bash
# Check what's using a port
lsof -i :5433

# Stop conflicting service
docker stop <container-name>
```

### Connection Refused from Container
```bash
# Ensure using host.docker.internal (Mac/Windows)
# Or use host network IP on Linux
ip addr show docker0
```

### Services Not Starting
```bash
# Check Docker compose logs
docker-compose logs postgres

# Verify health status
docker-compose ps
```

## Conclusion

The host-based services approach with port shifting provides the best balance of:
- **Simplicity:** Minimal changes to existing code
- **Compatibility:** Works on all platforms
- **Isolation:** Projects don't interfere with each other
- **Performance:** No nested virtualization overhead

This solution can be implemented immediately and will resolve the current issues with projects like FlowForge that need their own PostgreSQL, Redis, and other services.