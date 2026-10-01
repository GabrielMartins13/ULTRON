"""Ouvido (voz -> texto, Whisper do Groq) e voz (texto -> fala, Edge TTS)."""

import asyncio
import json
import uuid
import urllib.request

EXTENSOES = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a",
             "audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-m4a": "m4a"}


def transcrever(audio: bytes, tipo: str, cfg: dict) -> str:
    """Manda o áudio para o Whisper (API compatível com OpenAI) e devolve o texto."""
    ext = EXTENSOES.get(tipo.split(";")[0].strip(), "webm")
    fronteira = uuid.uuid4().hex

    def campo(nome, valor):
        return (f"--{fronteira}\r\nContent-Disposition: form-data; name=\"{nome}\""
                f"\r\n\r\n{valor}\r\n").encode()

    corpo = (campo("model", cfg["STT_MODELO"]) + campo("language", "pt")
             + campo("response_format", "json")
             + f"--{fronteira}\r\nContent-Disposition: form-data; name=\"file\"; "
               f"filename=\"fala.{ext}\"\r\nContent-Type: {tipo}\r\n\r\n".encode()
             + audio + f"\r\n--{fronteira}--\r\n".encode())
    req = urllib.request.Request(
        cfg["STT_URL"].rstrip("/") + "/audio/transcriptions", data=corpo,
        headers={"Authorization": f"Bearer {cfg['STT_CHAVE']}",
                 "Content-Type": f"multipart/form-data; boundary={fronteira}",
                 "User-Agent": "ultron/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read()).get("text", "").strip()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Whisper HTTP {e.code}: {e.read()[:300].decode(errors='ignore')}")


async def _falar(texto, voz, velocidade, tom):
    import edge_tts
    audio = bytearray()
    async for parte in edge_tts.Communicate(texto, voz, rate=velocidade, pitch=tom).stream():
        if parte["type"] == "audio":
            audio.extend(parte["data"])
    return bytes(audio)


def sintetizar(texto: str, cfg: dict) -> bytes | None:
    """Gera MP3 com a voz neural. Devolve None se falhar (o app usa a voz do aparelho)."""
    try:
        return asyncio.run(_falar(texto, cfg["VOZ"], cfg["VOZ_VELOCIDADE"], cfg["VOZ_TOM"])) or None
    except Exception as e:
        print(f"[voz] falhou, o navegador vai falar no lugar: {e}")
        return None
