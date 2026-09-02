# petite-étoile — Asterisk PBX dockerisé + interface de gestion

Stack Docker Compose pour un PBX résidentiel Asterisk (trunks VoIP.ms +
Twilio) avec une interface web full CRUD (extensions, trunks, routes,
voicemail, CDR). Remplace un déploiement précédent (Debian nu sur Proxmox,
config à la main) par quelque chose de reproductible et plus simple à
restaurer après corruption.

## Architecture

```
petite-etoile/
├── docker-compose.yml            # topologie prod (asterisk en network_mode: host)
├── docker-compose.override.yml   # dev local (asterisk en bridge normal)
├── asterisk/                     # image Asterisk compilée from source
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── etc-asterisk/             # config statique de base (copiée une fois)
│   └── etc-asterisk-templates/   # manager.conf/cdr_pgsql.conf/msmtprc (rendus à chaque boot)
├── webapp/                       # FastAPI — interface de gestion
│   ├── app/
│   ├── alembic/
│   └── Dockerfile
└── data/                         # volumes persistants (bind mounts)
    ├── asterisk-etc/             # pjsip.conf/extensions.conf/voicemail.conf générés
    ├── asterisk-spool/           # voicemail, recordings
    ├── asterisk-log/
    └── postgres/
```

**La base Postgres est la source de vérité.** Chaque modification
(extension, trunk, route) déclenche : écriture en DB → régénération de
`pjsip.conf` / `extensions.conf` / `voicemail.conf` depuis des templates
Jinja2 → reload sélectif via AMI (`module reload res_pjsip.so`, `dialplan
reload`, `voicemail reload`). Pas de restart de conteneur, pas de coupure des appels
en cours.

**Important — la régénération est toujours totale, pas incrémentale.** Les
3 fichiers sont entièrement réécrits depuis l'état complet de la DB à
*chaque* déclenchement, pas seulement la section touchée. Concrètement :
toute modification manuelle faite directement dans `pjsip.conf`,
`extensions.conf` ou `voicemail.conf` (ou via la CLI Asterisk, `asterisk
-rx "..."`) sera perdue dès qu'une extension, un trunk ou une route
*quelconque* est créé/modifié/supprimé via l'UI ou l'API — même un
enregistrement complètement différent de celui que vous avez édité à la
main. C'est voulu (source de vérité unique = DB), mais ça peut surprendre
en debug. Les seuls déclencheurs possibles sont : POST/PUT/DELETE sur
`/api/extensions`, `/api/trunks`, `/api/inbound-routes`,
`/api/outbound-routes` (ou les formulaires équivalents de l'UI), et
`POST /api/reload`. Aucune régénération périodique/planifiée n'existe, et
les commandes CLI/AMI envoyées directement à Asterisk (`pjsip send
register`, etc.) ne peuvent pas déclencher de régénération — le webapp n'a
aucune visibilité sur ces actions. Chaque régénération logge son
déclencheur (`Regenerating ... (reason: extension 101 updated)`, etc.)
dans les logs du conteneur `webapp` — utile pour retracer une écrasement
inattendu.

Le CDR fonctionne à l'inverse : Asterisk (`cdr_pgsql`) écrit directement
dans la table `cdr` de la même base Postgres ; le webapp ne fait que lire.

### Pourquoi `network_mode: host` pour asterisk ?

Asterisk + RTP dans Docker est pénible (NAT du conteneur + NAT du routeur
maison). En faisant tourner le conteneur `asterisk` en `network_mode: host`,
le LXC expose directement son IP LAN — pas besoin de mapper la plage RTP
(10000-20000/udp) port par port, et une couche de NAT en moins.
`webapp` et `db` restent sur le réseau bridge Docker interne.

Cela a deux conséquences qu'il faut connaître :

1. **AMI** : `webapp` (bridge) doit joindre `asterisk` (host) via l'IP du
   LXC — on utilise `host.docker.internal` (résolu via `extra_hosts:
   host-gateway`) plutôt que `127.0.0.1`, qui ne fonctionnerait pas depuis
   un conteneur bridge. `manager.conf` écoute donc sur `0.0.0.0` (obligé,
   puisque le trafic arrive par l'interface bridge Docker, pas loopback) et
   restreint l'accès par ACL (`permit=172.16.0.0/12`) plutôt que par bind.
2. **cdr_pgsql** : à l'inverse, Asterisk (host) doit joindre `db` (bridge).
   `db` publie donc son port sur `127.0.0.1:5432` de l'hôte, et
   `cdr_pgsql.conf` pointe sur `127.0.0.1`.

`docker-compose.override.yml` (chargé automatiquement en local) bascule
`asterisk` en réseau bridge normal pour que tout ça marche sans LXC/LAN réel
— pratique pour développer ou pour que Claude Code valide que la stack
démarre. Pour un déploiement réel, il faut explicitement **ignorer**
l'override :

```bash
docker compose -f docker-compose.yml up -d
```

## 1. Préparation du LXC Proxmox (manuel, avant tout le reste)

Sur le host Proxmox :

```bash
pct set <VMID> -features nesting=1,keyctl=1
```

Dans le LXC :

```bash
apt update && apt install -y docker.io docker-compose-plugin
systemctl enable --now docker
```

Donnez au LXC une IP fixe sur le LAN (ex. `192.168.0.146`) — c'est cette IP
qui sera utilisée par les softphones et par Tailscale.

### Pare-feu / NAT du routeur

- **5060/udp (SIP)** : seulement via Tailscale, jamais exposé publiquement.
- **10000-20000/udp (RTP)** : idem, seulement pour les softphones externes
  qui en ont besoin (via Tailscale).

## 2. Déploiement

```bash
git clone <ce repo> petite-etoile && cd petite-etoile
cp .env.example .env
# éditer .env : DB_PASSWORD, AMI_SECRET, SECRET_KEY, ADMIN_PASSWORD, ...
mkdir -p data/asterisk-etc data/asterisk-spool data/asterisk-log data/postgres

# Prod (LXC réel, asterisk en network_mode: host) :
docker compose -f docker-compose.yml up -d --build

# Migrations DB (déjà lancées automatiquement au démarrage du conteneur
# webapp — voir webapp/Dockerfile — mais peuvent être relancées à la main) :
docker compose exec webapp alembic upgrade head
```

L'interface est servie sur `http://<IP-du-LXC>:8000`. Connectez-vous avec
`ADMIN_USERNAME` / `ADMIN_PASSWORD` (ou le mot de passe généré et loggé au
premier démarrage si `ADMIN_PASSWORD` était vide) puis changez-le.

Aucune donnée n'est reprise de l'ancien serveur : extensions, trunks et
routes se créent à neuf depuis l'interface une fois déployée.

### Développement local (sans LXC)

```bash
cp .env.example .env
docker compose up -d --build   # charge automatiquement l'override bridge
```

## Variables d'environnement

Voir `.env.example` — chaque variable y est commentée. Les identifiants de
trunk (VoIP.ms, Twilio) ne sont **pas** dans `.env` : ils se créent depuis
la page *Trunks* de l'interface et sont stockés en DB.

## Modules Asterisk

Compilé depuis les sources (LTS courante — voir
`asterisk/Dockerfile`, `ASTERISK_SERIES`) plutôt que le paquet Debian,
souvent daté. Modules activés : `chan_pjsip` + `res_pjsip*`, `app_voicemail`,
`cdr_pgsql`, `res_musiconhold`, `app_dial`, `app_queue`, `res_ari*` (ARI
compilé mais désactivé par défaut dans `http.conf` — AMI suffit pour le
webapp), `app_directory` (répertoire par nom, voir IVR ci-dessous) et
`chan_rtp` (paging multicast).

## IVR (répertoire / accueil automatique)

Un seul menu d'accueil, configurable sur la page *IVR* de l'interface et
utilisable comme destination sur n'importe quelle route entrante. Les
prompts sont en **français** (`CORE-SOUNDS-FR-ULAW`, `CHANNEL(language)=fr`
posé dès `Answer()`) — Asterisk retombe automatiquement sur le prompt
anglais pour tout ce que le paquet français ne couvre pas.

- l'appelant qui connaît le numéro de poste peut le composer immédiatement
  (dial-through direct, aucune touche à presser) ;
- appuyer sur **1** ouvre le sous-menu répertoire :
  - **1** = recherche par nom épelé (`Directory()`, contre les entrées
    `voicemail.conf` — seules les extensions avec messagerie vocale
    activée y apparaissent) ;
  - **2** = liste parlée, plafonnée à 9 entrées (une par chiffre),
    triée alphabétiquement par nom — inclut les extensions avec messagerie
    vocale activée **et** la case "visible dans le répertoire" cochée
    (page *Extensions*, indépendant l'un de l'autre). Chaque entrée
    annonce le nom enregistré par la personne (`*97` → options de la
    boîte vocale → enregistrer son nom) si disponible, sinon le numéro de
    poste en secours ; appuyer sur le chiffre annoncé compose directement
    cette extension ;
- sans touche pressée dans le délai configuré, l'appel bascule vers le
  fallback choisi (extension, groupe de sonnerie, boîte vocale ou
  raccrocher).

Comme "1" est aussi un préfixe valide de certaines extensions à plusieurs
chiffres, Asterisk attend brièvement d'autres chiffres après un "1" avant
de trancher (comportement standard de collecte DTMF, pas un bug — le même
compromis existe dans n'importe quel IVR qui réutilise "1" comme option de
menu).

### Message d'accueil personnalisé

Composez **\*81** depuis n'importe quel poste interne pour enregistrer votre
propre message d'accueil, à la place des prompts génériques d'Asterisk
(`vm-enter-num-to-call`, `vm-press`). Le message est relu immédiatement
pour confirmation, avec une option pour le réenregistrer avant de le
sauvegarder — un essai abandonné ou raccroché en cours de route ne touche
jamais le message actuellement actif. La page *IVR* affiche si un message
personnalisé est configuré (avec un lecteur audio de prévisualisation) et
permet de le supprimer pour revenir au message par défaut. La page *IVR*
affiche aussi la structure complète du menu (quelle touche fait quoi, et
qui est dans la liste parlée) — utile comme script si vous enregistrez
votre propre message. `*81` est joignable comme `*97`/`*98`/`*80`, sans
protection par NIP.

## Sécurité

- SIP (5060/udp) accessible uniquement via Tailscale.
- `manager.conf` restreint l'accès AMI par ACL (voir plus haut).
- Endpoints PJSIP avec `disallow=all` / `allow=ulaw,alaw` explicite, pas de
  wildcard.
- Mots de passe SIP en clair dans `pjsip.conf` (requis par Asterisk) mais
  jamais renvoyés par l'API/l'UI une fois enregistrés (champs à saisie
  seule, jamais affichés).
- Rate-limit (5/min/IP) sur `/api/auth/login`.
- **Hors scope de ce dépôt** (à faire une fois le LXC prêt, dépend des
  chemins réels) : configuration `fail2ban` sur les logs Asterisk, tuning
  RTP/NAT fin, seed des vraies extensions/trunks/DIDs.

## Dépannage rapide

- `GET /health` sur le webapp indique si l'AMI est connecté.
- Logs Asterisk : `data/asterisk-log/` (bind mount, lisible depuis l'hôte).
- Si le reload PJSIP ne semble pas pris en compte : vérifier que webapp a
  bien accès en écriture au même volume que `/etc/asterisk` du conteneur
  asterisk (`data/asterisk-etc` doit être monté dans les deux services).
- Pour forcer une régénération + reload manuel : `POST /api/reload`.
