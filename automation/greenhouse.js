const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const value = argv[i];
    if (!value.startsWith('--')) continue;
    const key = value.slice(2);
    if (key === 'submit' || key === 'headless') {
      args[key] = true;
    } else {
      args[key] = argv[i + 1];
      i += 1;
    }
  }
  return args;
}

function escapeHtml(value) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

function markdownToHtml(markdown) {
  const lines = markdown.split(/\r?\n/);
  const output = [];
  let inList = false;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (line.startsWith('- ')) {
      if (!inList) {
        output.push('<ul>');
        inList = true;
      }
      output.push(`<li>${escapeHtml(line.slice(2))}</li>`);
      continue;
    }
    if (inList) {
      output.push('</ul>');
      inList = false;
    }
    if (!line) {
      output.push('<div class="space"></div>');
    } else if (line.startsWith('# ')) {
      output.push(`<h1>${escapeHtml(line.slice(2))}</h1>`);
    } else if (line.startsWith('## ')) {
      output.push(`<h2>${escapeHtml(line.slice(3))}</h2>`);
    } else {
      output.push(`<p>${escapeHtml(line)}</p>`);
    }
  }
  if (inList) output.push('</ul>');
  return output.join('\n');
}

async function ensureTailoredPdf(browser, packetPath, fallbackResume) {
  const packet = path.resolve(packetPath);
  const existingPdf = path.join(packet, 'tailored_cv.pdf');
  if (fs.existsSync(existingPdf)) return existingPdf;

  const markdownPath = path.join(packet, 'tailored_cv.md');
  if (!fs.existsSync(markdownPath)) return path.resolve(fallbackResume);

  const markdown = fs.readFileSync(markdownPath, 'utf8');
  const page = await browser.newPage();
  await page.setContent(`<!doctype html>
    <html>
      <head>
        <meta charset="utf-8">
        <style>
          @page { size: Letter; margin: 0.5in; }
          body { font-family: Arial, sans-serif; color: #15171a; font-size: 10.5pt; line-height: 1.28; }
          h1 { font-size: 21pt; margin: 0 0 3px; }
          h2 { font-size: 11.5pt; text-transform: uppercase; border-bottom: 1px solid #555; margin: 12px 0 5px; }
          p { margin: 2px 0; }
          ul { margin: 3px 0 5px 18px; padding: 0; }
          li { margin: 2px 0; }
          .space { height: 3px; }
        </style>
      </head>
      <body>${markdownToHtml(markdown)}</body>
    </html>`);
  await page.pdf({ path: existingPdf, format: 'Letter', printBackground: true });
  await page.close();
  return existingPdf;
}

async function fillByLabel(page, labelPattern, value) {
  if (!value) return false;
  const locator = page.getByLabel(labelPattern).first();
  if (!(await locator.count())) return false;
  try {
    await locator.fill(String(value));
    return true;
  } catch {
    return false;
  }
}

async function chooseByLabel(page, labelPattern, answerPattern) {
  const field = page.getByLabel(labelPattern).first();
  if (!(await field.count())) return false;
  try {
    const tag = await field.evaluate((element) => element.tagName.toLowerCase());
    if (tag === 'select') {
      const options = await field.locator('option').allTextContents();
      const match = options.find((option) => answerPattern.test(option.trim()));
      if (!match) return false;
      await field.selectOption({ label: match });
      return true;
    }
  } catch {
    return false;
  }
  return false;
}

async function clickApplyEntry(page) {
  const apply = page.getByRole('link', { name: /apply/i }).or(
    page.getByRole('button', { name: /apply/i }),
  ).first();
  if (await apply.count()) {
    await apply.click();
    await page.waitForLoadState('domcontentloaded').catch(() => {});
  }
}

async function fillCommonFields(page, profile, answers, resumePath, coverLetterPath) {
  const contact = profile.contact || {};
  const nameParts = String(profile.name || '').trim().split(/\s+/);
  const firstName = answers.first_name || nameParts[0] || '';
  const lastName = answers.last_name || nameParts.slice(1).join(' ');

  await fillByLabel(page, /first name/i, firstName);
  await fillByLabel(page, /last name/i, lastName);
  await fillByLabel(page, /^name$/i, profile.name);
  await fillByLabel(page, /email/i, contact.email);
  await fillByLabel(page, /phone/i, contact.phone);
  await fillByLabel(page, /linkedin/i, answers.linkedin);
  await fillByLabel(page, /(website|portfolio)/i, contact.portfolio);
  await fillByLabel(page, /(current location|location)/i, answers.location || contact.location);

  const resumeInput = page.locator('input[type="file"]').filter({ has: page.locator('xpath=..') }).first();
  const fileInputs = page.locator('input[type="file"]');
  const count = await fileInputs.count();
  if (count > 0) await fileInputs.nth(0).setInputFiles(resumePath);
  if (count > 1 && fs.existsSync(coverLetterPath)) await fileInputs.nth(1).setInputFiles(coverLetterPath);

  await chooseByLabel(page, /(authorized|legally authorized).*(work|employment)/i, /^(yes|authorized)$/i);
  if (answers.requires_sponsorship === true) {
    await chooseByLabel(page, /(sponsor|sponsorship|visa)/i, /^yes$/i);
  } else if (answers.requires_sponsorship === false) {
    await chooseByLabel(page, /(sponsor|sponsorship|visa)/i, /^no$/i);
  }
}

async function requiredUnansweredFields(page) {
  return page.locator('input:required, textarea:required, select:required').evaluateAll((elements) =>
    elements
      .filter((element) => {
        if (element.disabled || element.type === 'hidden') return false;
        if (element.type === 'radio') {
          const group = Array.from(document.querySelectorAll(`input[type="radio"][name="${CSS.escape(element.name)}"]`));
          return !group.some((radio) => radio.checked);
        }
        if (element.type === 'checkbox') return !element.checked;
        return !String(element.value || '').trim();
      })
      .map((element) => {
        const id = element.id;
        const label = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
        return (label && label.textContent.trim()) || element.name || element.id || element.type;
      }),
  );
}

async function main() {
  const args = parseArgs(process.argv);
  for (const required of ['job-url', 'packet', 'profile', 'answers', 'result']) {
    if (!args[required]) throw new Error(`Missing --${required}`);
  }

  const profile = JSON.parse(fs.readFileSync(path.resolve(args.profile), 'utf8'));
  const answers = JSON.parse(fs.readFileSync(path.resolve(args.answers), 'utf8'));
  const resultPath = path.resolve(args.result);
  const packetPath = path.resolve(args.packet);
  fs.mkdirSync(packetPath, { recursive: true });

  const browser = await chromium.launch({ headless: Boolean(args.headless) });
  const context = await browser.newContext();
  const page = await context.newPage();
  const resumePath = await ensureTailoredPdf(
    browser,
    packetPath,
    answers.fallback_resume || 'resume/Barney_Jin_SDE_Resume.pdf',
  );
  const coverLetterPath = path.join(packetPath, 'cover_letter.pdf');

  const result = {
    job_url: args['job-url'],
    resume_path: resumePath,
    submitted: false,
    ready_to_submit: false,
    required_unanswered: [],
    screenshot: path.join(packetPath, 'application_preview.png'),
  };

  try {
    await page.goto(args['job-url'], { waitUntil: 'domcontentloaded', timeout: 45000 });
    await clickApplyEntry(page);
    await fillCommonFields(page, profile, answers, resumePath, coverLetterPath);
    result.required_unanswered = await requiredUnansweredFields(page);
    result.ready_to_submit = result.required_unanswered.length === 0;
    await page.screenshot({ path: result.screenshot, fullPage: true });

    if (args.submit && result.ready_to_submit) {
      const submit = page.getByRole('button', { name: /submit application|submit/i }).first();
      if (!(await submit.count())) throw new Error('Submit button was not found.');
      await submit.click();
      await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
      const confirmation = page.getByText(/thank you|application (was )?submitted|application received/i).first();
      result.submitted = Boolean(await confirmation.count());
      if (!result.submitted) {
        result.required_unanswered = await requiredUnansweredFields(page);
        result.error = 'Submission confirmation was not detected. The tracker was not marked applied.';
      }
      await page.screenshot({ path: path.join(packetPath, 'application_submitted.png'), fullPage: true });
    }

    fs.writeFileSync(resultPath, JSON.stringify(result, null, 2));
    if (!args.headless && !args.submit) {
      console.log('Application is filled for review. Close the browser window when finished.');
      await page.waitForEvent('close', { timeout: 0 }).catch(() => {});
    }
  } finally {
    if (browser.isConnected()) await browser.close();
  }
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.stack || error.message);
    process.exit(1);
  });
}

module.exports = {
  ensureTailoredPdf,
  fillCommonFields,
  markdownToHtml,
  requiredUnansweredFields,
};
