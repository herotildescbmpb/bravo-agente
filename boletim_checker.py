#!/usr/bin/env python3
"""
Agente Bravo RH — Verificação de Boletim Interno CBMPB
Com notificação automática via WhatsApp (CallMeBot).

Secrets necessários no GitHub:
  BRAVO_MATRICULA       → matrícula sem dígito verificador
  BRAVO_DATANASC        → data de nascimento YYYY-MM-DD
  WHATSAPP_PHONE        → número com DDI, sem espaços (+5583999991234)
  WHATSAPP_APIKEY       → chave gerada pelo CallMeBot
"""

import os
import re
import sys
import json
import urllib.parse
import requests
from datetime import datetime
from pathlib import Path

# ─── CONFIGURAÇÕES ────────────────────────────────────────────────────────────
MATRICULA        = os.getenv("BRAVO_MATRICULA",   "524380")
DATA_NASCIMENTO  = os.getenv("BRAVO_DATANASC",    "1990-10-06")   # YYYY-MM-DD
UNIDADE          = os.getenv("BRAVO_UNIDADE",     "ccb")
ANO              = os.getenv("BRAVO_ANO") or str(datetime.now().year)
BASE_URL         = "https://bravo.bombeiros.pb.gov.br/bravoRH/boletins/"
OUTPUT_DIR       = Path(os.getenv("BRAVO_OUTPUT_DIR", "boletins"))

# WhatsApp — CallMeBot
WA_PHONE         = os.getenv("WHATSAPP_PHONE",   "")   # ex: +5583912345678
WA_APIKEY        = os.getenv("WHATSAPP_APIKEY",  "")
WA_NOTIFY_ALWAYS = os.getenv("WA_NOTIFY_ALWAYS", "true").lower() == "true"

# Termos de busca (separados por vírgula na env var)
_termos_default  = ",".join([
    MATRICULA,
    "524.380",
    "HEROTILDES",
    "ARAÚJO WANDERLEY",
    "WANDERLEY DE ARAÚJO",
    "DAL",
    "DIRETORIA DE APOIO LOG",
    "CAP HERO",
])
TERMOS_BUSCA     = [t.strip() for t in os.getenv("BRAVO_TERMOS", _termos_default).split(",") if t.strip()]

# GitHub Actions
GITHUB_STEP_SUMMARY = os.getenv("GITHUB_STEP_SUMMARY")
# ─────────────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer":           BASE_URL,
    "Accept":            "text/html, */*; q=0.01",
    "Accept-Language":   "pt-BR,pt;q=0.9",
    "X-Requested-With":  "XMLHttpRequest",
    "Origin":            "https://bravo.bombeiros.pb.gov.br",
}

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ── Bravo RH ─────────────────────────────────────────────────────────────────

def obter_pagina():
    session = requests.Session()
    r = session.get(BASE_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    limit   = re.search(r'name="limit"[^>]*value="([^"]+)"', r.text)
    boletim = re.search(r'<option value="(\d+\.pdf)"', r.text)
    if not limit or not boletim:
        raise RuntimeError("Falha ao extrair parâmetros da página.")
    return session, limit.group(1), boletim.group(1)


def buscar_url_pdf(session, limit, boletim_pdf):
    payload = {
        "limit":           limit,
        "local":           UNIDADE,
        "ano_bol":         ANO,
        "boletim":         boletim_pdf,
        "matricula":       MATRICULA,
        "data_nascimento": DATA_NASCIMENTO,
    }
    r = session.post(BASE_URL + "selBoletim", data=payload, headers=HEADERS, timeout=20)
    r.raise_for_status()
    if "corretamente" in r.text:
        raise PermissionError("Credenciais inválidas — verifique matrícula e data de nascimento.")
    match = re.search(r'href="(https://[^"]+\.pdf)"', r.text)
    return match.group(1) if match else None


def baixar_pdf(session, pdf_url, boletim_pdf):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    num   = boletim_pdf.replace(".pdf", "")
    fname = OUTPUT_DIR / f"Boletim_{num}_{ANO}.pdf"
    if fname.exists():
        log(f"PDF já existe: {fname}")
        return fname
    r = session.get(pdf_url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    fname.write_bytes(r.content)
    log(f"PDF salvo: {fname} ({len(r.content) // 1024} KB)")
    return fname


def extrair_texto(pdf_path):
    import subprocess
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True, text=True, timeout=30, encoding="utf-8"
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    except FileNotFoundError:
        pass
    try:
        from pypdf import PdfReader
        r = PdfReader(str(pdf_path))
        return "\n".join(p.extract_text() or "" for p in r.pages)
    except ImportError:
        log("AVISO: pypdf não instalado. Instale com: pip install pypdf")
    return ""


def analisar(texto, boletim_pdf):
    num = boletim_pdf.replace(".pdf", "")
    mencoes = {}
    for termo in TERMOS_BUSCA:
        linhas = [l.strip() for l in texto.splitlines()
                  if termo.lower() in l.lower() and l.strip()]
        if linhas:
            mencoes[termo] = linhas[:5]

    secoes = list(dict.fromkeys(
        re.findall(r'^(\d+\. [A-ZÁÉÍÓÚÂÊÎÔÛÃÕÇ ]+)$', texto, re.MULTILINE)
    ))

    return {
        "boletim":             num,
        "ano":                 ANO,
        "data_verificacao":    datetime.now().isoformat(),
        "mencoes_encontradas": bool(mencoes),
        "mencoes":             mencoes,
        "secoes_publicadas":   secoes,
    }


# ── WhatsApp via CallMeBot ────────────────────────────────────────────────────

def _wa_send(texto: str):
    """Envia mensagem de texto via CallMeBot. Retorna True se OK."""
    if not WA_PHONE or not WA_APIKEY:
        log("WhatsApp: WHATSAPP_PHONE ou WHATSAPP_APIKEY não configurados — pulando.")
        return False
    texto_enc = urllib.parse.quote(texto)
    url = f"https://api.callmebot.com/whatsapp.php?phone={WA_PHONE}&text={texto_enc}&apikey={WA_APIKEY}"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            log("WhatsApp: mensagem enviada com sucesso.")
            return True
        else:
            log(f"WhatsApp: erro HTTP {r.status_code} — {r.text[:120]}")
    except Exception as e:
        log(f"WhatsApp: falha na requisição — {e}")
    return False


def montar_mensagem_whatsapp(dados: dict, pdf_url: str) -> str:
    """
    Monta a mensagem que vai chegar no seu WhatsApp.
    Dois formatos dependendo se há menções ou não.
    """
    num  = dados["boletim"]
    ano  = dados["ano"]
    hora = datetime.fromisoformat(dados["data_verificacao"]).strftime("%d/%m/%Y %H:%M")

    if dados["mencoes_encontradas"]:
        # ─ Mensagem de ALERTA ──────────────────────────────────────────────
        linhas = [
            f"⚠️ *BOLETIM CBMPB Nº {num}/{ano}*",
            f"📅 {hora} | QCG",
            "",
            "🔴 *ATENÇÃO — Você foi mencionado!*",
            "",
        ]
        for termo, trechos in dados["mencoes"].items():
            linhas.append(f"🔎 *[{termo}]*")
            for t in trechos[:3]:           # máx 3 linhas por termo no WA
                linhas.append(f"  → {t[:120]}")  # evitar mensagem enorme
            linhas.append("")

        linhas += [
            "─────────────────────",
            f"🔗 {pdf_url}",
        ]
    else:
        # ─ Mensagem informativa (publicação sem menção direta) ─────────────
        secoes_str = ""
        if dados["secoes_publicadas"]:
            secoes_str = "\n".join(f"  • {s}" for s in dados["secoes_publicadas"][:6])
            secoes_str = "\n\n*Seções publicadas:*\n" + secoes_str

        linhas = [
            f"📋 *BOLETIM CBMPB Nº {num}/{ano}*",
            f"📅 {hora} | QCG",
            "",
            "✅ Sem menções diretas à sua matrícula/nome.",
            secoes_str,
            "",
            "─────────────────────",
            f"🔗 {pdf_url}",
        ]

    return "\n".join(linhas).strip()


def notificar_whatsapp(dados: dict, pdf_url: str):
    """Decide se e o quê notificar, e envia."""
    tem_mencao = dados["mencoes_encontradas"]

    if not tem_mencao and not WA_NOTIFY_ALWAYS:
        log("WhatsApp: sem menções e WA_NOTIFY_ALWAYS=false — notificação suprimida.")
        return

    msg = montar_mensagem_whatsapp(dados, pdf_url)
    _wa_send(msg)


# ── GitHub Actions helpers ────────────────────────────────────────────────────

def set_output(key, value):
    gho = os.getenv("GITHUB_OUTPUT")
    if gho:
        with open(gho, "a") as f:
            f.write(f"{key}={value}\n")


def escrever_github_summary(dados, pdf_url):
    if not GITHUB_STEP_SUMMARY:
        return
    num   = dados["boletim"]
    icone = "⚠️" if dados["mencoes_encontradas"] else "✅"
    linhas = [
        f"## {icone} Boletim Interno Nº {num}/{dados['ano']} — CBMPB/QCG",
        f"**Verificado em:** {datetime.fromisoformat(dados['data_verificacao']).strftime('%d/%m/%Y %H:%M')}",
        f"**PDF:** [{num}.pdf]({pdf_url})",
        "",
    ]
    if dados["mencoes"]:
        linhas.append("### ⚠️ Menções encontradas\n")
        for termo, trechos in dados["mencoes"].items():
            linhas.append(f"**`{termo}`**")
            for t in trechos:
                linhas.append(f"> {t}")
            linhas.append("")
    else:
        linhas.append("### ✅ Nenhuma menção direta neste boletim.")

    if dados["secoes_publicadas"]:
        linhas.append("\n### 📋 Seções publicadas")
        for s in dados["secoes_publicadas"]:
            linhas.append(f"- {s}")

    with open(GITHUB_STEP_SUMMARY, "a", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")


# ── Relatório no terminal ─────────────────────────────────────────────────────

def imprimir_relatorio(dados):
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  BOLETIM Nº {dados['boletim']}/{dados['ano']} — CBMPB/QCG")
    print(f"  {datetime.fromisoformat(dados['data_verificacao']).strftime('%d/%m/%Y %H:%M')}")
    print(sep)
    if dados["mencoes"]:
        print("\n⚠️  MENÇÕES ENCONTRADAS:\n")
        for termo, linhas in dados["mencoes"].items():
            print(f"  [{termo}]")
            for l in linhas:
                print(f"    → {l}")
            print()
    else:
        print("\n✅ Sem menções diretas à sua matrícula/nome.\n")
    if dados["secoes_publicadas"]:
        print("  Seções:")
        for s in dados["secoes_publicadas"]:
            print(f"    • {s}")
    print(f"\n{sep}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log("Iniciando verificação do Bravo RH...")
    session, limit, boletim_pdf = obter_pagina()
    log(f"Boletim mais recente: {boletim_pdf} ({ANO})")

    pdf_url = buscar_url_pdf(session, limit, boletim_pdf)
    if not pdf_url:
        num = boletim_pdf.replace(".pdf", "")
        log(f"Boletim nº {num} ainda não publicado — nada a fazer.")
        if WA_NOTIFY_ALWAYS and WA_PHONE and WA_APIKEY:
            hora = datetime.now().strftime("%d/%m/%Y %H:%M")
            msg  = (
                f"⏳ *BOLETIM CBMPB Nº {num}/{ANO}*\n"
                f"📅 {hora} | QCG\n\n"
                f"Boletim ainda não publicado no Bravo RH.\n"
                f"Verificarei novamente amanhã às 20h."
            )
            _wa_send(msg)
        sys.exit(0)
    log(f"URL do PDF: {pdf_url}")

    pdf_path = baixar_pdf(session, pdf_url, boletim_pdf)
    texto    = extrair_texto(pdf_path)
    dados    = analisar(texto, boletim_pdf)

    imprimir_relatorio(dados)
    escrever_github_summary(dados, pdf_url)
    notificar_whatsapp(dados, pdf_url)

    set_output("boletim_num", dados["boletim"])
    set_output("mencoes",     str(dados["mencoes_encontradas"]).lower())
    set_output("pdf_url",     pdf_url)

    result_path = OUTPUT_DIR / "ultimo_resultado.json"
    result_path.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    log("Concluído.")


if __name__ == "__main__":
    main()
