# Deployment: DigitalOcean Droplet + Daily Cron

1. Create a small DigitalOcean Droplet from the "Docker" marketplace image (Ubuntu + Docker pre-installed).
2. SSH in and clone this repo:
   ```
   git clone <repo-url> /root/opticlone
   cd /root/opticlone
   ```
3. Create `/root/opticlone/.env` from `.env.sample` (leave `OPENAI_API_KEY` blank; this build's stub uploader needs none).
4. Build the image once:
   ```
   docker build -t opticlone .
   ```
5. Create the persistent state/log directories on the droplet's disk:
   ```
   mkdir -p /root/opticlone/state /root/opticlone/logs
   ```
6. Add a daily cron entry (`crontab -e`):
   ```
   0 6 * * * cd /root/opticlone && docker run --rm --env-file .env \
     -v /root/opticlone/state:/app/state -v /root/opticlone/logs:/app/logs opticlone \
     >> /root/opticlone/logs/cron-$(date +\%F).log 2>&1
   ```
   The bind-mounted `state/` directory is what makes delta detection work across runs — the container itself is fully ephemeral, but the manifest lives on the droplet's disk between invocations.

## Viewing job logs

SSH into the droplet and tail the latest log:
```
ssh root@<droplet-ip>
tail -f /root/opticlone/logs/cron-$(date +%F).log
```
Or inspect the last run's summary directly:
```
cat /root/opticlone/state/last_delta.json
```
