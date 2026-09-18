import logging
import socket
from typing import Tuple
from app.core.config import settings

logger = logging.getLogger("atlas.scanner")

# Standard industry EICAR test signature string
EICAR_SIGNATURE = (
    b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
)


class MalwareScannerService:
    def __init__(self):
        self.enabled = settings.CLAMAV_ENABLED
        self.host = settings.CLAMAV_HOST
        self.port = settings.CLAMAV_PORT
        self.timeout = settings.SCANNER_TIMEOUT_SECONDS

    async def scan_bytes(self, file_bytes: bytes) -> Tuple[bool, str]:
        """
        Scans an in-memory byte buffer.
        Returns:
            (is_clean: bool, threat_name: str)
        """
        # 1. Built-in EICAR signature heuristic check
        if EICAR_SIGNATURE in file_bytes:
            logger.warning("Threat detected via signature match: Eicar-Test-Signature")
            return False, "Eicar-Test-Signature"

        # 2. ClamAV daemon check over network socket if enabled
        if self.enabled:
            return self._scan_clamav(file_bytes)

        # Default clean pass if no threats found and ClamAV is disabled/not required
        return True, ""

    def _scan_clamav(self, file_bytes: bytes) -> Tuple[bool, str]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect((self.host, self.port))

                # ClamAV INSTREAM protocol format: 'zINSTREAM\0' followed by chunk length prefixes
                sock.sendall(b"zINSTREAM\0")

                chunk_size = 2048
                for i in range(0, len(file_bytes), chunk_size):
                    chunk = file_bytes[i : i + chunk_size]
                    size_header = len(chunk).to_bytes(4, byteorder="big")
                    sock.sendall(size_header + chunk)

                # Send 0-length chunk to denote EOF
                sock.sendall((0).to_bytes(4, byteorder="big"))

                response = sock.recv(1024).decode("utf-8", errors="ignore").strip()

                if "OK" in response:
                    return True, ""
                elif "FOUND" in response:
                    # Format: stream: <ThreatName> FOUND
                    threat_parts = response.replace("stream:", "").replace("FOUND", "").strip()
                    logger.warning("ClamAV detected threat: %s", threat_parts)
                    return False, threat_parts
                else:
                    logger.error("Unexpected ClamAV daemon response: %s", response)
                    return False, "Suspicious-Scanner-Error"

        except Exception as exc:
            logger.warning("ClamAV connection failed (%s), defaulting to pass-through.", exc)
            return True, ""


malware_scanner = MalwareScannerService()