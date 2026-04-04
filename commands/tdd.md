Implement a feature using strict Test-Driven Development workflow.

## Usage
Describe the feature you want to implement:
```
/tdd Add a function that calculates player XP from completed tasks
```

## Instructions

Follow the RED-GREEN-REFACTOR cycle strictly:

### 1. RED Phase - Write Failing Tests First
- Understand the requirements from the user's description
- Create or update test file(s) with descriptive test cases covering:
  - Happy path (expected behavior)
  - Edge cases (empty input, boundary values)
  - Error cases (invalid input, missing data)
- Run tests to confirm they FAIL (if they pass, the tests aren't testing new behavior)

### 2. GREEN Phase - Minimal Implementation
- Write the MINIMUM code needed to make all tests pass
- No premature optimization, no extra features
- Run tests to confirm they all PASS

### 3. REFACTOR Phase
- Clean up the implementation while keeping tests green
- Extract helpers if code is duplicated
- Improve naming and readability
- Run tests after each refactor step to ensure they still pass

### 4. Verify
- Run the full test suite (not just new tests) to check for regressions
- Report coverage if available

## Rules
- NEVER write implementation before tests
- NEVER skip the failing test verification
- Keep each test focused on ONE behavior
- Test names should describe the behavior, not the implementation
