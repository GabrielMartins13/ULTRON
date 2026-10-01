# U.L.T.R.O.N.

Assistente pessoal de voz, inspirado no Ultron dos Vingadores (mas leal a você). Você conversa falando, como numa ligação, e ele responde em voz alta. Ele lembra o que você conta sobre você, pesquisa na internet (jogos, notícias, preços) e consulta a previsão do tempo. Tudo roda num celular Android velho, que vira o servidor.

```
 Seu celular (app no navegador)              Celular velho (Termux)                 Internet (grátis)
 ┌───────────────────────────┐   https   ┌──────────────────────────┐
 │ microfone → detecta a fala├──────────►│ server.py                │──► Groq Whisper (voz → texto)
 │ toca a resposta em voz    │◄──────────┤  ├ brain.py  (mente)      │──► Groq / Gemini (cérebro)
 └───────────────────────────┘ Cloudflare│  ├ voice.py  (ouvido/voz)│──► Edge TTS (texto → voz)
                                  túnel  │  └ data/ (memória)       │──► Open-Meteo (clima)
                                         └──────────────────────────┘
```

O celular velho não tem força pra rodar uma IA sozinho. Por isso o "pensar", o "ouvir" e o "falar" usam serviços gratuitos na internet, e o celular velho cuida da conversa, da memória e do acesso.

## O que você precisa

- O celular Android velho, ligado na tomada e no Wi‑Fi
- Uma chave grátis do **Groq**: https://console.groq.com/keys. Não pede cartão. Ela serve pro cérebro e pro ouvido.
- Seu celular de uso, com Safari (iPhone) ou Chrome (Android)

## Instalação no celular velho

1. Instale o **Termux** e o **Termux:Boot** pela **F-Droid** (https://f-droid.org). As versões da Play Store estão abandonadas e não funcionam direito.
2. Abra o Termux:Boot uma vez (é só abrir e fechar). Isso deixa o Ultron ligar sozinho quando o celular reiniciar.
3. No Android, vá em **Configurações → Apps → Termux → Bateria** e marque **Sem restrições**. Sem isso, o Android "mata" o Ultron depois de um tempo.
4. No Termux, rode:

   ```bash
   pkg install -y git
   git clone https://github.com/<seu-usuario>/ultron.git
   cd ultron
   bash scripts/instalar.sh
   nano .env        # preencha ULTRON_SENHA, DONO_NOME e LLM_CHAVE (Ctrl+O salva, Ctrl+X sai)
   bash scripts/iniciar.sh
   ```

5. Vai aparecer um endereço tipo `https://palavras-aleatorias.trycloudflare.com`. É o Ultron no ar.

## Usando no seu celular

1. Abra o endereço no Safari ou no Chrome e entre com a senha.
2. Coloque na tela de início. No iPhone: **Compartilhar → Adicionar à Tela de Início**. No Android: **⋮ → Adicionar à tela inicial**.
3. Toque em **Ligar** e permita o microfone. Agora é só falar. Quando você para de falar, ele responde e volta a escutar sozinho.

- Toque no orbe enquanto ele fala para **interromper**.
- ⌨ escreve em vez de falar. 🧠 mostra o que ele lembra de você. ↻ começa outra conversa (a memória continua).
- Exemplos: *"Ultron, lembra que a minha mãe faz aniversário dia 12 de março"*, *"Vai chover amanhã?"*, *"Quando é o próximo jogo do Corinthians?"*, *"Esquece aquilo da academia"*.
- Use fone de ouvido em lugar barulhento: ajuda ele a saber quando você terminou de falar.

### O endereço muda

O endereço gratuito do Cloudflare muda cada vez que o Ultron reinicia. Para receber o endereço novo no celular automaticamente:

1. Instale o app **ntfy** (iPhone ou Android).
2. Invente um nome de tópico difícil de adivinhar, como `ultron-gabriel-8f3k2`. Coloque em `NTFY_TOPICO` no `.env` e inscreva-se nesse mesmo tópico no app.
3. Toda vez que o Ultron ligar, chega uma notificação com o link.

O endereço atual também fica salvo no arquivo `endereco.txt`, dentro da pasta do Ultron no celular velho.

Para ter um endereço fixo, dá pra usar um túnel nomeado do Cloudflare (precisa de um domínio próprio) ou o Tailscale.

## Configuração (`.env`)

| Variável | Para quê |
|---|---|
| `ULTRON_SENHA` | Senha para abrir o app. O endereço é público, então use uma senha forte. |
| `DONO_NOME` | Como o Ultron te chama |
| `LLM_URL`, `LLM_CHAVE`, `LLM_MODELO` | O cérebro. Padrão: Groq com `openai/gpt-oss-120b`. Também funciona com o Gemini (veja o `.env.example`) ou qualquer API compatível com OpenAI. |
| `STT_CHAVE`, `STT_MODELO` | O ouvido (Whisper do Groq). Se ficar vazio e o cérebro for o Groq, usa a mesma chave. Sem chave do Groq, o app usa o reconhecimento de voz do navegador (funciona melhor no Chrome). |
| `BUSCA_CHAVE`, `BUSCA_MODELO` | Pesquisa na web (modelo `groq/compound-mini`, grátis). Se ficar vazio e o cérebro for o Groq, usa a mesma chave. |
| `VOZ`, `VOZ_VELOCIDADE`, `VOZ_TOM` | Voz neural da Microsoft. Masculina: `pt-BR-AntonioNeural`. Femininas: `pt-BR-FranciscaNeural` e `pt-BR-ThalitaMultilingualNeural`. O `VOZ_TOM` negativo deixa a voz mais grave, no estilo do Ultron. |
| `CIDADE` | Cidade padrão do clima |
| `NTFY_TOPICO` | Avisa o endereço novo pelo app ntfy |

Para trocar a personalidade, edite o texto em `_sistema()` no `brain.py`. Para dar novas habilidades, adicione uma ferramenta em `FERRAMENTAS` e trate ela em `_executar()`.

## Limites do plano grátis

O plano grátis do Groq dá algo em torno de 30 pedidos por minuto e alguns milhares por dia. Para uma pessoa conversando, sobra. Se um modelo for desativado pelo Groq, troque `LLM_MODELO` pela lista em https://console.groq.com/docs/models.

## Problemas comuns

- **"Abra pelo endereço https para usar o microfone"**: o navegador só libera o microfone em https. Use o endereço do `trycloudflare.com`, e não o IP do celular.
- **Ele fala com voz de robô**: a voz neural (Edge TTS) falhou e o app usou a voz do seu celular. Veja o `ultron.log` ou a tela do Termux.
- **Parou de responder depois de um tempo**: confira se a bateria do Termux está em "Sem restrições" e se a notificação do Termux continua aparecendo.
- **A tela apagou e ele desligou**: o celular corta o microfone com a tela apagada. Enquanto está ligado, o app tenta manter a tela acesa.
