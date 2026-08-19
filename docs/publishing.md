# Project Guard Publishing

This document describes the minimal v0.6.1 publishing path. It uses GitHub
Actions and PyPI Trusted Publishing; it does not use a long-lived API token.

Project Guard v0.6.1 has been successfully published to PyPI. TestPyPI and
PyPI were verified in clean environments with version, CLI help, prepare,
multi-language, package-resource, and artifact-isolation smoke checks. The
verified command reports `project-guard --version -> 0.6.1`.

## Source integrity

The current v0.6.1 package source is the immutable `v0.6.1` tag:

```text
23b1bb27e7201c604c5dc869fb60fbca36c51e2e
```

The tag was not moved, and v0.6.1 was not re-uploaded with different contents.

The v0.6.0 workflow built the immutable `v0.6.0` tag, not the branch commit
that added the workflow. Its historical source commit was:

```text
4de5faac778d8045098f5a7f49d5ce2525b4bb4c
```

The workflow is manual-only. Its `target` input is either `testpypi` or
`pypi`; pushing `main`, opening a pull request, or pushing a tag does not
publish a package.

## Trusted Publisher setup

TestPyPI and PyPI are separate services and require separate Trusted Publisher
entries. Configure both entries in the corresponding account:

- Owner: `wangboning757-creator`
- Repository: `project-guard`
- Workflow: `publish.yml`
- Environment: `testpypi` for TestPyPI, `pypi` for PyPI

For a new package that does not yet exist, use the current pending-publisher flow.
The first successful upload creates the project. TestPyPI also requires its
own account.

Configure the `pypi` GitHub Environment with required reviewers before using
the production target. The `testpypi` Environment may remain unprotected if
the project owner accepts that tradeoff.

Official references:

- <https://docs.pypi.org/trusted-publishers/>
- <https://docs.pypi.org/trusted-publishers/adding-a-publisher/>
- <https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/>
- <https://github.com/pypa/gh-action-pypi-publish>

## TestPyPI procedure

1. Configure the TestPyPI Trusted Publisher entry.
2. Run `Publish Project Guard` with `target: testpypi`.
3. Confirm the package metadata and files on TestPyPI.
4. Install from TestPyPI in a clean environment, using the normal PyPI index
   for dependencies when necessary:

   ```powershell
   python -m venv .tmp-testpypi-venv
   .tmp-testpypi-venv\Scripts\python -m pip install `
     --index-url https://test.pypi.org/simple/ `
     --extra-index-url https://pypi.org/simple/ `
     project-guard==0.6.1
   .tmp-testpypi-venv\Scripts\project-guard --version
   ```

5. Run `--help`, `inspect`, `prepare`, and `init-cline-plugin` in a temporary
   Git repository. Confirm the five Guard artifacts and generated Plugin JS.
6. Remove the temporary environment and repository.

Do not retry an upload with different contents if a file was accepted. Python
package release files are immutable.

## Production procedure

After TestPyPI verification, configure the PyPI Trusted Publisher entry and
stop for explicit production approval. The production command is the same
workflow with `target: pypi`, and the `pypi` Environment should require manual
approval.

This repository does not automatically publish GitHub Releases. The v0.6.1
PyPI artifact was built from the release tag, and a clean installation with
`pip install project-guard==0.6.1` was verified. No package re-upload is
needed.
