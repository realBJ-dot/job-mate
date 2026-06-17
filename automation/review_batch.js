const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');
const {
  applicationScope,
  clickApplyEntry,
  ensureTailoredPdf,
  fillCommonFields,
  fillConfiguredQuestions,
  formFieldDiagnostics,
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
    const scope = await applicationScope(page);
    result.application_frame_url = scope.url();
    await fillCommonFields(scope, profile, answers, resumePath, coverLetterPath);
    result.configured_answers = await fillConfiguredQuestions(scope, answers, {
      company: job.company || '',
      title: job.title || '',
      focus: job.focus || '',
      job_url: result.job_url || '',
    });
    result.field_diagnostics = await formFieldDiagnostics(scope);
    result.fillable_fields = await scope.locator('input:not([type="hidden"]), textarea, select').count();
    result.application_form_detected = Boolean(
      (await scope.getByText(/apply for this job|resume\/cv|resume|cover letter/i).count()) ||
        (await scope.getByLabel(/first name|last name|email/i).count()),
    );
    result.required_unanswered = await requiredUnansweredFields(scope);
    result.human_verification_required = (await hasHumanVerification(scope)) || (await hasHumanVerification(page));
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
  for (const [index, job] of jobs.entries()) {
    const result = await preparePage({ browser, context, job, profile, answers });
    results.push(result);
    console.log(
      `[${index + 1}] [${result.ready_to_submit ? 'ready' : 'review'}] ${job.score} ${job.company} - ${job.title} (${job.job_key})`,
    );
  }
  console.log('');
  console.log('Prepared application tabs are open. Finish captcha/dropdowns/custom questions and click Submit manually.');
  console.log('When done, enter submitted job numbers like "1,3,4", "all", or press Enter for none. The tracker will skip submitted jobs next time.');
  const submittedInput = await new Promise((resolve) => process.stdin.once('data', (data) => resolve(String(data || '').trim())));
  const submittedIndexes = new Set();
  if (/^all$/i.test(submittedInput)) {
    results.forEach((_, index) => submittedIndexes.add(index));
  } else {
    for (const piece of submittedInput.split(',')) {
      const index = Number.parseInt(piece.trim(), 10);
      if (Number.isInteger(index) && index >= 1 && index <= results.length) submittedIndexes.add(index - 1);
    }
  }
  for (const [index, result] of results.entries()) {
    if (submittedIndexes.has(index)) {
      result.submitted = true;
      result.submitted_by_user = true;
      result.ready_to_submit = false;
    }
  }
  fs.writeFileSync(resultPath, JSON.stringify(results, null, 2));
  await browser.close();
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.stack || error.message);
    process.exit(1);
  });
}
