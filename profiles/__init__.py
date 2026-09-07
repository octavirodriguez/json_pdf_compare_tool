"""Document-model profiles for model-specific audit rules."""

from .es_aeat_modelo_100 import EsAeatModelo100Profile
from .es_ss_vida_laboral import EsSsVidaLaboralProfile
from .fr_urssaf_autoentrepreneur import FrUrssafAutoentrepreneurProfile
from .it_agenzia_entrate_certificazione_unica import ItAgenziaEntrateCertificazioneUnicaProfile
from .it_agenzia_entrate_ricevuta import ItAgenziaEntrateRicevutaProfile
from .it_anpr_certificato import ItAnprCertificatoProfile
from .it_inps_estratto_conto import ItInpsEstrattoContoProfile


PROFILES = (
    EsAeatModelo100Profile(),
    EsSsVidaLaboralProfile(),
    FrUrssafAutoentrepreneurProfile(),
    ItAgenziaEntrateCertificazioneUnicaProfile(),
    ItAgenziaEntrateRicevutaProfile(),
    ItAnprCertificatoProfile(),
    ItInpsEstrattoContoProfile(),
)


def detect_profile(pdf_text, json_data):
    """Return the first profile that recognizes the document, if any."""
    return next(
        (profile for profile in PROFILES if profile.detect(pdf_text, json_data)),
        None,
    )