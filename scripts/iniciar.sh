#!/data/data/com.termux/files/usr/bin/bash
# Liga o Ultron e cria um endereço https público (Cloudflare) para usar o microfone de qualquer lugar.
cd "$(dirname "$0")/.."
command -v termux-wake-lock >/dev/null && termux-wake-lock  # não deixa o Android "dormir" o Ultron

PORTA=$(grep -E '^PORTA=' .env 2>/dev/null | tail -1 | cut -d= -f2-); PORTA=${PORTA:-8000}
NTFY=$(grep -E '^NTFY_TOPICO=' .env 2>/dev/null | tail -1 | cut -d= -f2-)

trap 'kill 0' INT TERM  # Ctrl+C desliga tudo (servidor e túnel)

# Servidor: se cair, sobe de novo
( while true; do python server.py; echo "Servidor caiu, reiniciando em 5s"; sleep 5; done ) &
sleep 2

# Túnel: o endereço muda cada vez que liga; mostramos aqui e (opcional) mandamos pelo ntfy
while true; do
  cloudflared tunnel --no-autoupdate --url "http://localhost:$PORTA" 2>&1 | while read -r linha; do
    url=$(echo "$linha" | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com')
    if [ -n "$url" ]; then
      echo
      echo "=============================================="
      echo "  Ultron no ar:  $url"
      echo "=============================================="
      echo "$url" > endereco.txt
      [ -n "$NTFY" ] && curl -s -H "Title: Ultron online" -H "Click: $url" -d "$url" "https://ntfy.sh/$NTFY" >/dev/null
    fi
  done
  echo "Túnel caiu, reconectando em 5s"; sleep 5
done &
wait
