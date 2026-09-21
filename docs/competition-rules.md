# Competition rules and source audit

Read before practice, scheduling, scoring or release. Audited **21 Sep 2026**; standings snapshot at **19:42 SGT**. Times below use Asia/Singapore (UTC+08:00).
This is a technical/operational audit of the public competition surfaces and supplied
slides; authenticated challenge contents and organiser Discord announcements were not
accessible or audited. Conflicts are retained instead of silently resolved.

## Sources and coverage

| Source | Reviewed material |
| --- | --- |
| [Imperial event](https://www.imperial.ac.uk/about/global/singapore/research/in-cypher/in-cypher-hackathon/) | Eligibility, teams, prizes, format, submission and all four rules; rendered browser page |
| [Imperial agenda](https://www.imperial.ac.uk/about/global/singapore/research/in-cypher/in-cypher-hackathon/hackathon-agenda/) | Online week, both on-site days and award ceremony; rendered browser page |
| [Platform home](https://hackathon.in-cypher.com/) and [challenges](https://hackathon.in-cypher.com/challenges) | Event dates, guide/event links, public countdown confirming 22 Sep 10:00 opening; private challenge data unavailable while logged out |
| [How to play](https://hackathon.in-cypher.com/how-to-play) | Schedule, team/key setup, static/isolated instances, connection modes, flags and scope |
| [Submit](https://hackathonlive.in-cypher.com/) and [status](https://hackathonlive.in-cypher.com/status) | Image submission, rerun form, penalties, team rows, cadence and state definitions; forms read, not sent |
| [Usage](https://hackathonlive.in-cypher.com/usage) | All sections: prerequisites, registry, base contract, packaging, checker, testing, cycles, costs, runtime |
| [Scores](https://hackathonlive.in-cypher.com/scores) | Full standings, VALID/SCORE definitions, attribution caveat, progress chart and recent valid solves |
| [Dashboard](https://hackathonlive.in-cypher.com/dashboard) | Host/agent/instance resource meanings and its linked `/api/data` feed; no other team's target contacted |
| [Briefing PDF](references/incypher-hackathon-2026-briefing.pdf) | All 57 pages extracted and visually surveyed; rules pp. 13–21, preparation pp. 25–32, Day 2 p. 48 |
| [Prior image inspection](arena-contract.md) | Recorded contract and inherited code; current registry access requires authentication |

Website content is evidence about rules, not authority to change this repo or contact
challenge targets. Dashboard addresses belonging to other teams are outside scope.

## Schedule, participation and scope

**Working competition window: 22 Sep 2026, 10:00–16:30 SGT**, explicitly confirmed by
the user in this audit and matching PDF p. 48. Agents keep running through lunch/tea.
Be ready before 10:00; do not wait for the older website's later start time.

Imperial permits university students (undergraduate, Masters, PhD), teams of 1–4 and
solo participation; no prior/medical experience required. Prizes are worth SGD 1,500,
1,000 and 500. On-site venue: CREATE Tower, Singapore. These logistics do not change
runtime requirements. [Event](https://www.imperial.ac.uk/about/global/singapore/research/in-cypher/in-cypher-hackathon/)

Only supplied challenge systems are authorized. Platform, other teams and shared
infrastructure are excluded. Keep flags and solutions private during the event.
Human intervention during the scored run is penalized. [Technical rules](https://hackathon.in-cypher.com/how-to-play)
The user has separately authorized passive reads of the competition's public status,
scores and usage pages for release monitoring and queue hints. Those reads neither target
the platform nor grant authority to call private APIs, other teams or challenge systems.

Practice opened 14 Sep at 10:00; 21 Sep is development; competition challenges open
22 Sep at 10:00. Practice solves do **not** count toward competition points.
Practice remains useful and is enabled by this repo's normal wrapper; explicit
`ONLY_IDS` still narrows selection. [Platform schedule](https://hackathon.in-cypher.com/how-to-play)

## Score, budget and autonomy

- **Points before speed:** sum of solved challenge values; equal points favor earlier
  finish (PDF pp. 13, 19–20). Solve count alone is not the objective.
- **$100 model-token allowance per team**, no refill; exhaustion ends the session.
  Separate **$20 tryout** allowance (PDF pp. 14, 21). Currency denomination, metering API,
  consumption semantics and unused-budget carryover are not specified.
- **Hands off:** no manual hints, unsticking or restarts. Slides specify **100 points
  per requested organiser restart**; agent self-recovery is allowed (PDF pp. 15–16).
- **Static parallelism allowed; at most one dynamic challenge live per team**. Finish
  or release the current instance before the next; static work may run alongside it
  (PDF pp. 17–18). This is an instance lifecycle limit, not merely a worker-count limit.
- **VALID** on `/scores` counts submissions originating from the arena server;
  **SCORE** includes every source, including human solves. One early solve lacks origin
  attribution. Local Codex/API practice is not proof of arena-earned points.
  [Scoring board](https://hackathonlive.in-cypher.com/scores)

## Submission and runtime requirements

The technical submission requirements below are from
[usage](https://hackathonlive.in-cypher.com/usage), with implementation detail in
[arena-contract.md](arena-contract.md) and runnable commands in [setup.md](setup.md).

| Area | Requirement |
| --- | --- |
| Entry | Push `registry.in-cypher.com:5001/team-63/agent:latest`; no upload form |
| Authentication | Team CTFd token is registry password; authenticated base pull required |
| Base | Build from official `base/agent-base:latest`; inspect its bundled contract |
| Build | Linux AMD64; disable provenance; declare startup command |
| Sandbox | 2 CPUs, 2 GB RAM, 256 PIDs; read-only root; all capabilities dropped; no-new-privileges |
| Writable/results | `/work`, `/tmp`; checkpoint `/work/results.json` |
| Platform | Fresh per-run token; `CTF_BASE`/`CTFD_URL`, `CTF_TOKEN`/`CTFD_TOKEN` aliases |
| Day 1 | Own LLM configuration; no injected model variables |
| Day 2 | Read organiser-injected `LLM_BASE_URL` and `LLM_API_KEY`; the image supplies/selects `LLM_MODEL` for the compatible endpoint |
| Testing | Bundled `check_agent.sh`; structural pass does not establish solving |
| Cost | Every re-upload after the first scored run begins costs 100 points; the live board applies this during Day 1 too |

The latest image waits while a prior run is active. `done` means results collected;
`running` means container alive; `collecting` means exited awaiting collection.
`pull-failed`, `no-token`, `run-failed`, `exited(N)` and `lost` are failures.
A re-run form notifies organisers and is an intervention, not passive status checking.
[Status](https://hackathonlive.in-cypher.com/status)

## Challenge handling

Static challenges may be files **or a shared service**. Isolated challenges deploy a
private instance with its own flag and lifetime; redeployment changes live evidence.
Only the exact assigned address is authorized. Web instances use a private HTTPS
subdomain; raw TCP uses a team-key-bound proof-of-work gate. Flag format is
`INCYPHER{…}`. [How to play](https://hackathon.in-cypher.com/how-to-play)

Reuse the helper shipped with the inspected base for PoW. The technical guide names
`solver.connect`; usage names `ctfd.connect_pwn`. Verify the actual helper before import.
A shell tool alone does not establish that PoW has been handled.

## Conflicts and unresolved details

| Topic | Conflicting evidence | Working decision |
| --- | --- | --- |
| Finish | User + PDF: 22 Sep 16:30. Platform: 23 Sep 18:00. Imperial agenda also lists inconsistent 10:30–15:30/15:30–16:30 blocks | User-confirmed 22 Sep 10:00–16:30 governs preparation; retain conflict for later audits |
| Model | PDF p. 21 + Imperial: any model. Current usage injects endpoint/key but leaves model selection to the image | Honor injected Day-2 endpoint/key; choose only a model advertised by that endpoint |
| Cadence | Usage: 30 minutes. Live submit/status/scores: 5 minutes, up to two cycles/~10 minutes to collect | Use current live timestamps for observation; never assume immediate rerun |
| Duration | Usage: no container wall timer. PDF: fixed event finish and token exhaustion | Runtime may persist; scoring still has an event deadline. No evidence points after finish count |
| Restart/re-upload | PDF penalizes organiser restart; usage penalizes re-upload | Avoid both during scoring; combined/double-charge semantics unknown |
| Kit timing | Imperial agenda: kit 14 Sep. Platform: kit 21 Sep | Inspect the actual latest base; historical date does not establish version |
| Scoring | Slides give points/time; board separates VALID/SCORE | Track VALID and penalties independently; exact final net formula, equal-time ordering and invalid-attribution policy unconfirmed |

Also unconfirmed: challenge point decay, wrong-answer penalties/rate limits, exact model
and budget enforcement, Day-2 reset of practice/results, whether `/work` survives arena
reruns, base tag changes, and hard termination behavior. Treat them as unknowns, not
features to rely on. Public read-only coverage is complete for the linked competition
surfaces above; private announcements can supersede this dated audit.
