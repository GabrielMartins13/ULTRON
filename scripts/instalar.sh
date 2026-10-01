#!/data/data/com.termux/files/usr/bin/bash
# Instala o Ultron no Termux (Android). Rode uma vez:  bash scripts/instalar.sh
set -e
cd "$(dirname "$0")/.."

echo "==> Atualizando pacotes do Termux"
pkg update -y
pkg install -y python cloudflared termux-api git

echo "==> Instalando a voz (edge-tts)"
# Pula partes em C que às vezes não compilam no Android (as versões em Python puro funcionam igual)
AIOHTTP_NO_EXTENSIONS=1 MULTIDICT_NO_EXTENSIONS=1 YARL_NO_EXTENSIONS=1 \
  FROZENLIST_NO_EXTENSIONS=1 PROPCACHE_NO_EXTENSIONS=1 \
  pip install --upgrade edge-tts

if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "==> Criei o arquivo .env. Agora edite com:  nano .env"
  echo "    Preencha pelo menos ULTRON_SENHA e LLM_CHAVE."
fi

echo "==> Configurando para ligar sozinho quando o celular reiniciar (precisa do app Termux:Boot)"
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/ultron.sh <<BOOT
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
cd "$PWD" && bash scripts/iniciar.sh >> ultron.log 2>&1
BOOT
chmod +x ~/.termux/boot/ultron.sh scripts/*.sh

echo
echo "Pronto! Para ligar o Ultron agora:  bash scripts/iniciar.sh"
