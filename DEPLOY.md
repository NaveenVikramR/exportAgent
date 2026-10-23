# Deploying ExportAgent on AWS EC2

This guide puts the public demo on one small server in **Asia Pacific (Mumbai), ap-south-1**. It is written for someone using the AWS console for the first time. Follow the steps in order and copy commands exactly.

**What you end up with:** `https://<your-ip-with-dashes>.sslip.io` serving the app, with HTTPS from Caddy. The API and web app run as Docker containers that are built by GitHub Actions; the server only downloads them.

| Piece | Choice |
|---|---|
| Server | EC2 t4g.micro (2 vCPU, 1 GB RAM, ARM), Ubuntu 24.04, 2 GB swap |
| Disk | 10 GB gp3 |
| Address | 1 Elastic IP + free `sslip.io` name |
| Database | SQLite file in a Docker volume, backed up nightly, 7 days kept |
| Images | GitHub Container Registry, private, pulled with a read-only token (free) |
| Not used | Load balancer, RDS, NAT gateway, anything else that costs extra |

## Cost

Prices for Mumbai, taken from AWS's published price list in October 2026. The server runs 730 hours a month.

| Item | Price | Per month |
|---|---|---|
| t4g.micro, on demand | $0.0056 per hour | $4.09 |
| 10 GB gp3 disk | $0.0912 per GB-month | $0.91 |
| Public IPv4 (the Elastic IP) | $0.005 per hour | $3.65 |
| Data out | first 100 GB a month free | $0.00 |
| **Total** | | **about $8.65** |

Running until 15 December costs about $15 of credits. The t3.micro fallback ($0.0112 an hour) would bring the total to about $12.70 a month.

You pay these from your credits until you delete everything (see the last section). A stopped instance still pays for the disk and the Elastic IP, about $4.56 a month.

---

## 0. Before you start

1. **Check your Region.** In [AWS Settings](https://settings.aws.com/), open **View all projects → your project → Overview → Additional Info → Region**. It must say **Asia Pacific (Mumbai)**. Your project can only create resources in its own Region. If it shows another Region, stop and tell Claude.
2. **Check your plan and credits.** In **AWS Settings → Billing**, note your remaining credits and, on the free plan, the plan end date. The demo has to stay up until 15 December.
3. **Set the console to Mumbai.** In the [EC2 console](https://console.aws.amazon.com/ec2/), the Region menu at the top right must say **Asia Pacific (Mumbai)**. Check it every time you open the console.

## 1. Keep the images private and make a read-only token (one time)

GitHub Actions builds the images when code is pushed to `main`. Because the repository is public, GitHub made the images public too. Make them private, so only the server (with a token) can download them. Private images are free; GitHub currently charges nothing for container storage or downloads.

**Make both images private.**

1. Open <https://github.com/NaveenVikramR/exportAgent/actions> and wait for the latest **images** run to show a green tick.
2. Open <https://github.com/NaveenVikramR?tab=packages>. You will see `exportagent-api` and `exportagent-web`.
3. For each one: click it, then **Package settings** (right side) → **Danger Zone → Change visibility → Private**, and type the name to confirm.

**Create a classic token that can only read packages.** The server uses it to download the images.

1. Open <https://github.com/settings/tokens> and click **Generate new token → Generate new token (classic)**.
2. **Note:** `exportagent-ec2 pull`
3. **Expiration:** choose **Custom** and pick **31 Dec 2026**, after the demo ends.
4. **Select scopes:** tick only **read:packages**. Leave everything else unticked, including `repo` and `write:packages`.
5. Click **Generate token**. Copy the token (it starts with `ghp_`) and keep the page open. GitHub shows it only once, and you'll paste it on the server in step 5.

Don't save the token in a file, a note or chat. If you lose it, delete it on the same page and make a new one.

## 2. Import your SSH key

An ed25519 key pair was created on your PC:

- Public key, which is safe to upload: `C:\Users\Admin\.ssh\exportagent_ec2.pub`
- Private key, which you never share or upload: `C:\Users\Admin\.ssh\exportagent_ec2`

1. EC2 console → left menu **Network & Security → Key Pairs**.
2. **Actions → Import key pair**.
3. Name: `exportagent-ec2`.
4. Click **Browse** and pick `C:\Users\Admin\.ssh\exportagent_ec2.pub`. Windows hides the `.ssh` folder from some views, so type the path into the file dialog if you can't see it.
5. Click **Import key pair**.

## 3. Launch the server

EC2 console → **Instances → Launch instances**.

1. **Name:** `exportagent`
2. **Application and OS Images:** **Ubuntu**, then **Ubuntu Server 24.04 LTS (HVM), SSD Volume Type**. Set **Architecture** to **64-bit (Arm)**.
3. **Instance type:** `t4g.micro`. If it is not offered, go back and pick **64-bit (x86)** and `t3.micro`. The images work on both.
4. **Key pair:** `exportagent-ec2`
5. **Network settings → Edit:**
   - Auto-assign public IP: **Enable**. The Elastic IP replaces this address in step 4.
   - Firewall: **Create security group**, named `exportagent-web`.
   - Rule 1: Type **SSH**, Source type **My IP**.
   - **Add security group rule:** Type **HTTP**, Source type **Anywhere**.
   - **Add security group rule:** Type **HTTPS**, Source type **Anywhere**.
6. **Configure storage:** `10` GiB, **gp3**.
7. **Advanced details** (expand it):
   - **Credit specification:** **Standard**. The default, Unlimited, can bill extra if the CPU stays busy. Standard slows the server down instead.
   - **Metadata version:** **V2 only (token required)**.
8. Click **Launch instance**.

## 4. Attach an Elastic IP

1. EC2 console → **Network & Security → Elastic IPs → Allocate Elastic IP address → Allocate**.
2. Select the new address, then **Actions → Associate Elastic IP address**.
3. Resource type **Instance**, choose `exportagent`, then click **Associate**.
4. Write down the address, for example `13.201.45.67`. Your site will be `13-201-45-67.sslip.io`, the same numbers with dashes.

## 5. Connect and install

On your PC, open **Windows Terminal** or **PowerShell**. Replace `13.201.45.67` with your Elastic IP:

```powershell
ssh -i $env:USERPROFILE\.ssh\exportagent_ec2 ubuntu@13.201.45.67
```

The first time, type `yes` when it asks whether to trust the host. You are now on the server, and the prompt looks like `ubuntu@ip-...:~$`.

Copy the app's config and install everything:

```bash
sudo git clone https://github.com/NaveenVikramR/exportAgent.git /opt/exportagent
sudo chown -R ubuntu:ubuntu /opt/exportagent
sudo bash /opt/exportagent/deploy/setup.sh
exit
```

`setup.sh` creates the 2 GB swap file, installs Docker, limits log sizes, creates `deploy/.env` and schedules the nightly backup.

Partway through, it asks two questions:

- **GitHub username:** press **Enter** to accept `NaveenVikramR`.
- **GitHub token:** paste the `ghp_` token from step 1 with **right-click** and press **Enter**. Nothing appears as you paste; that is deliberate.

It should print **Login Succeeded**. Docker may warn that the credential is stored *unencrypted* in `/home/ubuntu/.docker/config.json`. That file is the only place the token is kept, and only the `ubuntu` user can read it. If the login fails, run `sudo bash /opt/exportagent/deploy/setup.sh --relogin` to try again.

Log out with `exit`, then reconnect with the same `ssh` command so the Docker permission takes effect.

## 6. Type your keys into `.env`

Your keys never leave your PC except into this file on the server. Don't paste them into chat, email or GitHub.

```bash
nano /opt/exportagent/deploy/.env
```

The nano editor opens. Use the arrow keys to move, and fill in the three lines:

```
SITE_ADDRESS=13-201-45-67.sslip.io
NEBIUS_API_KEY=paste-your-nebius-key-here
TAVILY_API_KEY=paste-your-tavily-key-here
```

- To paste in Windows Terminal, **right-click** or press **Ctrl+Shift+V**. Ctrl+V does not work in nano.
- Leave no spaces or quotes around the `=`.
- To save: **Ctrl+O**, then **Enter**. To leave: **Ctrl+X**.

Check the file without showing the keys. Each line should show the variable name and `set`:

```bash
sed -E 's/=(.+)/=set/' /opt/exportagent/deploy/.env
```

## 7. Start the app

```bash
cd /opt/exportagent/deploy
docker compose pull
docker compose up -d
docker compose ps
```

All three services (`api`, `web`, `caddy`) should say **Up**. Caddy needs up to a minute for the HTTPS certificate. Then open:

- `https://13-201-45-67.sslip.io` for the app, which should show the dashboard with the demo emails.
- `https://13-201-45-67.sslip.io/health` for the health check. It should show `"status":"ok"`, `"demo_loaded":true`, `"mode":"live"` and today's spend against the $1.00 cap.

## 8. Alerts

1. **AWS Budgets: one budget, two alerts.** Expected usage is about $8.65 a month. These alerts only email you if something costs more than planned.
   1. Open the **Billing and Cost Management** console, then **Budgets → Create budget**.
   2. Choose **Customize (advanced)**, then **Cost budget**, then **Next**.
   3. Name `exportagent-monthly`, period **Monthly**, renewal **Recurring budget**, budgeting method **Fixed**, amount **12.00**.
   4. Under **Budget scope**, keep **All AWS services**. Open **Advanced options** and make sure **Credits** is *not* ticked. You want to see what the usage costs before credits pay for it. Click **Next**.
   5. **Add an alert threshold:** threshold **10**, type **Absolute value**, trigger **Actual**, and your email as the recipient.
   6. **Add an alert threshold** again: threshold **12**, type **Absolute value**, trigger **Forecasted**, same email.
   7. Click **Next**, skip the actions, then **Create budget**.

   The first alert emails you once actual spend this month passes **$10**. The second emails you as soon as AWS forecasts the month will end above **$12**.
2. **UptimeRobot.** It's free at <https://uptimerobot.com>. Click **New monitor**, choose type **HTTP(s) – Keyword**, set the URL to `https://13-201-45-67.sslip.io/health`, keyword `"status":"ok"`, alert when the keyword **doesn't exist**, interval 5 minutes. Add your email as the alert contact.

## 9. Load test: is 1 GB enough?

The memory limits add up to 834 MB (api 450, web 256, caddy 128), and the server has about 900 MB plus 2 GB of swap. A container can't take more than its limit, and swap catches short peaks. This test shows whether real use fits.

Open **two** SSH windows to the server.

**Window 1: watch.** Leave this running.

```bash
cd /opt/exportagent/deploy
docker stats
```

**Window 2: load.** This starts 5 risk-agent runs at the same time, the heaviest thing the app does.

```bash
free -m
bash /opt/exportagent/deploy/loadtest.sh
free -m
```

The test first runs one request alone as a baseline, then 5 at once. Then it restores the demo data and shows `/health`, and checks whether any container was killed. Most model responses come from the cache. Prompts that aren't cached yet are live calls, about $0.03–0.04 per test, counted against the $1 daily cap. Run it at most a few times a day.

**What to look at:**

| Where | What | Fine | Move to t4g.small |
|---|---|---|---|
| `docker stats`, MEM USAGE / LIMIT | `api` | under ~380 MiB of 450 | stays above ~420 MiB, or hits the limit |
| `docker stats`, MEM USAGE / LIMIT | `web` | under ~200 MiB of 256 | stays above ~240 MiB |
| `free -m`, Mem row | `available` | over ~150 MB | under ~100 MB after the test ends |
| `free -m`, Swap row | `used` | under ~300 MB | over ~600 MB, or still growing on each run |
| `loadtest.sh` | HTTP codes | all `200` | any `500` or `502`, or a timeout |
| `loadtest.sh` | time for the 5 runs | under ~3× the single baseline | over ~5× the baseline, or any run over 60 s |
| `loadtest.sh` | OOMKilled / restarts | `false` / `0` | `true`, or restarts above 0 |

On a PC the same test took 3.8 s for one run, and 0.2–12.3 s for 5 at once, all `200`. Expect the server to be somewhat slower; what matters is the ratio to its own baseline.

To see whether the server is short of memory right now, run `vmstat 1 10`. Non-zero numbers that keep appearing in the `si` and `so` columns mean it is swapping. Pages will feel slow, and it's time to move up.

**Move to t4g.small (2 GB) if** two or more rows land in the right-hand column, or any container was OOM-killed. It costs about twice as much for the instance, roughly $4 more a month. To switch:

1. **Instances:** select `exportagent`, then **Instance state → Stop**, and wait until it shows **Stopped**.
2. **Actions → Instance settings → Change instance type →** `t4g.small` **→ Apply**.
3. **Instance state → Start.** The Elastic IP, disk and data stay the same, and the containers start by themselves.
4. If you set up budgets, raise them to $15 actual and $18 forecast.

---

## Updating to a new version

Pushing to `main` builds new images, which takes a few minutes; watch the **images** workflow on GitHub. Then, on the server:

```bash
cd /opt/exportagent && git pull
cd deploy
docker compose pull
docker compose up -d
docker image prune -f
```

If `docker compose pull` says **denied** or **unauthorized**, the GitHub token has expired or was deleted. Make a new one (step 1) and run `sudo bash /opt/exportagent/deploy/setup.sh --relogin`.

`git pull` updates the config files, `pull` fetches the new images, `up -d` restarts only what changed, and `prune` deletes the old images so the disk doesn't fill.

To go back to an older version, set `IMAGE_TAG=<commit sha>` in `.env` and run `docker compose up -d` again.

## If the site is down

Work through these in order and stop when it's fixed.

1. **Is the server running?** EC2 console → **Instances**: the state should be **Running**, and the status checks should show **2/2 checks passed**. If it is stopped, select it and choose **Instance state → Start**. The Elastic IP stays the same.
2. **Can you connect?** Run the `ssh` command. If it times out, your home IP may have changed. In **Security Groups → exportagent-web → Edit inbound rules**, set the SSH source to **My IP** again and save.
3. **Are the containers up?**
   ```bash
   cd /opt/exportagent/deploy
   docker compose ps
   docker compose logs --tail 100 api
   docker compose logs --tail 50 caddy
   ```
   A service that is not **Up** can be restarted with `docker compose up -d`. To restart everything, use `docker compose restart`.
4. **Is the disk or memory full?** Run `df -h /` (Use% should be under 90%) and `free -h`. If the disk is full, run `docker image prune -af` and `sudo journalctl --vacuum-size=50M`.
5. **Still broken?** Reboot the instance: **Instance state → Reboot**. The containers start again by themselves.
6. **"Access Denied", or everything stopped at once?** Your project may have reached a spend limit, or used up its credits or free plan. Check **AWS Settings → Billing**. Only the project owner can change a spend limit.

**`/health` says `"mode":"cached"`.** This is normal once today's $1.00 of model calls is used up. The demo emails still work from stored results, and live calls resume at 00:00 UTC.

**Demo data got messy.** The **Reset demo** button restores it. To restore last night's backup instead:

```bash
cd /opt/exportagent/deploy
docker compose exec api ls /data/backups
docker compose stop api
docker compose run --rm --no-deps api cp /data/backups/exportagent-YYYY-MM-DD.db /data/exportagent.db
docker compose start api
```

## Teardown after 15 December

Do this so credits stop draining. Stopping the instance is **not** enough: a stopped instance still pays for its disk ($0.91 a month) and its Elastic IP ($3.65 a month). Do the steps in order, in the EC2 console with the Region set to **Mumbai**.

**Optional: keep a copy of the data first.** On the server:

```bash
cd /opt/exportagent/deploy && bash backup.sh
docker compose cp api:/data/backups ./backups-final
```

Then on your PC, in PowerShell:

```powershell
scp -i $env:USERPROFILE\.ssh\exportagent_ec2 -r ubuntu@13.201.45.67:/opt/exportagent/deploy/backups-final .
```

1. **Terminate the instance.** Go to **Instances**, select `exportagent`, then **Instance state → Terminate (delete) instance → Terminate**. Wait until the state shows **Terminated**; this takes a minute or two.
2. **Release the Elastic IP.** It is billed every hour until it is released, even with no server attached.
   1. Go to **Network & Security → Elastic IPs** and select the address.
   2. If **Associated instance ID** still shows an instance, use **Actions → Disassociate Elastic IP address** first.
   3. Then **Actions → Release Elastic IP addresses → Release**. The list should now be empty.
3. **Delete the volume.** Go to **Elastic Block Store → Volumes**. The 10 GB disk is normally deleted with the instance. If any volume is still listed with state **available**, select it, then **Actions → Delete volume → Delete**. The list should be empty.
4. **Delete any snapshots.** Go to **Elastic Block Store → Snapshots**, with the filter set to **Owned by me**. This setup makes none, but if any are listed, select them, then **Actions → Delete snapshot → Delete**.
5. **Check for leftover AMIs.** Go to **Images → AMIs**, filter **Owned by me**. If you ever made an image of the server, select it, then **Actions → Deregister AMI**, and delete its snapshot as in step 4.
6. **Optional, and free to keep:** delete the `exportagent-web` security group (**Network & Security → Security Groups**) and the `exportagent-ec2` key pair (**Key Pairs**).
7. **Optional, budget alerts:** in **Billing and Cost Management → Budgets**, select `exportagent-monthly`, then **Actions → Delete**. Budgets cost nothing, so you can keep it to catch anything you missed.
8. **Optional, GitHub:**
   - Delete the `exportagent-ec2 pull` token at <https://github.com/settings/tokens>. It expires on 31 Dec 2026 anyway.
   - Delete the two images at <https://github.com/NaveenVikramR?tab=packages>, via **Package settings → Delete this package**.
   - Delete UptimeRobot's monitor, or it will email you that the site is down.
9. **Check it worked.** A day later, in **Billing and Cost Management → Bills**, the EC2 lines for the current day should be $0. Also look at **AWS Settings → Billing**: your credits should stop going down.

You can also run a quick check with the AWS CLI, if it's set up for this project. All three commands should print `[]`:

```bash
aws ec2 describe-instances --region ap-south-1 --filters Name=instance-state-name,Values=pending,running,stopping,stopped --query 'Reservations[].Instances[].InstanceId'
aws ec2 describe-addresses --region ap-south-1 --query 'Addresses[].PublicIp'
aws ec2 describe-volumes --region ap-south-1 --query 'Volumes[].VolumeId'
```
