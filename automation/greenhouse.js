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

function fieldLabel(element) {
  const id = element.id;
  const label = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
  const wrappingLabel = element.closest('label');
  const group = element.closest('.field, .application-question, .custom-question, div');
  return (
    (label && label.textContent.trim()) ||
    (wrappingLabel && wrappingLabel.textContent.trim()) ||
    element.getAttribute('aria-label') ||
    element.getAttribute('placeholder') ||
    element.name ||
    element.id ||
    (group && group.textContent.trim().slice(0, 220)) ||
    element.type ||
    ''
  );
}

function renderTemplate(template, context) {
  return String(template || '').replace(/\{([a-zA-Z0-9_]+)\}/g, (_, key) => context[key] || '');
}

function patternMatches(pattern, text) {
  if (!pattern || !text) return false;
  return new RegExp(pattern, 'i').test(text);
}

function isSensitiveQuestion(label) {
  return /gender|race|ethnic|veteran|disability|sexual orientation|pronoun|demographic/i.test(label || '');
}

function configuredAnswer(entries, label, context) {
  for (const entry of entries || []) {
    if (entry.sensitive !== true && isSensitiveQuestion(label)) continue;
    if (patternMatches(entry.match, label)) {
      return {
        ...entry,
        value: renderTemplate(entry.answer ?? entry.value ?? entry.select ?? '', context),
      };
    }
  }
  return null;
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

async function fillConfiguredQuestions(page, answers, context) {
  const configured = answers.question_answers || [];
  const dropdowns = answers.dropdown_answers || [];
  const radios = answers.radio_answers || [];
  const checks = answers.checkbox_answers || [];
  const fills = {
    text: 0,
    dropdown: 0,
    radio: 0,
    checkbox: 0,
  };

  const textFields = page.locator('textarea, input:not([type]), input[type="text"], input[type="url"]');
  for (let index = 0; index < await textFields.count(); index += 1) {
    const field = textFields.nth(index);
    const current = await field.inputValue().catch(() => '');
    if (current && current.trim()) continue;
    const label = await field.evaluate(fieldLabel).catch(() => '');
    const answer = configuredAnswer(configured, label, context);
    if (!answer || !answer.value) continue;
    await field.fill(answer.value).catch(() => {});
    fills.text += 1;
  }

  const selects = page.locator('select');
  for (let index = 0; index < await selects.count(); index += 1) {
    const select = selects.nth(index);
    const label = await select.evaluate(fieldLabel).catch(() => '');
    const answer = configuredAnswer(dropdowns, label, context);
    if (!answer || !answer.value) continue;
    const options = await select.locator('option').allTextContents();
    const match = options.find((option) => new RegExp(answer.value, 'i').test(option.trim()));
    if (!match) continue;
    await select.selectOption({ label: match }).catch(() => {});
    fills.dropdown += 1;
  }

  const radioGroups = await page.locator('input[type="radio"]').evaluateAll((elements) => {
    return Array.from(new Set(elements.map((element) => element.name).filter(Boolean)));
  });
  for (const name of radioGroups) {
    const group = page.locator(`input[type="radio"][name="${name.replaceAll('"', '\\"')}"]`);
    const first = group.first();
    const label = await first
      .evaluate((element) => {
        const fieldset = element.closest('fieldset');
        const legend = fieldset ? fieldset.querySelector('legend') : null;
        return (legend && legend.textContent.trim()) || element.name || '';
      })
      .catch(() => name);
    const answer = configuredAnswer(radios, label, context);
    if (!answer || !answer.value) continue;
    const options = await group.evaluateAll((elements) =>
      elements.map((element) => {
        const id = element.id;
        const label = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
        return {
          value: element.value || '',
          label: (label && label.textContent.trim()) || element.value || '',
        };
      }),
    );
    const matchIndex = options.findIndex((option) => new RegExp(answer.value, 'i').test(option.label || option.value));
    if (matchIndex < 0) continue;
    await group.nth(matchIndex).check().catch(() => {});
    fills.radio += 1;
  }

  const checkboxes = page.locator('input[type="checkbox"]');
  for (let index = 0; index < await checkboxes.count(); index += 1) {
    const checkbox = checkboxes.nth(index);
    const label = await checkbox.evaluate(fieldLabel).catch(() => '');
    const answer = configuredAnswer(checks, label, context);
    if (!answer || answer.check !== true) continue;
    await checkbox.check().catch(() => {});
    fills.checkbox += 1;
  }

  return fills;
}

async function clickApplyEntry(page) {
  const cookie = page.getByRole('button', { name: /accept all|accept cookies|reject all/i }).or(
    page.getByText(/accept all|accept cookies|reject all/i),
  ).first();
  if (await cookie.count()) {
    await cookie.click().catch(() => {});
    await page.waitForTimeout(500);
  }

  const apply = page.getByRole('link', { name: /apply now|apply for this job|apply/i }).or(
    page.getByRole('button', { name: /apply now|apply for this job|apply/i }),
  ).first();
  if (await apply.count()) {
    await apply.click();
    await page.waitForLoadState('domcontentloaded').catch(() => {});
    await page.waitForTimeout(1200);
  }
}

async function hasHumanVerification(page) {
  return Boolean(await page.locator('iframe[src*="recaptcha"], .g-recaptcha, [data-sitekey]').count());
}

async function uploadResume(page, resumePath) {
  const attach = page.getByText(/^Attach$/).first();
  if (await attach.count()) {
    const chooserPromise = page.waitForEvent('filechooser', { timeout: 5000 }).catch(() => null);
    await attach.click().catch(() => {});
    const chooser = await chooserPromise;
    if (chooser) {
      await chooser.setFiles(resumePath);
      await page.waitForTimeout(1200);
      return true;
    }
  }

  const fileInputs = page.locator('input[type="file"]');
  if (await fileInputs.count()) {
    await fileInputs.nth(0).setInputFiles(resumePath);
    await page.waitForTimeout(1200);
    return true;
  }
  return false;
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

  await uploadResume(page, resumePath);

  const fileInputs = page.locator('input[type="file"]');
  const count = await fileInputs.count();
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
        const wrappingLabel = element.closest('label');
        const fieldset = element.closest('fieldset');
        const legend = fieldset ? fieldset.querySelector('legend') : null;
        const group = element.closest('.field, .application-question, .custom-question, div');
        return (
          (label && label.textContent.trim()) ||
          (legend && legend.textContent.trim()) ||
          (wrappingLabel && wrappingLabel.textContent.trim()) ||
          element.getAttribute('aria-label') ||
          element.getAttribute('placeholder') ||
          element.name ||
          element.id ||
          (group && group.textContent.trim().slice(0, 220)) ||
          element.type ||
          ''
        );
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
  const jobMeta = {
    company: args.company || '',
    title: args.title || '',
    focus: args.focus || '',
    job_url: args['job-url'] || '',
  };
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
    fillable_fields: 0,
    required_unanswered: [],
    screenshot: path.join(packetPath, 'application_preview.png'),
  };

  try {
    await page.goto(args['job-url'], { waitUntil: 'domcontentloaded', timeout: 45000 });
    await clickApplyEntry(page);
    await fillCommonFields(page, profile, answers, resumePath, coverLetterPath);
    result.configured_answers = await fillConfiguredQuestions(page, answers, jobMeta);
    result.fillable_fields = await page.locator('input:not([type="hidden"]), textarea, select').count();
    result.application_form_detected = Boolean(
      (await page.getByText(/apply for this job|resume\/cv|resume|cover letter/i).count()) ||
        (await page.getByLabel(/first name|last name|email/i).count()),
    );
    result.required_unanswered = await requiredUnansweredFields(page);
    result.human_verification_required = await hasHumanVerification(page);
    result.ready_to_submit =
      result.application_form_detected && result.fillable_fields > 0 && result.required_unanswered.length === 0;
    if (result.fillable_fields === 0) {
      result.error = 'No application form fields were detected on this page.';
    }
    if (!result.application_form_detected) {
      result.error = 'No application form was detected on this page.';
    }
    if (result.human_verification_required) {
      result.ready_to_submit = false;
      result.error = 'Human verification is required on this form.';
    }
    await page.screenshot({ path: result.screenshot, fullPage: true });

    if (args.submit && result.ready_to_submit) {
      const submit = page.getByRole('button', { name: /submit application|submit/i }).or(
        page.locator('input[type="submit"], button[type="submit"]'),
      ).first();
      if (!(await submit.count())) {
        result.error = 'Submit button was not found. The filled application is ready for manual review.';
      } else {
        await submit.click();
        await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
        const confirmation = page.getByText(/thank you|application (was )?submitted|application received/i).first();
        result.submitted = Boolean(await confirmation.count());
        if (!result.submitted) {
          result.required_unanswered = await requiredUnansweredFields(page);
          result.error = 'Submission confirmation was not detected. The tracker was not marked applied.';
        }
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
  clickApplyEntry,
  fillCommonFields,
  fillConfiguredQuestions,
  fieldLabel,
  markdownToHtml,
  requiredUnansweredFields,
  uploadResume,
  hasHumanVerification,
};
