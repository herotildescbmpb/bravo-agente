# 📋 Agente Bravo RH — Boletim Diário CBMPB + WhatsApp

Verifica diariamente o Boletim Interno do CBMPB e envia notificação no **WhatsApp** via [CallMeBot](https://www.callmebot.com/).

---

## ✅ Setup em 4 passos

### Passo 1 — Ativar o CallMeBot no seu WhatsApp

> Faça isso uma única vez. Leva menos de 2 minutos.

1. Salve o número **+34 623 78 64 49** na agenda (pode chamar de "CallMeBot")
2. Envie a mensagem exata pelo WhatsApp:
   ```
   I allow callmebot to send me messages
   ```
3. Aguarde a resposta com a sua **APIKEY** (chega em segundos)

---

### Passo 2 — Adicionar Secrets no GitHub

`Settings → Secrets and variables → Actions → New repository secret`

| Secret | Valor | Descrição |
|--------|-------|-----------|
| `BRAVO_MATRICULA` | `524380` | Matrícula sem dígito verificador |
| `BRAVO_DATANASC` | `1990-10-06` | Data de nascimento (YYYY-MM-DD) |
| `WHATSAPP_PHONE` | `+5583912345678` | Seu número com DDI (+55) |
| `WHATSAPP_APIKEY` | `123456` | Chave recebida do CallMeBot |

---

### Passo 3 — Ativar o workflow

1. Vá em **Actions** no seu repositório
2. Clique em **"I understand my workflows, enable them"**
3. Selecione **📋 Boletim Diário CBMPB** → **Run workflow** para testar

---

### Passo 4 — Estrutura de arquivos no repo

```
.github/
└── workflows/
    └── boletim-diario.yml   ← agendamento automático
boletins/                    ← PDFs versionados (criada automaticamente)
boletim_checker.py           ← agente principal
requirements.txt
README.md
```

---

## 📱 Mensagens recebidas no WhatsApp

**Quando você é citado (⚠️ alerta):**
```
⚠️ BOLETIM CBMPB Nº 87/2026
📅 13/05/2026 08:03 | QCG

🔴 ATENÇÃO — Você foi mencionado!

🔎 [524380]
  → 524380 CAP HEROTILDES ...

─────────────────────
🔗 https://bravo.bombeiros.pb.gov.br/...
```

**Quando não há menção (✅ informativo):**
```
📋 BOLETIM CBMPB Nº 87/2026
📅 13/05/2026 08:03 | QCG

✅ Sem menções diretas à sua matrícula/nome.

Seções publicadas:
  • 2. ENSINO E INSTRUÇÃO
  • 3. ASSUNTOS GERAIS E ADMINISTRATIVOS
  • 4. JUSTIÇA E DISCIPLINA

─────────────────────
🔗 https://bravo.bombeiros.pb.gov.br/...
```

---

## ⚙️ Personalização de termos de busca

Por padrão o agente busca pelos termos:

```
524380, 524.380, HEROTILDES, ARAÚJO WANDERLEY,
WANDERLEY DE ARAÚJO, DAL, DIRETORIA DE APOIO LOG, CAP HERO
```

Para adicionar ou alterar, inclua a env var `BRAVO_TERMOS` no workflow:

```yaml
env:
  BRAVO_TERMOS: "524380,HEROTILDES,DAL,SOBREIRA,524.380-2"
```

---

## 🔔 Controle de notificações

| Variável | Padrão | Comportamento |
|----------|--------|---------------|
| `WA_NOTIFY_ALWAYS=true` | ✅ padrão | Notifica em toda publicação |
| `WA_NOTIFY_ALWAYS=false` | — | Só notifica se houver menção |

---

## 💻 Execução local

```bash
pip install requests pypdf
sudo apt install poppler-utils    # Linux
# ou: brew install poppler        # macOS

export BRAVO_MATRICULA=524380
export BRAVO_DATANASC=1990-10-06
export WHATSAPP_PHONE=+5583912345678
export WHATSAPP_APIKEY=123456

python boletim_checker.py
```

---

## ⏰ Agendamento

O workflow roda automaticamente **seg–sáb às 08:00 BRT**.  
Para alterar, edite a linha `cron` no workflow:

```yaml
- cron: '0 11 * * 1-6'   # 11:00 UTC = 08:00 BRT (UTC-3)
```

