# docker-mounter
Utility to mount Docker images locally without requiring container creation. This is useful for analysing contents of
Docker images from within the host operating system without incurring the overhead of container creation.

This tool relies on some potentially unstable docker implementation details, and may break in future Docker versions!

## Installation

This tool can be installed from PyPI using:

```bash
pip install docker-mounter
```

Alternatively, the tool can be installed from source using:

```bash
poetry install
```

## Compatibility
Due to use of overlay2, tool is only compatible with Linux 3.19+.

It has currently only been tested with Docker version 27.3.1, build ce12230.

## Required Permissions
This tool requires:
1. Access to the Docker daemon socket (user must be root or in the docker group)
2. Root privileges when using the `--mount` option

## Usage

```bash
Usage: docker-mount [OPTIONS] IMAGE

╭─ Arguments ─────────────────────────────────────────────────────────╮
│ *    image      TEXT  [default: None] [required]                    │
╰─────────────────────────────────────────────────────────────────────╯
╭─ Options ───────────────────────────────────────────────────────────╮
│ --mount-point                  PATH  [default: None]                │
│ --pull           --no-pull           [default: no-pull]             │
│ --mount          --no-mount          [default: no-mount]            │
│ --help                               Show this message and exit.    │
╰─────────────────────────────────────────────────────────────────────╯
```

## Example Usage

### Mount ubuntu:latest image to /mnt/docker-image and pull the image if it is not present
```bash
sudo docker-mount --mount --pull --mount-point /mnt/docker-image ubuntu:latest
```

### Mount ubuntu:latest image to /mnt/docker-image and do not pull the image
```bash
sudo docker-mount --mount --no-pull --mount-point /mnt/docker-image ubuntu:latest
```

### Generate command to mount ubuntu:latest image to /mnt/docker-image but do not mount or pull the image
```bash
docker-mount --mount-point /mnt/docker-image ubuntu:latest
```
