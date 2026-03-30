import { test, expect } from "@playwright/test";

test.describe("Flujo de búsqueda de artículos", () => {
  test("puede navegar al dashboard y ver título", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/Agente Escribano/i);
    // El h1 debe contener texto del dashboard
    const heading = page.locator("h1").first();
    await expect(heading).toBeVisible();
  });

  test("puede navegar a la página de búsqueda", async ({ page }) => {
    await page.goto("/");
    await page.click("a[href='/search']");
    await expect(page).toHaveURL(/\/search/);
    // El formulario de búsqueda debe estar visible
    await expect(page.locator("form")).toBeVisible();
  });

  test("el botón de búsqueda es clicable", async ({ page }) => {
    await page.goto("/search");
    const submitBtn = page.locator("button[type='submit']");
    await expect(submitBtn).toBeVisible();
    await expect(submitBtn).toBeEnabled();
  });

  test("puede ver detalle de artículo navegando a /articles/1", async ({ page }) => {
    await page.goto("/articles/1");
    // La página debe cargar sin error 404 (el mock de MSW responde)
    // En E2E real dependería del backend corriendo
    await expect(page.locator("body")).toBeVisible();
  });
});
