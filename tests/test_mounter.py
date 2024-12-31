from pathlib import Path
import pytest
from docker_mounter.mounter import (
    compute_chain_id,
    compute_chain_ids,
    DockerMounterException,
    generate_overlay_mount_command,
)


def test_compute_chain_id_base_layer():
    """Test computing chain ID for base layer (no parent)"""
    diff_id = "sha256:1234567890"
    result = compute_chain_id(diff_id)
    assert result == diff_id


def test_compute_chain_id_with_parent():
    """Test computing chain ID for layer with parent"""
    parent_chain_id = "sha256:1234567890"
    diff_id = "sha256:abcdef0123"
    result = compute_chain_id(diff_id, parent_chain_id)
    # This is the actual SHA256 hash of "sha256:1234567890 sha256:abcdef0123"
    expected = "sha256:83883872ef1b9b916151696045bcc621c9e0b12bb498636c7a42cfe29185f3aa"
    assert result == expected


def test_compute_chain_ids():
    """Test computing chain IDs for multiple layers"""
    diff_ids = [
        "sha256:1234567890",
        "sha256:abcdef0123",
        "sha256:9876543210",
    ]
    result = compute_chain_ids(diff_ids)
    assert len(result) == 3
    assert result[0] == diff_ids[0]  # First layer should be same as diff_id
    # Other layers should be computed based on their parent


def test_generate_overlay_mount_command(mocker):
    """Test generating overlay mount command"""
    # Mock Path.exists to return True
    mocker.patch("pathlib.Path.exists", return_value=True)
    
    # Mock Path.resolve to return predictable paths
    def mock_resolve(self):
        return f"/resolved{str(self)}"
    mocker.patch.object(Path, "resolve", mock_resolve)
    
    mount_point = Path("/tmp/test")
    lower_paths = [Path("/lower1"), Path("/lower2")]
    upper_dir = Path("/upper")
    
    result = generate_overlay_mount_command(mount_point, lower_paths, upper_dir)
    
    assert "mount -t overlay" in result
    assert "lowerdir=/resolved/lower1:/resolved/lower2" in result
    assert "upperdir=/resolved/upper" in result
    assert "/resolved/tmp/test" in result


def test_generate_overlay_mount_command_nonexistent_mount_point(mocker):
    """Test generating overlay mount command with nonexistent mount point"""
    # Mock Path.exists to return False for mount point
    mocker.patch("pathlib.Path.exists", return_value=False)
    
    mount_point = Path("/nonexistent")
    lower_paths = [Path("/lower1")]
    
    with pytest.raises(DockerMounterException):
        generate_overlay_mount_command(mount_point, lower_paths, None) 