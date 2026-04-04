#!/bin/bash
printf '%s' 'Please perform a systematic verification of all recent code changes:

## 1. Requirements Alignment
- Compare the implemented changes against the original requirements/plan
- List any deviations or missing features
- Confirm all acceptance criteria are met

## 2. Code Quality Check
- Identify any code smells, anti-patterns, or style inconsistencies
- Check for proper error handling and edge cases
- Verify naming conventions are followed

## 3. Functionality Verification
- Trace through the logic flow of major changes
- Identify any potential bugs or logical errors
- Check that all new functions/methods work as intended

## 4. Integration Points
- Verify changes integrate properly with existing code
- Check for any broken dependencies or imports
- Ensure no existing functionality was accidentally broken

## 5. Security & Performance
- Flag any potential security vulnerabilities introduced
- Note any obvious performance concerns

Please provide:
1. A summary of what was changed (high-level)
2. Any issues found (categorized by severity: critical/high/medium/low)
3. Specific line numbers or files where problems exist
4. Recommended fixes for any issues identified' | pbcopy
