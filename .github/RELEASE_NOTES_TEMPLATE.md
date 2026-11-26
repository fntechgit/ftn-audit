<!--
Patch record of a release. Pushing a tag X.Y.Z or vX.Y.Z, betas included (v1.0.0b7; the number
must match the version in pyproject.toml), runs .github/workflows/release-draft.yml, which creates
the release as a draft with generated notes and this template, with X.Y.Z replaced by the tag.
A pre-release version is marked as a pre-release.

To create the draft by hand instead:

  gh release create X.Y.Z --draft --generate-notes --notes-file .github/RELEASE_NOTES_TEMPLATE.md

Fill in the fields below, then publish the release. Add the publish date once the
version is on PyPI (./build_and_publish.sh).
-->

## Patch record

- Release tag: X.Y.Z
- Published to PyPI: YYYY-MM-DD
- Components updated: list them here. A grouped Dependabot pull request shows only its group name under "Dependency updates", so copy the packages from its description.
- CVEs and advisories addressed: none
