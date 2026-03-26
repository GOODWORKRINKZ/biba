---
name: biba-deployment
description: Use when deploying or updating BiBa on the robot, especially when pulling the latest GHCR image and restarting the compose stack through the robot-side bbupdate workflow.
---

# BiBa Deployment

## Overview

BiBa must be updated from GitHub and GHCR through the robot-side update workflow.
Do not hand-edit the cloned repo on the robot and do not replace `bbupdate` with ad-hoc compose commands unless the user explicitly asks for low-level recovery.

## When to Use

- Deploying a freshly pushed BiBa change to the robot
- Updating the robot to the latest GHCR image
- Restarting the stack after a normal GitHub-based release
- Verifying that the robot is running the intended revision and driver mode

## Core Rule

Use the robot's own `bbupdate` workflow.

Before running `bbupdate` for a freshly pushed change, verify the relevant GitHub Actions build is green.
Prefer `gh` over web polling when the GitHub CLI is available.

Expected behavior of `bbupdate`:

1. `git pull --ff-only`
2. `docker compose pull`
3. `docker compose up -d`

This preserves the intended deployment path: GitHub repo + GHCR image + robot-side update command.

## CI Gate

If the deploy depends on a newly built GHCR image, wait for the GitHub Actions run to finish successfully before updating the robot.

Preferred commands with GitHub CLI:

```bash
gh run view <run-id> --repo GOODWORKRINKZ/biba
gh run watch <run-id> --repo GOODWORKRINKZ/biba --exit-status
```

Prefer `gh run watch` as the default waiting mechanism when the terminal supports it.
Use polling or API-based fallbacks only when `gh run watch` output is unusable in the current session.

Useful fallback discovery commands:

```bash
gh run list --repo GOODWORKRINKZ/biba --limit 10
gh run view <run-id> --repo GOODWORKRINKZ/biba --json status,conclusion,jobs
```

Confirm before deploy:

- the workflow run finished
- the image build job succeeded
- the pushed revision matches the run you are about to deploy

Do not start `bbupdate` while the image build is still running unless the user explicitly asks to deploy a possibly stale image.

## SSH Invocation

On BiBa, aliases from `~/biba/scripts/biba_aliases.sh` require an interactive shell.
For remote execution over SSH, use:

```bash
sshpass -p 'open' ssh -tt -o StrictHostKeyChecking=no biba@<robot-ip> \
  'bash -ic "source ~/biba/scripts/biba_aliases.sh; bbupdate"'
```

Why:

- `bash -lc` may not expose the alias correctly in non-interactive execution
- `bash -ic` loads an interactive shell, so `bbupdate` and related aliases work as defined on the robot
- `-tt` ensures a tty is allocated, which avoids interactive-shell edge cases on the robot

## Post-Deploy Verification

After `bbupdate`, verify all of the following:

```bash
sshpass -p 'open' ssh -tt -o StrictHostKeyChecking=no biba@<robot-ip> \
  'bash -ic "source ~/biba/scripts/biba_aliases.sh; bbhealth"'

sshpass -p 'open' ssh -o StrictHostKeyChecking=no biba@<robot-ip> \
  'git -C ~/biba rev-parse HEAD && git -C ~/biba log -1 --oneline'

sshpass -p 'open' ssh -o StrictHostKeyChecking=no biba@<robot-ip> \
  'docker inspect biba-biba-controller-1 --format "{{range .Config.Env}}{{println .}}{{end}}" | sort | egrep "MOTOR_DRIVER_TYPE|LEFT_MOTOR|RIGHT_MOTOR"'
```

Confirm:

- the container is running and healthy
- the robot repo HEAD matches the intended pushed revision
- the effective env inside the container matches the target motor-driver mode

## Do Not Do This

- Do not edit files directly in `~/biba` on the robot during normal deployment
- Do not run ad-hoc `docker compose up -d` as a substitute for `bbupdate` during routine updates
- Do not assume aliases work through `bash -lc`; use the interactive-shell invocation above