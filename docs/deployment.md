# Deployment: Fly.io Scheduled Machine

Fly.io's [scheduled Machines](https://fly.io/docs/machines/flyctl/fly-machine-run/)
are a better fit for this job than a cron-on-a-VM setup: the same Machine starts
on a daily cycle, runs the container's entrypoint to completion, and auto-stops
when it exits — so you're billed for the few seconds/minutes the job actually
runs per day, not for a droplet sitting idle 24/7.

## One-time setup

1. Install `flyctl` and log in:
   ```
   fly auth login
   ```
2. Create the app shell (no deploy yet):
   ```
   fly apps create opticlone-job
   ```
3. Create a small persistent volume for `state/` (a Fly volume is 1:1 with a
   Machine and lives on the same physical host, so this is what survives
   between scheduled runs — the container filesystem itself is fully ephemeral,
   same as before):
   ```
   fly volumes create opticlone_state --app opticlone-job --region sin --size 1
   ```
4. Set the three OpenAI secrets so the job uses the real
   `OpenAIVectorStoreUploader` instead of the stub. Leave all three unset to
   keep using the stub (e.g. for a dry run):
   ```
   fly secrets set OPENAI_API_KEY=sk-... --app opticlone-job
   fly secrets set OPENAI_ASSISTANT_ID=asst_1C5Q789Hqdbzv9nJsij2DDaI --app opticlone-job
   fly secrets set OPENAI_VECTOR_STORE_ID=vs_... --app opticlone-job
   ```
   `OPENAI_VECTOR_STORE_ID` should be set only *after* a first successful run
   has created one and logged its id (see the README's "Verifying the real
   uploader" section) — leaving it unset on the very first run is expected
   and correct; the uploader creates the store itself.
5. Build and push the image (build-only — do **not** use plain `fly deploy`
   here, see the note below):
   ```
   fly deploy --app opticlone-job --build-only --push
   ```
   This prints the pushed image reference, e.g.
   `registry.fly.io/opticlone-job:deployment-01ABC...`.
6. Create the scheduled Machine, mounting the volume at `/app/state`:
   ```
   fly machine run registry.fly.io/opticlone-job:deployment-01ABC... \
     --app opticlone-job --region sin --schedule daily \
     -v opticlone_state:/app/state
   ```
   Note: Fly's `daily` schedule is fuzzy (roughly once every ~24h from
   creation time), not a fixed clock time like a cron entry — if you need an
   exact time of day, that's a documented Fly limitation, not something this
   job controls.

## Updating the image after a code change

**Do not run plain `fly deploy` on this app** — community reports indicate a
plain deploy can wipe a Machine's schedule configuration. Instead:

```
fly deploy --app opticlone-job --build-only --push
fly machine update <machine-id> --app opticlone-job \
  --image registry.fly.io/opticlone-job:<new-deployment-tag> \
  --schedule daily
```

Always re-pass `--schedule daily` on update so the schedule isn't silently
dropped. Get the machine ID via `fly machine list --app opticlone-job`.

## Viewing job logs

```
fly logs --app opticlone-job
```

Or use the Fly dashboard's Monitoring page for the app (`fly dashboard opticlone-job`).

## Viewing the last-run artifact

The Machine is normally in a stopped state between scheduled runs. Start it
briefly to inspect the mounted state, then let it go back to sleep on its own
schedule:

```
fly machine start <machine-id> --app opticlone-job
fly ssh console --app opticlone-job -C "cat /app/state/last_delta.json"
```

## Cost note

This replaces an earlier DigitalOcean Droplet design, which bills for a
continuously-running VM regardless of whether the job is executing. A
scheduled Fly Machine only bills for compute while actually started — for a
job that runs for well under a minute once a day, this is close to free
beyond the volume's small storage cost.
