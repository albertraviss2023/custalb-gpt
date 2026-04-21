# Development Workflow

This project follows a professional Git-based CI/CD workflow.

## Rules
1. **Branching**: No direct work on `main`. Create feature branches (`feat/`, `fix/`, `chore/`, `refactor/`).
2. **Local Validation**: Run `make validate` before submitting a Pull Request.
3. **Pull Requests**: All changes must be proposed via a Pull Request and approved by the Tech Lead.

## CI/CD Pipeline
This project uses a unified GitHub Actions pipeline (`.github/workflows/pipeline.yml`):
- **Validation**: Every PR and push to `main` is validated using `make validate`.
- **Preview Environments**: Every PR is automatically built and deployed to a unique Kubernetes namespace (`personal-goi-pr-<num>`).
- **Production**: Merges to `main` are deployed to the production namespace (`personal-goi`).

### Preview URLs
Preview environments are accessible at `http://pr-<num>.goi.local`.

## Pull Request Process
1. Create a branch from `main`.
2. Implement changes and add/update tests.
3. Run `make validate`.
4. Push branch and open a PR using the provided template.
5. Wait for Tech Lead review and approval.
