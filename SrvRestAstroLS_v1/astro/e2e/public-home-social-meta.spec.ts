import { expect, test } from "@playwright/test";

test.describe("Public Home — social sharing metadata", () => {
  test("root page has correct Open Graph and Twitter metadata", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/Team360/);

    const ogTitle = await page.locator('meta[property="og:title"]').getAttribute("content");
    const ogUrl = await page.locator('meta[property="og:url"]').getAttribute("content");
    const ogImage = await page.locator('meta[property="og:image"]').getAttribute("content");
    const ogDescription = await page.locator('meta[property="og:description"]').getAttribute("content");
    const canonical = await page.locator('link[rel="canonical"]').getAttribute("href");
    const twitterCard = await page.locator('meta[name="twitter:card"]').getAttribute("content");
    const ogType = await page.locator('meta[property="og:type"]').getAttribute("content");

    expect(ogTitle).toBeTruthy();
    expect(ogDescription).toBeTruthy();
    expect(ogUrl).toBe("https://team360.live/");
    expect(ogImage).toBe("https://team360.live/social/team360-social-preview.png");
    expect(ogImage).toMatch(/^https:\/\/team360\.live\//);
    expect(canonical).toBe("https://team360.live/");
    expect(twitterCard).toBe("summary_large_image");
    expect(ogType).toBe("website");

    // No duplicates
    await expect(page.locator('meta[property="og:title"]')).toHaveCount(1);
    await expect(page.locator('meta[property="og:description"]')).toHaveCount(1);
    await expect(page.locator('meta[property="og:url"]')).toHaveCount(1);
    await expect(page.locator('meta[property="og:image"]')).toHaveCount(1);
    await expect(page.locator('link[rel="canonical"]')).toHaveCount(1);
  });

  test("t360 page has distinct canonical URL", async ({ page }) => {
    await page.goto("/t360");
    const canonical = await page.locator('link[rel="canonical"]').getAttribute("href");
    const ogUrl = await page.locator('meta[property="og:url"]').getAttribute("content");
    // Astro dev uses no trailing slash, build adds one — accept both
    expect(canonical).toMatch(/^https:\/\/team360\.live\/t360\/?$/);
    expect(ogUrl).toMatch(/^https:\/\/team360\.live\/t360\/?$/);
  });
});
