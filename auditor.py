import json
import os
import sys
from datetime import datetime
from pathlib import Path
import pypdf


def extreure_text_pdf(ruta_pdf):
    """Extreu tot el text pla d'un PDF."""
    try:
        reader = pypdf.PdfReader(ruta_pdf)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        print(f"❌ Error llegint el PDF {ruta_pdf}: {e}")
        return ""


def comparar_json_amb_pdf(dades_json, text_pdf):
    """Recorre el JSON recursivament i comprova si els valors existeixen al PDF."""
    errors = []
    encerts = []

    def generar_variants_numeriques(valor_str):
        variants = [valor_str]
        try:
            val_float = float(valor_str)
            # Format europeu amb punts de milers i coma decimal (1.166,34)
            variants.append(f"{val_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            # Format europeu amb punts de milers i punt decimal (1.166.34)
            variants.append(f"{val_float:,.2f}".replace(",", "."))
        except ValueError:
            pass
        return variants

    def buscar_recursia(obj, ruta=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                buscar_recursia(v, f"{ruta}.{k}" if ruta else k)
        elif isinstance(obj, list):
            for i, elem in enumerate(obj):
                buscar_recursia(elem, f"{ruta}[{i}]")
        elif obj is not None and str(obj).strip() != "":
            valor_str = str(obj).strip()

            if valor_str.lower() in ["true", "false"]:
                return

            variants = generar_variants_numeriques(valor_str)
            if any(var in text_pdf for var in variants):
                encerts.append((ruta, valor_str))
            else:
                errors.append((ruta, valor_str))

    buscar_recursia(dades_json)
    return encerts, errors


def generar_report_markdown(resultats, dir_reports):
    """Genera un fitxer Markdown clar, estructurat i comentat."""
    ara = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nom_fitxer_report = f"report_auditoria_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    ruta_report = os.path.join(dir_reports, nom_fitxer_report)

    total_docs = len(resultats)
    docs_correctes = sum(1 for r in resultats if len(r["errors"]) == 0)
    docs_amb_errors = total_docs - docs_correctes
    total_incidencies = sum(len(r["errors"]) for r in resultats)

    md = []
    md.append("# 📊 Informe d'Auditoria IRS (Model 3)\n")
    md.append(f"**Data d'execució:** `{ara}`  \n")
    md.append(f"**Ubicació de l'informe:** `{ruta_report}`\n")
    md.append("---\n")

    # Resum executiu
    md.append("## 📈 Resum Executiu\n")
    md.append(f"- **Documents analitzats:** {total_docs}")
    md.append(f"- **Documents 100% correctes:** {docs_correctes} ✅")
    md.append(f"- **Documents amb incidències:** {docs_amb_errors} ⚠️")
    md.append(f"- **Total d'incidències trobades:** {total_incidencies}\n")

    # Taula d'estat
    md.append("### 📑 Estat per Document\n")
    md.append("| Document | Correctes | Incidències | Estat |")
    md.append("| :--- | :---: | :---: | :---: |")
    for r in resultats:
        estat = "✅ OK" if len(r["errors"]) == 0 else "❌ AMB INCIDÈNCIES"
        md.append(f"| `{r['nom']}` | {len(r['encerts'])} | {len(r['errors'])} | {estat} |")
    md.append("\n---\n")

    # Detall per document
    md.append("## 🔍 Detall d'Auditoria per Document\n")
    for r in resultats:
        md.append(f"### 📄 Document: `{r['nom']}`\n")
        md.append(f"- **Camps que coincideixen:** {len(r['encerts'])}")
        md.append(f"- **Diferències trobades:** {len(r['errors'])}\n")

        if r["errors"]:
            md.append("#### ⚠️ Incidències a revisar:\n")
            md.append("> **Nota d'interpretació:** El camp del JSON existeix però el seu valor no s'ha trobat imprès textualment ni en format numèric estàndard dins del PDF.\n")
            for ruta, valor in r["errors"]:
                md.append(f"* **Camp / Ruta JSON:** `{ruta}`")
                md.append(f"  * **Valor esperat (JSON):** `{valor}`")
                md.append("  * *Comentari:* Comprovar si al PDF aquest valor apareix en un altre format, si està truncat o si falten pàgines.\n")
        else:
            md.append("🎉 **Tots els camps extrets al JSON s'han validat correctament contra el PDF.**\n")

        md.append("---\n")

    # Guardar fitxer
    with open(ruta_report, "w", encoding="utf-8") as f:
        f.writelines("\n".join(md))

    return ruta_report


def auditar_carpeta_recursiva(dir_arrel, dir_reports):
    """Cerca tots els PDFs i JSONs, els compara i genera un report."""
    mapa_pdfs = {}
    mapa_jsons = {}

    path_arrel = Path(dir_arrel)
    if not path_arrel.exists():
        print(f"❌ La carpeta '{dir_arrel}' no existeix.")
        return

    for fitxer in path_arrel.rglob("*"):
        if fitxer.is_file():
            if fitxer.suffix.lower() == ".pdf":
                mapa_pdfs[fitxer.stem] = fitxer
            elif fitxer.suffix.lower() == ".json":
                mapa_jsons[fitxer.stem] = fitxer

    noms_comuns = set(mapa_pdfs.keys()).intersection(set(mapa_jsons.keys()))

    if not noms_comuns:
        print(f"⚠️ No s'han trobat parelles de fitxers PDF i JSON amb el mateix nom a '{dir_arrel}'.")
        return

    print(f"\n🔍 Executant auditoria de {len(noms_comuns)} parelles de fitxers...\n" + "=" * 60)

    resultats = []

    for nom in sorted(noms_comuns):
        ruta_pdf = mapa_pdfs[nom]
        ruta_json = mapa_jsons[nom]

        text_pdf = extreure_text_pdf(ruta_pdf)

        try:
            with open(ruta_json, "r", encoding="utf-8") as f:
                dades_json = json.load(f)
        except Exception as e:
            print(f"❌ Error llegint el JSON {ruta_json.name}: {e}")
            continue

        encerts, errors = comparar_json_amb_pdf(dades_json, text_pdf)

        resultats.append({
            "nom": nom,
            "encerts": encerts,
            "errors": errors
        })

        print(f"📄 Processat: {nom} | ✅ {len(encerts)} ok | ❌ {len(errors)} errors")

    # Generar el report
    ruta_report = generar_report_markdown(resultats, dir_reports)

    print("\n" + "=" * 60)
    print(f"📊 Auditoria finalitzada!")
    print(f"📁 Informe generat correctament a: {ruta_report}")


if __name__ == "__main__":
    dir_data = sys.argv[1] if len(sys.argv) > 1 else "./data"
    dir_reports = "./reports"

    # Crear carpetes si no existeixen
    os.makedirs(dir_data, exist_ok=True)
    os.makedirs(dir_reports, exist_ok=True)

    auditar_carpeta_recursiva(dir_data, dir_reports)