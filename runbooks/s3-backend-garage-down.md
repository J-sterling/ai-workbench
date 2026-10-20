# Self-hosted S3 (Garage) state backend is down

Tags: terraform, s3, garage, docker, state, monitoring

## Symptoms
- Every Terraform run fails at init or workspace selection, e.g.
  `Error: Failed to get existing workspaces: RequestError: send request failed ... dial tcp <host>:3900: connect: connection refused` (or `i/o timeout`).
- Unlike bad credentials (403 / InvalidAccessKeyId), nothing is answering on the S3 port at all.
- The `garage` container is stopped or restarting; its logs show it cannot read `garage.toml`, or the path is a directory.
- Nobody noticed for days: there is no monitoring on the backend.

## Root cause
The container's bind-mounted config file was replaced by an empty directory, typically after a host reboot raced the mount (Docker creates a directory when a bind-mount source file is missing). The data volume and metadata are intact if the container was only stopped, never removed.

## Diagnose
```bash
docker ps -a --filter name=garage
ls -ld /path/to/garage.toml        # "d" at the start means it became a directory
docker volume ls | grep garage
```

## Fix
Remove the empty directory first (`cp` onto a directory copies *into* it and the container still fails), recreate `garage.toml` as a file from version control or backup, then start the container again:
```bash
rmdir /path/to/garage.toml                      # fails safely if it is not empty
cp /path/to/garage.toml.bak /path/to/garage.toml
docker start garage
```
This is config reconstruction, not data recovery: do not delete the volume. Add an uptime monitor (TCP check on port 3900) so the next outage is noticed.

## Needs approval
Restarting the backend container. Never delete or recreate the data volume without explicit approval: it holds all Terraform state.
