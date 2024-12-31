from pathlib import Path
import pytest
from pytest_mock import MockerFixture
import docker
from docker_mounter.mounter import resolve_and_generate_mount_command, DockerMounterException


@pytest.fixture
def mock_docker_client(mocker: MockerFixture):
    """Create a mock Docker client"""
    mock_client = mocker.patch("docker.from_env")
    return mock_client.return_value


@pytest.fixture
def mock_image(mocker: MockerFixture):
    """Create a mock Docker image"""
    mock = mocker.MagicMock()
    mock.attrs = {
        "RootFS": {
            "Layers": [
                "sha256:layer1",
                "sha256:layer2",
            ]
        }
    }
    return mock


def test_resolve_and_generate_mount_command_cached_image(
    mock_docker_client, mock_image, mocker: MockerFixture
):
    """Test resolving mount command for cached image"""
    mock_docker_client.images.get.return_value = mock_image
    
    # Mock the filesystem operations
    mocker.patch("pathlib.Path.exists", return_value=True)
    mocker.patch("pathlib.Path.open", mocker.mock_open(read_data="test-cache-id"))
    
    mount_point = Path("/tmp/test")
    command, result_mount_point = resolve_and_generate_mount_command(
        "test:latest", mount_point, pull=False
    )
    
    assert isinstance(command, str)
    assert "mount -t overlay" in command
    assert result_mount_point == mount_point
    mock_docker_client.images.get.assert_called_once_with("test:latest")
    mock_docker_client.images.pull.assert_not_called()


def test_resolve_and_generate_mount_command_pull_image(
    mock_docker_client, mock_image, mocker: MockerFixture
):
    """Test resolving mount command with image pull"""
    mock_docker_client.images.get.side_effect = [
        docker.errors.ImageNotFound("Image not found"),
        mock_image,
    ]
    mock_docker_client.images.pull.return_value = mock_image
    
    # Mock the filesystem operations
    mocker.patch("pathlib.Path.exists", return_value=True)
    mocker.patch("pathlib.Path.open", mocker.mock_open(read_data="test-cache-id"))
    
    mount_point = Path("/tmp/test")
    command, result_mount_point = resolve_and_generate_mount_command(
        "test:latest", mount_point, pull=True
    )
    
    assert isinstance(command, str)
    mock_docker_client.images.pull.assert_called_once_with("test:latest")


def test_resolve_and_generate_mount_command_no_pull_failure(mock_docker_client):
    """Test failure when image not found and pull disabled"""
    mock_docker_client.images.get.side_effect = docker.errors.ImageNotFound("Image not found")
    
    with pytest.raises(DockerMounterException):
        resolve_and_generate_mount_command("test:latest", Path("/tmp/test"), pull=False) 