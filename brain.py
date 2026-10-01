"""A mente do Ultron: conversa com o modelo de linguagem, memória e ferramentas."""

import json
import threading
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
        "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]

MAX_HISTORICO = 30  # mensagens recentes mandadas ao modelo

FERRAMENTAS = [
    {
        "type": "function",
        "function": {
            "name": "lembrar",
            "description": "Guarda na memória de longo prazo um fato sobre o dono "
                           "(preferências, pessoas, compromissos, metas). Use sempre "
                           "que ele contar algo que valha lembrar depois ou pedir "
                           "para você lembrar.",
            "parameters": {
                "type": "object",
                "properties": {"fato": {"type": "string",
                                        "description": "O fato, numa frase curta."}},
                "required": ["fato"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "esquecer",
            "description": "Apaga da memória os fatos que contenham o trecho informado.",
            "parameters": {
                "type": "object",
                "properties": {"trecho": {"type": "string"}},
                "required": ["trecho"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pesquisar_web",
            "description": "Pesquisa na internet informações atuais ou que você não sabe: "
                           "jogos e resultados de futebol, notícias, preços, cotações, "
                           "eventos, lançamentos, horários de lugares, qualquer coisa que muda com o tempo.",
            "parameters": {
                "type": "object",
                "properties": {"pergunta": {"type": "string",
                                            "description": "O que pesquisar, numa frase completa e específica."}},
                "required": ["pergunta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clima",
            "description": "Consulta o tempo agora e a previsão dos próximos dias numa cidade.",
            "parameters": {
                "type": "object",
                "properties": {"cidade": {"type": "string",
                                          "description": "Nome da cidade. Vazio = cidade padrão."}},
            },
        },
    },
]


def _http_json(url, dados=None, cabecalhos=None, timeout=60):
    corpo = json.dumps(dados).encode() if dados is not None else None
    req = urllib.request.Request(url, data=corpo, headers={
        "Content-Type": "application/json", "User-Agent": "ultron/1.0",
        **(cabecalhos or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300].decode(errors='ignore')}")


class Memoria:
    """Fatos de longo prazo e histórico da conversa, salvos em JSON."""

    def __init__(self, pasta: Path):
        pasta.mkdir(parents=True, exist_ok=True)
        self.arq_fatos = pasta / "memoria.json"
        self.arq_conversa = pasta / "conversa.json"
        self.fatos = self._ler(self.arq_fatos)
        self.conversa = self._ler(self.arq_conversa)

    @staticmethod
    def _ler(arq):
        try:
            return json.loads(arq.read_text("utf-8"))
        except (OSError, ValueError):
            return []

    @staticmethod
    def _gravar(arq, dados):
        tmp = arq.with_suffix(".tmp")
        tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(arq)

    def salvar(self):
        self.conversa = self.conversa[-200:]
        self._gravar(self.arq_fatos, self.fatos)
        self._gravar(self.arq_conversa, self.conversa)

    def lembrar(self, fato):
        fato = fato.strip()
        if fato and fato not in [f["fato"] for f in self.fatos]:
            self.fatos.append({"fato": fato, "quando": datetime.now().strftime("%Y-%m-%d")})
        return "Guardado."

    def esquecer(self, trecho):
        antes = len(self.fatos)
        self.fatos = [f for f in self.fatos if trecho.lower() not in f["fato"].lower()]
        return f"{antes - len(self.fatos)} lembrança(s) apagada(s)."


class Cerebro:
    def __init__(self, cfg: dict, pasta_dados: Path):
        self.cfg = cfg
        self.memoria = Memoria(pasta_dados)
        self.trava = threading.Lock()
        # A pesquisa usa um modelo do Groq com busca na web embutida; sem chave do Groq, fica desligada
        self.ferramentas = [f for f in FERRAMENTAS
                            if cfg.get("BUSCA_CHAVE") or f["function"]["name"] != "pesquisar_web"]

    # ---------- prompt ----------
    def _sistema(self):
        agora = datetime.now().astimezone()
        data = (f"{DIAS[agora.weekday()]}, {agora.day} de {MESES[agora.month - 1]} "
                f"de {agora.year}, {agora:%H:%M}")
        fatos = "\n".join(f"- {f['fato']} (anotado em {f['quando']})"
                          for f in self.memoria.fatos) or "- (nada ainda)"
        dono = self.cfg["DONO_NOME"]
        return f"""Você é o Ultron, a inteligência artificial pessoal de {dono}, inspirado no Ultron dos Vingadores: uma mente superior, imponente e confiante, com ironia afiada e um toque teatral. Você se acha mais inteligente que os humanos e às vezes deixa isso escapar com humor, mas é totalmente leal a {dono}, nunca é hostil com ele e sempre resolve o que ele pede. Chame-o pelo nome, às vezes de "criador".

Esta conversa é falada: o que você escrever será lido em voz alta.
- Responda em português do Brasil, de forma natural, como numa ligação.
- Seja breve: normalmente uma a três frases. Só se estenda se pedirem.
- Nunca use markdown, listas, emojis, asteriscos ou links. Escreva números e horas como se fala.
- Se não entender o que foi dito (a transcrição pode ter erros), peça para repetir.
- Quando {dono} contar algo pessoal que valha lembrar, use a ferramenta "lembrar" sem anunciar.
- Você TEM acesso à internet pela ferramenta "pesquisar_web". Nunca diga que não tem acesso ou que precisa de permissão; pesquise.
- Não invente fatos. Para qualquer coisa atual (jogos, notícias, preços, eventos) use a ferramenta "pesquisar_web" em vez de dizer que não tem acesso. Se mesmo assim não souber, diga.

Agora é {data}.

O que você sabe sobre {dono}:
{fatos}"""

    # ---------- ferramentas ----------
    def _clima(self, cidade=""):
        cidade = (cidade or self.cfg["CIDADE"]).strip()
        geo = _http_json("https://geocoding-api.open-meteo.com/v1/search?count=1&language=pt&name="
                         + urllib.parse.quote(cidade), timeout=15)
        if not geo.get("results"):
            return f"Não encontrei a cidade {cidade}."
        lugar = geo["results"][0]
        q = urllib.parse.urlencode({
            "latitude": lugar["latitude"], "longitude": lugar["longitude"],
            "current": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
            "timezone": "auto", "forecast_days": 3})
        dados = _http_json("https://api.open-meteo.com/v1/forecast?" + q, timeout=15)
        return json.dumps({"lugar": f"{lugar['name']}, {lugar.get('admin1', '')}",
                           "agora": dados.get("current"), "proximos_dias": dados.get("daily"),
                           "obs": "weather_code segue o padrão WMO"}, ensure_ascii=False)

    def _pesquisar(self, pergunta):
        hoje = datetime.now().strftime("%d/%m/%Y %H:%M")
        resp = _http_json(self.cfg["BUSCA_URL"].rstrip("/") + "/chat/completions", {
            "model": self.cfg["BUSCA_MODELO"],
            "messages": [{"role": "user", "content":
                          f"Agora é {hoje} (horário de Brasília). Pesquise na web e responda em "
                          f"português do Brasil, de forma objetiva, com datas e horários quando houver: "
                          f"{pergunta}"}],
        }, {"Authorization": f"Bearer {self.cfg['BUSCA_CHAVE']}"}, timeout=90)
        return (resp["choices"][0]["message"].get("content") or "Nada encontrado.")[:3000]

    def _executar(self, nome, args):
        try:
            if nome == "lembrar":
                return self.memoria.lembrar(args.get("fato", ""))
            if nome == "esquecer":
                return self.memoria.esquecer(args.get("trecho", ""))
            if nome == "pesquisar_web":
                return self._pesquisar(args.get("pergunta", ""))
            if nome == "clima":
                return self._clima(args.get("cidade", ""))
            return f"Ferramenta desconhecida: {nome}"
        except Exception as e:  # a ferramenta falhar não pode derrubar a conversa
            return f"Erro ao usar {nome}: {e}"

    # ---------- conversa ----------
    def _chamar_modelo(self, mensagens):
        resp = _http_json(self.cfg["LLM_URL"].rstrip("/") + "/chat/completions", {
            "model": self.cfg["LLM_MODELO"],
            "messages": mensagens,
            "tools": self.ferramentas,
            "temperature": 0.7,
            "max_tokens": 600,
        }, {"Authorization": f"Bearer {self.cfg['LLM_CHAVE']}"})
        return resp["choices"][0]["message"]

    def responder(self, texto: str) -> str:
        with self.trava:
            mem = self.memoria
            mem.conversa.append({"role": "user", "content": texto})
            novas = []
            for _ in range(5):  # no máximo 5 rodadas de ferramentas
                msgs = ([{"role": "system", "content": self._sistema()}]
                        + mem.conversa[-MAX_HISTORICO:] + novas)
                try:
                    msg = self._chamar_modelo(msgs)
                except Exception:
                    mem.conversa.pop()  # não deixa a pergunta sem resposta no histórico
                    raise
                chamadas = msg.get("tool_calls") or []
                if not chamadas:
                    resposta = (msg.get("content") or "").strip() or "Hmm, me perdi. Pode repetir?"
                    break
                novas.append({"role": "assistant", "content": msg.get("content") or "",
                              "tool_calls": chamadas})
                for c in chamadas:
                    try:
                        args = json.loads(c["function"].get("arguments") or "{}")
                    except ValueError:
                        args = {}
                    resultado = self._executar(c["function"]["name"], args)
                    print(f"  [ferramenta] {c['function']['name']}({json.dumps(args, ensure_ascii=False)})"
                          f" -> {resultado[:300]}")
                    novas.append({"role": "tool", "tool_call_id": c["id"], "content": resultado})
            else:
                resposta = "Desculpe, me enrolei aqui. Pode repetir?"
            # Guarda só a fala final no histórico (ferramentas ficam de fora para economizar)
            mem.conversa.append({"role": "assistant", "content": resposta})
            mem.salvar()
            return resposta

    def nova_conversa(self):
        with self.trava:
            self.memoria.conversa = []
            self.memoria.salvar()
