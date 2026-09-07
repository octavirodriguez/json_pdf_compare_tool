"""Document-model profiles for model-specific audit rules."""

from .aeat_modelo_100 import AeatModelo100Profile
from .agenzia_entrate_certificazione_unica import AgenziaEntrateCertificazioneUnicaProfile
from .anpr import AnprProfile
from .inps import InpsProfile
from .ricevuta_agenzia_entrate import RicevutaAgenziaEntrateProfile
from .urssaf_autoentrepreneur import UrssafAutoentrepreneurProfile


PROFILES = (
    UrssafAutoentrepreneurProfile(),
    AeatModelo100Profile(),
    AnprProfile(),
    AgenziaEntrateCertificazioneUnicaProfile(),
    InpsProfile(),
    RicevutaAgenziaEntrateProfile(),
)


def detect_profile(pdf_text, json_data):
    """Return the first profile that recognizes the document, if any."""
    return next(
        (profile for profile in PROFILES if profile.detect(pdf_text, json_data)),
        None,
    )