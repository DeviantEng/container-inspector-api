#!/usr/bin/env python3
"""
Docker Container Inspector API
FastAPI service to inspect Docker containers across multiple hosts
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import subprocess
import json
import os

app = FastAPI(
    title="Docker Container Inspector API",
    description="API to inspect Docker containers across multiple hosts",
    version="1.0.0"
)

# Enable CORS for Grafana
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration - read from environment or default to localhost
DOCKER_HOSTS = os.getenv("DOCKER_HOSTS", "localhost").split(",")
DOCKER_HOSTS = [host.strip() for host in DOCKER_HOSTS]  # Remove any whitespace
LOCAL_HOST = os.getenv("LOCAL_HOST", "false").strip().lower()

# Determine if we have a local host that can use docker socket
USE_LOCAL_SOCKET = LOCAL_HOST != "false" and os.path.exists("/var/run/docker.sock")


class ContainerInfo(BaseModel):
    name: str
    host: str
    image: str
    state: str
    status: str


class ContainerList(BaseModel):
    containers: List[ContainerInfo]


def run_ssh_command(host: str, command: str) -> tuple[str, str, int]:
    """Execute command via SSH on remote host, or locally via docker socket if it's the local host"""
    
    # Check if this is the local host and we should use docker socket
    if USE_LOCAL_SOCKET and host == LOCAL_HOST and command.startswith("docker "):
        try:
            result = subprocess.run(
                ["bash", "-c", command],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", "Command timed out", 1
        except Exception as e:
            return "", str(e), 1
    
    # Use SSH for remote hosts or if local socket is not available
    cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5", f"root@{host}", command]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", 1
    except Exception as e:
        return "", str(e), 1


@app.get("/")
def read_root():
    """Health check endpoint"""
    return {
        "service": "Docker Container Inspector API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/api/containers", response_model=ContainerList)
def list_containers():
    """List all containers across all Docker hosts"""
    all_containers = []
    
    for host in DOCKER_HOSTS:
        # Get container list in JSON format
        command = 'docker ps -a --format "{{json .}}"'
        stdout, stderr, returncode = run_ssh_command(host, command)
        
        if returncode != 0:
            continue
        
        # Parse each line as JSON
        for line in stdout.strip().split('\n'):
            if not line:
                continue
            try:
                container = json.loads(line)
                all_containers.append(ContainerInfo(
                    name=container.get('Names', 'unknown'),
                    host=host,
                    image=container.get('Image', 'unknown'),
                    state=container.get('State', 'unknown'),
                    status=container.get('Status', 'unknown')
                ))
            except json.JSONDecodeError:
                continue
    
    return ContainerList(containers=all_containers)


@app.get("/api/container/{container_name}/logs")
def get_container_logs(
    container_name: str,
    host: str = Query(..., description="Docker host where container is running"),
    tail: int = Query(500, description="Number of log lines to return", ge=1, le=10000),
    since: Optional[str] = Query(None, description="Show logs since timestamp (e.g. 2023-01-01T00:00:00)")
):
    """Get logs from a specific container"""
    command = f"docker logs --tail {tail}"
    if since:
        command += f" --since {since}"
    command += f" {container_name}"
    
    stdout, stderr, returncode = run_ssh_command(host, command)
    
    if returncode != 0:
        raise HTTPException(status_code=404, detail=f"Container not found or error: {stderr}")
    
    # Docker logs go to both stdout and stderr, combine them
    logs = stdout + stderr
    
    return {
        "container": container_name,
        "host": host,
        "lines": tail,
        "logs": logs
    }


@app.get("/api/container/{container_name}/inspect")
def inspect_container(
    container_name: str,
    host: str = Query(..., description="Docker host where container is running")
):
    """Get full docker inspect output for a container"""
    command = f"docker inspect {container_name}"
    
    stdout, stderr, returncode = run_ssh_command(host, command)
    
    if returncode != 0:
        raise HTTPException(status_code=404, detail=f"Container not found: {stderr}")
    
    try:
        inspect_data = json.loads(stdout)
        return {
            "container": container_name,
            "host": host,
            "inspect": inspect_data[0] if inspect_data else {}
        }
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse inspect output: {str(e)}")


@app.get("/api/container/{container_name}/compose")
def get_compose_file(
    container_name: str,
    host: str = Query(..., description="Docker host where container is running")
):
    """Get the docker-compose.yml file for a container"""
    # Try to find the compose file by looking at container labels
    command = f"docker inspect {container_name} --format '{{{{index .Config.Labels \"com.docker.compose.project.working_dir\"}}}}'"
    
    stdout, stderr, returncode = run_ssh_command(host, command)
    
    if returncode != 0 or not stdout.strip():
        raise HTTPException(status_code=404, detail="Could not find compose project directory")
    
    compose_dir = stdout.strip()
    
    # Read the compose file
    command = f"cat {compose_dir}/docker-compose.yml"
    stdout, stderr, returncode = run_ssh_command(host, command)
    
    if returncode != 0:
        raise HTTPException(status_code=404, detail=f"Compose file not found: {stderr}")
    
    return {
        "container": container_name,
        "host": host,
        "compose_file_path": f"{compose_dir}/docker-compose.yml",
        "compose_content": stdout
    }


@app.get("/api/container/{container_name}/env")
def get_container_env(
    container_name: str,
    host: str = Query(..., description="Docker host where container is running")
):
    """Get environment variables for a container"""
    command = f"docker inspect {container_name} --format '{{{{json .Config.Env}}}}'"
    
    stdout, stderr, returncode = run_ssh_command(host, command)
    
    if returncode != 0:
        raise HTTPException(status_code=404, detail=f"Container not found: {stderr}")
    
    try:
        env_list = json.loads(stdout)
        # Convert list of "KEY=VALUE" to dict
        env_dict = {}
        for env_var in env_list:
            if '=' in env_var:
                key, value = env_var.split('=', 1)
                env_dict[key] = value
        
        return {
            "container": container_name,
            "host": host,
            "environment": env_dict
        }
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse environment: {str(e)}")


@app.get("/api/container/{container_name}/stats")
def get_container_stats(
    container_name: str,
    host: str = Query(..., description="Docker host where container is running")
):
    """Get real-time container stats (single snapshot)"""
    command = f"docker stats {container_name} --no-stream --format '{{{{json .}}}}'"
    
    stdout, stderr, returncode = run_ssh_command(host, command)
    
    if returncode != 0:
        raise HTTPException(status_code=404, detail=f"Container not found: {stderr}")
    
    try:
        stats = json.loads(stdout)
        return {
            "container": container_name,
            "host": host,
            "stats": stats
        }
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse stats: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
