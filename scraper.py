import instaloader
import gspread
import time
import random
import re
import os
import json
import base64
import pickle
import requests
import logging
from datetime import datetime
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()

IG_USERNAME = os.getenv("IG_USERNAME")
IG_PASSWORD = os.getenv("IG_PASSWORD")
IG_SESSION = os.getenv("IG_SESSION")
SHEETS_ID = os.getenv("SHEETS_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_CREDS = os.getenv("GOOGLE_CREDENTIALS")

TARGET_PROFILES = [
    "rockcontent",
    "v4company",
    "rdstation",
    "agencia.wbi",
]

LIMITE_SEGUIDORES_POR_ALVO = 80
LIMITE_COMENTADORES_POR_POST = 30
POSTS_POR_ALVO = 3
LIMITE_TOTAL_POR_DIA = 250

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

def conectar_sheets():
    creds_dict = json.loads(GOOGLE_CREDS)
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEETS_ID)

def buscar_usernames_existentes(planilha):
    existentes = set()
    for aba in ["leads_qualificados", "ja_processados"]:
        try:
            ws = planilha.worksheet(aba)
            dados = ws.col_values(1)
            existentes.update([u.strip().lower() for u in dados[1:] if u])
        except:
            pass
    log.info(f"@ já processados: {len(existentes)}")
    return existentes

def salvar_lead_qualificado(planilha, lead):
    ws = planilha.worksheet("leads_qualificados")
    ws.append_row([
        lead.get("username", ""),
        lead.get("nome_completo", ""),
        lead.get("bio", "")[:200],
        lead.get("email", ""),
        lead.get("telefone", ""),
        lead.get("link_externo", ""),
        "Sim" if lead.get("is_business") else "Não",
        lead.get("fonte", ""),
        lead.get("origem_detalhada", ""),
        str(lead.get("score_icp", "")),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "pendente"
    ])
    log.info(f"QUALIFICADO: @{lead.get('username')} | "
             f"email={lead.get('email')[:30] if lead.get('email') else '-'} | "
             f"tel={lead.get('telefone') or '-'}")

def registrar_processado(planilha, username, motivo):
    try:
        ws = planilha.worksheet("ja_processados")
        ws.append_row([username, motivo, datetime.now().strftime("%Y-%m-%d %H:%M")])
    except:
        pass

def extrair_contatos(bio, link):
    email, telefone = "", ""
    texto = (bio or "") + " " + (link or "")

    email_match = re.search(
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', texto
    )
    if email_match:
        email = email_match.group(0)

    wapp = re.search(r'wa\.me/(\d{10,15})', texto)
    if wapp:
        telefone = wapp.group(1)

    if not telefone:
        tel = re.search(
            r'(?:whatsapp|wpp|zap|tel|fone)?[\s:]*'
            r'(?:\+?55)?[\s\-]?(?:\(?\d{2}\)?)[\s\-]?\d{4,5}[\s\-]?\d{4}',
            texto, re.IGNORECASE
        )
        if tel:
            numero = re.sub(r'\D', '', tel.group(0))
            if 10 <= len(numero) <= 13:
                telefone = numero

    return email, telefone

def classificar_icp(username, bio, nome, is_business, link):
    palavras_b2b = ["agência","agencia","consultoria","marketing","tech",
                    "software","soluções","vendas","b2b","startup"]
    
    if is_business and any(p in (bio or "").lower() for p in palavras_b2b):
        return 9, "b2b_target"

    prompt = f"""Analise este perfil do Instagram e classifique o seu potencial como um lead B2B.

ICP ideal: Empresas, fundadores, CEOs ou tomadores de decisão em empresas no Brasil.

Perfil a analisar:
- Username: {username}
- Nome: {nome}
- Bio: {bio}
- Link: {link}
- Conta Business: {is_business}

Retorne APENAS JSON puro:
{{"score": <0-10>, "segmento": "<b2b_target|pf_irrelevante|bot>", "motivo": "<max 10 palavras>"}}

8-10: Claramente uma empresa ou tomador de decisão B2B
5-7: Provável negócio, mas incerto
0-4: Pessoa física comum ou fora do perfil corporativo"""

    try:
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}")
        r = requests.post(
            url,
            headers={"content-type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 100,
                    "responseMimeType": "application/json"
                }
            },
            timeout=15
        )
        resposta = r.json()
        texto = resposta["candidates"][0]["content"]["parts"][0]["text"]
        texto = re.sub(r'```json|```', '', texto).strip()
        res = json.loads(texto)
        return res.get("score", 0), res.get("segmento", "irrelevante")
    except Exception as e:
        log.error(f"Erro Gemini: {e}")
        return 0, "erro"

def processar_usuario(L, username, fonte, origem_detalhada, planilha, existentes, contadores):
    if username in existentes:
        return False

    existentes.add(username)
    contadores["coletados"] += 1
    time.sleep(random.uniform(2, 4))

    try:
        p = instaloader.Profile.from_username(L.context, username)

        bio    = p.biography or ""
        nome   = p.full_name or username
        link   = p.external_url or ""
        is_biz = p.is_business_account
        b_email = getattr(p, 'business_email', "") or ""
        b_phone = getattr(p, 'business_phone_number', "") or ""

        email_bio, tel_bio = extrair_contatos(bio, link)
        email    = b_email or email_bio
        telefone = b_phone or tel_bio

        if not email and not telefone:
            registrar_processado(planilha, username, "sem_contato")
            contadores["sem_contato"] += 1
            return False

        score, segmento = classificar_icp(username, bio, nome, is_biz, link)

        if score < 6:
            registrar_processado(planilha, username, f"score_baixo_{segmento}")
            contadores["fora_icp"] += 1
            return False

        lead = {
            "username": username,
            "nome_completo": nome,
            "bio": bio,
            "email": email,
            "telefone": telefone,
            "link_externo": link,
            "is_business": is_biz,
            "fonte": fonte,
            "origem_detalhada": origem_detalhada,
            "score_icp": score,
        }
        salvar_lead_qualificado(planilha, lead)
        contadores["qualificados"] += 1
        return True

    except instaloader.exceptions.ProfileNotExistsException:
        return False
    except Exception as e:
        log.warning(f"Erro @{username}: {str(e)[:80]}")
        return False

def coletar_seguidores(L, alvo, planilha, existentes, contadores):
    log.info(f"SEGUIDORES de @{alvo}")
    try:
        profile = instaloader.Profile.from_username(L.context, alvo)
    except Exception as e:
        log.error(f"Erro @{alvo}: {e}")
        return

    coletados_aqui = 0
    try:
        for follower in profile.get_followers():
            if coletados_aqui >= LIMITE_SEGUIDORES_POR_ALVO:
                break
            if contadores["coletados"] >= LIMITE_TOTAL_POR_DIA:
                return
            processar_usuario(
                L, follower.username.lower(),
                fonte="seguidor_alvo",
                origem_detalhada=alvo,
                planilha=planilha,
                existentes=existentes,
                contadores=contadores
            )
            coletados_aqui += 1
    except Exception as e:
        log.warning(f"Interrompido seguidores @{alvo}: {e}")

def coletar_comentadores_alvo(L, alvo, planilha, existentes, contadores):
    log.info(f"COMENTADORES de posts @{alvo}")
    try:
        profile = instaloader.Profile.from_username(L.context, alvo)
        posts = profile.get_posts()

        posts_processados = 0
        for post in posts:
            if posts_processados >= POSTS_POR_ALVO:
                break
            if contadores["coletados"] >= LIMITE_TOTAL_POR_DIA:
                return

            comentadores_aqui = 0
            try:
                for comment in post.get_comments():
                    if comentadores_aqui >= LIMITE_COMENTADORES_POR_POST:
                        break
                    processar_usuario(
                        L, comment.owner.username.lower(),
                        fonte="comentador_alvo",
                        origem_detalhada=f"{alvo}_post_{post.shortcode}",
                        planilha=planilha,
                        existentes=existentes,
                        contadores=contadores
                    )
                    comentadores_aqui += 1
            except Exception as e:
                log.warning(f"Erro post {post.shortcode}: {e}")
                continue

            posts_processados += 1
            time.sleep(random.uniform(3, 6))
    except Exception as e:
        log.error(f"Erro comentadores @{alvo}: {e}")

def main():
    log.info("=" * 50)
    log.info("INICIANDO PIPELINE DE EXTRACAO DE LEADS B2B")
    log.info("=" * 50)

    planilha = conectar_sheets()
    existentes = buscar_usernames_existentes(planilha)

    L = instaloader.Instaloader(
        quiet=True,
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        save_metadata=False
    )

    log.info("Carregando sessao do Instagram via cookies")
    try:
        cookies = pickle.loads(base64.b64decode(IG_SESSION))
        L.context._session.cookies = cookies
        L.context.username = IG_USERNAME
        log.info("Sessao carregada")
    except Exception as e:
        log.error(f"Erro ao carregar sessao: {e}")
        return

    contadores = {
        "coletados": 0,
        "qualificados": 0,
        "sem_contato": 0,
        "fora_icp": 0
    }

    dia = datetime.now().timetuple().tm_yday
    alvo_dia = TARGET_PROFILES[dia % len(TARGET_PROFILES)]
    alvo_extra = TARGET_PROFILES[(dia + 1) % len(TARGET_PROFILES)]

    if contadores["coletados"] < LIMITE_TOTAL_POR_DIA:
        coletar_seguidores(L, alvo_dia, planilha, existentes, contadores)

    if contadores["coletados"] < LIMITE_TOTAL_POR_DIA:
        coletar_comentadores_alvo(L, alvo_dia, planilha, existentes, contadores)

    if contadores["coletados"] < LIMITE_TOTAL_POR_DIA:
        coletar_comentadores_alvo(L, alvo_extra, planilha, existentes, contadores)

    log.info("=" * 50)
    log.info(f"RESUMO")
    log.info(f"   Alvo principal: @{alvo_dia}")
    log.info(f"   Alvo extra: @{alvo_extra}")
    log.info(f"   Coletados: {contadores['coletados']}")
    log.info(f"   Qualificados: {contadores['qualificados']}")
    log.info(f"   Sem contato: {contadores['sem_contato']}")
    log.info(f"   Fora ICP: {contadores['fora_icp']}")
    log.info("=" * 50)

if __name__ == "__main__":
    main()
