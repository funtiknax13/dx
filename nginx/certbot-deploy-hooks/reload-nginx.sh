#!/bin/sh
# certbot renews cert files on disk but never reloads nginx on its own here
# (authenticator=webroot, no --nginx installer plugin) — without this, nginx
# keeps serving the stale pre-renewal cert from its running workers until
# it's manually reloaded/restarted. Install: copy to
# /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh and `chmod +x` it —
# certbot runs every executable script in that directory after a successful
# renewal. See DEPLOY.md.
systemctl reload nginx
