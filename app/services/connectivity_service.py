"""
Service untuk test konektivitas SSH ke device jaringan.
"""
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException
from sqlmodel import Session

from app.database import engine
from app.logging_config import get_logger
from app.models import Device
from app.services.base_service import BaseNetworkService

logger = get_logger(__name__)
_service = BaseNetworkService()

CONNECT_TIMEOUT = 10  # detik


def test_device_connection(device_id: int) -> dict:
    """
    Test SSH connectivity ke device. Timeout 10 detik.
    Return: {"status": "online"|"offline"|"auth_error", "message": str, "prompt": str|None}
    """
    with Session(engine) as session:
        device = session.get(Device, device_id)
        if not device:
            return {"status": "error", "message": "Device not found", "prompt": None}
        if not device.credential:
            return {"status": "error", "message": "No credential assigned", "prompt": None}

        try:
            params = _service._build_device_params(device)
            params["timeout"] = CONNECT_TIMEOUT
            params["banner_timeout"] = CONNECT_TIMEOUT
            params.pop("global_delay_factor", None)

            with ConnectHandler(**params) as conn:
                prompt = conn.find_prompt()

            logger.info(f"Connection test OK: {device.hostname} ({device.ip_address}) → prompt: {prompt}")
            return {"status": "online", "message": f"Connected — prompt: {prompt}", "prompt": prompt}

        except NetmikoAuthenticationException:
            logger.warning(f"Auth failed for {device.hostname}")
            return {"status": "auth_error", "message": "Authentication failed", "prompt": None}
        except NetmikoTimeoutException:
            logger.warning(f"Timeout connecting to {device.hostname}")
            return {"status": "offline", "message": "Connection timed out", "prompt": None}
        except Exception as e:
            logger.warning(f"Connection test failed for {device.hostname}: {e}")
            return {"status": "offline", "message": str(e), "prompt": None}
