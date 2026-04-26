# autodeploy

Self-hosted auto-deploy for your VPS. Push to GitHub → your server pulls and restarts automatically.

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/braxtonelmer/autodeploy/master/install.sh | bash
```

Or from source:

```bash
git clone https://github.com/braxtonelmer/autodeploy.git
cd autodeploy
pip install -e .
```

---

## Setup

Run the setup wizard inside your project repo:

```bash
cd /path/to/your/repo
autodeploy init
```

It will ask you for:

1. **Repo path** — absolute path to your project (e.g. `/home/ubuntu/myapp`)
2. **Branch** — which branch to watch (default: `main`)
3. **Build commands** — one per line, empty line to finish (e.g. `npm install`, `npm run build`)
4. **Restart command** — how to restart your app (e.g. `pm2 restart myapp`)
5. **Health check URL** — optional, autodeploy will poll this after restart to confirm it's up
6. **Webhook secret** — press Enter to generate one automatically

After `init`:
- `deploy.yaml` is written to your repo root — **commit this file**
- `.env` is written to the current directory — **do not commit this file** (add it to `.gitignore`)
- A systemd service is created and enabled

Then start the server:

```bash
autodeploy start
```

---

## Commands

| Command | What it does |
|---|---|
| `autodeploy init` | Interactive setup wizard |
| `autodeploy start` | Start the webhook server via systemd |
| `autodeploy stop` | Stop the webhook server |
| `autodeploy status` | Show current commit, branch, last deploy result |
| `autodeploy logs` | Show last 20 deploys (use `-n 50` for more) |
| `autodeploy rollback` | Roll back to the commit before the last deploy |

---

## deploy.yaml examples

### Node.js with PM2

```yaml
branch: main

build:
  - npm install --production
  - npm run build

restart:
  command: pm2 restart myapp

health_check:
  url: http://localhost:3000/health
  timeout: 30
  retries: 3

rollback:
  on_failure: true
```

### Python with Gunicorn

```yaml
branch: main

build:
  - pip install -r requirements.txt

restart:
  command: systemctl restart myapp

health_check:
  url: http://localhost:8000/health
  timeout: 30
  retries: 3

rollback:
  on_failure: true
```

### Docker Compose

```yaml
branch: main

build:
  - docker compose pull
  - docker compose build

restart:
  command: docker compose up -d

health_check:
  url: http://localhost:80/health
  timeout: 60
  retries: 5

rollback:
  on_failure: false
```

### Static site (nginx)

```yaml
branch: main

build:
  - npm ci
  - npm run build
  - rsync -a --delete dist/ /var/www/mysite/

restart:
  command: nginx -s reload

rollback:
  on_failure: true
```

---

## GitHub webhook setup

1. Go to your repo → **Settings** → **Webhooks** → **Add webhook**
2. **Payload URL**: `https://yourdomain.com/webhook`
3. **Content type**: `application/json`
4. **Secret**: paste the secret from your `.env` file (`WEBHOOK_SECRET=...`)
5. **Which events**: select **Just the push event**
6. Click **Add webhook**

GitHub will send a ping — you should see a green checkmark.

---

## nginx config

autodeploy binds to `127.0.0.1:5000` by default. Put nginx in front of it to handle HTTPS:

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location /webhook {
        proxy_pass         http://127.0.0.1:5000/webhook;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_read_timeout 60s;
    }

    location /health {
        proxy_pass http://127.0.0.1:5000/health;
    }
}
```

Get a free certificate with Certbot:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

---

## Rollback

When a deploy fails and `rollback.on_failure: true` is set in `deploy.yaml`, autodeploy automatically:

1. Runs `git reset --hard <previous-commit>`
2. Re-runs your restart command
3. Logs the result as `rolled_back`

To roll back manually at any time:

```bash
autodeploy rollback
```

This resets to the commit before the most recent deploy and re-runs the restart command. Build steps are **not** re-run on rollback.

To see deploy history before rolling back:

```bash
autodeploy logs
```

---

## Environment variables (.env)

| Variable | Description | Default |
|---|---|---|
| `WEBHOOK_SECRET` | GitHub webhook secret | required |
| `REPO_PATH` | Absolute path to your repo | required |
| `PORT` | Port to bind the webhook server | `5000` |
| `LOG_PATH` | Path to the deploy log file | `~/.autodeploy/deploy.log.jsonl` |

---

## Troubleshooting

**Wrong secret / signature mismatch**

The webhook server returns 403. Make sure the secret in your GitHub webhook settings matches `WEBHOOK_SECRET` in `.env` exactly — no extra spaces or quotes.

**Port not open / GitHub can't reach the server**

Check your firewall allows port 443 (or 80):
```bash
sudo ufw allow 443
```
Also verify nginx is running and your SSL cert is valid. Test locally:
```bash
curl -s http://127.0.0.1:5000/health
# should return {"status": "ok"}
```

**Git permission errors**

The service runs as the user set during `autodeploy init`. That user must own the repo directory and have SSH access to GitHub (if using SSH remotes) or a credential helper configured for HTTPS.

```bash
# check who owns the repo
ls -la /path/to/repo

# run the pull manually as the service user to test
sudo -u youruser git -C /path/to/repo pull origin main
```

**Deploy not triggering**

Check the service is running:
```bash
autodeploy status
journalctl -u autodeploy -f
```

Check the GitHub webhook delivery tab (Settings → Webhooks → Recent Deliveries) for error responses.

**Viewing full deploy output**

```bash
autodeploy logs -n 5
cat ~/.autodeploy/deploy.log.jsonl | python3 -m json.tool | less
```
