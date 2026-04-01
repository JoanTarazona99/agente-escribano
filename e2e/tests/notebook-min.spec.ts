import { test, expect } from "@playwright/test";

test.describe("Notebook UI mínima", () => {
  test("/notebooks/26 muestra artículos y no supera 10 visibles", async ({ page, request }) => {
    const apiResp = await request.get("http://localhost:8000/api/notebooks/26/");
    expect(apiResp.ok()).toBeTruthy();
    const notebook = await apiResp.json();

    await page.goto("/notebooks/26");
    await expect(page.locator(".nb-sources__title")).toBeVisible();

    const cards = page.locator(".article-card");
    await expect(cards.first()).toBeVisible({ timeout: 15000 });

    const uiCount = await cards.count();
    expect(uiCount).toBeGreaterThan(0);
    expect(uiCount).toBeLessThanOrEqual(10);

    const countText = (await page.locator(".nb-sources__count").textContent())?.trim() ?? "0";
    const badgeCount = Number.parseInt(countText, 10);
    expect(Number.isNaN(badgeCount)).toBeFalsy();
    expect(badgeCount).toBeLessThanOrEqual(10);

    const apiArticlesCount = Number(notebook.articles_count ?? 0);
    expect(uiCount).toBeLessThanOrEqual(apiArticlesCount || 10);
  });
});
