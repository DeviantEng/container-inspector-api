# Docker Container Inspector API

FastAPI-based service to inspect Docker containers across multiple hosts for use with Grafana dashboards.

## Features

- List all containers across multiple Docker hosts
- Get container logs (with tail and since filters)
- Get full `docker inspect` output
- Retrieve docker-compose.yml file contents
- Get container environment variables
- Get real-time container stats

## Prerequisites

- SSH key-based authentication configured between monitoring host and Docker hosts
- Root SSH access to all Docker hosts

## Building

```bash
docker build -t ghcr.io/yourusername/container-inspector-api:latest .
```

## Running

### Using Docker Compose (Recommended)

1. Update the image name in `docker-compose.yml` with your GitHub Container Registry username
2. Deploy:

```bash
docker compose up -d
```

### Standalone Docker

```bash
docker run -d \
  --name container-inspector-api \
  -p 8000:8000 \
  -v /root/.ssh:/root/.ssh:ro \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  ghcr.io/yourusername/container-inspector-api:latest
```

## API Endpoints

### Health Check
```
GET /
```

### List All Containers
```
GET /api/containers
```

Returns list of all containers across all configured hosts.

### Get Container Logs
```
GET /api/container/{container_name}/logs?host=docker01&tail=500&since=2024-01-01T00:00:00
```

**Parameters:**
- `host` (required): Docker host where container is running
- `tail` (optional, default=500): Number of log lines to return (1-10000)
- `since` (optional): Show logs since timestamp

### Get Container Inspect
```
GET /api/container/{container_name}/inspect?host=docker01
```

Returns full `docker inspect` JSON output.

### Get Compose File
```
GET /api/container/{container_name}/compose?host=docker01
```

Returns the docker-compose.yml file contents for the container's project.

### Get Environment Variables
```
GET /api/container/{container_name}/env?host=docker01
```

Returns container environment variables as key-value pairs.

### Get Container Stats
```
GET /api/container/{container_name}/stats?host=docker01
```

Returns real-time container resource usage statistics (single snapshot).

## Configuration

The API reads Docker hosts from environment variables:

**DOCKER_HOSTS** - Comma-separated list of Docker hosts to query:
```bash
DOCKER_HOSTS=docker01,docker02,docker03
```
**Default:** `localhost` (local Docker only)

**LOCAL_HOST** - Which host in DOCKER_HOSTS is the local host (uses Docker socket instead of SSH):
```bash
LOCAL_HOST=docker01
```
**Default:** `false` (all hosts use SSH)

Set `LOCAL_HOST=false` if the API is not running on any of the Docker hosts (e.g., separate monitoring server).

Edit `docker-compose.yml` or pass via command line:

```bash
docker run -e DOCKER_HOSTS=docker01,docker02,docker03 -e LOCAL_HOST=docker01 ...
```

**Example configurations:**

Running on docker01:
```yaml
environment:
  - DOCKER_HOSTS=docker01,docker02,docker03
  - LOCAL_HOST=docker01
```

Running on a separate monitoring server:
```yaml
environment:
  - DOCKER_HOSTS=docker01,docker02,docker03
  - LOCAL_HOST=false
```

## Security Considerations

- This API requires root SSH access to Docker hosts
- No authentication is implemented - use within trusted networks only
- Consider adding authentication/authorization for production use
- Runs on port 8000 by default

## Integration with Grafana

Use Grafana's **Infinity** or **JSON API** datasource to query this API:

1. Install Infinity datasource plugin in Grafana
2. Create a new Infinity datasource pointing to `http://container-inspector-api:8000`
3. Create panels that query the API endpoints

Example Infinity datasource query for container list:
- URL: `http://container-inspector-api:8000/api/containers`
- Parser: Backend
- Format: JSON

## License

MIT
