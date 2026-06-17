const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const {
  clickApplyEntry,
  ensureTailoredPdf,
  fillCommonFields,
  fillConfiguredQuestions,
  hasHumanVerification,
  requiredUnansweredFields,
} = require('./greenhouse.js');

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const value = argv[i];
    if (!value.startsWith('--')) continue;
    const key = value.slice(2);
    args[key] = argv[i + 1];
    i += 1;
  }
  return args;
}

async function preparePage({ browser, context, job, profile, answers }) {
  const packetPath = path.resolve(job.packet_path);
  fs.mkdirSync(packetPath, { recursive: true });
  const resumePath = await ensureTailoredPdf(browser, packetPath, answers.fallback_resume || 'resume/Barney_Jin_SDE_Resume.pdf');
  const coverLetterPath = path.join(packetPath, 'cover_letter.pdf');
  const page = await context.newPage();
  const result = {
    job_key: job.job_key,
    company: job.company,
    title: job.title,
    score: job.score,
    job_url: job.application_url || job.job_url,
    resume_path: resumePath,
    submitted: false,
    ready_to_submit: false,
    fillable_fields: 0,
    required_unanswered: [],
    screenshot: path.join(packetPath, 'application_preview.png'),
  };

  try {
    await page.goto(result.job_url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await clickApplyEntry(page);
    await fillCommonFields(page, profile, answers, resumePath, coverLetterPath);
    result.configured_answers = await fillConfiguredQuestions(page, answers, {
      company: job.company || '',
      title: job.title || '',
      focus: job.focus || '',
      job_url: result.job_url || '',
    });
    result.fillable_fields = await page.locator('input:not([type="hidden"]), textarea, select').count();
    result.application_form_detected = Boolean(
      (await page.getByText(/apply for this job|resume\/cv|resume|cover letter/i).count()) ||
        (await page.getByLabel(/first name|last name|email/i).count()),
    );
    result.required_unanswered = await requiredUnansweredFields(page);
    result.human_verification_required = await hasHumanVerification(page);
    result.ready_to_submit =
      result.application_form_detected &&
      result.fillable_fields > 0 &&
      result.required_unanswered.length === 0 &&
      !result.human_verification_required;
    if (!result.application_form_detected) result.error = 'No application form was detected on this page.';
    if (result.human_verification_required) result.error = 'Human verification is required on this form.';
    await page.screenshot({ path: result.screenshot, fullPage: true }).catch(() => {});
    return result;
  } catch (error) {
    result.error = error.message || String(error);
    await page.screenshot({ path: result.screenshot, fullPage: true }).catch(() => {});
    return result;
  }
}

async function main() {
  const args = parseArgs(process.argv);
  for (const required of ['jobs', 'profile', 'answers', 'result']) {
    if (!args[required]) throw new Error(`Missing --${required}`);
  }
  const jobs = JSON.parse(fs.readFileSync(path.resolve(args.jobs), 'utf8'));
  const profile = JSON.parse(fs.readFileSync(path.resolve(args.profile), 'utf8'));
  const answers = JSON.parse(fs.readFileSync(path.resolve(args.answers), 'utf8'));
  const resultPath = path.resolve(args.result);

  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const results = [];
  for (const job of jobs) {
    const result = await preparePage({ browser, context, job, profile, answers });
    results.push(result);
    console.log(
      `[${result.ready_to_submit ? 'ready' : 'review'}] ${job.score} ${job.company} - ${job.title} (${job.job_key})`,
    );
  }
  fs.writeFileSync(resultPath, JSON.stringify(results, null, 2));
  console.log('');
  console.log('Prepared application tabs are open. Finish captcha/dropdowns/custom questions and click Submit manually.');
  console.log('Press Enter in this terminal when you are done to close the browser.');
  await new Promise((resolve) => process.stdin.once('data', resolve));
  await browser.close();
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.stack || error.message);
    process.exit(1);
  });
}
