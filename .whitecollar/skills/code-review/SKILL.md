---
name: code-review
description: Perform thorough code review with quality checks. Use when reviewing code, checking for bugs, or analyzing code quality.
argument-hint: <file-path>
user-invocable: true
action-sets:
  - file_operations
---

# Code Review Skill

When reviewing code, follow these structured steps to ensure comprehensive analysis.

## 1. Initial Analysis

Start by understanding the code:
- Identify the programming language and framework
- Understand the overall structure and purpose
- Note key dependencies and imports
- Identify the scope of the code (single function, module, etc.)

## 2. Quality Checks

Perform these checks in order:

### Correctness
- Check for bugs and logic errors
- Verify edge case handling
- Look for off-by-one errors
- Check null/undefined handling
- Verify loop termination conditions

### Security
- Look for injection vulnerabilities (SQL, command, XSS)
- Check for hardcoded secrets or credentials
- Verify input validation at boundaries
- Check for insecure data handling
- Review authentication/authorization logic

### Performance
- Identify inefficient algorithms (O(n^2) when O(n) is possible)
- Look for unnecessary database queries or API calls
- Check for memory leaks or resource cleanup
- Identify caching opportunities

### Maintainability
- Check code organization and structure
- Verify naming conventions are followed
- Look for code duplication
- Check for appropriate abstraction levels
- Verify error messages are helpful

## 3. Output Format

Present your findings in this structured format:

```
## Code Review Summary

**File:** [filename]
**Language:** [language]
**Overall Assessment:** [Good/Needs Work/Critical Issues]

### Issues Found

#### Critical
- [Line X]: [Issue description]
  - Problem: [What's wrong]
  - Fix: [Suggested solution]

#### Important
- [Line X]: [Issue description]
  - Suggestion: [How to improve]

#### Minor
- [Line X]: [Issue description]
  - Note: [Optional improvement]

### Positive Aspects
- [What's done well]

### Recommendations
1. [Priority recommendation]
2. [Secondary recommendation]
```

## Guidelines

- Be specific with line numbers
- Provide concrete fix suggestions
- Acknowledge good practices
- Prioritize security and correctness over style
- Don't nitpick formatting if the code is otherwise good
