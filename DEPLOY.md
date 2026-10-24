# Deploying ExportAgent on AWS EC2

The public demo runs on one small EC2 server in **Asia Pacific (Sydney), ap-southeast-2**. The server only downloads Docker images that GitHub Actions builds, then serves them with automatic HTTPS from Caddy.

## Live deployment

**URL: <https://3-104-80-176.sslip.io>**. The health check is at <https://3-104-80-176.sslip.io/health>.

Deployed on 24 October 2026 with the AWS CLI, in account `121728644468`. Every resource is tagged `Project=ExportAgent`.

| Resource | ID | Details |
|---|---|---|
| EC2 instance | `i-0bb6ebc9cbec44c5c` | t4g.micro (2 vCPU, 1 GB RAM, ARM), ap-southeast-2a, Ubuntu 24.04 (`ami-0b58dc56768a169ca`), standard CPU credits, IMDSv2 required |
| Root volume | `vol-0421f1d6e24e5ef68` | 10 GB gp3, encrypted, deleted with the instance |
| Elastic IP | `eipalloc-0bb989304b463a2e4` | **3.104.80.176**, association `eipassoc-04af2c01795ca1c0d` |
| Network interface | `eni-03562bf80d540f6f1` | The instance's own; deleted with it |
| Security group | `sg-02e88eda2ccd60068` (`exportagent-web`) | 22 from 171.76.106.177/32 only (`sgr-019ebd96b44c2903d`), 80 (`sgr-02a22a8e127fb7b1c`) and 443 (`sgr-0c1f112dc3049d47d`) from anywhere |
| Key pair | `key-0fd6247b1fa7c7432` (`exportagent-ec2`) | ed25519, fingerprint `SHA256:6khSO1OhrnJ5OJ5e5fY8ArIncC1fRtVFIA5KG8OGBjc` |
| AWS Budget | `exportagent-monthly` | Monthly, credits excluded. Emails at **$15 actual** and **$17 forecast** |
| VPC / subnet | `vpc-04a41b296745d1f2e` / `subnet-02ca15879ee8c16cc` | The account's default VPC, not created by us |

| Piece | Choice |
|---|---|
| Containers | `api` (FastAPI), `web` (Next.js standalone) and `caddy`, from `deploy/docker-compose.yml` |
| Database | SQLite in a Docker volume, in WAL mode. Backed up nightly at 02:30 UTC, last 7 days kept |
| Images | GitHub Container Registry, **private**, pulled with a classic `read:packages` token |
| Limits | $1/day model spend cap, 10 LLM requests per minute per IP, memory limits per container, log rotation |
| Not used | Load balancer, RDS, NAT gateway, anything else that costs extra |

**Why Sydney and not Mumbai:** this AWS project is restricted to one Region, Sydney. A service control policy denies every EC2 call in ap-south-1.

## Cost

Prices for Sydney, from the AWS Price List API in October 2026. The server runs 730 hours a month.

| Item | Price | Per month |
|---|---|---|
| t4g.micro, on demand | $0.0106 per hour | $7.74 |
| 10 GB gp3 disk | $0.096 per GB-month | $0.96 |
| Public IPv4 (the Elastic IP) | $0.005 per hour | $3.65 |
| Data out | first 100 GB a month free | $0.00 |
| **Total** | | **about $12.35** |

Running from 24 October to 15 December costs about $21 of the $119.81 free-plan credits. The free plan expires on 21 April 2027. A t4g.small ($0.0212 an hour) would make the total about $20.10 a month.

You pay these from your credits until you delete everything (see [Teardown](#teardown-after-15-december)). A stopped instance still pays for its disk and Elastic IP, about $4.61 a month.

## Load test results (24 October 2026)

`deploy/loadtest.sh` ran one forced risk-agent run alone as a baseline, then 5 at once. Memory was sampled every 2 seconds throughout.

| Measure | Result | Move to t4g.small at | Verdict |
|---|---|---|---|
| Single run (baseline) | 14.5 s | n/a | n/a |
| 5 concurrent runs | 12.4 to 29.6 s, all HTTP 200; 2.0× the baseline | over ~5× the baseline, any run over 60 s, or any 5xx | fine |
| `api` memory peak | 128 MiB of 450 | stays above ~420 MiB | fine |
| `web` memory peak | 51 MiB of 256 | stays above ~240 MiB | fine |
| `caddy` memory peak | 26 MiB of 128 | n/a | fine |
| Lowest `available` (`free -m`) | 352 MB | under ~100 MB | fine |
| Highest swap used | 64 MB | over ~600 MB, or growing on each run | fine |
| OOM kills / restarts | none / 0 | any | fine |

**Conclusion:** t4g.micro is enough. Latency comes mostly from the model calls, not from the server. The test cost $0.054 in live calls, out of the $1 daily cap.

---

## Everyday tasks

All commands start from your PC. Connect first:

```powershell
ssh -i $env:USERPROFILE\.ssh\exportagent_ec2 ubuntu@3.104.80.176
```

### Update to a new version

Pushing to `main` builds new images, which takes a few minutes; watch the **images** workflow on GitHub. Then, on the server:

```bash
cd /opt/exportagent && git pull
cd deploy
docker compose pull
docker compose up -d
docker image prune -f
```

`git pull` updates the config files, `pull` fetches the new images, `up -d` restarts only what changed, and `prune` deletes old images so the disk doesn't fill.

To go back to an older version, set `IMAGE_TAG=<commit sha>` in `.env` and run `docker compose up -d` again.

If `docker compose pull` says **denied** or **unauthorized**, the GitHub token has expired or was deleted. Make a new one (see [GitHub token](#github-token)), then run this and paste it at the hidden prompt:

```bash
sudo bash /opt/exportagent/deploy/setup.sh --relogin
```

### Change the API keys

```bash
nano /opt/exportagent/deploy/.env
```

Use the arrow keys to move. To paste, **right-click** or press **Ctrl+Shift+V**; Ctrl+V does not work in nano. Leave no spaces or quotes around `=`. To save, press **Ctrl+O** then **Enter**; to quit, press **Ctrl+X**. Then run `cd /opt/exportagent/deploy && docker compose up -d`.

To check the file without showing the keys:

```bash
sed -E 's/=(.+)/=<set>/' /opt/exportagent/deploy/.env
```

### Run the load test again

Open a second SSH window and run `docker stats` in it. Then, in the first window:

```bash
free -m; bash /opt/exportagent/deploy/loadtest.sh; free -m
```

Compare the results with the table above. Each test costs a few cents of live calls, counted against the $1 cap. The test restores the demo data when it finishes.

**To switch to t4g.small**, run this from your PC. It needs `aws login` (see [Using the AWS CLI](#using-the-aws-cli)). The site is down for about 2 minutes, and the IP, disk and data stay the same:

```bash
aws ec2 stop-instances --instance-ids i-0bb6ebc9cbec44c5c
aws ec2 wait instance-stopped --instance-ids i-0bb6ebc9cbec44c5c
aws ec2 modify-instance-attribute --instance-id i-0bb6ebc9cbec44c5c --instance-type t4g.small
aws ec2 start-instances --instance-ids i-0bb6ebc9cbec44c5c
```

Then raise the budget alerts to about $22 actual and $25 forecast.

## If the site is down

Work through these in order and stop when it's fixed.

1. **Check `/health`.** Open <https://3-104-80-176.sslip.io/health>. If it shows JSON with `"status":"ok"`, the server is fine and the problem is in the page or your connection.
2. **Is the server running?** In the [EC2 console](https://ap-southeast-2.console.aws.amazon.com/ec2/home?region=ap-southeast-2#Instances:), with the Region set to **Sydney**, `exportagent` should be **Running** with **2/2 checks passed**. If it is stopped, choose **Instance state → Start**. The IP stays the same.
3. **Can you connect?** If `ssh` times out, your home IP has probably changed. Go to **Security Groups → exportagent-web → Edit inbound rules**, set the SSH rule's source to **My IP**, and click **Save rules**.
4. **Are the containers up?**
   ```bash
   cd /opt/exportagent/deploy
   docker compose ps
   docker compose logs --tail 100 api
   docker compose logs --tail 50 caddy
   ```
   Restart with `docker compose up -d`, or everything with `docker compose restart`.
5. **Is the disk or memory full?** `df -h /` should show under 90% used, and `free -h` should show some memory available. If the disk is full, run `docker image prune -af` and `sudo journalctl --vacuum-size=50M`.
6. **Still broken?** Reboot the instance with **Instance state → Reboot**. The containers start by themselves.
7. **"Access Denied", or everything stopped at once?** The project may have hit a spend limit, or run out of credits or free-plan time. Check **AWS Settings → Billing**. Only the project owner can change a spend limit.

**`/health` says `"mode":"cached"`.** This is normal once today's $1.00 of model calls is used up. The demo still works from stored results, and live calls resume at 00:00 UTC.

**Demo data got messy.** The **Reset demo** button restores it. To restore last night's backup instead:

```bash
cd /opt/exportagent/deploy
docker compose exec api ls /data/backups
docker compose stop api
docker compose run --rm --no-deps api cp /data/backups/exportagent-YYYY-MM-DD.db /data/exportagent.db
docker compose start api
```

## Monitoring

- **AWS Budget `exportagent-monthly`:** an email at $15 actual spend in a month, and one when the forecast passes $17. Expected spend is about $12.35. Credits are excluded, so it tracks what the usage really costs.
- **UptimeRobot:** a free monitor of `/health` every 5 minutes, which emails you when it fails. It is set up by hand:
  1. Sign up or log in at <https://uptimerobot.com> and click **+ New monitor**.
  2. **Monitor type:** **Keyword**.
  3. **URL:** `https://3-104-80-176.sslip.io/health`
  4. **Keyword:** `"status":"ok"`, and choose to alert when the keyword **does not exist**.
  5. **Interval:** 5 minutes. Under **How will we notify you?**, tick your email.
  6. Click **Create monitor**. It should turn green within a few minutes.

## Using the AWS CLI

The CLI uses short-term credentials from `aws login`; no access keys are stored. Sign in through the **Sydney** endpoint. The Mumbai endpoint fails with "Something went wrong" for this project.

```bash
aws login --profile exportagent --region ap-southeast-2
export AWS_PROFILE=exportagent AWS_REGION=ap-southeast-2   # PowerShell: $env:AWS_PROFILE="exportagent"; $env:AWS_REGION="ap-southeast-2"
aws sts get-caller-identity                                 # Account should be 121728644468
```

The credentials refresh themselves for up to 12 hours; after that, run `aws login` again.

To list everything this deployment created:

```bash
aws resourcegroupstaggingapi get-resources --tag-filters Key=Project,Values=ExportAgent --query 'ResourceTagMappingList[].ResourceARN'
```

## GitHub token

The server pulls the private images with a **classic** token that has only the `read:packages` scope. GHCR does not accept fine-grained tokens. To make a new one:

1. Open <https://github.com/settings/tokens/new>.
2. Note: `exportagent-ec2 pull`. Expiration: **Custom**, 31 Dec 2026.
3. Tick only **read:packages**, then click **Generate token** and copy the `ghp_…` token.
4. On the server, run `sudo bash /opt/exportagent/deploy/setup.sh --relogin` and paste the token at the hidden prompt. It is stored only in `/home/ubuntu/.docker/config.json`, which only the `ubuntu` user can read.

**Package settings.** On each package (`exportagent-api`, `exportagent-web`). To confirm the Actions access works, run the **images** workflow by hand (**Actions → images → Run workflow**); a green run means it can still push.
- **Inherit access from source repository** is turned off. A package linked to a public repository is otherwise public too.
- **Manage Actions access** gives `NaveenVikramR/exportAgent` the **Write** role, so the build workflow can still push.
- **Visibility** is **Private**.

To check that anonymous downloads are refused (expect HTTP 401):

```bash
t=$(curl -s "https://ghcr.io/token?scope=repository:naveenvikramr/exportagent-api:pull" | cut -d'"' -f4)
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $t" https://ghcr.io/v2/naveenvikramr/exportagent-api/manifests/latest
```

---

## Teardown after 15 December

Do this so credits stop draining. Stopping the instance is **not** enough: a stopped instance still pays for its disk ($0.96 a month) and its Elastic IP ($3.65 a month).

**Optional: keep a copy of the data first.** On the server:

```bash
cd /opt/exportagent/deploy && bash backup.sh && docker compose cp api:/data/backups ./backups-final
```

Then on your PC:

```powershell
scp -i $env:USERPROFILE\.ssh\exportagent_ec2 -r ubuntu@3.104.80.176:/opt/exportagent/deploy/backups-final .
```

### With the AWS CLI

After `aws login` (see [Using the AWS CLI](#using-the-aws-cli)), with `AWS_PROFILE=exportagent` and `AWS_REGION=ap-southeast-2` set:

```bash
# 1. Terminate the instance (also deletes its root volume and network interface)
aws ec2 terminate-instances --instance-ids i-0bb6ebc9cbec44c5c
aws ec2 wait instance-terminated --instance-ids i-0bb6ebc9cbec44c5c

# 2. Release the Elastic IP (billed every hour until released, even with no instance)
aws ec2 release-address --allocation-id eipalloc-0bb989304b463a2e4

# 3. Delete the volume if it is somehow still there (usually prints an error that it does not exist: fine)
aws ec2 delete-volume --volume-id vol-0421f1d6e24e5ef68

# 4. Delete any snapshots (this setup makes none; the list should be empty)
aws ec2 describe-snapshots --owner-ids self --query 'Snapshots[].SnapshotId'

# 5. Free to keep, but tidy: security group and key pair
aws ec2 delete-security-group --group-id sg-02e88eda2ccd60068
aws ec2 delete-key-pair --key-pair-id key-0fd6247b1fa7c7432

# 6. Optional: the budget alerts (free to keep)
aws budgets delete-budget --region us-east-1 --account-id 121728644468 --budget-name exportagent-monthly
```

If step 4 lists any snapshot IDs, delete each one with `aws ec2 delete-snapshot --snapshot-id <id>`.

**Check that nothing is left.** Each command should print `[]`:

```bash
aws ec2 describe-instances --filters Name=instance-state-name,Values=pending,running,stopping,stopped --query 'Reservations[].Instances[].InstanceId'
aws ec2 describe-addresses --query 'Addresses[].PublicIp'
aws ec2 describe-volumes --query 'Volumes[].VolumeId'
aws ec2 describe-snapshots --owner-ids self --query 'Snapshots[].SnapshotId'
aws resourcegroupstaggingapi get-resources --tag-filters Key=Project,Values=ExportAgent --query 'ResourceTagMappingList[].ResourceARN'
```

### Or in the console (Region: Sydney)

1. **Instances:** select `exportagent`, then **Instance state → Terminate (delete) instance**. Wait for **Terminated**.
2. **Elastic IPs:** select 3.104.80.176. If it still shows an instance, use **Actions → Disassociate** first. Then **Actions → Release Elastic IP addresses → Release**.
3. **Volumes:** delete any volume still listed as **available**.
4. **Snapshots** (filter **Owned by me**): delete any that are listed.
5. **AMIs** (filter **Owned by me**): deregister any image of the server, then delete its snapshot.
6. Optionally delete security group `exportagent-web` and key pair `exportagent-ec2`.
7. Optionally, under **Billing and Cost Management → Budgets**, delete `exportagent-monthly`.

### Outside AWS (optional)

- Delete the classic token at <https://github.com/settings/tokens>. It expires on 31 Dec 2026 anyway.
- Delete the two packages at <https://github.com/NaveenVikramR?tab=packages>, via **Package settings → Delete this package**.
- Delete the UptimeRobot monitor, or it will email you that the site is down.

**A day later**, check **AWS Settings → Billing**. The credits should stop going down.

---

## Rebuilding from scratch

To redo the deployment on a new server:

1. **AWS resources:** create them as in the table at the top. That means importing the key pair, creating the security group in the default VPC, launching the instance, and allocating and associating the Elastic IP. Tag everything `Project=ExportAgent`.
2. **Server setup:** connect with `ssh`, then:
   ```bash
   sudo git clone https://github.com/NaveenVikramR/exportAgent.git /opt/exportagent
   sudo chown -R ubuntu:ubuntu /opt/exportagent
   sudo bash /opt/exportagent/deploy/setup.sh
   ```
   `setup.sh` creates the 2 GB swap file, installs Docker, sets log limits, creates `deploy/.env` (mode 600) and schedules the nightly backup. It also asks for the GitHub token at a hidden prompt, or skips that if there is no terminal; add it later with `--relogin`.
3. **`.env`:** fill in `SITE_ADDRESS` (the Elastic IP with dashes, plus `.sslip.io`), `NEBIUS_API_KEY` and `TAVILY_API_KEY`.
4. **Start:**
   ```bash
   cd /opt/exportagent/deploy && docker compose pull && docker compose up -d
   ```
   Caddy fetches the HTTPS certificate within a minute.
