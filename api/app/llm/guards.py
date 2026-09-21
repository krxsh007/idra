from __future__ import annotations

import re

# Regex pattern matching integer or float numbers (including commas in numbers like 1,000)
NUMBER_REGEX = re.compile(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b")

# Certainty language / absolute claims forbidden in disaster decision support summaries
FORBIDDEN_CERTAINTY_PATTERNS = [
    re.compile(r"\bguaranteed\b", re.IGNORECASE),
    re.compile(r"\bguarantee\b", re.IGNORECASE),
    re.compile(r"\b100%\s*(?:safe|certain|secure|casualty-free)\b", re.IGNORECASE),
    re.compile(r"\bcompletely\s+(?:safe|contained|eliminated|prevented)\b", re.IGNORECASE),
    re.compile(r"\bzero\s+risk\b", re.IGNORECASE),
    re.compile(r"\bno\s+danger\b", re.IGNORECASE),
    re.compile(r"\bundoubtedly\b", re.IGNORECASE),
    re.compile(r"\bwithout\s+a\s+doubt\b", re.IGNORECASE),
]


def fence_untrusted_input(text: str, label: str = "untrusted_input") -> str:
    """Sanitize and enclose untrusted user/citizen text into XML fences."""
    sanitized = text.replace("<", "&lt;").replace(">", "&gt;")
    return f"<{label}>\n{sanitized}\n</{label}>"


def check_numeric_consistency(
    generated_text: str,
    allowed_numbers: set[int | float],
    tolerance: float = 0.05,
) -> list[str]:
    """Flag numbers appearing in generated text that are not present in allowed_numbers.

    Returns a list of warning messages for unrecognized numbers.
    """
    warnings: list[str] = []
    found_matches = NUMBER_REGEX.findall(generated_text)

    for match_str in found_matches:
        cleaned_num_str = match_str.replace(",", "")
        try:
            val = float(cleaned_num_str)
        except ValueError:
            continue

        # Small integers (0, 1, 2) often represent counts, days, or ranks and are common in phrasing
        if val in (0, 1, 2):
            continue

        is_present = False
        for allowed in allowed_numbers:
            diff = abs(allowed - val)
            rel = diff / max(abs(allowed), 1e-6)
            if diff <= tolerance or rel <= tolerance:
                is_present = True
                break

        if not is_present:
            warnings.append(f"Unverified numeric claim '{match_str}' found in generated response.")

    return warnings


def check_forbidden_language(generated_text: str) -> list[str]:
    """Detect overconfident certainty language or unsubstantiated absolutes.

    Returns a list of violation descriptions.
    """
    violations: list[str] = []
    for pattern in FORBIDDEN_CERTAINTY_PATTERNS:
        match = pattern.search(generated_text)
        if match:
            phrase = match.group(0)
            violations.append(
                f"Forbidden certainty phrase '{phrase}' violates disaster advisory safety rules."
            )
    return violations
