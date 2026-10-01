#!/data/data/com.termux/files/usr/bin/bash
# Liga o Ultron e cria um endereço https público (Cloudflare) para usar o microfone de qualquer lugar.
cd "$(dirname "$0")/.."
command -v termux-wake-lock >/dev/null && termux-wake-lock  # não deixa o Android "dormir" o Ultron

PORTA=$(grep -E '^PORTA=' .env 2>/dev/null | tail -1 | cut -d= -f2-); PORTA=${PORTA:-8000}
NTFY=$(grep -E '^NTFY_TOPICO=' .env 2>/dev/null | tail -1 | cut -d= -f2-)

trap 'kill 0' INT TERM  # Ctrl+C desliga tudo (servidor e túnel)

avisar() { [ -n "$NTFY" ] && curl -s -H "Title: $1" ${3:+-H "Click: $3"} -d "$2" "https://ntfy.sh/$NTFY" >/dev/null; }

# Servidor: se cair (ou for reiniciado por uma atualização), sobe de novo
( while true; do
    python server.py & echo $! > .servidor.pid; wait $!
    echo "Servidor reiniciando..."; sleep 2
  done ) &
sleep 2

# Atualização automática: a cada 3 minutos procura novidades no GitHub. Se houver,
# baixa e reinicia só o servidor; o túnel continua de pé, então o link não muda.
( while true; do
    sleep 180
    git fetch -q origin 2>/dev/null || continue
    if [ "$(git rev-parse HEAD)" != "$(git rev-parse '@{u}')" ] && git pull -q --ff-only; then
      echo; echo "==> Atualizado: $(git log -1 --format=%s)"
      kill "$(cat .servidor.pid)" 2>/dev/null
      avisar "Ultron atualizado" "$(git log -1 --format=%s)" "$(cat endereco.txt 2>/dev/null)"
    fi
  done ) &

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
      avisar "Ultron online" "$url" "$url"
    fi
  done
  echo "Túnel caiu, reconectando em 5s"; sleep 5
done &
wait
