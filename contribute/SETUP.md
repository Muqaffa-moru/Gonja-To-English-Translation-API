# Gonja contribution page: setup (about 15 minutes)

What you get: a page on your Vercel site where anyone can translate English sentences into Gonja.
Answers go into a Google Sheet. Later you export that sheet and import it with `tools/import_csv.py`.

## Part A: the Google Sheet (where answers are stored)
1. Go to sheets.google.com and create a new blank sheet. Name it "Gonja submissions".
2. Menu: **Extensions → Apps Script**. A code editor opens.
3. Delete the default code, paste everything from `Code.gs`, and click **Save** (disk icon).
4. Recommended: set an access code so strangers cannot spam you.
   Left sidebar: **Project Settings (gear) → Script properties → Add script property**
   Property: `ACCESS_CODE`   Value: a word you choose (you will tell your contributors this word).
5. Click **Deploy → New deployment**. Click the gear next to "Select type" and choose **Web app**.
   - Execute as: **Me**
   - Who has access: **Anyone**
   Click **Deploy**. Google asks you to authorise: choose your account. If it says "Google hasn't verified this app",
   click **Advanced → Go to (project name)**. This is your own script, so that is expected.
6. Copy the **Web app URL** (it looks like `https://script.google.com/macros/s/.../exec`).

## Part B: the page on your Vercel site
1. Build the page with your address inside (from the project folder):
   `python tools/build_contribute_page.py gonja_prompts.csv --endpoint PASTE-THE-WEB-APP-URL`
   This creates `contribute/gonja-contribute.html`. (Or open the HTML file and replace
   `PASTE_YOUR_WEB_APP_URL_HERE` by hand.)
2. Copy `gonja-contribute.html` into your site's **`public/`** folder
   (Next.js, Vite, React and most frameworks serve `public/` as-is; for a plain HTML site put it in the root).
3. Deploy as you normally do (push to GitHub, or run `vercel --prod`).
4. Your page is at: `https://YOUR-SITE/gonja-contribute.html`

## Part C: test before sharing
1. Open the page. Enter the name "Test", tick the consent box, answer two sentences, click **Save my answers**.
2. Check the Google Sheet: a "Submissions" tab should show your two rows. Delete them afterwards.

## Part D: bring the answers into your dataset
1. In the Sheet, open the **Submissions** tab: **File → Download → Comma Separated Values (.csv)**.
2. Save it in your `sheets/` folder, e.g. `sheets/web-2026-11.csv`.
3. Preview, then import (same tool as before; it ignores the extra columns):
   ```
   python tools/import_csv.py sheets/ --dry-run
   python tools/import_csv.py sheets/ --consent
   ```
   Re-importing the same file is safe: duplicates are skipped.
4. Then a different speaker reviews the new pairs (step 4), as before.

## Good to know
- **Anyone with the link can submit**, so bad or joke answers will arrive. That is why the access code exists, and why nothing
  enters training until a second speaker has reviewed it.
- The Sheet contains people's names. Do not make it public.
- If you edit `Code.gs` later: **Deploy → Manage deployments → pencil icon → Version: New version → Deploy**.
  This keeps the same web app URL. ("New deployment" creates a different URL.)
- The page orders sentences so the least-answered come first, and lets people add a second way to say a sentence.
- Drafts are saved in the visitor's browser, so a refresh does not lose their work.
- Prefer to keep everything inside Vercel? Possible with a serverless function plus a database (for example Postgres or Redis
  from the Vercel marketplace), but it needs more setup than the Sheet.
