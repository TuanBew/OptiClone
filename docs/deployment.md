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
   has created one and logged its id (see "Verifying the real uploader"
   below) — leaving it unset on the very first run is expected and correct;
   the uploader creates the store itself.
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

## Verifying the real uploader (do this before scaling up)

The uploader is fully covered by offline tests, but should be run against
the real OpenAI API deliberately, not incidentally — only you, with your own
API key and budget, should decide when that happens. Recommended order,
since OpenAI usage is billed:

1. Confirm `.venv/Scripts/pytest -v` is fully green first.
2. **Back up and clear local state first.** `state/` is gitignored but
   persists across runs on your machine, and if you've scraped articles
   locally before, `state/manifest.json` already tracks them. Running the
   tiny-scope test below without clearing it will likely fetch an article
   that's already recorded with an unchanged hash, get classified `skipped`,
   and never reach the uploader at all — a silent no-op on your one live
   attempt. Move the existing state aside first (skip this step if you don't
   already have a local `state/` directory):
   ```bash
   mv state state_backup   # restore later with: mv state_backup state
   ```
3. Run locally with a tiny scope to exercise the real path end-to-end at
   near-zero cost:
   ```bash
   # In .env: set OPENAI_API_KEY and OPENAI_ASSISTANT_ID, leave
   # OPENAI_VECTOR_STORE_ID empty, and set ARTICLE_LIMIT=1
   .venv/Scripts/python main.py
   ```
   Check the log line `Created new OpenAI Vector Store id=...` and
   `files embedded=1 chunks embedded=N`, then copy the printed vector store
   id into `.env` as `OPENAI_VECTOR_STORE_ID` so the next run reuses it
   instead of creating another one.
4. Run again locally with the same small `ARTICLE_LIMIT` to confirm a
   no-change second run uploads nothing. With an empty delta,
   `OpenAIVectorStoreUploader.upload()` returns immediately without logging
   a `files embedded=...` line at all — the signal to look for instead is
   `main.py`'s own summary line: `Delta complete: added=0 updated=0 skipped=1`.
5. Do **not** restore the `state_backup` you made in Step 2. The manifest now
   on disk already has a real `file_id` for the one article you just tested,
   and leaving it in place means the next run correctly treats that article
   as `skipped` (no wasted duplicate re-upload) while every other article —
   never actually uploaded to OpenAI before this point — gets embedded for
   real for the first time. (`state_backup` exists only as a rollback if the
   tiny test needs to be abandoned and retried from a clean slate:
   `rm -rf state && mv state_backup state` restores it for that case.) Keep
   `OPENAI_API_KEY` set, raise `ARTICLE_LIMIT` back to 50 (or unset it) for
   the full local run, then set the three OpenAI values as Fly secrets
   (Step 4 above) and redeploy the scheduled Machine.

Treat any failure in steps 3-4 as a stopping point to fix and re-test
offline first (adding a case to `tests/test_openai_uploader.py` if it
reveals a gap in the mocked coverage) rather than immediately retrying
against the live API.
