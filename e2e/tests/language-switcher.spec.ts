import { test, expect } from "@playwright/test";

test.describe("Cambio de idioma", () => {
  test("tiene tres botones de idioma visibles", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "ES" })).toBeVisible();
    await expect(page.getByRole("button", { name: "RU" })).toBeVisible();
    await expect(page.getByRole("button", { name: "EN" })).toBeVisible();
  });

  test("el botón de idioma activo tiene aria-pressed=true", async ({ page }) => {
    await page.goto("/");
    // El idioma detectado puede variar, pero siempre un botón debe estar activo
    const activeBtn = page.locator("[aria-pressed='true']");
    await expect(activeBtn).toHaveCount(1);
  });

  test("puede cambiar a inglés y el estado se actualiza", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "EN" }).click();
    const enBtn = page.getByRole("button", { name: "EN" });
    await expect(enBtn).toHaveAttribute("aria-pressed", "true");
  });

  test("puede cambiar a ruso", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "RU" }).click();
    const ruBtn = page.getByRole("button", { name: "RU" });
    await expect(ruBtn).toHaveAttribute("aria-pressed", "true");
  });
});
