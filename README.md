# SportsStats: football value finder

Every morning GitHub runs the analysis on its own servers and updates your website. Nothing runs
on your PC and Cowork isn't involved. You just open the page.

What the page shows:
- **Value picks:** prices that beat the model's fair price by 5–30%.
- **Check manually:** gaps above 30%, which usually mean team news the model can't see.
- **All matches:** every market for every match (tap a match to open it). Filter by league at the top.
- **Previous days:** archive of the last 60 days.

## Setting up the website (once, about 15 minutes)

1. **GitHub account:** sign up free at https://github.com.
2. **New repository:** click **+ > New repository**, name it `sportsstats`, set it to **Public**, and create it.
   A public repository is what makes the free website possible. Your API keys are stored as secrets and never visible.
   Anyone who finds the URL could see the picks. To keep it private you'd need GitHub Pro ($4/month).
3. **Upload the code:** either give Claude access to push it, or on the repository page choose
   **Add file > Upload files** and drag in everything in this folder *except* `.env`, `data`, `output` and `_to_delete`.
   Then add the scheduler: **Add file > Create new file**, type the name `.github/workflows/daily.yml`,
   paste in the contents of `daily-workflow.yml`, and commit.
4. **API keys:** go to **Settings > Secrets and variables > Actions > New repository secret** and add
   `ODDS_API_KEY` and/or `API_FOOTBALL_KEY` (see "Data sources" below). This step is optional: without keys the site
   still runs, but only covers match result and over/under 2.5.
5. **Turn on the website:** go to **Settings > Pages**, choose Source: *Deploy from a branch*, Branch: `main`, Folder: `/docs`.
6. **First run:** go to **Actions > Daily shortlist > Run workflow**. After about 3 minutes your site is live at
   `https://<your-username>.github.io/sportsstats/`. From then on it updates by itself at 07:00 Paris time
   (06:00 in winter). The **Run workflow** button refreshes it at any time, for example after team news.

## Data sources and cost

| Source | What it gives | Cost |
|---|---|---|
| football-data.co.uk | 3+ seasons of results, half-time goals and corners (for the model), plus fixtures with bet365, Betfair Exchange, William Hill and other odds for 1X2 and O/U 2.5 | Free, no key |
| API-Football | Odds for most of your markets (BTTS, double chance, DNB, first half, corners), FA Cup | Free 100 requests/day, which is enough for one daily run |
| The Odds API | 21 UK bookmakers and exchanges, including Betfair Exchange, Sky Bet, William Hill, Paddy Power, Smarkets (not bet365) | Free 500 credits/month is **not** enough for a daily run. The $30/month plan is |

Suggested start: football-data plus the free API-Football key. Add The Odds API once the backtest shows the model works.

## Changing things

Everything adjustable is in `config.yaml`: leagues, markets, the edge and odds thresholds, bookmakers and days ahead.
Edit it on GitHub (click the file, then the pencil icon) and the next run uses the new settings.

## Running on your own PC (optional)

```
python -m pip install -r requirements.txt
python probe.py        # which markets/bookmakers each source returns -> output/coverage_report.md
python run.py          # print today's shortlist
python build_site.py   # build the website locally into docs/
```
Put keys in a `.env` file (copy `.env.example`) for local runs.

## How the model works

Each team gets an attack and a defence rating from the last 3 seasons, with recent matches weighted more
(half-life 180 days) plus a home advantage. That gives expected goals and a full score-line grid, from which
home/away win, double chance, draw no bet, over/under 1.5/2.5/3.5 and BTTS are read. First-half goals use the
same method on half-time scores. Corners use the same method on corners won, allowing for their extra variability.
Edge = model probability x best UK odds - 1. Exchange prices are reduced by commission first (Betfair 5%, set in `config.yaml`).
Non-UK prices such as Pinnacle only feed the market average and are never shown as a price to take.

## Known gaps

- **FA Cup:** no history source yet (needs ratings that compare teams across divisions).
- **Backtest:** proving the edges are real against past closing odds is the next job.
- No injury or team news. Check the shortlist on Flashscore / SofaScore.
- A team name that doesn't match between sources is listed at the bottom of the page. Add it to `team_aliases.yaml`.
