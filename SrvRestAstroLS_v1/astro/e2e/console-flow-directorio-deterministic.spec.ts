import { test, expect } from "@playwright/test";

// Deterministic browser regression. The caller creates one fresh fixture with
// the real PostgreSQL Flow harness and passes its marker/request identity.

const marker = process.env.TEAM360_FLOW_DEMO_MARKER ?? "";
const requestId = process.env.TEAM360_FLOW_DEMO_REQUEST_ID ?? "";

test("fresh PostgreSQL fixture is discoverable as AUDIT_SNAPSHOT", async ({ page }) => {
  if (!marker || !requestId) {
    throw new Error("TEAM360_FLOW_DEMO_MARKER and TEAM360_FLOW_DEMO_REQUEST_ID are required");
  }
  await page.goto("/w/ws-team360-control/flow");
  await expect(page.getByText("Backend Flow · datos reales", { exact: true })).toBeVisible();
  const response = await page.request.get(`/api/team360-flow/executive?search=${encodeURIComponent(marker)}&page_size=20`);
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  expect(payload.pagination.total).toBe(1);
  expect(payload.items[0].request_id).toBe(requestId);
  expect(payload.items[0].data_source).toBe("AUDIT_SNAPSHOT");

  const token = requestId.slice(0, 8);
  const search = page.getByRole("searchbox", { name: "Buscar caso" });
  await search.fill(token);
  const item = page.locator("ul li button", { hasText: `#${token}` });
  await expect(item).toHaveCount(1);
  await item.click();
  const detail = page.locator('[data-selected="yes"]');
  await expect(detail.getByText("Registro final auditado", { exact: true })).toBeVisible();
  await expect(detail.getByText("Caso resuelto", { exact: true })).toBeVisible();
  await expect(detail.getByText("Evidencia y trazabilidad", { exact: true })).toBeVisible();
});
