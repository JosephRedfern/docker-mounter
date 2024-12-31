# docker-mounter
Utility to mount Docker images locally without requiring container creation. This is useful for analysing contents of
Docker images from within the host operating system without incurring the overhead of container creation.

This tool relies on some potentially unstable docker implementation details, and may break in future Docker versions!

## Compatibility
Due to use of overlay2, tool is only compatible with Linux 3.19+.

It has currently only been tested with Docker version 27.3.1, build ce12230.

## Usage

```bash
 Usage: python -m docker_mounter.mounter [OPTIONS] IMAGE

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
python -m docker_mounter.mounter --mount --pull --mount-point /mnt/docker-image ubuntu:latest
```

### Mount ubuntu:latest image to /mnt/docker-image and do not pull the image
```bash
python -m docker_mounter.mounter --mount --no-pull --mount-point /mnt/docker-image ubuntu:latest
```

### Generate command to mount ubuntu:latest image to /mnt/docker-image but do not mount or pullthe image
```bash
python -m docker_mounter.mounter --mount-point /mnt/docker-image ubuntu:latest
```

### Generate command to mount ubuntu:latest image to /mnt/docker-image but do not mount or pullthe image
```bash
python -m docker_mounter.mounter --mount-point /mnt/docker-image ubuntu:latest
```
