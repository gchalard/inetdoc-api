# utils/schemas.py


from schema import And, Optional, Or, Schema, SchemaError, Regex
from typing import Any, Dict
import sys

from utils.constants import ALLOWED_OS
from utils.console_attr import ConsoleAttr, console_print

tap_schema = Schema(
    {
        "tap_name": And(str, Regex(r'^tap[0-9]*$')),
        "mode": And(str, lambda mode : mode in ["access", "trunk"]),
        "tapnum": int,
        Optional("tag"): Optional(int),
        Optional("trunks"): Optional([int])
        
    }
)

def validate_tap(data: Dict[str, Any], **kwargs: Dict[str, Any]):
    
    print(f"Validating schema with data : {data}")
    
    if data.get("mode") == "access" and "trunks" not in data:
        schema = Schema(
            {
                "tap_name": And(str, Regex(r'^tap[0-9]*$')),
                "mode": And(str, lambda mode : mode == "access"),
                "tapnum": int,
                "tag": int
            }
        )
        try:
            schema.validate(data)
        except SchemaError as e:
            raise SchemaError(f"Base schema validation error: {e}")

    # If mode is "trunk", ensure "trunks" is present
    if data.get("mode") == "trunk" and "tag" not in data:
        schema = Schema(
            {
                "tap_name": And(str, Regex(r'^tap[0-9]*$')),
                "mode": And(str, lambda mode : mode == "trunk"),
                "tapnum": int,
                "trunks": [int]
            }
        )
        try:
            schema.validate(data)
        except SchemaError as e:
            raise SchemaError(f"Base schema validation error: {e}")
    
    print("Base schema validated")

    # Additional conditional validation
    if data.get("mode") == "access" and "tag" not in data:
        raise SchemaError("'tag' is required when 'mode' is 'access'.")

    # If mode is "trunk", ensure "trunks" is present
    if data.get("mode") == "trunk" and "trunks" not in data:
        raise SchemaError("'trunks' is required when 'mode' is 'trunk'.")    
    
image_schema = Schema(
    {
        "name": str,
        "url": str,
        Optional("packages"): Optional([str])
    }
)

linux_schema = Schema(
    {
        "vm_name": str,
        "os": "linux",
        "master_image": str,
        "force_copy": bool,
        "memory": And(int, lambda n: n >= 512),
        "tapnum": int,
        Optional("cloud_init"): {
            Optional("force_seed"): bool,
            Optional("users"): [
                {"name": str, "sudo": str, Optional("ssh_authorized_keys"): [str]}
            ],
            Optional("hostname"): str,
            Optional("packages"): [str],
            Optional("netplan"): dict,
            Optional("write_files"): [
                {"path": str, "content": str, Optional("append"): bool}
            ],
            Optional("runcmd"): [Or(str, [str])],
        },
        Optional("devices"): dict,
    }
)

iosxe_schema = Schema(
    {
        "vm_name": str,
        "os": "iosxe",
        "master_image": str,
        "force_copy": bool,
        "tapnumlist": And([int], lambda l : len(l) == len(set(l))),
    }
)

windows_schema = Schema(
    {
        "vm_name": str,
        "os": "windows",
        "master_image": str,
        "force_copy": bool,
        "memory": And(int, lambda n: n >= 512),
        "tapnum": int,
        Optional("devices"): dict,
    }
)

def validate_image(data: Any, **kwargs: Dict[str, Any]):
    image_schema.validate(data=data)

def validate_schema(vm: dict):
    """Validate virtual machine YAML declaration against predefined schemas.

    This function validates the virtual machine declaration against the appropriate
    schema based on the OS type (linux, windows, or iosxe). Each schema defines
    the required and optional fields for that OS type.

    Args:
        vm (dict): Virtual machine declaration to validate.
            Example:
            {
                'vm_name': 'vm1',
                'os': 'linux',
                'master_image': 'debian-testing-amd64.qcow2',
                'force_copy': False,
                'memory': 2048,
                'tapnum': 1
            }

    Raises:
        KeyError: If 'os' is not in the VM dict.
        ValueError: If the OS is not yet supported.
        SchemaError: If VM declaration doesn't match the schema.
        SystemExit: If schema validation fails.

    Example:
        >>> vm = {'vm_name': 'vm1', 'os': 'linux', ...}
        >>> validate_schema(vm)
    """

    if not 'os' in vm:
        raise KeyError("The provided VM declaration is missing the required 'os' field.")
    
    if vm['os'] not in ALLOWED_OS:
        raise ValueError(f"The OS type must be one of {', '.join(ALLOWED_OS)}.")
    
    try:
        if vm["os"] == "linux":
            linux_schema.validate(vm)
        elif vm["os"] == "windows":
            windows_schema.validate(vm)
        elif vm["os"] == "iosxe":
            iosxe_schema.validate(vm)

    except SchemaError as e:
        console_print(
            f"Error in VM '{vm.get('vm_name', 'unknown')}': {str(e)}", ConsoleAttr.ERROR
        )
        sys.exit(1)