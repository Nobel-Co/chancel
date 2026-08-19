# PyPI Trusted Publishing

**Fetched:** 2026-08-19  
**Sources:** https://github.com/pypa/gh-action-pypi-publish (README)

---

## 1. What Is Trusted Publishing

**Source:** https://docs.pypi.org/trusted-publishers/  
**Status:** UNSOURCEABLE — PyPI docs blocked by Cloudflare rate limiting

UNSOURCED: Official two-sentence definition of Trusted Publishing, OIDC mechanism, and benefit of not storing tokens. Use GitHub Action README context below instead.

---

## 2. PyPI-Side Configuration for GitHub Actions Publisher

**Source:** https://docs.pypi.org/trusted-publishers/adding-a-publisher/  
**Status:** UNSOURCEABLE — PyPI docs blocked by Cloudflare rate limiting

UNSOURCED: Exact fields required (owner, repository name, workflow filename, environment name), configuration interface, "pending publisher" setup for projects that do not exist yet, and how these are set on the PyPI project page.

---

## 3. GitHub Actions Workflow Requirements

**Source:** https://github.com/pypa/gh-action-pypi-publish (README)

### Required Permissions Block

```yaml
permissions:
  id-token: write
```

This permission is **mandatory** for trusted publishing. The `id-token: write` permission allows the workflow to request an OIDC token from GitHub, which is exchanged with PyPI for temporary credentials.

### Recommended Environment Configuration

```yaml
environment:
  name: pypi
  url: https://pypi.org/p/<your-pypi-project-name>
```

Use a dedicated environment. Environment protection rules provide an additional layer of security — you can restrict which branches or tags can deploy to PyPI.

### Publishing Action Usage

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      # Build distributions in this job
      - run: python -m build
      - uses: actions/upload-artifact@v3
        with:
          name: dist
          path: dist/

  publish:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: pypi
      url: https://pypi.org/p/your-package
    permissions:
      id-token: write
    steps:
      - uses: actions/download-artifact@v3
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@release/v1
```

### Optional Configuration Parameters

```yaml
with:
  packages-dir: custom-dir/           # Default: dist/
  verify-metadata: false              # Skip twine check
  skip-existing: true                 # Tolerate duplicate uploads
  verbose: true                        # Enable debug output
  print-hash: true                     # Show SHA256/MD5/BLAKE2
  attestations: false                 # Disable attestation generation
  repository-url: https://test.pypi.org/legacy/  # Use TestPyPI or custom index
```

---

## 4. Documented Gotchas & Constraints

**Source:** https://github.com/pypa/gh-action-pypi-publish (README)

### Workflow Filename Must Match Exactly

The workflow file name you configure on PyPI (during publisher setup) must match **exactly** the actual file in the repository. Mismatches will cause OIDC token requests to fail.

### Runner Requirements

**GNU/Linux Only:** The action is docker-based and "can only be used from within GNU/Linux based jobs." Windows and macOS runners are unsupported.

**No Container Jobs:** "Running the action in a job that has a `container:` set is not supported."

### Reusable Workflow Limitation

**Reusable workflows are unsupported:** "Trusted publishing cannot be used from within a reusable workflow at this time."

**Workaround:** Create a non-reusable workflow that calls the publishing job directly, or trigger a separate standard workflow.

### Composite Actions Not Supported

"Invoking `pypi-publish` from composite actions is unsupported" due to privilege escalation risks when using Trusted Publishing.

### Single Invocation Per Job

"Invoking `pypi-publish` more than once in the same job is not considered supported."

### Build and Publish Must Be Separate

This GitHub Action "has nothing to do with building package distributions." Build distributions (wheels, sdists) in a separate job and place them in `dist/` before calling the action. Use `actions/upload-artifact@v3` and `actions/download-artifact@v3` to transfer the built artifacts between jobs.

### Why Use a Dedicated Environment

- Enables environment protection rules to restrict which branches/tags can publish
- Provides an audit trail and separate approval workflow
- Isolates publishing permissions from other workflow steps
- Makes the intent explicit to future maintainers

---

## Summary

PyPI Trusted Publishing uses OIDC to eliminate the need for stored PyPI tokens. GitHub Actions workflows must:

1. Include `permissions: id-token: write` in the publishing job
2. Use a dedicated `environment` block pointing to the PyPI project
3. Run on Ubuntu (GNU/Linux) without container jobs
4. Build distributions separately, then invoke `pypa/gh-action-pypi-publish@release/v1`
5. Ensure the workflow filename matches the publisher configuration on PyPI exactly
6. Never use reusable workflows or composite actions for publishing

**Key caveat:** This is not a reusable workflow setup — trusted publishing requires a dedicated, standard workflow.

---

## PyPI-side configuration (RESOLVED — was UNSOURCED above)

Escalation note: sourced 2026-08-19 by the orchestrator through a real browser after plain
fetches hit Cloudflare. Sources:
- https://docs.pypi.org/trusted-publishers/adding-a-publisher/
- https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/

### Adding a publisher to an existing project (verbatim, key passages)

> For GitHub Actions, you must provide the repository owner's name, the repository's name,
> and the filename of the GitHub Actions workflow that's authorized to upload to PyPI. In
> addition, you may optionally provide the name of a GitHub Actions environment.

> Configuring an environment is optional, but strongly recommended: with a GitHub
> environment, you can apply additional restrictions to your trusted workflow, such as
> requiring manual approval on each run by a trusted subset of repository maintainers.

Location: "Your projects" -> Manage -> "Publishing" in the project sidebar.
Fields for GitHub Actions: repository owner, repository name, workflow filename
(e.g. `release.yml` for `.github/workflows/release.yml`), optional environment name.

### Pending publisher for a project that does not exist yet (verbatim, key passages)

> you can configure a "pending" publisher that will create the project when used for the
> first time. "Pending" publishers are converted into "normal" publishers on first use,
> meaning that no further configuration is required.

> A "pending" publisher does not create a project or reserve a project's name until it is
> actually used to publish. If you create a "pending" publisher but another user registers
> the project name before you actually publish to it, your "pending" publisher will be
> invalidated.

Location: account sidebar -> "publishing" (not under any project, since it does not exist).
Same fields as a normal publisher PLUS the name of the PyPI project to be created.

### Chancel-specific values (for the owner to enter; no token is ever stored)

- PyPI project name: `chancel` (pending publisher — name is NOT reserved until first publish)
- Owner: `Nobel-Co` · Repository: `chancel` · Workflow: `release.yml` · Environment: `pypi`
