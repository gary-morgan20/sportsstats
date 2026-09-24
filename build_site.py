"""Run the daily analysis and write the website into docs/. GitHub Actions runs this every morning."""
from sportsstats.config import load_config
from sportsstats.pipeline import analyse
from sportsstats.site import write_site

if __name__ == "__main__":
    cfg = load_config()
    result = analyse(cfg, days=cfg["site"]["days_ahead"])
    write_site(result, cfg)
    print(f"Site written: {result['matches']} matches, {len(result['table'])} markets priced.")
