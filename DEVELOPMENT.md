# Development Workflow

This project follows a professional Git-based CI/CD workflow.

## Rules
1. **Branching**: No direct work on `main`. Create feature branches (`feat/`, `fix/`, `chore/`, `refactor/`).
2. **Local Validation**: Run `make validate` before submitting a Pull Request.
3. **Pull Requests**: All changes must be proposed via a Pull Request and approved by the Tech Lead.

## Local Validation Pipeline
The validation pipeline includes:
- **Backend**:
  - `ruff check`: Linting
  - `pytest`: Unit and integration tests
- **Frontend**:
  - `npm run lint`: ESLint checks
  - `npm run build`: Type checking (tsc) and production build (vite)

Run all checks with:
```bash
make validate
```

## Pull Request Process
1. Create a branch from `main`.
2. Implement changes and add/update tests.
3. Run `make validate`.
4. Push branch and open a PR using the provided template.
5. Wait for Tech Lead review and approval.
