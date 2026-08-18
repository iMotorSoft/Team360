import { test, expect } from "@playwright/test";

const searchToken = process.env.TEAM360_FLOW_PAGE_SEARCH ?? "";
const expectedCount = Number(process.env.TEAM360_FLOW_PAGE_COUNT ?? "0");

test("isolated fixture pagination survives unrelated database growth", async ({ page }) => {
  if (!searchToken || !expectedCount) {
    throw new Error("TEAM360_FLOW_PAGE_SEARCH and TEAM360_FLOW_PAGE_COUNT are required");
  }

  await page.goto("/w/ws-team360-control/flow");
  await expect(page.getByText("Backend Flow · datos reales", { exact: true })).toBeVisible();

  const pageOne = await page.request.get(
    `/api/team360-flow/executive?search=${encodeURIComponent(searchToken)}&page=1&page_size=10`,
  );
  const first = await pageOne.json();
  expect(first.pagination.total).toBe(expectedCount);
  expect(first.items).toHaveLength(10);

  const pageTwo = await page.request.get(
    `/api/team360-flow/executive?search=${encodeURIComponent(searchToken)}&page=2&page_size=10`,
  );
  const second = await pageTwo.json();
  expect(second.items).toHaveLength(10);

  const pageThree = await page.request.get(
    `/api/team360-flow/executive?search=${encodeURIComponent(searchToken)}&page=3&page_size=10`,
  );
  const third = await pageThree.json();
  expect(third.items).toHaveLength(expectedCount - 20);

  const search = page.getByRole("searchbox", { name: "Buscar caso" });
  const searchPageOne = page.waitForResponse((response) =>
    response.url().includes("/api/team360-flow/executive?") &&
    response.url().includes(`search=${encodeURIComponent(searchToken)}`) &&
    response.url().includes("page=1"),
  );
  await search.fill(searchToken);
  await searchPageOne;
  await expect(page.locator("ul li button")).toHaveCount(Math.min(expectedCount, 20));
  if (expectedCount > 20) {
    const searchPageTwo = page.waitForResponse((response) =>
      response.url().includes("/api/team360-flow/executive?") &&
      response.url().includes(`search=${encodeURIComponent(searchToken)}`) &&
      response.url().includes("page=2"),
    );
    await page.getByRole("button", { name: "Siguiente" }).click({ force: true });
    await searchPageTwo;
    await expect(page.getByText("Página 2", { exact: true })).toBeVisible();
    await expect(page.locator("ul li button")).toHaveCount(expectedCount - 20);
  }
});
