# GitHub-only install guidance

Relay's Python package metadata currently uses the distribution name
`relay-agent`, but the public PyPI namespace with that name is not the HarperZ9
Relay distribution. Do not run `pip install relay-agent` and do not document it
as a Relay install path.

Use one of these GitHub-pinned paths after the release owner has committed and
published the candidate.

## Source pin

Replace `<accepted-commit>` with the reviewed commit SHA from
`https://github.com/HarperZ9/relay`.

```bash
python -m pip install "relay-agent @ git+https://github.com/HarperZ9/relay.git@<accepted-commit>"
```

This still installs a package whose local metadata name is `relay-agent`, but the
source is pinned to HarperZ9 GitHub. The commit SHA is the authority; omitting it
turns the install into a moving target.

## Release wheel

After the GitHub Release exists, download the wheel and SHA-256 receipt from the
release page. Candidate placeholders:

```text
tag: v0.2.0
wheel: relay_agent-0.2.0-py3-none-any.whl
sdist: relay_agent-0.2.0.tar.gz
sha256: <release-sha256-from-SHA256SUMS.txt>
url: https://github.com/HarperZ9/relay/releases/download/v0.2.0/<asset-name>
```

Verify the hash before installing. Example:

```bash
python -m pip install --no-index ./relay_agent-0.2.0-py3-none-any.whl
```

This path does not query PyPI. If a future release moves to a new verified
package namespace, update this page and the release notes before publishing.
