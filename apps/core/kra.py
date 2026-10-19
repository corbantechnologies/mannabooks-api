"""KRA PINs: 11 characters, A (individuals) or P (companies and other non-individuals), nine digits, a check letter."""
import re

from rest_framework import serializers

PIN = re.compile(r"[AP]\d{9}[A-Z]")


def clean_pin(value: str, *, required: bool = False) -> str:
    """Upper-case and check a KRA PIN; blank is allowed unless `required`."""
    value = (value or "").strip().upper().replace(" ", "")
    if not value and not required:
        return value
    if PIN.fullmatch(value):
        return value
    if value[:1] not in ("A", "P"):
        problem = "It must start with A (a person) or P (a company or other organisation)."
    elif len(value) != 11:
        digits = sum(c.isdigit() for c in value)
        problem = f"It has {len(value)} characters ({digits} digits); a PIN has 11: the letter, nine digits and a letter."
    else:
        problem = "After the first letter come nine digits, then one letter."
    raise serializers.ValidationError(f"Check the KRA PIN. {problem} For example P051234567X or A123456789B.")
