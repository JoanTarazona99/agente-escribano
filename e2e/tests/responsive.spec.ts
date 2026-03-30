import { test, expect } from "@playwright/test";

const BREAKPOINTS = [
  { name: "mobile", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1280, height: 800 },
];

for (const bp of BREAKPOINTS) {
  test.describe(`Responsive — ${bp.name} (${bp.width}px)`, () => {
    test.use({ viewport: { width: bp.width, height: bp.height } });

    test("navbar es visible", async ({ page }) => {
      await page.goto("/");
      const navbar = page.locator("header.navbar");
      await expect(navbar).toBeVisible();
    });

    test("contenido principal es accesible", async ({ page }) => {
      await page.goto("/");
      const main = page.locator("main.app__main");
      await expect(main).toBeVisible();
    });

    test("página de búsqueda carga correctamente", async ({ page }) => {
      await page.goto("/search");
      await expect(page.locator("form")).toBeVisible();
      const submitBtn = page.locator("button[type='submit']");
      await expect(submitBtn).toBeVisible();
    });

    test("language switcher es accesible", async ({ page }) => {
      await page.goto("/");
      // En mobile el texto de la marca se oculta pero los botones de idioma deben seguir visibles
      await expect(page.locator(".lang-switcher")).toBeVisible();
    });

    test("no hay overflow horizontal", async ({ page }) => {
      await page.goto("/");
      const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
      expect(bodyWidth).toBeLessThanOrEqual(bp.width + 2); // 2px de tolerancia
    });
  });
}
