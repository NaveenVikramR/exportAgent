# Deploying ExportAgent on AWS EC2

This guide puts the public demo on one small server in **Asia Pacific (Mumbai), ap-south-1**. It is written for someone using the AWS console for the first time. Follow the steps in order and copy commands exactly.

**What you end up with:** `https://<your-ip-with-dashes>.sslip.io` serving the app, with HTTPS from Caddy. The API and web app run as Docker containers that are built by GitHub Actions; the server only downloads them.

| Piece | Choice |
|---|---|
| Server | EC2 t4g.micro (2 vCPU, 1 GB RAM, ARM), Ubuntu 24.04, 2 GB swap |
| Disk | 10 GB gp3 |
| Address | 1 Elastic IP + free `sslip.io` name |
| Database | SQLite file in a Docker volume, backed up nightly, 7 days kept |
| Images | GitHub Container Registry (free for public repos) |
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

## 1. Make the Docker images public (one time)

GitHub Actions builds the images when code is pushed to `main`. New GitHub packages start out private, so the server could not download them.

1. Open <https://github.com/NaveenVikramR/exportAgent/actions> and wait for the **images** workflow to show a green tick.
2. Open <https://github.com/NaveenVikramR?tab=packages>. You will see `exportagent-api` and `exportagent-web`.
3. For each one: click it, then **Package settings** (bottom right) → **Danger Zone → Change visibility → Public**, and type the name to confirm.

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

`setup.sh` creates the 2 GB swap file, installs Docker, limits log sizes, creates `deploy/.env` and schedules the nightly backup. Log out with `exit`, then reconnect with the same `ssh` command so the Docker permission takes effect.

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

1. **AWS Budgets.** Open the **Billing and Cost Management** console, then **Budgets → Create budget → Use a template → Monthly cost budget**. Enter the amount and your email, then **Create budget**. Expected usage is about $8.65 a month, so a **$5** budget will email you around day 17 of each month. Pick **$10** if you only want to hear about unexpected spend.
2. **UptimeRobot.** It's free at <https://uptimerobot.com>. Click **New monitor**, choose type **HTTP(s) – Keyword**, set the URL to `https://13-201-45-67.sslip.io/health`, keyword `"status":"ok"`, alert when the keyword **doesn't exist**, interval 5 minutes. Add your email as the alert contact.

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

## Deleting everything after 15 December

Do this so credits stop draining. All of it is in the EC2 console, in **Mumbai**.

1. **Instances:** select `exportagent`, then **Instance state → Terminate (delete) instance**. Wait until the state is **Terminated**. This also deletes its 10 GB disk.
2. **Elastic IPs:** select the address, then **Actions → Release Elastic IP addresses → Release**. An Elastic IP that isn't released keeps costing $3.65 a month even with no server.
3. **Volumes** (under Elastic Block Store): the list should be empty. Delete any `exportagent` volume left over.
4. **Snapshots:** this should be empty too, since this setup creates none.
5. Optional and free: delete the `exportagent-web` security group and the `exportagent-ec2` key pair.
6. A day later, check **AWS Settings → Billing**. EC2 charges should stop on the day you deleted things.

The GitHub images cost nothing and can stay.
