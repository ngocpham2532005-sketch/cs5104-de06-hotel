"""Sinh build/compose.<MÁY>.yml từ deploy.toml: chỉ các trạm của máy đó, cổng công bố ra LAN."""
import sys
from cfg import DB, ROOT, SITES, site

machine = (sys.argv[1] if len(sys.argv) > 1 else "A").upper()
mine = [s for s in SITES if site(s)["machine"] == machine]
if not mine:
    sys.exit(f"Máy {machine} không có trạm nào trong deploy.toml")
lines = [f"name: cs5104-de06-{machine.lower()}", "services:"]
for s in mine:
    i = site(s)
    lines += [
        f"  {s}:",
        "    build: ../docker",
        "    image: cs5104-de06-pg:18",
        f"    container_name: hotel_{s}",
        "    environment:",
        f"      POSTGRES_USER: {DB['user']}",
        f"      POSTGRES_PASSWORD: \"{DB['password']}\"",
        "    command: [\"postgres\", \"-c\", \"max_prepared_transactions=50\", \"-c\", \"listen_addresses=*\"]",
        "    ports:",
        f"      - \"0.0.0.0:{i['port']}:5432\"",
        "    volumes:",
        f"      - pg_{s}:/var/lib/postgresql",       # postgres:18 dùng /var/lib/postgresql/18/docker
        "    cap_add: [NET_ADMIN]",                      # cho tc netem (make delay-on)
        "    healthcheck:",
        f"      test: [\"CMD-SHELL\", \"pg_isready -U {DB['user']}\"]",
        "      interval: 2s",
        "      timeout: 3s",
        "      retries: 30",
    ]
lines += ["volumes:"] + [f"  pg_{s}: {{}}" for s in mine]
out = ROOT / "build" / f"compose.{machine}.yml"
out.parent.mkdir(exist_ok=True)
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"{out.relative_to(ROOT)}: {', '.join(f'{s}:{site(s)['port']}' for s in mine)}")
