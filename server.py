"""Servidor do Ultron. Roda no celular velho (Termux) e serve o app de voz.

Uso:  python server.py
"""

import base64
import hmac
import json
import mimetypes
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from brain import Cerebro
from voice import sintetizar, transcrever

RAIZ = Path(__file__).resolve().parent
WEB = RAIZ / "web"
MAX_AUDIO = 15 * 1024 * 1024
# Frases que o Whisper costuma "ouvir" em silêncio ou ruído
FANTASMAS = {"legendas pela comunidade amara.org", "obrigado por assistir",
             "inscreva-se no canal", "obrigado por assistir ao vídeo", "tchau, tchau"}


def carregar_config():
    cfg = {}
    env = RAIZ / ".env"
    if env.exists():
        for linha in env.read_text("utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    cfg.update({k: v for k, v in os.environ.items() if k in cfg or k.startswith(("ULTRON_", "LLM_", "STT_", "BUSCA_"))})
    padroes = {
        "DONO_NOME": "chefe", "LLM_URL": "https://api.groq.com/openai/v1",
        "LLM_MODELO": "openai/gpt-oss-120b", "STT_MODELO": "whisper-large-v3-turbo",
        "VOZ": "pt-BR-AntonioNeural", "VOZ_VELOCIDADE": "-4%", "VOZ_TOM": "-14Hz", "CIDADE": "São Paulo",
        "PORTA": "8000",
    }
    for k, v in padroes.items():
        cfg[k] = cfg.get(k) or v
    # O ouvido usa o Whisper do Groq; se não houver chave própria, aproveita a do cérebro
    cfg["STT_URL"] = cfg.get("STT_URL") or "https://api.groq.com/openai/v1"
    if not cfg.get("STT_CHAVE") and "groq.com" in cfg["LLM_URL"]:
        cfg["STT_CHAVE"] = cfg.get("LLM_CHAVE", "")
    # Pesquisa na web: modelo do Groq com busca embutida (mesma chave grátis)
    cfg["BUSCA_URL"] = cfg.get("BUSCA_URL") or "https://api.groq.com/openai/v1"
    cfg["BUSCA_MODELO"] = cfg.get("BUSCA_MODELO") or "groq/compound-mini"
    if not cfg.get("BUSCA_CHAVE") and "groq.com" in cfg["LLM_URL"]:
        cfg["BUSCA_CHAVE"] = cfg.get("LLM_CHAVE", "")

    faltando = [k for k in ("ULTRON_SENHA", "LLM_CHAVE") if not cfg.get(k)]
    if faltando:
        raise SystemExit(f"Configure no arquivo .env: {', '.join(faltando)}")
    if cfg["ULTRON_SENHA"] == "troque-esta-senha":
        raise SystemExit("Troque ULTRON_SENHA no .env por uma senha sua.")
    return cfg


CFG = carregar_config()
CEREBRO = Cerebro(CFG, RAIZ / "data")
_erros_senha = []  # horários das senhas erradas recentes


class Handler(BaseHTTPRequestHandler):
    server_version = "Ultron"

    def log_message(self, fmt, *args):
        if not self.path.startswith("/api/"):
            return
        print(f"[{time.strftime('%H:%M:%S')}] {fmt % args}")

    # ---------- respostas ----------
    def _json(self, codigo, dados):
        corpo = json.dumps(dados, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(corpo)

    def _corpo(self, limite=MAX_AUDIO):
        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho > limite:
            raise ValueError("Envio grande demais.")
        return self.rfile.read(tamanho)

    def _autorizado(self):
        agora = time.time()
        _erros_senha[:] = [t for t in _erros_senha if agora - t < 600]
        if len(_erros_senha) >= 10:  # 10 erros em 10 minutos: bloqueia por um tempo
            return False
        ok = hmac.compare_digest(self.headers.get("X-Ultron-Senha", "").encode(),
                                 CFG["ULTRON_SENHA"].encode())
        if not ok:
            _erros_senha.append(agora)
            time.sleep(1)
        return ok

    # ---------- rotas ----------
    def do_GET(self):
        if self.path == "/api/config":
            return self._json(200, {"nome": CFG["DONO_NOME"],
                                    "ouvido": "servidor" if CFG.get("STT_CHAVE") else "navegador"})
        if self.path == "/api/memoria":
            if not self._autorizado():
                return self._json(401, {"erro": "Senha errada."})
            return self._json(200, {"fatos": CEREBRO.memoria.fatos})
        self._estatico()

    def do_POST(self):
        if not self._autorizado():
            return self._json(401, {"erro": "Senha errada."})
        try:
            if self.path == "/api/entrar":
                return self._json(200, {"ok": True})
            if self.path == "/api/nova-conversa":
                CEREBRO.nova_conversa()
                return self._json(200, {"ok": True})
            if self.path == "/api/falar":
                return self._conversar(self._corpo())
            if self.path == "/api/escrever":
                texto = json.loads(self._corpo(100_000) or b"{}").get("texto", "")
                return self._responder(texto.strip())
            self._json(404, {"erro": "Rota não existe."})
        except Exception as e:
            print(f"[erro] {e}")
            self._json(500, {"erro": str(e)})

    def _conversar(self, audio):
        if len(audio) < 2000:
            return self._json(200, {"ouvi": "", "resposta": ""})
        texto = transcrever(audio, self.headers.get("Content-Type", "audio/webm"), CFG)
        return self._responder(texto)

    def _responder(self, texto):
        if not texto or texto.lower().strip(" .!") in FANTASMAS:
            return self._json(200, {"ouvi": texto, "resposta": ""})
        inicio = time.time()
        resposta = CEREBRO.responder(texto)
        audio = sintetizar(resposta, CFG)
        print(f"  você: {texto}\n  ultron: {resposta}  ({time.time() - inicio:.1f}s)")
        self._json(200, {"ouvi": texto, "resposta": resposta,
                         "audio": base64.b64encode(audio).decode() if audio else None})

    def _estatico(self):
        caminho = self.path.split("?")[0]
        arq = (WEB / (caminho.lstrip("/") or "index.html")).resolve()
        if not arq.is_relative_to(WEB) or not arq.is_file():
            arq = WEB / "index.html"
        dados = arq.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(arq.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(dados)


if __name__ == "__main__":
    mimetypes.add_type("application/manifest+json", ".webmanifest")
    porta = int(CFG["PORTA"])
    print(f"Ultron online em http://localhost:{porta}  (cérebro: {CFG['LLM_MODELO']}, "
          f"ouvido: {'Whisper' if CFG.get('STT_CHAVE') else 'navegador'}, "
          f"pesquisa: {'sim' if CFG.get('BUSCA_CHAVE') else 'não'}, voz: {CFG['VOZ']})")
    ThreadingHTTPServer(("0.0.0.0", porta), Handler).serve_forever()
