import os
import subprocess
from pathlib import Path


def test_install_systemd_script_creates_service_and_env(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    systemd_dir = tmp_path / "systemd-system"
    etc_dir = tmp_path / "etc"

    result = subprocess.run(
        ["bash", str(repo_root / "scripts" / "install_systemd.sh")],
        cwd=repo_root,
        env={
            **os.environ,
            "SYSTEMD_DIR": str(systemd_dir),
            "ETC_DIR": str(etc_dir),
            "RUN_USER": "pi",
            "SKIP_SYSTEMCTL": "1",
        },
        capture_output=True,
        text=True,
        check=True,
    )

    service_path = systemd_dir / "stock-alert-bot.service"
    env_path = etc_dir / "stock-alert-bot.env"

    assert service_path.exists()
    assert env_path.exists()
    service_text = service_path.read_text(encoding="utf-8")
    assert "User=pi" in service_text
    assert "python3 bot.py --scheduler" in service_text
    assert str(repo_root) in service_text
    assert "Created env file" in result.stdout
