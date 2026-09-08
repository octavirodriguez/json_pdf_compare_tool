"""Tests for document-profile detection and profile-specific comparison rules."""

from auditor import compare_json_with_pdf
from profiles import detect_profile


class TestDocumentProfiles:
    def test_urssaf_zero_amounts_match_with_profile(self):
        pdf = (
            "DÉCLARATION MENSUELLE DE CHIFFRE D'AFFAIRES\n"
            "Régime micro-social simplifié\n"
            "Chiffre d'affaires des ventes de marchandises\n0 €\n"
            "Cotisations, contributions et impôts\n0 €\n"
        )
        profile = detect_profile(pdf, {})
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {
                "declaration": {"chiffreAffairesDesVentesDeMarchandises": "0"},
                "montantAPayer": {"cotisationsEtContributions": [{"montant": "0"}]},
            },
            pdf,
            profile=profile,
        )
        assert any("chiffreAffairesDesVentesDeMarchandises" in path for path, _ in matches)
        assert any("cotisationsEtContributions[0].montant" in path for path, _ in matches)
        assert not mismatches
        assert not unverifiable

    def test_aeat_modelo_100_short_codes_match_with_profile(self):
        pdf = (
            "Agencia Tributaria Impuesto sobre la Renta de las Personas Físicas\n"
            "Modelo 100\nEstado civil (el 31-12-2025) (2) Casado/a 0007\n"
            "Situación. 1 0065\n"
        )
        profile = detect_profile(pdf, {})
        assert profile.name == "aeat_modelo_100"
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"estadoCivil": "2", "inmuebles": [{"situacion": "1"}]},
            pdf,
            profile=profile,
        )
        assert ("estadoCivil", "2") in matches
        assert ("inmuebles[0].situacion", "1") in matches
        assert not mismatches
        assert not unverifiable

    def test_aeat_modelo_100_unanchored_short_code_remains_unverifiable(self):
        pdf = "Agencia Tributaria\nModelo 100\nCódigo interno: 1\n"
        profile = detect_profile(pdf, {})
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"codigo": "1"}, pdf, profile=profile
        )
        assert not matches and not mismatches
        assert unverifiable == [("codigo", "1")]

    def test_aeat_modelo_303_profile_matches_period(self):
        pdf = "Agencia Tributaria\nImpuesto sobre el Valor Añadido\nModelo 303 Autoliquidación\nEjercicio 2025 Período 4T\n"
        profile = detect_profile(pdf, {})
        assert profile.name == "aeat_modelo_303_iva_autoliquidacion"
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"devengo": {"periodo": "4T"}}, pdf, profile=profile
        )
        assert ("devengo.periodo", "4T") in matches
        assert not mismatches and not unverifiable

    def test_detects_aeat_modelo_390_profile(self):
        pdf = "Agencia Tributaria\nImpuesto sobre el Valor Añadido\nModelo 390\nDeclaración-Resumen anual\n"
        profile = detect_profile(pdf, {})
        assert profile.name == "aeat_modelo_390_iva_resumen_anual"

    def test_datos_fiscales_matches_name_and_nif(self):
        pdf = (
            "Consulta de Datos Fiscales\n"
            "DATOS IDENTIFICATIVOS\n"
            "NIF:\n12345678Z\n"
            "NOMBRE:\nTEST PERSON\n"
            "DOMICILIO FISCAL\n"
        )
        profile = detect_profile(pdf, {})
        assert profile.name == "aeat_datos_fiscales"

        matches, mismatches, unverifiable = compare_json_with_pdf(
            {
                "informacionPersonal": {
                    "identificacion": "12345678Z",
                    "nombre": "TEST PERSON",
                }
            },
            pdf,
            profile=profile,
        )

        assert ("informacionPersonal.identificacion", "12345678Z") in matches
        assert ("informacionPersonal.nombre", "TEST PERSON") in matches
        assert not mismatches
        assert not unverifiable

    def test_aeat_modelo_303_unanchored_short_code_remains_unverifiable(self):
        pdf = "Agencia Tributaria\nImpuesto sobre el Valor Añadido\nModelo 303 Autoliquidación\nCódigo interno 4T\n"
        profile = detect_profile(pdf, {})
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"codigo": "4T"}, pdf, profile=profile
        )
        assert not matches and not mismatches
        assert unverifiable == [("codigo", "4T")]

    def test_detects_anpr_profile(self):
        profile = detect_profile(
            "Protocollo ANPR: 4476086914\nCertificato contestuale Anagrafico di nascita\nAnagrafe Nazionale della Popolazione Residente",
            {},
        )
        assert profile.name == "anpr"

    def test_detects_agenzia_entrate_certification_profile(self):
        profile = detect_profile(
            "DATI ANAGRAFICI\nCERTIFICAZIONE LAVORO DIPENDENTE\nCertificazione redditi",
            {},
        )
        assert profile.name == "agenzia_entrate_certificazione_unica"

    def test_detects_inps_profile(self):
        profile = detect_profile(
            "Estratto conto previdenziale\nRegime generale\nCodice fiscale", {}
        )
        assert profile.name == "inps"

    def test_vida_laboral_profile_matches_visible_fields(self):
        pdf = (
            "INFORME DE VIDA LABORAL\nTesorería General de la Seguridad Social\n"
            "INFORME DE VIDA LABORAL - SITUACIONES\n"
            "nacido/a el 6 de octubre de 1981\nD.N.I. 04715345G\n"
            "22 Años 8.308 días 9 meses 0 días\n"
        )
        profile = detect_profile(pdf, {})
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {
                "informacionPersonal": {"fechaNacimiento": "1981-10-06", "identificacion": "04715345G"},
                "resumen": {"periodoAlta": {"anos": "22", "meses": "9", "dias": "8308"}},
            },
            pdf,
            profile=profile,
        )
        assert ("informacionPersonal.fechaNacimiento", "1981-10-06") in matches
        assert not mismatches and not unverifiable

    def test_vida_laboral_unrelated_short_code_remains_unverifiable(self):
        pdf = "INFORME DE VIDA LABORAL\nTesorería General de la Seguridad Social\nINFORME DE VIDA LABORAL - SITUACIONES\n"
        profile = detect_profile(pdf, {})
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"codigoInterno": "1"}, pdf, profile=profile
        )
        assert not matches and not mismatches
        assert unverifiable == [("codigoInterno", "1")]

    def test_vida_laboral_profile_matches_table_values(self):
        pdf = (
            "INFORME DE VIDA LABORAL\nTesorería General de la Seguridad Social\n"
            "INFORME DE VIDA LABORAL - SITUACIONES\n"
            "01.09.2025 01.09.2025 31.08.2025 401 --- 01 1\n"
        )
        profile = detect_profile(pdf, {})
        assert profile.name == "seguridad_social_vida_laboral"
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"situaciones": [{"grupoCotizacion": "01", "dias": "1"}]},
            pdf,
            profile=profile,
        )
        assert ("situaciones[0].grupoCotizacion", "01") in matches
        assert ("situaciones[0].dias", "1") in matches
        assert not mismatches and not unverifiable

    def test_detects_seguridad_social_bases_cotizacion_profile(self):
        profile = detect_profile(
            "INFORME INTEGRAL DE BASES DE COTI\nZACIÓN\nRégimen: GENERAL\nEnero Febrero Marzo\n",
            {},
        )
        assert profile.name == "seguridad_social_bases_cotizacion"

    def test_detects_ricevuta_agenzia_profile(self):
        profile = detect_profile(
            "COMUNICAZIONE DI AVVENUTO RICEVIMENTO\nDichiarazione 730 2024\nProtocollo",
            {},
        )
        assert profile.name == "ricevuta_agenzia_entrate"

    def test_vida_laboral_matches_identification_when_present(self):
        pdf = (
            "INFORME DE VIDA LABORAL\nTesorería General de la Seguridad Social\n"
            "INFORME DE VIDA LABORAL - SITUACIONES\nIdentificación: Y3475110P\n"
        )
        profile = detect_profile(pdf, {})
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"informacionPersonal": {"identificacion": "Y3475110P"}},
            pdf,
            profile=profile,
        )
        assert ("informacionPersonal.identificacion", "Y3475110P") in matches
        assert not mismatches and not unverifiable

    def test_vida_laboral_identification_ignores_leading_zero(self):
        pdf = (
            "INFORME DE VIDA LABORAL\nTesorería General de la Seguridad Social\n"
            "INFORME DE VIDA LABORAL - SITUACIONES\nD.N.I. 050894813E\n"
        )
        profile = detect_profile(pdf, {})
        matches, mismatches, unverifiable = compare_json_with_pdf(
            {"informacionPersonal": {"identificacion": "50894813E"}},
            pdf,
            profile=profile,
        )
        assert ("informacionPersonal.identificacion", "50894813E") in matches
        assert not mismatches and not unverifiable