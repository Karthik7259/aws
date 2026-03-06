from __future__ import annotations

import os
import subprocess
from pathlib import Path


class OtpDeliveryError(Exception):
    pass


def send_otp_email(*, email: str, otp: str) -> None:
    backend_root = Path(__file__).resolve().parents[2]
    script_path = backend_root / "scripts" / "send-otp-email.mjs"

    if not script_path.exists():
        raise OtpDeliveryError(f"Missing Nodemailer script at {script_path}")

    command = ["node", str(script_path), email, otp]

    process = subprocess.run(
        command,
        cwd=backend_root,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        check=False,
    )

    if process.returncode != 0:
        stderr = process.stderr.strip() or process.stdout.strip() or "Unknown mailer error"
        raise OtpDeliveryError(stderr)


def send_admin_access_granted_email(*, email: str, full_name: str, department: str) -> None:
    backend_root = Path(__file__).resolve().parents[2]
    script_path = backend_root / "scripts" / "send-admin-access-email.mjs"

    if not script_path.exists():
        raise OtpDeliveryError(f"Missing access email script at {script_path}")

    command = ["node", str(script_path), email, full_name, department]

    process = subprocess.run(
        command,
        cwd=backend_root,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        check=False,
    )

    if process.returncode != 0:
        stderr = process.stderr.strip() or process.stdout.strip() or "Unknown mailer error"
        raise OtpDeliveryError(stderr)
