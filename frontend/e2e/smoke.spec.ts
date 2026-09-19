import { test, expect } from '@playwright/test';

test.describe('FalsePay HCP Outbound - E2E User Journey', () => {
  test('full review flow: queue -> secure portal -> notice -> enrollment', async ({ page }) => {
    // 1. Load review workspace
    await page.goto('/');

    // Check branding and the data signal indicator
    await expect(page.locator('header')).toContainText('FalsePay');
    await expect(page.getByText('Review queue')).toBeVisible();
    await expect(page.getByText('Tiger Data')).toBeVisible();

    // 2. Select Dr. Jane Miller (has unreviewed payments & high mismatch score)
    const doctorRow = page.locator('tr').filter({ hasText: 'Jane Miller' });
    await expect(doctorRow).toBeVisible();
    await doctorRow.click();

    // Verify the review workspace renders Dr. Jane Miller immediately
    const portalRegion = page.getByRole('region', { name: 'Physician audit workspace' });
    await expect(portalRegion).toBeVisible();
    await expect(portalRegion.getByText('Dr. Jane Miller')).toBeVisible();
    await expect(portalRegion.getByText('Specialty Mismatch Detected')).toBeVisible();

    // 3. Create a secure review link
    const launchBtn = page.getByRole('button', { name: /Create review link/i });
    await expect(launchBtn).toBeEnabled();
    await launchBtn.click();

    // Modal should appear
    const modal = page.getByRole('dialog');
    await expect(modal).toBeVisible();
    await expect(modal.getByRole('heading', { name: 'Create secure review link' })).toBeVisible();

    // Submit Alert dispatch
    const sendBtn = modal.getByRole('button', { name: /Create secure review link/i });
    await sendBtn.click();

    // 4. Modal closes and link status appears
    await expect(modal).not.toBeVisible();
    await expect(portalRegion.getByText(/Secure review link created/i)).toBeVisible();

    // 5. Zero-login 1-Click Dispute (No SMS, No OTP required)
    const disputeBtn = portalRegion.getByRole('button', { name: /Dispute Unreviewed Items/i });
    await expect(disputeBtn).toBeVisible();
    await disputeBtn.click();

    // 6. Formal 42 CFR § 403.908 Dispute Notice preview
    await expect(portalRegion.getByText(/42 CFR § 403.908/i).first()).toBeVisible({ timeout: 5000 });
    await expect(portalRegion.getByText(/CMS Open Payments Dispute Notice/i)).toBeVisible();

    // 7. Optional ongoing monitoring
    const enrollBtn = portalRegion.getByRole('button', { name: /Start ongoing monitoring/i });
    await expect(enrollBtn).toBeVisible();
    await enrollBtn.click();

    // 8. Review-ready monitoring confirmation
    await expect(portalRegion.getByText('Notice ready for review')).toBeVisible();
    await expect(portalRegion.getByText('Ongoing monitoring active')).toBeVisible();
  });

  test('standalone zero-login route /audit/[token] renders audit card and handles 1-click dispute', async ({ page }) => {
    // Navigate to standalone token route
    await page.goto('/audit/mock_token_1235149876');

    await expect(page.locator('header')).toContainText('FalsePay');
    await expect(page.getByText('Dr. Jane Miller')).toBeVisible();
    await expect(page.getByText('Specialty Mismatch Detected')).toBeVisible();

    const disputeBtn = page.getByRole('button', { name: /Dispute Unreviewed Items/i });
    await expect(disputeBtn).toBeVisible();
    await disputeBtn.click();

    // Directly transitions to dispute notice without OTP
    await expect(page.getByText(/42 CFR § 403.908/i).first()).toBeVisible({ timeout: 5000 });
    const enrollBtn = page.getByRole('button', { name: /Start ongoing monitoring/i });
    await expect(enrollBtn).toBeVisible();
    await enrollBtn.click();

    await expect(page.getByText('Notice ready for review')).toBeVisible();
    await expect(page.getByText('Ongoing monitoring active')).toBeVisible();
  });
});
