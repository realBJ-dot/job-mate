const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const value = argv[i];
    if (!value.startsWith('--')) continue;
    const key = value.slice(2);
    if (key === 'headless') {
      args[key] = true;
    } else {
      args[key] = argv[i + 1];
      i += 1;
    }
  }
  return args;
}

function buildSearchUrl({ keywords, location, easyApply, recentDays }) {
  const params = new URLSearchParams();
  params.set('keywords', keywords || 'software engineer');
  params.set('location', location || 'United States');
  if (easyApply) params.set('f_AL', 'true');
  if (recentDays) params.set('f_TPR', `r${Number(recentDays) * 86400}`);
  return `https://www.linkedin.com/jobs/search/?${params.toString()}`;
}

function normalizeJobId(url, fallback) {
  const match = String(url || '').match(/(?:currentJobId=|\/jobs\/view\/)(\d+)/);
  return match ? match[1] : fallback;
}

async function login(args) {
  const storageState = path.resolve(args['storage-state'] || 'state/linkedin_storage_state.json');
  fs.mkdirSync(path.dirname(storageState), { recursive: true });
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('https://www.linkedin.com/login', { waitUntil: 'domcontentloaded' });
  console.log('Log into LinkedIn in the opened browser. Press Enter here after the LinkedIn jobs page loads.');
  await new Promise((resolve) => process.stdin.once('data', resolve));
  await context.storageState({ path: storageState });
  await browser.close();
  console.log(`Saved LinkedIn session to ${storageState}`);
}

async function collectFromCards(page, maxJobs) {
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(2500);
  const cards = page.locator('[data-job-id], .job-card-container, .jobs-search-results__list-item');
  const count = Math.min(await cards.count(), maxJobs);
  const jobs = [];

  for (let index = 0; index < count; index += 1) {
    const card = cards.nth(index);
    await card.scrollIntoViewIfNeeded().catch(() => {});
    const extracted = await card.evaluate((node) => {
      const text = (selector) => node.querySelector(selector)?.textContent?.trim() || '';
      const link = node.querySelector('a[href*="/jobs/view/"], a[href*="currentJobId="]');
      const url = link ? link.href : '';
      return {
        id: node.getAttribute('data-job-id') || '',
        title: text('.job-card-list__title, .job-card-container__link, a[href*="/jobs/view/"]'),
        company: text('.job-card-container__primary-description, .artdeco-entity-lockup__subtitle'),
        location: text('.job-card-container__metadata-item, .job-card-container__metadata-wrapper li'),
        url,
        content: node.textContent?.trim() || '',
      };
    });

    const id = normalizeJobId(extracted.url, extracted.id || `card-${index}`);
    const title = extracted.title || 'LinkedIn Job';
    const company = extracted.company || 'LinkedIn';
    jobs.push({
      id,
      title,
      company,
      location: extracted.location || 'Unspecified',
      url: extracted.url || `https://www.linkedin.com/jobs/view/${id}/`,
      content: extracted.content || `${title} ${company}`,
      source: 'linkedin',
    });
  }
  return jobs;
}

async function search(args) {
  const output = path.resolve(args.output || 'state/linkedin_jobs.json');
  const storageState = path.resolve(args['storage-state'] || 'state/linkedin_storage_state.json');
  const maxJobs = Number(args.max || 25);
  const url = args.url || buildSearchUrl({
    keywords: args.keywords,
    location: args.location,
    easyApply: args['easy-apply'] !== 'false',
    recentDays: args['recent-days'] || 7,
  });

  if (!fs.existsSync(storageState)) {
    throw new Error(`LinkedIn session not found at ${storageState}. Run: python3 main.py linkedin-login`);
  }

  const browser = await chromium.launch({ headless: Boolean(args.headless) });
  const context = await browser.newContext({ storageState });
  const page = await context.newPage();
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });

  if (/\/login|checkpoint|captcha/i.test(page.url())) {
    await browser.close();
    throw new Error('LinkedIn requires login or verification. Run python3 main.py linkedin-login and complete any challenge manually.');
  }

  const jobs = await collectFromCards(page, maxJobs);
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, JSON.stringify({ url, jobs }, null, 2));
  await browser.close();
  console.log(`Wrote ${jobs.length} LinkedIn jobs to ${output}`);
}

async function main() {
  const args = parseArgs(process.argv);
  const mode = args.mode || 'search';
  if (mode === 'login') {
    await login(args);
  } else if (mode === 'search') {
    await search(args);
  } else {
    throw new Error(`Unknown mode: ${mode}`);
  }
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message || error);
    process.exit(1);
  });
}

module.exports = { buildSearchUrl, normalizeJobId };
