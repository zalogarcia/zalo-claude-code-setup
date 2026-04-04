Generate and run end-to-end tests using Playwright.

## Usage
Describe the user flow to test:
```
/e2e Test the login flow from landing page to dashboard
/e2e Test adding an item to cart and checking out
```

## Instructions

1. **Check Setup**: Verify Playwright is installed. If not, suggest `npm init playwright@latest`.

2. **Analyze the Flow**: Read the relevant pages/components to understand:
   - What URLs are involved
   - What selectors to use (prefer `data-testid`, then `role`, then CSS)
   - What assertions to make

3. **Generate Test File**: Create a Playwright test in `tests/e2e/` or `e2e/` (match existing convention) with:
   - `test.describe` block with clear flow name
   - Step-by-step actions with `await page.goto()`, `page.click()`, `page.fill()`, etc.
   - Assertions using `expect(page)` / `expect(locator)`
   - Proper `beforeEach` for common setup (login, navigation)

4. **Run the Test**: Execute with `npx playwright test <file> --headed` so the user can see it.

5. **Debug Failures**: If the test fails:
   - Check if selectors are correct
   - Add `await page.waitForSelector()` or `page.waitForURL()` for timing issues
   - Take screenshots at failure points for debugging

6. **Report**: Show pass/fail results and any flaky test concerns.
