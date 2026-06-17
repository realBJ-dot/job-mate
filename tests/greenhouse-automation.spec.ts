import { expect, test } from '@playwright/test';

const {
  fillCommonFields,
  fillConfiguredQuestions,
  requiredUnansweredFields,
} = require('../automation/greenhouse.js');

test('fills common application fields and uploads a resume', async ({ page }) => {
  await page.setContent(`
    <form>
      <label for="first_name">First name</label>
      <input id="first_name" required>
      <label for="last_name">Last name</label>
      <input id="last_name" required>
      <label for="email">Email</label>
      <input id="email" type="email" required>
      <label for="phone">Phone</label>
      <input id="phone">
      <label for="linkedin">LinkedIn</label>
      <input id="linkedin">
      <label for="authorization">Are you legally authorized to work?</label>
      <select id="authorization" required>
        <option value="">Select</option>
        <option>Yes</option>
        <option>No</option>
      </select>
      <label for="sponsorship">Will you require sponsorship?</label>
      <select id="sponsorship" required>
        <option value="">Select</option>
        <option>Yes</option>
        <option>No</option>
      </select>
      <label for="resume">Resume</label>
      <input id="resume" type="file" required>
    </form>
  `);

  await fillCommonFields(
    page,
    {
      name: 'Barney Jin',
      contact: {
        email: 'peiyuan3@illinois.edu',
        phone: '+1 (317) 316-7876',
        portfolio: 'https://example.com',
      },
    },
    {
      first_name: 'Barney',
      last_name: 'Jin',
      linkedin: 'https://linkedin.com/in/example',
      requires_sponsorship: true,
    },
    'resume/Barney_Jin_SDE_Resume.pdf',
    'missing-cover-letter.pdf',
  );

  await expect(page.getByLabel(/first name/i)).toHaveValue('Barney');
  await expect(page.getByLabel(/last name/i)).toHaveValue('Jin');
  await expect(page.getByLabel(/email/i)).toHaveValue('peiyuan3@illinois.edu');
  await expect(page.getByLabel(/authorized/i)).toHaveValue('Yes');
  await expect(page.getByLabel(/sponsorship/i)).toHaveValue('Yes');
  await expect(page.getByLabel(/resume/i)).toHaveValue(/Barney_Jin_SDE_Resume\.pdf$/);
  expect(await requiredUnansweredFields(page)).toEqual([]);
});

test('uploads resume through an attach button file chooser', async ({ page }) => {
  await page.setContent(`
    <button type="button" id="attach">Attach</button>
    <input id="resume" type="file" style="display:none">
    <script>
      document.querySelector('#attach').addEventListener('click', () => {
        document.querySelector('#resume').click();
      });
    </script>
  `);

  const { uploadResume } = require('../automation/greenhouse.js');
  expect(await uploadResume(page, 'resume/Barney_Jin_SDE_Resume.pdf')).toBeTruthy();
  await expect(page.locator('#resume')).toHaveValue(/Barney_Jin_SDE_Resume\.pdf$/);
});

test('reports unknown required questions instead of inventing an answer', async ({ page }) => {
  await page.setContent(`
    <label for="custom_question">Describe your favorite production incident</label>
    <textarea id="custom_question" name="custom_question" required></textarea>
  `);

  expect(await requiredUnansweredFields(page)).toEqual([
    'Describe your favorite production incident',
  ]);
});

test('detects human verification widgets', async ({ page }) => {
  await page.setContent('<div class="g-recaptcha" data-sitekey="test"></div>');
  const { hasHumanVerification } = require('../automation/greenhouse.js');
  expect(await hasHumanVerification(page)).toBeTruthy();
});

test('fills configured text, dropdown, radio, and consent answers', async ({ page }) => {
  await page.setContent(`
    <form>
      <label for="why">Why are you interested in our company?</label>
      <textarea id="why" required></textarea>
      <label for="source">How did you hear about us?</label>
      <select id="source" required>
        <option>Select...</option>
        <option>LinkedIn</option>
      </select>
      <fieldset>
        <legend>Will you require sponsorship?</legend>
        <label><input type="radio" name="sponsor" value="Yes" required>Yes</label>
        <label><input type="radio" name="sponsor" value="No" required>No</label>
      </fieldset>
      <label><input type="checkbox" id="privacy" required>I consent to privacy terms</label>
    </form>
  `);

  const fills = await fillConfiguredQuestions(
    page,
    {
      question_answers: [{ match: 'why.*company', answer: 'I like {company} and {title}.' }],
      dropdown_answers: [{ match: 'how did you hear', select: 'LinkedIn' }],
      radio_answers: [{ match: 'sponsor', answer: 'Yes' }],
      checkbox_answers: [{ match: 'privacy', check: true }],
    },
    { company: 'ExampleCo', title: 'Backend Engineer' },
  );

  expect(fills).toEqual({ text: 1, dropdown: 1, radio: 1, checkbox: 1 });
  await expect(page.locator('#why')).toHaveValue('I like ExampleCo and Backend Engineer.');
  await expect(page.locator('#source')).toHaveValue('LinkedIn');
  await expect(page.locator('input[name="sponsor"][value="Yes"]')).toBeChecked();
  await expect(page.locator('#privacy')).toBeChecked();
});
