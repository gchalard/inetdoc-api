# utils/constants.py

from pathlib import Path

### CONSTANTS ###

MASTER_DIR = Path.home() / "masters"
TEMPLATE_DIR = Path.joinpath(MASTER_DIR, "scripts/templates")
OVMF_CODE = Path("/usr/share/OVMF/OVMF_CODE_4M.secboot.fd")
OVMF_VARS = Path("/usr/share/OVMF/OVMF_VARS_4M.ms.fd")
CLOUD_INIT_FILES_DIR = Path.cwd() / "cloud_init_files"

CLOUD_INIT_NETPLAN_FILE = "/etc/netplan/50-cloud-init.yaml"
ALLOWED_OS=["linux", "ioxe", "windows"]
ALLOWED_CONFIG_TYPE=["cloud-config", "network-config"]