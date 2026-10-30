# Auto Daily Briefing (free, fully automatic)

Every morning at 07:00 IST this repo, with no server and no PC left on:

1. pulls the latest items from your RSS feeds (`config.yaml`)
2. asks Google Gemini (free tier) to write a short briefing
3. publishes it as a phone-friendly web page (GitHub Pages) plus a dated archive
4. sends it to your Telegram

Cost: Rs 0. If Gemini is unavailable it falls back to a plain headline list, so it never breaks.

## One-time setup (about 10 minutes)

1. **Create a GitHub repo** (public, so Pages is free) and upload everything in this folder, keeping the `.github` folder.
2. **Gemini key (free):** https://aistudio.google.com/apikey -> Create API key.
3. **Telegram bot (optional):** message @BotFather -> `/newbot` -> copy the token. Send any message to your bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `chat.id`.
4. In the repo: **Settings -> Secrets and variables -> Actions -> New repository secret**. Add:
   - `GEMINI_API_KEY`
   - `TELEGRAM_BOT_TOKEN` (optional)
   - `TELEGRAM_CHAT_ID` (optional)
5. **Settings -> Pages**: Source = *Deploy from a branch*, Branch = `main`, Folder = `/docs`.
6. **Actions tab -> daily-digest -> Run workflow** to test. After that it runs by itself daily.

Your page: `https://<your-username>.github.io/<repo-name>/`

## Customize

Edit only `config.yaml`: change feeds, interests, title, time window. To change the time, edit the `cron` line in `.github/workflows/digest.yml` (it is in UTC; IST = UTC + 5:30).

## Run locally (optional)

    pip install -r requirements.txt
    GEMINI_API_KEY=xxx python digest.py

## Ideas to extend

- Add feeds for any topic: prices, jobs, competitors, research papers.
- Add a second workflow for weekly summaries or price-change alerts.
- Swap Telegram for Discord or email by editing the `telegram()` function.
