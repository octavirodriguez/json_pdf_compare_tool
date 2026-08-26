"""Document-model profiles for model-specific audit rules."""

from .urssaf_autoentrepreneur import UrssafAutoentrepreneurProfile


PROFILES = (UrssafAutoentrepreneurProfile(),)


def detect_profile(pdf_text, json_data):
    """Return the first profile that recognizes the document, if any."""
    return next(
        (profile for profile in PROFILES if profile.detect(pdf_text, json_data)),
        None,
    )