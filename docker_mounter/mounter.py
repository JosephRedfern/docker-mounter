import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

import docker
import typer
from loguru import logger

app = typer.Typer()

"""
Docker images are made up of multiple layers. Each layer contains some subset of the overall filesystem for the container.

When the Docker image is pulled, Docker downloads a bunch of tar files (for each layer), and some metadata. The tar files
are extracted to directories in `/var/lib/docker/overlay2` at pull time. When a container is started, `overlayfs` is used
to mount a merged representation of the layers as a single coherent filesystem. You can find the path to the merged
directory on the host OS by running: `docker inspect CONTAINER_NAME_HERE | jq  '.[0].GraphDriver.Data.MergedDir'`, where
`CONTAINER_NAME_HERE` is the name of a running container.

There is no official way of mounting a Docker image without starting a container - but this is pretty inefficient. 

Alternatively, we can implement this ourselves. We can get a list of layers for an image (rather than a container) with:

    docker inspect hello-world:latest | jq .[0].RootFS.Layers

this gives a list of sha256 hashes for each layer. These layers don't map directly to directories in
`/var/lib/docker/overlay2` - instead a chain ID is used to name the directory. Chain ID is computed in
`compute_chain_id` below.

The computed chain IDs correspond to directories in: `/var/lib/docker/image/overlay2/layerdb/sha256/`. 

For instance, for `nginx:latest`, we get:

[
  "sha256:3e620c160447d1acff162610a533282fc64863123cba28ce40eaf98c17dde780",
  "sha256:880d2e736b16ec27cfe93230185b7fa9123b9b7007914ab06cad3dbcd03deaa0",
  "sha256:2c447934d7f2bbb627efecbd26692a9e28319d38d2936f7511bca77ffb7096de",
  "sha256:d06e03e55b64954a14f3de88bd37021e6c7c6d7d15aec93c6333e59ceb775f38",
  "sha256:d5c9fed2bbd4a673fc59864804e3f6a08cb72447eb5dc631c2f6903fbb089f57",
  "sha256:fc2efc334561650ca0f2be4e0245c176004739f50a5f965add8e6b417c227f03",
  "sha256:d93fefef05de8f71849a265e65bc5df15c67fbe7b14e51cac17794cb9f11ca1f"
]

let's call this aray `layer_hashes`.

The chain IDs here are:

[
    layer_hashes[0],
    sha256(layer_hashes[0] + " " + layer_hashes[1]),
    sha256(sha256(layer_hashes[0] + " " + layer_hashes[1]) + " " + layer_hashes[2]),
    sha256(sha256(sha256(layer_hashes[0] + " " + layer_hashes[1]) + " " + layer_hashes[2]) + " " + layer_hashes[3]),
    ...
]

These chain IDs correspond to directories in `/var/lib/docker/images/overlay2/layerdb/sha256/`. Within those
directories, a file called `cache-id` gives us the directory name in `/var/lib/docker/overlay2` for that layer. It's
fairly convoluted but with this information we can manually construct the merged filesystem for any Docker image.

(note the actual implementation uses ANOTHER layer of indirection, referencing hard links, but this is an
implementation detail!)

Some useful links:
- https://earthly.dev/blog/docker-image-storage-on-host/
- https://askubuntu.com/a/704358
- https://docs.docker.com/engine/storage/drivers/overlayfs-driver/
"""

DOCKER_ROOT = Path("/var/lib/docker")


class DockerMounterException(Exception):
    """
    Base class for exceptions in this module.
    """

    pass


def compute_chain_id(diff_id: str, parent_chain_id: str = "") -> str:
    """
    Compute a layer's ChainID according to Docker's specification.

    ChainID = SHA256(Parent's ChainID + " " + DiffID)
    For the base layer (no parent), ChainID = DiffID

    Args:
        diff_id: The layer's DiffID
        parent_chain_id: The parent layer's ChainID

    Returns:
        The layer's ChainID
    """
    if not parent_chain_id:
        return diff_id

    # Docker concatenates with a spacem
    chain_string = f"{parent_chain_id} {diff_id}"
    return f"sha256:{hashlib.sha256(chain_string.encode()).hexdigest()}"


def compute_chain_ids(diff_ids: list[str]) -> list[str]:
    """
    Compute chain IDs for each layer in a Docker image.

    Args:
        diff_ids: List of layer diff IDs from the Docker image

    Returns:
        List of computed chain IDs corresponding to each layer
    """
    chain_ids = []
    parent_chain_id = ""
    for diff_id in diff_ids:
        chain_id = compute_chain_id(diff_id, parent_chain_id)
        chain_ids.append(chain_id)
        parent_chain_id = chain_id
    return chain_ids


def generate_overlay_mount_command(mount_point: Path, lower_paths: list[Path], upper_dir: Path | None) -> str:
    """
    Generate a mount command for overlayfs.
    """

    if not mount_point.exists():
        raise DockerMounterException(f"Mount point doesn't exist: {mount_point}")

    # If we're given an upper dir, use it. Otherwise, generate a temporary one.
    if upper_dir is None:
        upper_dir = Path(tempfile.mkdtemp())
        logger.info(f"Using temporary upper dir: {upper_dir}")

    # Work dir is required by overlayfs for atomicity of operations... this will require manual cleanup
    work_dir = tempfile.mkdtemp()
    logger.info(f"Using temporary work dir: {work_dir}")
    upper_dir_arg = f",upperdir={upper_dir.resolve()},workdir={work_dir}"

    absolute_lower_paths = [str(path.resolve()) for path in lower_paths]

    return f"mount -t overlay -o lowerdir={':'.join(absolute_lower_paths)}{upper_dir_arg} none {mount_point.resolve()}"


def get_hard_link_paths(chain_ids: list[str], diff_ids: list[str]) -> list[Path]:
    """
    Docker saves space by using hard links for layers. This function returns the list of hard links.

    (note that diff_ids isn't strictly necessary here, but it's convenient to have for debugging)
    """

    hard_links = []

    for i, (chain_id, diff_id) in enumerate(zip(chain_ids, diff_ids)):
        chain_hash_type, chain_hash = chain_id.split(":")

        # Use ChainID to find the cache-id file. This cache-id is the name of the directory in
        # /var/lib/docker/overlay2 that contains the actual layer
        cache_id_path = DOCKER_ROOT / "image" / "overlay2" / "layerdb" / chain_hash_type / chain_hash / "cache-id"
        try:
            with cache_id_path.open() as f:
                cache_id = f.read().strip()
                if not cache_id:
                    raise DockerMounterException(f"Empty cache-id file for layer {diff_id}")
        except FileNotFoundError:
            raise DockerMounterException(f"Can't find cache-id file at {cache_id_path} for layer {diff_id}")

        overlay_directory = DOCKER_ROOT / "overlay2" / cache_id
        if not overlay_directory.exists():
            raise DockerMounterException(f"Overlay directory doesn't exist: {overlay_directory} for layer {diff_id}")

        hard_link_file = overlay_directory / "link"
        if not hard_link_file.exists():
            raise DockerMounterException(f"Hard link file doesn't exist: {hard_link_file} for layer {diff_id}")
        else:
            with hard_link_file.open() as f:
                hard_link = f.read().strip()
                hard_links.append(hard_link)

        logger.debug(f"Found layer {i+1}:")
        logger.debug(f"  ChainID: {chain_id}")
        logger.debug(f"  DiffID:  {diff_id}")
        logger.debug(f"  Path:    {overlay_directory}")
        logger.debug(f"  Hard link: {hard_link}")

    # Get the absolute paths to each layer
    absolute_paths = [DOCKER_ROOT / "overlay2" / "l" / hard_link for hard_link in hard_links]

    return absolute_paths


def resolve_and_generate_mount_command(
    image_name: str,
    mount_point: Path | None = None,
    upper_dir: Path | None = None,
    pull: bool = False,
) -> tuple[str, Path]:
    """
    Generate command to mount a Docker image on the host OS.

    Args:
        image_name: The name of the Docker image to mount
        mount_point: The path to mount the image at
        upper_dir: The path to the upper directory for the mount

    Raises:
        DockerMounterException: If the mount point or image doesn't exist

    Returns:
        The mount command as a string
    """

    client = docker.from_env()

    # Try to get the image from the local cache, optionally pull it if we don't have it
    try:
        image = client.images.get(image_name)
        logger.info(f"Using cached image: {image_name}")
    except docker.errors.ImageNotFound as e:
        if not pull:
            raise DockerMounterException(f"Image not found and pull is disabled: {image_name}") from e
        else:
            try:
                logger.info(f"Pulling image: {image_name}...")
                image = client.images.pull(image_name)
                logger.info(f"Pulled image: {image_name}")
            except (
                docker.errors.APIError,
                docker.errors.ImageNotFound,
                ValueError,
            ) as e:
                raise DockerMounterException(f"Failed to pull image {image_name}") from e

    # Get the DiffIDs from the image metadata
    diff_ids = image.attrs.get("RootFS", {}).get("Layers", [])

    # Compute ChainIDs for each layer - these are used to find the actual layer directories
    chain_ids = compute_chain_ids(diff_ids)

    # Track the hard-links that Docker has generated for each layer (this follows the same pattern as Docker)
    hard_link_paths = get_hard_link_paths(chain_ids, diff_ids)

    logger.debug(f"Hard link paths: {[str(path) for path in hard_link_paths]}")

    if mount_point is None:
        mount_point = Path(tempfile.mkdtemp())
        logger.info(f"Using temporary mount point: {mount_point}")

    mount_command = generate_overlay_mount_command(mount_point, hard_link_paths, upper_dir)

    return mount_command, mount_point


@app.command()
def main(image: str, mount_point: Path | None = None, pull: bool = False, mount: bool = False) -> None:
    try:
        mount_command, mount_point = resolve_and_generate_mount_command(image, mount_point, pull=pull)
    except DockerMounterException as e:
        raise typer.Exit(1) from e

    if mount:
        logger.info(f"Running mount command: {mount_command}")
        process = subprocess.run(mount_command, stdout=subprocess.PIPE, shell=True)
        if process.returncode != 0:
            raise typer.Exit(1) from DockerMounterException(f"Mount failed with return code {process.returncode}")
        else:
            logger.success(f"Mount successful for {image}, mounted at {str(mount_point)}")
            logger.info(f"You can unmount with: `umount {str(mount_point)}`")
    else:
        logger.info(f"Mount command: {mount_command}")
        logger.info(f"Mount point: {str(mount_point)}")
