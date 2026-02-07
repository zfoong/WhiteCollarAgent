---
name: git-commit
description: Create well-formatted git commits with conventional commit format. Use when committing code changes or creating git commits.
user-invocable: true
action-sets:
  - file_operations
  - shell
---

# Git Commit Skill

Create git commits following conventional commit format for clear, meaningful commit history.

## Conventional Commit Format

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types
- **feat**: A new feature
- **fix**: A bug fix
- **docs**: Documentation only changes
- **style**: Changes that don't affect code meaning (formatting, semicolons, etc.)
- **refactor**: Code change that neither fixes a bug nor adds a feature
- **perf**: Code change that improves performance
- **test**: Adding missing tests or correcting existing tests
- **chore**: Changes to build process or auxiliary tools

### Scope
The scope is optional and indicates the section of the codebase:
- Examples: `api`, `auth`, `ui`, `config`, `tests`

## Commit Process

### Step 1: Review Changes

Run these commands to understand what's being committed:

```bash
# See overall status
git status

# See staged changes
git diff --staged

# See unstaged changes
git diff
```

### Step 2: Stage Files Selectively

Stage only relevant files:

```bash
# Stage specific files
git add <file1> <file2>

# Stage parts of a file interactively
git add -p <file>
```

**Avoid:**
- `git add .` or `git add -A` (may include unintended files)
- Committing generated files, logs, or secrets

### Step 3: Craft the Commit Message

Write a meaningful commit message:

1. **Subject line** (required):
   - Use imperative mood ("Add feature" not "Added feature")
   - Keep under 72 characters
   - Start with lowercase after the type
   - No period at the end

2. **Body** (for complex changes):
   - Explain the "why" not the "what"
   - Wrap at 72 characters
   - Separate from subject with blank line

3. **Footer** (optional):
   - Reference issues: `Fixes #123`, `Closes #456`
   - Breaking changes: `BREAKING CHANGE: description`

### Step 4: Create the Commit

```bash
git commit -m "type(scope): description"
```

For multi-line commits:
```bash
git commit -m "type(scope): description" -m "Body text explaining the change in more detail."
```

## Examples

### Simple Feature
```
feat(auth): add password reset functionality
```

### Bug Fix with Issue Reference
```
fix(api): handle null response from external service

The external API sometimes returns null instead of an empty array.
This change adds proper null handling to prevent crashes.

Fixes #234
```

### Breaking Change
```
feat(api)!: change authentication endpoint response format

BREAKING CHANGE: The /auth/login endpoint now returns a different
JSON structure. Clients must update to handle the new format.
```

### Documentation Update
```
docs(readme): update installation instructions for Node 18
```

## Best Practices

1. **Atomic commits**: Each commit should represent one logical change
2. **Test before committing**: Ensure the code works
3. **Review staged changes**: Double-check what you're committing
4. **Don't commit secrets**: Check for API keys, passwords, tokens
5. **Keep commits small**: Easier to review and revert if needed

## What NOT to Commit

- `.env` files with secrets
- `node_modules/` or `venv/`
- Build artifacts
- IDE settings (unless shared)
- Large binary files
